#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cell Manager Module

Manages cell lifecycle in hive concurrent agent mode.
Each cell represents an independent task unit with defined input/output boundaries.

Usage:
    from cell_manager import CellManager

    cm = CellManager()
    cm.create_cell("cell-auth", ["spec/auth.md"], ["src/auth/*.ts"])
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from hive_config import HiveConfig


class CellManagerError(Exception):
    """Base exception for cell manager"""
    pass


class ValidationError(CellManagerError):
    """Raised when validation fails"""
    pass


class CellNotFoundError(CellManagerError):
    """Raised when cell is not found"""
    pass


class CellAlreadyExistsError(CellManagerError):
    """Raised when cell already exists"""
    pass


# Input validation patterns
VALID_CELL_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')
SAFE_PATH_PATTERN = re.compile(r'^[a-zA-Z0-9_./-]+$')


def validate_cell_id(cell_id: str) -> None:
    """Validate cell ID format

    Args:
        cell_id: Cell ID to validate

    Raises:
        ValidationError: If ID is invalid
    """
    if not cell_id:
        raise ValidationError("Cell ID cannot be empty")
    if not VALID_CELL_ID_PATTERN.match(cell_id):
        raise ValidationError(
            f"Invalid cell ID: '{cell_id}'. "
            f"Must start with alphanumeric and contain only alphanumeric, hyphen, or underscore. "
            f"Max length: 64 characters."
        )


def validate_path(path: str, name: str = "path") -> None:
    """Validate path to prevent traversal attacks

    Args:
        path: Path to validate
        name: Name for error messages

    Raises:
        ValidationError: If path is invalid or potentially dangerous
    """
    if not path:
        return  # Empty paths are allowed (optional)

    # Check for path traversal
    if '..' in path:
        raise ValidationError(f"Path traversal not allowed in {name}: '{path}'")

    # Check for absolute paths outside project
    if os.path.isabs(path):
        raise ValidationError(f"Absolute paths not allowed in {name}: '{path}'")

    # Check for null bytes
    if '\x00' in path:
        raise ValidationError(f"Null bytes not allowed in {name}")


def validate_path_in_bounds(base_path: Path, target_path: Path) -> bool:
    """Check if target path is within base path bounds

    Args:
        base_path: Base directory path
        target_path: Target path to check

    Returns:
        True if target is within base bounds
    """
    try:
        base_resolved = base_path.resolve()
        target_resolved = target_path.resolve()
        return str(target_resolved).startswith(str(base_resolved))
    except (OSError, ValueError):
        return False


@dataclass
class Cell:
    """Cell definition"""
    id: str
    description: str
    inputs: list[str]
    outputs: list[str]
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    worktree_path: Optional[str] = None
    branch: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CellManager:
    """Cell lifecycle manager

    Manages creation, tracking, and cleanup of independent task cells.
    """

    def __init__(self, hive_root: Optional[Path] = None):
        """Initialize cell manager

        Args:
            hive_root: Hive root directory, defaults to .trellis/
        """
        self.hive_root = hive_root or self._find_hive_root()
        self.cells_dir = self.hive_root / "cells"
        self.project_root = self.hive_root.parent
        self.cells_dir.mkdir(parents=True, exist_ok=True)

    def _find_hive_root(self) -> Path:
        """Find hive root directory"""
        current = Path.cwd()
        while current != current.parent:
            trellis_dir = current / ".trellis"
            if trellis_dir.exists():
                return trellis_dir
            current = current.parent
        return Path.cwd() / ".trellis"

    # ==================== Cell Lifecycle ====================

    def create_cell(
        self,
        cell_id: str,
        description: str,
        inputs: list[str],
        outputs: list[str],
        dependencies: Optional[list[str]] = None,
        create_worktree: bool = True
    ) -> dict[str, Any]:
        """Create a new cell

        Args:
            cell_id: Unique cell identifier
            description: Cell description
            inputs: Input file list
            outputs: Expected output file list
            dependencies: List of dependent cell IDs
            create_worktree: Whether to create isolated worktree

        Returns:
            Created cell configuration

        Raises:
            CellAlreadyExistsError: If cell already exists
            ValidationError: If input validation fails
        """
        # Validate inputs
        validate_cell_id(cell_id)

        for inp in inputs:
            validate_path(inp, "input file")
        for out in outputs:
            validate_path(out, "output file")

        if dependencies:
            for dep in dependencies:
                validate_cell_id(dep)

        cell_dir = self.cells_dir / cell_id

        if cell_dir.exists():
            raise CellAlreadyExistsError(f"Cell already exists: {cell_id}")

        # Verify path is within bounds
        if not validate_path_in_bounds(self.cells_dir, cell_dir):
            raise ValidationError(f"Cell directory outside allowed bounds: {cell_id}")

        cell_dir.mkdir(parents=True)

        # Create cell configuration
        now = datetime.now(timezone.utc).isoformat()
        cell_config: dict[str, Any] = {
            "id": cell_id,
            "description": description,
            "inputs": inputs,
            "outputs": outputs,
            "dependencies": dependencies or [],
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "worktree_path": None,
            "branch": None
        }

        # Create worktree if requested
        if create_worktree:
            try:
                worktree_path, branch = self._create_worktree(cell_id)
                cell_config["worktree_path"] = str(worktree_path)
                cell_config["branch"] = branch
            except Exception as e:
                # Log warning but don't fail
                print(f"Warning: Failed to create worktree: {e}")

        # Write configuration atomically
        self._write_cell_config(cell_dir, cell_config)

        # Create context file
        self._create_context_file(cell_dir, cell_id, inputs)

        return cell_config

    def _write_cell_config(self, cell_dir: Path, config: dict[str, Any]) -> None:
        """Write cell configuration atomically

        Args:
            cell_dir: Cell directory
            config: Configuration to write
        """
        config_file = cell_dir / "cell.json"
        temp_file = config_file.with_suffix('.tmp')

        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            temp_file.replace(config_file)
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def _create_context_file(
        self,
        cell_dir: Path,
        cell_id: str,
        inputs: list[str]
    ) -> None:
        """Create context file for cell

        Args:
            cell_dir: Cell directory
            cell_id: Cell ID
            inputs: Input file list
        """
        context_file = cell_dir / "context.jsonl"

        with open(context_file, 'w', encoding='utf-8') as f:
            for input_file in inputs:
                f.write(json.dumps({
                    "file": input_file,
                    "type": "input",
                    "reason": f"Cell {cell_id} input"
                }, ensure_ascii=False) + "\n")

    def _create_worktree(self, cell_id: str) -> tuple[Path, str]:
        """Create isolated worktree for cell

        Args:
            cell_id: Cell ID

        Returns:
            Tuple of (worktree_path, branch_name)

        Raises:
            CellManagerError: If worktree creation fails
        """
        # Validate cell_id again for safety
        validate_cell_id(cell_id)

        config = HiveConfig.load()
        worktree_base = Path(config.cell.worktree_base)
        if not worktree_base.is_absolute():
            worktree_base = self.project_root / worktree_base
        worktree_base = worktree_base.resolve()
        worktree_base.mkdir(parents=True, exist_ok=True)

        worktree_path = worktree_base / cell_id
        branch_name = f"cell/{cell_id}"

        # Check if already exists
        if worktree_path.exists():
            return worktree_path, branch_name

        # Verify worktree path is within bounds
        if not validate_path_in_bounds(worktree_base, worktree_path):
            raise CellManagerError(f"Worktree path outside allowed bounds: {cell_id}")

        # Create worktree using list form (no shell=True)
        cmd = [
            "git", "worktree", "add",
            "-b", branch_name,
            str(worktree_path)
        ]

        result = subprocess.run(
            cmd,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            # Try to recover - check if branch already exists
            if "already exists" in result.stderr:
                # Try with existing branch
                cmd_recover = [
                    "git", "worktree", "add",
                    str(worktree_path),
                    branch_name
                ]
                result = subprocess.run(
                    cmd_recover,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0:
                    return worktree_path, branch_name

            raise CellManagerError(f"Failed to create worktree: {result.stderr}")

        return worktree_path, branch_name

    def get_cell(self, cell_id: str) -> Optional[dict[str, Any]]:
        """Get cell information

        Args:
            cell_id: Cell ID

        Returns:
            Cell configuration or None if not found
        """
        validate_cell_id(cell_id)

        cell_dir = self.cells_dir / cell_id
        config_file = cell_dir / "cell.json"

        if not config_file.exists():
            return None

        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def update_cell_status(self, cell_id: str, status: str) -> bool:
        """Update cell status

        Args:
            cell_id: Cell ID
            status: New status

        Returns:
            True if updated successfully

        Raises:
            CellNotFoundError: If cell not found
        """
        validate_cell_id(cell_id)

        cell = self.get_cell(cell_id)
        if not cell:
            raise CellNotFoundError(f"Cell not found: {cell_id}")

        cell["status"] = status
        cell["updated_at"] = datetime.now(timezone.utc).isoformat()

        cell_dir = self.cells_dir / cell_id
        self._write_cell_config(cell_dir, cell)

        return True

    def list_cells(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        """List all cells

        Args:
            status: Filter by status (optional)

        Returns:
            List of cell configurations
        """
        cells = []

        for cell_dir in self.cells_dir.iterdir():
            if not cell_dir.is_dir():
                continue

            # Skip if directory name doesn't match pattern
            if not VALID_CELL_ID_PATTERN.match(cell_dir.name):
                continue

            config_file = cell_dir / "cell.json"
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    cell = json.load(f)
                    if status is None or cell.get("status") == status:
                        cells.append(cell)

        return cells

    def get_ready_cells(self) -> list[dict[str, Any]]:
        """Get cells ready for execution (dependencies satisfied)

        Returns:
            List of cells that can be assigned to workers
        """
        cells = self.list_cells()
        completed_ids = {c["id"] for c in cells if c["status"] == "completed"}

        ready = []
        for cell in cells:
            if cell["status"] != "pending":
                continue

            deps = cell.get("dependencies", [])
            if all(dep in completed_ids for dep in deps):
                ready.append(cell)

        return ready

    def cleanup_cell(self, cell_id: str, keep_worktree: bool = False) -> bool:
        """Clean up a cell

        Args:
            cell_id: Cell ID
            keep_worktree: Whether to preserve worktree

        Returns:
            True if cleanup successful
        """
        validate_cell_id(cell_id)

        cell = self.get_cell(cell_id)
        if not cell:
            return False

        # Remove worktree
        if not keep_worktree and cell.get("worktree_path"):
            self._remove_worktree(cell_id, cell["worktree_path"])

        # Remove cell directory with path validation
        cell_dir = self.cells_dir / cell_id

        if not validate_path_in_bounds(self.cells_dir, cell_dir):
            raise ValidationError(f"Cell directory outside allowed bounds: {cell_id}")

        # Check for symlinks (security)
        if cell_dir.is_symlink():
            raise ValidationError(f"Refusing to delete symlink: {cell_id}")

        if cell_dir.exists():
            shutil.rmtree(cell_dir)

        return True

    def _remove_worktree(self, cell_id: str, worktree_path: str) -> bool:
        """Remove worktree

        Args:
            cell_id: Cell ID
            worktree_path: Path to worktree

        Returns:
            True if removal successful
        """
        validate_cell_id(cell_id)

        worktree = Path(worktree_path)

        if not worktree.exists():
            return True

        # Verify path is reasonable
        if not str(worktree).endswith(cell_id):
            print(f"Warning: Worktree path doesn't match cell ID: {worktree}")

        # Remove worktree
        cmd = ["git", "worktree", "remove", str(worktree), "--force"]
        result = subprocess.run(
            cmd,
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"Warning: Failed to remove worktree: {result.stderr}")

        # Delete branch
        branch = f"cell/{cell_id}"
        result = subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            # Don't fail completely if branch deletion fails - it might not exist
            print(f"Warning: Failed to delete branch {branch}: {result.stderr}")

        return True

    # ==================== Cell Context ====================

    def get_cell_context(self, cell_id: str) -> list[dict[str, Any]]:
        """Get cell context

        Args:
            cell_id: Cell ID

        Returns:
            List of context entries
        """
        validate_cell_id(cell_id)

        context_file = self.cells_dir / cell_id / "context.jsonl"

        if not context_file.exists():
            return []

        contexts = []
        with open(context_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        contexts.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return contexts

    def add_cell_context(self, cell_id: str, file_path: str, reason: str) -> bool:
        """Add cell context entry

        Args:
            cell_id: Cell ID
            file_path: File path
            reason: Reason for inclusion

        Returns:
            True if added successfully
        """
        validate_cell_id(cell_id)
        validate_path(file_path, "context file path")

        context_file = self.cells_dir / cell_id / "context.jsonl"

        with open(context_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "file": file_path,
                "reason": reason
            }, ensure_ascii=False) + "\n")

        return True

    # ==================== Cell Validation ====================

    def validate_cell_outputs(self, cell_id: str) -> dict[str, Any]:
        """Validate cell outputs

        Args:
            cell_id: Cell ID

        Returns:
            Validation result
        """
        validate_cell_id(cell_id)

        cell = self.get_cell(cell_id)
        if not cell:
            return {"valid": False, "error": "Cell not found"}

        outputs = cell.get("outputs", [])
        worktree_path = cell.get("worktree_path")

        base_path = Path(worktree_path) if worktree_path else self.project_root

        results: dict[str, Any] = {
            "valid": True,
            "outputs": {},
            "missing": []
        }

        for output_pattern in outputs:
            if "*" in output_pattern:
                # Glob pattern
                matches = list(base_path.glob(output_pattern))
                results["outputs"][output_pattern] = {
                    "exists": len(matches) > 0,
                    "matches": [str(m.relative_to(base_path)) for m in matches[:5]]
                }
                if not matches:
                    results["missing"].append(output_pattern)
            else:
                file_path = base_path / output_pattern
                results["outputs"][output_pattern] = {
                    "exists": file_path.exists()
                }
                if not file_path.exists():
                    results["missing"].append(output_pattern)

        if results["missing"]:
            results["valid"] = False

        return results

    # ==================== Batch Operations ====================

    def cleanup_completed_cells(self, max_age_hours: int = 24) -> list[str]:
        """Clean up old completed cells

        Args:
            max_age_hours: Maximum retention time in hours

        Returns:
            List of cleaned cell IDs
        """
        cells = self.list_cells(status="completed")
        cleaned = []

        for cell in cells:
            updated_at = cell.get("updated_at") or cell.get("created_at")
            if not updated_at:
                continue

            try:
                # Handle various ISO formats
                if updated_at.endswith('Z'):
                    updated_at = updated_at[:-1] + '+00:00'
                updated_time = datetime.fromisoformat(updated_at)
                age_hours = (datetime.now(timezone.utc) - updated_time).total_seconds() / 3600

                if age_hours > max_age_hours:
                    self.cleanup_cell(cell["id"])
                    cleaned.append(cell["id"])
            except (ValueError, TypeError):
                continue

        return cleaned

    def archive_cells(self, output_dir: Optional[Path] = None) -> list[str]:
        """Archive all completed cells

        Args:
            output_dir: Archive directory

        Returns:
            List of archived cell IDs
        """
        if output_dir is None:
            output_dir = self.hive_root / "archive" / datetime.now().strftime("%Y-%m")

        output_dir.mkdir(parents=True, exist_ok=True)

        cells = self.list_cells(status="completed")
        archived = []

        for cell in cells:
            cell_dir = self.cells_dir / cell["id"]
            if cell_dir.exists() and validate_path_in_bounds(self.cells_dir, cell_dir):
                dest = output_dir / cell["id"]
                shutil.move(str(cell_dir), str(dest))
                archived.append(cell["id"])

        return archived


# ==================== CLI Interface ====================

def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Cell management tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # list command
    list_parser = subparsers.add_parser("list", help="List cells")
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--ready", action="store_true", help="Show only ready cells")

    # show command
    show_parser = subparsers.add_parser("show", help="Show cell details")
    show_parser.add_argument("cell_id", help="Cell ID")

    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Cleanup cells")
    cleanup_parser.add_argument("cell_id", nargs="?", help="Cell ID (omit to cleanup all completed)")
    cleanup_parser.add_argument("--max-age", type=int, default=24, help="Max age in hours")

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate cell outputs")
    validate_parser.add_argument("cell_id", help="Cell ID")

    args = parser.parse_args()
    cm = CellManager()

    if args.command == "list":
        if args.ready:
            cells = cm.get_ready_cells()
        else:
            cells = cm.list_cells(status=args.status)
        print(json.dumps(cells, indent=2, ensure_ascii=False))

    elif args.command == "show":
        cell = cm.get_cell(args.cell_id)
        if cell:
            print(json.dumps(cell, indent=2, ensure_ascii=False))
        else:
            print(f"Cell not found: {args.cell_id}")

    elif args.command == "cleanup":
        if args.cell_id:
            cm.cleanup_cell(args.cell_id)
            print(f"Cleaned: {args.cell_id}")
        else:
            cleaned = cm.cleanup_completed_cells(args.max_age)
            print(f"Cleaned {len(cleaned)} cells: {cleaned}")

    elif args.command == "validate":
        result = cm.validate_cell_outputs(args.cell_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
