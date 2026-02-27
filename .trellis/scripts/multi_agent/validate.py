#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Agent Pipeline: Drone Validation

Integrates DroneValidator into the multi-agent pipeline workflow.
Executes multi-dimensional cross-validation after implementation and check phases.

Usage:
    python3 validate.py <task-dir> [--dimensions technical strategic security]
    python3 validate.py <task-dir> --cross-validate --drones 3

This script:
1. Loads task configuration
2. Runs DroneValidator on the worktree
3. Handles validation failures with retry logic
4. Updates task status based on validation results
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.paths import (
    FILE_TASK_JSON,
    get_repo_root,
)
from hive.drone_validator import DroneValidator, ValidationDimension, DroneValidatorError


# =============================================================================
# Constants
# =============================================================================

DEFAULT_DIMENSIONS = ["technical", "strategic", "security"]
DEFAULT_DRONE_COUNT = 3
CONSENSUS_THRESHOLD = 90
MAX_RETRIES = 3


# =============================================================================
# Colors
# =============================================================================


class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"


def log_info(msg: str) -> None:
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def log_success(msg: str) -> None:
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {msg}")


def log_warn(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {msg}")


def log_error(msg: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")


# =============================================================================
# Helper Functions
# =============================================================================


def _read_json_file(path: Path) -> dict | None:
    """Read and parse a JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json_file(path: Path, data: dict) -> bool:
    """Write dict to JSON file."""
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except (OSError, IOError):
        return False


# =============================================================================
# Main Functions
# =============================================================================


def run_validation(
    task_dir: Path,
    worktree_path: Optional[str] = None,
    dimensions: Optional[list[str]] = None,
    cross_validate: bool = False,
    num_drones: int = DEFAULT_DRONE_COUNT,
    verbose: bool = False
) -> dict[str, Any]:
    """Run drone validation on a task
    
    Args:
        task_dir: Task directory path
        worktree_path: Worktree path for validation
        dimensions: Validation dimensions
        cross_validate: Use cross-validation
        num_drones: Number of drones for cross-validation
        verbose: Verbose output
        
    Returns:
        Validation result
    """
    project_root = get_repo_root()
    task_json_path = task_dir / FILE_TASK_JSON
    
    # Load task configuration
    task_data = _read_json_file(task_json_path)
    if not task_data:
        return {
            "success": False,
            "error": "task.json not found"
        }
    
    task_id = task_data.get("id", task_dir.name)
    
    # Determine worktree path
    if not worktree_path:
        worktree_path = task_data.get("worktree_path")
    
    # Determine base path for validation
    if worktree_path:
        base_path = Path(worktree_path)
    else:
        base_path = project_root
    
    if not base_path.exists():
        return {
            "success": False,
            "error": f"Worktree path does not exist: {base_path}"
        }
    
    # Default dimensions
    if not dimensions:
        dimensions = DEFAULT_DIMENSIONS
    
    log_info(f"Starting validation for task: {task_id}")
    log_info(f"Base path: {base_path}")
    log_info(f"Dimensions: {dimensions}")
    
    # Initialize validator
    dv = DroneValidator()
    
    try:
        if cross_validate:
            log_info(f"Running cross-validation with {num_drones} drones...")
            result = dv.cross_validate(
                cell_id=task_id,
                num_drones=num_drones,
                worktree_path=str(base_path)
            )
            
            # Extract consensus info
            consensus_reached = result.get("consensus_reached", False)
            avg_score = result.get("average_score", 0)
            
            if verbose:
                for i, drone_result in enumerate(result.get("drone_results", [])):
                    log_info(f"  Drone {i+1} score: {drone_result.get('consensus_score')}")
            
            return {
                "success": consensus_reached,
                "task_id": task_id,
                "consensus_reached": consensus_reached,
                "average_score": avg_score,
                "score_variance": result.get("score_variance", 0),
                "drone_count": num_drones,
                "details": result
            }
        else:
            log_info("Running single validation...")
            result = dv.validate_cell(
                cell_id=task_id,
                dimensions=dimensions,
                worktree_path=str(base_path)
            )
            
            consensus_reached = result.get("consensus_reached", False)
            consensus_score = result.get("consensus_score", 0)
            
            if verbose:
                for dim, dim_result in result.get("dimensions", {}).items():
                    log_info(f"  {dim}: {dim_result.get('score')}/100")
                    for issue in dim_result.get("issues", []):
                        log_warn(f"    - {issue.get('message', 'Unknown issue')}")
            
            return {
                "success": consensus_reached,
                "task_id": task_id,
                "consensus_reached": consensus_reached,
                "consensus_score": consensus_score,
                "dimensions": result.get("dimensions", {}),
                "details": result
            }
            
    except DroneValidatorError as e:
        log_error(f"Validation error: {e}")
        return {
            "success": False,
            "error": str(e),
            "task_id": task_id
        }


def run_validation_with_retry(
    task_dir: Path,
    worktree_path: Optional[str] = None,
    dimensions: Optional[list[str]] = None,
    cross_validate: bool = False,
    num_drones: int = DEFAULT_DRONE_COUNT,
    max_retries: int = MAX_RETRIES,
    on_retry: Optional[callable] = None
) -> dict[str, Any]:
    """Run validation with retry logic
    
    Args:
        task_dir: Task directory path
        worktree_path: Worktree path
        dimensions: Validation dimensions
        cross_validate: Use cross-validation
        num_drones: Number of drones
        max_retries: Maximum retry attempts
        on_retry: Callback for retry events
        
    Returns:
        Final validation result
    """
    for attempt in range(1, max_retries + 1):
        log_info(f"Validation attempt {attempt}/{max_retries}")
        
        result = run_validation(
            task_dir=task_dir,
            worktree_path=worktree_path,
            dimensions=dimensions,
            cross_validate=cross_validate,
            num_drones=num_drones
        )
        
        if result.get("success"):
            log_success(f"Validation passed on attempt {attempt}")
            return result
        
        # Check if we should retry
        score = result.get("consensus_score", result.get("average_score", 0))
        if score >= CONSENSUS_THRESHOLD - 10:  # Close to threshold
            log_warn(f"Score {score} close to threshold, may pass on retry")
        else:
            log_error(f"Score {score} too low, issues need fixing")
        
        # Callback for retry
        if on_retry and attempt < max_retries:
            on_retry(attempt, result)
    
    log_error(f"Validation failed after {max_retries} attempts")
    return result


def update_task_status(
    task_dir: Path,
    validation_result: dict[str, Any]
) -> bool:
    """Update task status based on validation result
    
    Args:
        task_dir: Task directory path
        validation_result: Validation result
        
    Returns:
        True if updated successfully
    """
    task_json_path = task_dir / FILE_TASK_JSON
    
    task_data = _read_json_file(task_json_path)
    if not task_data:
        return False
    
    # Add validation record
    if "validation_history" not in task_data:
        task_data["validation_history"] = []
    
    task_data["validation_history"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": validation_result.get("success", False),
        "score": validation_result.get("consensus_score", 
                                       validation_result.get("average_score", 0)),
        "consensus_reached": validation_result.get("consensus_reached", False)
    })
    
    # Update last validation
    task_data["last_validation"] = {
        "passed": validation_result.get("success", False),
        "score": validation_result.get("consensus_score",
                                       validation_result.get("average_score", 0)),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    return _write_json_file(task_json_path, task_data)


# =============================================================================
# CLI Interface
# =============================================================================

def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-Agent Pipeline: Drone Validation")
    parser.add_argument("task_dir", help="Task directory path")
    parser.add_argument(
        "--dimensions", 
        nargs="+",
        default=DEFAULT_DIMENSIONS,
        choices=["technical", "strategic", "security"],
        help="Validation dimensions"
    )
    parser.add_argument("--worktree", help="Worktree path")
    parser.add_argument(
        "--cross-validate",
        action="store_true",
        help="Use cross-validation with multiple drones"
    )
    parser.add_argument(
        "--drones",
        type=int,
        default=DEFAULT_DRONE_COUNT,
        help="Number of drones for cross-validation"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES,
        help="Maximum retry attempts"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--update-task",
        action="store_true",
        help="Update task status after validation"
    )
    
    args = parser.parse_args()
    
    project_root = get_repo_root()
    
    # Normalize task directory
    task_dir = Path(args.task_dir)
    if not task_dir.is_absolute():
        task_dir = project_root / args.task_dir
    
    if not task_dir.is_dir():
        log_error(f"Task directory not found: {task_dir}")
        return 1
    
    # Run validation
    print()
    print(f"{Colors.BLUE}=== Drone Validation ==={Colors.NC}")
    
    result = run_validation_with_retry(
        task_dir=task_dir,
        worktree_path=args.worktree,
        dimensions=args.dimensions,
        cross_validate=args.cross_validate,
        num_drones=args.drones,
        max_retries=args.max_retries
    )
    
    # Update task if requested
    if args.update_task:
        update_task_status(task_dir, result)
    
    # Print result
    print()
    if result.get("success"):
        print(f"{Colors.GREEN}=== Validation Passed ==={Colors.NC}")
        print(f"  Score: {result.get('consensus_score', result.get('average_score', 'N/A'))}")
        print(f"  Consensus: {result.get('consensus_reached', False)}")
    else:
        print(f"{Colors.RED}=== Validation Failed ==={Colors.NC}")
        print(f"  Error: {result.get('error', 'Unknown')}")
        print(f"  Score: {result.get('consensus_score', result.get('average_score', 'N/A'))}")
        
        # Print issues if available
        if args.verbose:
            for dim, dim_result in result.get("dimensions", {}).items():
                issues = dim_result.get("issues", [])
                if issues:
                    print(f"\n  {dim} issues:")
                    for issue in issues[:5]:  # Limit to 5
                        print(f"    - [{issue.get('severity', 'unknown')}] {issue.get('message', '')}")
    
    print()
    
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
