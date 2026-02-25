#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pheromone Communication Module

Core communication mechanism for hive concurrent agent mode.
Enables state sharing between workers, drones, and queen.

Usage:
    from pheromone import PheromoneManager

    pm = PheromoneManager()
    pm.write_progress("worker-001", "implementing", 60)
    status = pm.read_worker_status("worker-001")
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum
from contextlib import contextmanager

# Cross-platform file locking
HAS_FCNTL = False
HAS_MSVCRT = False

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        pass


class PheromoneError(Exception):
    """Base exception for pheromone module"""
    pass


class ValidationError(PheromoneError):
    """Raised when input validation fails"""
    pass


class WorkerNotFoundError(PheromoneError):
    """Raised when worker is not found"""
    pass


class DroneNotFoundError(PheromoneError):
    """Raised when drone is not found"""
    pass


class PheromoneType(Enum):
    """Pheromone types for communication"""
    PROGRESS = "progress"
    BLOCKER = "blocker"
    COMPLETION = "completion"
    ALERT = "alert"


class WorkerStatus(Enum):
    """Worker bee status"""
    IDLE = "idle"
    SCOUTING = "scouting"
    IMPLEMENTING = "implementing"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class DroneStatus(Enum):
    """Drone validator status"""
    WAITING = "waiting"
    VALIDATING = "validating"
    CONSENSUS = "consensus"
    REJECTED = "rejected"


# Input validation patterns
VALID_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')


def validate_id(id_str: str, name: str = "ID") -> None:
    """Validate ID format to prevent injection attacks

    Args:
        id_str: ID string to validate
        name: Name of the ID for error messages

    Raises:
        ValidationError: If ID is invalid
    """
    if not id_str:
        raise ValidationError(f"{name} cannot be empty")
    if not VALID_ID_PATTERN.match(id_str):
        raise ValidationError(
            f"Invalid {name}: '{id_str}'. "
            f"Must start with alphanumeric and contain only alphanumeric, hyphen, or underscore."
        )


@dataclass
class WorkerState:
    """Worker bee state"""
    id: str
    cell: str
    status: str
    progress: int
    last_update: str
    blocked_by: Optional[str] = None
    block_reason: Optional[str] = None


@dataclass
class DroneState:
    """Drone validator state"""
    id: str
    type: str  # technical, strategic, security
    status: str
    assigned_cells: list[str] = field(default_factory=list)
    score: Optional[int] = None
    issues: Optional[list[str]] = None


class FileLock:
    """Cross-platform file lock for concurrent access protection"""

    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self._lock_fd: Optional[int] = None
        self._lock_handle: Optional[Any] = None

    def acquire(self, timeout: float = 10.0) -> bool:
        """Acquire lock with timeout

        Args:
            timeout: Maximum time to wait for lock in seconds

        Returns:
            True if lock acquired, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                self.lock_file.parent.mkdir(parents=True, exist_ok=True)

                if HAS_FCNTL:
                    # Unix-like system
                    self._lock_fd = os.open(
                        str(self.lock_file),
                        os.O_CREAT | os.O_WRONLY,
                        0o644
                    )
                    fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return True

                elif HAS_MSVCRT:
                    # Windows system
                    self._lock_handle = open(str(self.lock_file), 'w')
                    try:
                        msvcrt.locking(self._lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
                        return True
                    except IOError:
                        self._lock_handle.close()
                        self._lock_handle = None
                        time.sleep(0.1)
                        continue

                else:
                    # No locking mechanism available, use advisory lock via presence
                    try:
                        # Use exclusive creation with timeout
                        self._lock_fd = os.open(
                            str(self.lock_file),
                            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                            0o644
                        )
                        return True
                    except FileExistsError:
                        time.sleep(0.1)
                        continue

            except (IOError, OSError):
                self._close_lock_resources()
                time.sleep(0.1)

        return False

    def _close_lock_resources(self) -> None:
        """Close any open lock resources"""
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except (IOError, OSError):
                pass
            self._lock_fd = None

        if self._lock_handle is not None:
            try:
                self._lock_handle.close()
            except (IOError, OSError):
                pass
            self._lock_handle = None

    def release(self) -> None:
        """Release the lock"""
        if self._lock_fd is not None or self._lock_handle is not None:
            try:
                if HAS_FCNTL and self._lock_fd is not None:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                elif HAS_MSVCRT and self._lock_handle is not None:
                    try:
                        msvcrt.locking(self._lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except IOError:
                        pass  # Ignore unlock errors
            except Exception as e:
                # Log warning but don't fail
                print(f"Warning: Lock release failed: {e}", file=sys.stderr)
            finally:
                self._close_lock_resources()

                # Clean up lock file for advisory locking mode
                if not (HAS_FCNTL or HAS_MSVCRT):
                    try:
                        if self.lock_file.exists():
                            self.lock_file.unlink()
                    except (IOError, OSError):
                        pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class PheromoneManager:
    """Pheromone manager for hive communication

    Handles worker/drone state management and inter-agent communication
    through pheromone traces.
    """

    # Maximum retry attempts for file operations
    MAX_RETRIES = 3

    def __init__(self, hive_root: Optional[Path] = None):
        """Initialize pheromone manager

        Args:
            hive_root: Hive root directory, defaults to .trellis/
        """
        self.hive_root = hive_root or self._find_hive_root()
        self.pheromone_file = self.hive_root / "pheromone.json"
        self.lock_file = self.hive_root / ".pheromone.lock"
        self._initialized = False
        self._ensure_pheromone_file()

    def _find_hive_root(self) -> Path:
        """Find hive root directory"""
        current = Path.cwd()
        while current != current.parent:
            trellis_dir = current / ".trellis"
            if trellis_dir.exists():
                return trellis_dir
            current = current.parent
        return Path.cwd() / ".trellis"

    def _ensure_pheromone_file(self) -> None:
        """Ensure pheromone file exists"""
        if not self.pheromone_file.exists():
            self._create_empty_pheromone()
        self._initialized = True

    def _create_empty_pheromone(self) -> None:
        """Create empty pheromone file"""
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "hive_id": f"hive-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}",
            "status": "inactive",
            "created_at": now,
            "queen": {
                "phase": "idle",
                "last_heartbeat": now
            },
            "workers": [],
            "drones": [],
            "pheromones": []
        }
        self._write_pheromone_atomic(data)

    def _read_pheromone(self) -> dict[str, Any]:
        """Read pheromone file with retry logic

        Returns:
            Pheromone data dictionary

        Raises:
            PheromoneError: If read fails after retries
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                with open(self.pheromone_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except FileNotFoundError:
                if attempt == 0:
                    self._create_empty_pheromone()
                else:
                    raise PheromoneError("Failed to create pheromone file")
            except json.JSONDecodeError as e:
                if attempt < self.MAX_RETRIES - 1:
                    # Try to recover by recreating
                    self._create_empty_pheromone()
                    time.sleep(0.1 * (attempt + 1))
                else:
                    raise PheromoneError(f"Invalid JSON in pheromone file: {e}")

        return {}

    def _write_pheromone_atomic(self, data: dict[str, Any]) -> None:
        """Write pheromone file atomically

        Args:
            data: Data to write
        """
        self.hive_root.mkdir(parents=True, exist_ok=True)

        # Write to temp file first, then atomic replace
        temp_file = self.pheromone_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.pheromone_file)
        finally:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    def _write_pheromone(self, data: dict[str, Any]) -> None:
        """Write pheromone file with lock protection

        Args:
            data: Data to write
        """
        with FileLock(self.lock_file):
            self._write_pheromone_atomic(data)

    @contextmanager
    def _locked_operation(self):
        """Context manager for locked file operations"""
        lock = FileLock(self.lock_file)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    # ==================== Hive Control ====================

    def activate_hive(self, worker_count: int = 3) -> str:
        """Activate hive

        Args:
            worker_count: Number of workers

        Returns:
            hive_id: Hive ID
        """
        data = self._read_pheromone()
        data["status"] = "active"
        data["queen"]["phase"] = "planning"
        data["queen"]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        data["config"] = {"worker_count": worker_count}
        self._write_pheromone(data)
        return data["hive_id"]

    def deactivate_hive(self) -> None:
        """Deactivate hive"""
        data = self._read_pheromone()
        data["status"] = "inactive"
        data["queen"]["phase"] = "dormant"
        self._write_pheromone(data)

    def get_hive_status(self) -> dict[str, Any]:
        """Get hive overall status"""
        data = self._read_pheromone()
        workers = data.get("workers", [])

        active_workers = len([w for w in workers if w["status"] in ["implementing", "scouting"]])
        blocked_workers = len([w for w in workers if w["status"] == "blocked"])
        completed_workers = len([w for w in workers if w["status"] == "completed"])

        return {
            "hive_id": data["hive_id"],
            "status": data["status"],
            "phase": data["queen"]["phase"],
            "active_workers": active_workers,
            "blocked_workers": blocked_workers,
            "completed_workers": completed_workers,
            "total_workers": len(workers),
            "total_drones": len(data.get("drones", []))
        }

    # ==================== Worker Management ====================

    def register_worker(self, worker_id: str, cell_id: str) -> bool:
        """Register a worker

        Args:
            worker_id: Worker ID
            cell_id: Assigned cell ID

        Returns:
            True if registered successfully

        Raises:
            ValidationError: If IDs are invalid
        """
        validate_id(worker_id, "worker_id")
        validate_id(cell_id, "cell_id")

        data = self._read_pheromone()

        # Check if already registered
        for worker in data["workers"]:
            if worker["id"] == worker_id:
                return False

        now = datetime.now(timezone.utc).isoformat()
        worker_state = {
            "id": worker_id,
            "cell": cell_id,
            "status": WorkerStatus.IDLE.value,
            "progress": 0,
            "last_update": now
        }
        data["workers"].append(worker_state)
        self._write_pheromone(data)
        return True

    def write_progress(self, worker_id: str, status: str, progress: int) -> bool:
        """Write progress pheromone

        Args:
            worker_id: Worker ID
            status: Status
            progress: Progress (0-100)

        Returns:
            True if updated successfully

        Raises:
            WorkerNotFoundError: If worker not found
        """
        validate_id(worker_id, "worker_id")

        if not 0 <= progress <= 100:
            raise ValidationError(f"Progress must be 0-100, got {progress}")

        data = self._read_pheromone()

        worker_found = False
        for worker in data["workers"]:
            if worker["id"] == worker_id:
                worker["status"] = status
                worker["progress"] = progress
                worker["last_update"] = datetime.now(timezone.utc).isoformat()
                # Clear blocked status
                if status != WorkerStatus.BLOCKED.value:
                    worker["blocked_by"] = None
                    worker["block_reason"] = None
                worker_found = True
                break

        if not worker_found:
            raise WorkerNotFoundError(f"Worker not found: {worker_id}")

        # Add pheromone trace
        self._add_pheromone_trace(data, PheromoneType.PROGRESS, {
            "worker_id": worker_id,
            "status": status,
            "progress": progress
        })

        self._write_pheromone(data)
        return True

    def write_blocker(self, worker_id: str, blocked_by: str, reason: str) -> bool:
        """Write blocker pheromone

        Args:
            worker_id: Blocked worker ID
            blocked_by: Blocking source
            reason: Block reason

        Returns:
            True if updated successfully
        """
        validate_id(worker_id, "worker_id")

        data = self._read_pheromone()

        worker_found = False
        for worker in data["workers"]:
            if worker["id"] == worker_id:
                worker["status"] = WorkerStatus.BLOCKED.value
                worker["blocked_by"] = blocked_by
                worker["block_reason"] = reason
                worker["last_update"] = datetime.now(timezone.utc).isoformat()
                worker_found = True
                break

        if not worker_found:
            raise WorkerNotFoundError(f"Worker not found: {worker_id}")

        # Add alert pheromone
        self._add_pheromone_trace(data, PheromoneType.ALERT, {
            "type": "blocker",
            "worker_id": worker_id,
            "blocked_by": blocked_by,
            "reason": reason
        })

        self._write_pheromone(data)
        return True

    def write_completion(self, worker_id: str) -> bool:
        """Write completion pheromone

        Args:
            worker_id: Completed worker ID

        Returns:
            True if updated successfully
        """
        validate_id(worker_id, "worker_id")

        data = self._read_pheromone()

        cell_id = None
        for worker in data["workers"]:
            if worker["id"] == worker_id:
                worker["status"] = WorkerStatus.COMPLETED.value
                worker["progress"] = 100
                worker["last_update"] = datetime.now(timezone.utc).isoformat()
                cell_id = worker.get("cell")
                break

        if cell_id is None:
            raise WorkerNotFoundError(f"Worker not found: {worker_id}")

        self._add_pheromone_trace(data, PheromoneType.COMPLETION, {
            "worker_id": worker_id,
            "cell_id": cell_id
        })

        self._write_pheromone(data)
        return True

    def read_worker_status(self, worker_id: str) -> Optional[dict[str, Any]]:
        """Read worker status

        Args:
            worker_id: Worker ID

        Returns:
            Worker state or None if not found
        """
        data = self._read_pheromone()
        for worker in data["workers"]:
            if worker["id"] == worker_id:
                return worker
        return None

    def get_all_workers(self) -> list[dict[str, Any]]:
        """Get all workers"""
        data = self._read_pheromone()
        return data.get("workers", [])

    def get_blocked_workers(self) -> list[dict[str, Any]]:
        """Get all blocked workers"""
        data = self._read_pheromone()
        return [w for w in data.get("workers", []) if w["status"] == WorkerStatus.BLOCKED.value]

    # ==================== Drone Management ====================

    def register_drone(self, drone_id: str, drone_type: str) -> bool:
        """Register a drone validator

        Args:
            drone_id: Drone ID
            drone_type: Type (technical, strategic, security)

        Returns:
            True if registered successfully
        """
        validate_id(drone_id, "drone_id")

        if drone_type not in ("technical", "strategic", "security"):
            raise ValidationError(f"Invalid drone_type: {drone_type}")

        data = self._read_pheromone()

        for drone in data["drones"]:
            if drone["id"] == drone_id:
                return False

        drone_state = {
            "id": drone_id,
            "type": drone_type,
            "status": DroneStatus.WAITING.value,
            "assigned_cells": [],
            "score": None,
            "issues": []
        }
        data["drones"].append(drone_state)
        self._write_pheromone(data)
        return True

    def assign_drone_to_cells(self, drone_id: str, cell_ids: list[str]) -> bool:
        """Assign drone to cells

        Args:
            drone_id: Drone ID
            cell_ids: Cell IDs to validate

        Returns:
            True if assigned successfully
        """
        validate_id(drone_id, "drone_id")

        data = self._read_pheromone()

        for drone in data["drones"]:
            if drone["id"] == drone_id:
                drone["assigned_cells"] = cell_ids
                drone["status"] = DroneStatus.VALIDATING.value
                self._write_pheromone(data)
                return True

        raise DroneNotFoundError(f"Drone not found: {drone_id}")

    def write_drone_result(self, drone_id: str, score: int, issues: list[str]) -> bool:
        """Write drone validation result

        Args:
            drone_id: Drone ID
            score: Score (0-100)
            issues: List of issues found

        Returns:
            True if updated successfully
        """
        validate_id(drone_id, "drone_id")

        if not 0 <= score <= 100:
            raise ValidationError(f"Score must be 0-100, got {score}")

        data = self._read_pheromone()

        for drone in data["drones"]:
            if drone["id"] == drone_id:
                drone["score"] = score
                drone["issues"] = issues
                drone["status"] = (
                    DroneStatus.CONSENSUS.value if score >= 90
                    else DroneStatus.REJECTED.value
                )
                self._write_pheromone(data)
                return True

        raise DroneNotFoundError(f"Drone not found: {drone_id}")

    def get_consensus_score(self) -> int:
        """Get drone consensus score

        Returns:
            Average score of all drones
        """
        data = self._read_pheromone()
        drones = data.get("drones", [])

        if not drones:
            return 0

        scores = [d["score"] for d in drones if d["score"] is not None]
        return int(sum(scores) / len(scores)) if scores else 0

    def is_consensus_reached(self, threshold: int = 90) -> bool:
        """Check if consensus is reached"""
        return self.get_consensus_score() >= threshold

    # ==================== Pheromone Traces ====================

    def _add_pheromone_trace(self, data: dict[str, Any], p_type: PheromoneType, content: dict[str, Any]) -> None:
        """Add pheromone trace"""
        trace = {
            "type": p_type.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": content
        }
        if "pheromones" not in data:
            data["pheromones"] = []
        data["pheromones"].append(trace)

    def get_recent_traces(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent pheromone traces"""
        data = self._read_pheromone()
        traces = data.get("pheromones", [])
        return traces[-limit:] if traces else []

    # ==================== Heartbeat & Timeout ====================

    def send_heartbeat(self) -> None:
        """Send queen heartbeat"""
        data = self._read_pheromone()
        data["queen"]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        self._write_pheromone(data)

    def check_timeouts(self, timeout_seconds: int = 300) -> list[str]:
        """Check for timed out workers

        Args:
            timeout_seconds: Timeout in seconds

        Returns:
            List of timed out worker IDs
        """
        data = self._read_pheromone()
        now = datetime.now(timezone.utc)
        timed_out = []

        for worker in data.get("workers", []):
            if worker["status"] in [WorkerStatus.COMPLETED.value, WorkerStatus.FAILED.value]:
                continue

            try:
                last_update_str = worker["last_update"]
                # Handle various ISO formats
                if last_update_str.endswith('Z'):
                    last_update_str = last_update_str[:-1] + '+00:00'
                last_update = datetime.fromisoformat(last_update_str)

                if (now - last_update).total_seconds() > timeout_seconds:
                    timed_out.append(worker["id"])
            except (ValueError, KeyError):
                # Invalid timestamp, consider as timed out
                timed_out.append(worker["id"])

        return timed_out


# ==================== CLI Interface ====================

def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Pheromone communication tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # status command
    subparsers.add_parser("status", help="Show hive status")

    # worker command
    worker_parser = subparsers.add_parser("worker", help="Worker management")
    worker_parser.add_argument("--list", action="store_true", help="List all workers")
    worker_parser.add_argument("--blocked", action="store_true", help="List blocked workers")

    # consensus command
    subparsers.add_parser("consensus", help="Consensus status")

    # trace command
    trace_parser = subparsers.add_parser("trace", help="Pheromone traces")
    trace_parser.add_argument("--limit", type=int, default=10, help="Number of traces")

    args = parser.parse_args()
    pm = PheromoneManager()

    if args.command == "status":
        status = pm.get_hive_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))

    elif args.command == "worker":
        if args.blocked:
            workers = pm.get_blocked_workers()
        else:
            workers = pm.get_all_workers()
        print(json.dumps(workers, indent=2, ensure_ascii=False))

    elif args.command == "consensus":
        score = pm.get_consensus_score()
        reached = pm.is_consensus_reached()
        print(json.dumps({
            "consensus_score": score,
            "threshold": 90,
            "reached": reached
        }, indent=2))

    elif args.command == "trace":
        traces = pm.get_recent_traces(args.limit)
        print(json.dumps(traces, indent=2, ensure_ascii=False))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
