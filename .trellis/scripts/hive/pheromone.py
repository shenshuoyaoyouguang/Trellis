#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pheromone Module - Hive communication system

Manages pheromone-based state synchronization for concurrent agents.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict, List

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
                    try:
                        fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        return True
                    except (IOError, OSError):
                        os.close(self._lock_fd)
                        self._lock_fd = None
                        time.sleep(0.1)
                        continue

                elif HAS_MSVCRT:
                    # Windows system - use 'a+' to avoid truncating file
                    self._lock_handle = open(str(self.lock_file), 'a+')
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
        if not self.acquire():
            raise TimeoutError(f"Failed to acquire lock on {self.lock_file}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class PheromoneManager:
    """Manages pheromone-based inter-agent communication"""

    def __init__(self, hive_root: Optional[Path] = None):
        """Initialize pheromone manager

        Args:
            hive_root: Hive root directory, defaults to .trellis/
        """
        self.hive_root = hive_root or self._find_hive_root()
        self.pheromone_file = self.hive_root / "pheromone.json"
        self.lock_file = self.hive_root / ".pheromone.lock"

    def _find_hive_root(self) -> Path:
        """Find hive root directory"""
        current = Path.cwd()
        while current != current.parent:
            trellis_dir = current / ".trellis"
            if trellis_dir.exists():
                return trellis_dir
            current = current.parent
        return Path.cwd() / ".trellis"

    def _read_pheromone(self) -> Dict[str, Any]:
        """Read pheromone file

        Returns:
            Pheromone data dictionary
        """
        if not self.pheromone_file.exists():
            return {"status": "inactive"}

        with open(self.pheromone_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_pheromone_atomic(self, data: Dict[str, Any]) -> None:
        """Write pheromone file atomically

        Args:
            data: Pheromone data to write
        """
        self.hive_root.mkdir(parents=True, exist_ok=True)

        temp_file = self.pheromone_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.pheromone_file)
        finally:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    def write_pheromone(self, data: Dict[str, Any]) -> None:
        """Write pheromone file with lock protection

        Args:
            data: Pheromone data to write
        """
        with FileLock(self.lock_file):
            self._write_pheromone_atomic(data)

    def is_hive_active(self) -> bool:
        """Check if hive mode is active

        Returns:
            True if hive is active
        """
        data = self._read_pheromone()
        return data.get("status") == "active"

    def get_current_cell(self) -> Optional[str]:
        """Get current active cell ID

        Returns:
            Cell ID or None
        """
        data = self._read_pheromone()
        return data.get("current_cell")

    def get_worker_id(self) -> Optional[str]:
        """Get current worker ID

        Returns:
            Worker ID or None
        """
        data = self._read_pheromone()
        return data.get("worker_id")

    def update_worker_status(
        self,
        worker_id: str,
        cell_id: str,
        status: str,
        progress: int = 0,
        subagent_type: str = "implement"
    ) -> None:
        """Update worker status in pheromone

        Args:
            worker_id: Worker identifier
            cell_id: Cell being worked on
            status: Worker status
            progress: Progress percentage
            subagent_type: Agent type
        """
        data = self._read_pheromone()
        now = datetime.now(timezone.utc).isoformat()

        workers = data.get("workers", [])
        worker_found = False

        for worker in workers:
            if worker["id"] == worker_id:
                worker["status"] = status
                worker["progress"] = progress
                worker["last_update"] = now
                worker_found = True
                break

        if not worker_found:
            workers.append({
                "id": worker_id,
                "cell": cell_id,
                "status": status,
                "progress": progress,
                "last_update": now
            })

        data["workers"] = workers
        self.write_pheromone(data)


# Global instance
_pheromone_manager: Optional[PheromoneManager] = None


def get_pheromone_manager(reload: bool = False) -> PheromoneManager:
    """Get global pheromone manager instance

    Args:
        reload: Force reload

    Returns:
        PheromoneManager instance
    """
    global _pheromone_manager

    if _pheromone_manager is None or reload:
        _pheromone_manager = PheromoneManager()

    return _pheromone_manager


def reset_pheromone_manager() -> None:
    """Reset global pheromone manager instance"""
    global _pheromone_manager
    _pheromone_manager = None


if __name__ == "__main__":
    pm = get_pheromone_manager()
    print(f"Hive root: {pm.hive_root}")
    print(f"Pheromone file: {pm.pheromone_file}")
    print(f"Hive active: {pm.is_hive_active()}")
