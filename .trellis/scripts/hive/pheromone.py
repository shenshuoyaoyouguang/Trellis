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
import threading
import time
from dataclasses import dataclass
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


# Lock status constants
LOCK_STALE_THRESHOLD = 300  # Seconds after which a lock is considered stale


class LockInfo:
    """Lock information for diagnostics"""
    
    def __init__(
        self,
        holder_pid: Optional[int] = None,
        holder_time: Optional[float] = None,
        holder_hostname: Optional[str] = None
    ):
        self.holder_pid = holder_pid
        self.holder_time = holder_time
        self.holder_hostname = holder_hostname
    
    @classmethod
    def from_file(cls, lock_file: Path) -> Optional["LockInfo"]:
        """Read lock info from file
        
        Args:
            lock_file: Lock file path
            
        Returns:
            LockInfo or None if file doesn't exist
        """
        if not lock_file.exists():
            return None
        
        try:
            with open(lock_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            parts = content.split(':')
            if len(parts) >= 2:
                return cls(
                    holder_pid=int(parts[0]),
                    holder_time=float(parts[1]),
                    holder_hostname=parts[2] if len(parts) > 2 else None
                )
        except (ValueError, IOError, OSError):
            pass
        
        return None
    
    def to_string(self) -> str:
        """Convert to string for file storage"""
        import socket
        hostname = self.holder_hostname or socket.gethostname()
        return f"{self.holder_pid or os.getpid()}:{self.holder_time or time.time()}:{hostname}"
    
    def is_stale(self, threshold: float = LOCK_STALE_THRESHOLD) -> bool:
        """Check if lock is stale
        
        Args:
            threshold: Seconds after which lock is considered stale
            
        Returns:
            True if lock is stale
        """
        if self.holder_time is None:
            return True
        
        return (time.time() - self.holder_time) > threshold


class FileLock:
    """Cross-platform file lock for concurrent access protection
    
    Features:
    - Cross-platform support (Unix fcntl, Windows msvcrt)
    - Lock stale detection and automatic cleanup
    - Lock holder information tracking
    - Timeout support with configurable wait
    """
    
    def __init__(self, lock_file: Path, stale_threshold: float = LOCK_STALE_THRESHOLD):
        """Initialize file lock
        
        Args:
            lock_file: Path to lock file
            stale_threshold: Seconds after which a lock is considered stale
        """
        self.lock_file = lock_file
        self.stale_threshold = stale_threshold
        self._lock_fd: Optional[int] = None
        self._lock_handle: Optional[Any] = None
        self._owned = False
        self._acquire_time: Optional[float] = None

    def acquire(self, timeout: float = 10.0) -> bool:
        """Acquire lock with timeout
        
        Args:
            timeout: Maximum time to wait for lock in seconds
            
        Returns:
            True if lock acquired, False if timeout
        """
        start_time = time.time()
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        while time.time() - start_time < timeout:
            try:
                # Check for stale locks before attempting
                self._cleanup_stale_lock()
                
                if HAS_FCNTL:
                    # Unix-like system - use fcntl for robust locking
                    if self._acquire_fcntl():
                        return True
                        
                elif HAS_MSVCRT:
                    # Windows system - use msvcrt with improved handling
                    if self._acquire_msvcrt():
                        return True
                        
                else:
                    # Fallback - use atomic file creation
                    if self._acquire_atomic():
                        return True
                
                # Wait before retry
                time.sleep(0.1)
                
            except (IOError, OSError) as e:
                # Log error and retry
                if 'resource temporarily unavailable' not in str(e).lower():
                    print(f"Lock acquisition error: {e}", file=sys.stderr)
                self._close_lock_resources()
                time.sleep(0.1)
        
        return False

    def _acquire_fcntl(self) -> bool:
        """Acquire lock using fcntl (Unix)
        
        Returns:
            True if lock acquired
        """
        self._lock_fd = os.open(
            str(self.lock_file),
            os.O_CREAT | os.O_RDWR,
            0o644
        )
        try:
            # Try non-blocking lock
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._owned = True
            self._acquire_time = time.time()
            self._write_lock_info()
            return True
        except (IOError, OSError):
            os.close(self._lock_fd)
            self._lock_fd = None
            return False

    def _acquire_msvcrt(self) -> bool:
        """Acquire lock using msvcrt (Windows)
        
        Returns:
            True if lock acquired
        """
        try:
            # Use 'r+' mode to read existing content first
            self._lock_handle = open(str(self.lock_file), 'a+')
            
            # Try to lock the first byte
            msvcrt.locking(self._lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
            
            self._owned = True
            self._acquire_time = time.time()
            self._write_lock_info()
            return True
        except IOError:
            if self._lock_handle:
                try:
                    self._lock_handle.close()
                except IOError:
                    pass
                self._lock_handle = None
            return False

    def _acquire_atomic(self) -> bool:
        """Acquire lock using atomic file creation (fallback)
        
        Returns:
            True if lock acquired
        """
        try:
            # Use exclusive creation
            self._lock_fd = os.open(
                str(self.lock_file),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644
            )
            self._owned = True
            self._acquire_time = time.time()
            self._write_lock_info()
            return True
        except FileExistsError:
            return False

    def _write_lock_info(self) -> None:
        """Write lock holder information"""
        info = LockInfo(
            holder_pid=os.getpid(),
            holder_time=time.time()
        )
        
        try:
            if self._lock_fd is not None:
                # Write to file descriptor
                os.write(self._lock_fd, info.to_string().encode('utf-8'))
            elif self._lock_handle is not None:
                # Write to file handle
                self._lock_handle.seek(0)
                self._lock_handle.truncate()
                self._lock_handle.write(info.to_string())
                self._lock_handle.flush()
        except (IOError, OSError):
            pass  # Non-critical, continue

    def _cleanup_stale_lock(self) -> None:
        """Clean up stale locks if found"""
        info = LockInfo.from_file(self.lock_file)
        
        if info and info.is_stale(self.stale_threshold):
            # Lock is stale, attempt cleanup
            try:
                self.lock_file.unlink()
                print(f"Cleaned up stale lock: {self.lock_file}", file=sys.stderr)
            except (IOError, OSError):
                pass

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
        if not self._owned:
            return
        
        try:
            if HAS_FCNTL and self._lock_fd is not None:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                
            elif HAS_MSVCRT and self._lock_handle is not None:
                try:
                    # Seek to beginning before unlocking
                    self._lock_handle.seek(0)
                    msvcrt.locking(self._lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                except IOError:
                    pass  # Ignore unlock errors
        except Exception as e:
            # Log warning but don't fail
            print(f"Warning: Lock release failed: {e}", file=sys.stderr)
        finally:
            self._close_lock_resources()
            self._owned = False
            self._acquire_time = None
            
            # Clean up lock file for atomic mode
            if not (HAS_FCNTL or HAS_MSVCRT):
                try:
                    if self.lock_file.exists():
                        self.lock_file.unlink()
                except (IOError, OSError):
                    pass

    def is_locked(self) -> bool:
        """Check if lock is currently held by anyone
        
        Returns:
            True if locked
        """
        if self._owned:
            return True
            
        info = LockInfo.from_file(self.lock_file)
        if info and not info.is_stale(self.stale_threshold):
            return True
            
        return False

    def get_lock_info(self) -> Optional[LockInfo]:
        """Get current lock holder information
        
        Returns:
            LockInfo or None if not locked
        """
        if self._owned:
            return LockInfo(
                holder_pid=os.getpid(),
                holder_time=self._acquire_time
            )
        return LockInfo.from_file(self.lock_file)

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

    def get_active_trails(self) -> Dict[str, Any]:
        """Get all active pheromone trails

        Returns:
            Dictionary containing active pheromones and worker status
        """
        data = self._read_pheromone()
        
        # Get active pheromones if available
        active_pheromones = data.get("active_pheromones", [])
        
        # Get workers status
        workers = data.get("workers", [])
        
        # Get blockers
        blockers = [
            p for p in active_pheromones
            if p.get("type") == "blocker"
        ]
        
        return {
            "status": data.get("status", "inactive"),
            "active_pheromones": active_pheromones,
            "workers": workers,
            "blockers": blockers,
            "current_cell": data.get("current_cell"),
            "last_updated": data.get("last_updated")
        }

    def clear_all(self) -> None:
        """Clear all pheromone trails and reset to inactive state"""
        default_state = {
            "status": "inactive",
            "workers": [],
            "active_pheromones": [],
            "current_cell": None,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        self.write_pheromone(default_state)


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


# =============================================================================
# Pheromone Types
# =============================================================================

from enum import Enum
from typing import Callable


class PheromoneType(Enum):
    """Pheromone types for different communication purposes"""
    PROGRESS = "progress"       # Progress update
    BLOCKER = "blocker"         # Blocker alert
    COMPLETION = "completion"   # Task completion
    ALERT = "alert"             # Warning/alert
    HEARTBEAT = "heartbeat"     # Worker heartbeat
    SYNC = "sync"               # Synchronization signal
    REQUEST = "request"         # Resource request


@dataclass
class PheromoneEntry:
    """Single pheromone entry"""
    type: PheromoneType
    source: str                 # Worker or cell ID
    target: Optional[str]       # Target cell or worker (None = broadcast)
    data: Dict[str, Any]
    timestamp: str
    ttl: int = 300              # Time to live in seconds
    strength: float = 1.0       # Pheromone strength (decays over time)


class PheromoneSubscriber:
    """Subscriber for pheromone events"""
    
    def __init__(self, callback: Callable[[PheromoneEntry], None], 
                 pheromone_types: Optional[list[PheromoneType]] = None):
        """Initialize subscriber
        
        Args:
            callback: Callback function for pheromone events
            pheromone_types: Types to subscribe to (None = all types)
        """
        self.callback = callback
        self.pheromone_types = pheromone_types or list(PheromoneType)
        self.active = True
    
    def should_receive(self, entry: PheromoneEntry) -> bool:
        """Check if subscriber should receive this pheromone"""
        return self.active and entry.type in self.pheromone_types
    
    def notify(self, entry: PheromoneEntry) -> None:
        """Notify subscriber of new pheromone"""
        if self.should_receive(entry):
            try:
                self.callback(entry)
            except Exception:
                pass  # Don't fail on callback errors


class EnhancedPheromoneManager(PheromoneManager):
    """Enhanced pheromone manager with decay, propagation, and subscriptions
    
    Additional features:
    - Pheromone decay (TTL-based)
    - Cross-worktree propagation
    - Event subscription system
    - History tracking
    """
    
    def __init__(self, hive_root: Optional[Path] = None):
        """Initialize enhanced pheromone manager
        
        Args:
            hive_root: Hive root directory
        """
        super().__init__(hive_root)
        
        # Subscribers
        self._subscribers: list[PheromoneSubscriber] = []
        
        # History
        self._history: list[PheromoneEntry] = []
        self._max_history = 1000
        
        # Worktree tracking
        self._worktrees: dict[str, Path] = {}
        
        # Decay thread
        self._decay_thread: Optional[threading.Thread] = None
        self._stop_decay = threading.Event()
    
    # ==================== Lifecycle ====================
    
    def start_decay_monitor(self, interval: int = 30) -> None:
        """Start decay monitoring thread
        
        Args:
            interval: Check interval in seconds
        """
        if self._decay_thread and self._decay_thread.is_alive():
            return
        
        self._stop_decay.clear()
        self._decay_thread = threading.Thread(
            target=self._decay_loop,
            args=(interval,),
            daemon=True
        )
        self._decay_thread.start()
    
    def stop_decay_monitor(self) -> None:
        """Stop decay monitoring thread"""
        self._stop_decay.set()
        
        if self._decay_thread and self._decay_thread.is_alive():
            self._decay_thread.join(timeout=5.0)
    
    def _decay_loop(self, interval: int) -> None:
        """Decay monitoring loop"""
        while not self._stop_decay.is_set():
            try:
                self.decay_pheromones()
            except Exception as e:
                print(f"Decay error: {e}", file=sys.stderr)
            
            self._stop_decay.wait(interval)
    
    # ==================== Pheromone Operations ====================
    
    def emit(
        self,
        pheromone_type: PheromoneType,
        source: str,
        data: Dict[str, Any],
        target: Optional[str] = None,
        ttl: int = 300,
        strength: float = 1.0
    ) -> PheromoneEntry:
        """Emit a pheromone
        
        Args:
            pheromone_type: Type of pheromone
            source: Source ID (worker/cell)
            data: Pheromone data
            target: Target ID (None = broadcast)
            ttl: Time to live in seconds
            strength: Initial strength
            
        Returns:
            Created pheromone entry
        """
        entry = PheromoneEntry(
            type=pheromone_type,
            source=source,
            target=target,
            data=data,
            timestamp=datetime.now(timezone.utc).isoformat(),
            ttl=ttl,
            strength=strength
        )
        
        # Add to history
        self._add_to_history(entry)
        
        # Write to pheromone file
        self._write_entry(entry)
        
        # Notify subscribers
        self._notify_subscribers(entry)
        
        # Propagate to worktrees if broadcast
        if target is None:
            self._propagate_to_worktrees(entry)
        
        return entry
    
    def _write_entry(self, entry: PheromoneEntry) -> None:
        """Write pheromone entry to file"""
        data = self._read_pheromone()
        
        # Add to active pheromones
        if "active_pheromones" not in data:
            data["active_pheromones"] = []
        
        data["active_pheromones"].append({
            "type": entry.type.value,
            "source": entry.source,
            "target": entry.target,
            "data": entry.data,
            "timestamp": entry.timestamp,
            "ttl": entry.ttl,
            "strength": entry.strength
        })
        
        self.write_pheromone(data)
    
    def _add_to_history(self, entry: PheromoneEntry) -> None:
        """Add entry to history"""
        self._history.append(entry)
        
        # Trim history if needed
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
    
    # ==================== Decay ====================
    
    def decay_pheromones(self, ttl: Optional[int] = None) -> int:
        """Decay pheromones based on age
        
        Args:
            ttl: Override TTL (None = use entry's TTL)
            
        Returns:
            Number of expired pheromones
        """
        data = self._read_pheromone()
        now = datetime.now(timezone.utc)
        
        active = data.get("active_pheromones", [])
        surviving = []
        expired = 0
        
        for p in active:
            try:
                # Calculate age
                ts = p.get("timestamp", "")
                if ts.endswith('Z'):
                    ts = ts[:-1] + '+00:00'
                entry_time = datetime.fromisoformat(ts)
                age_seconds = (now - entry_time).total_seconds()
                
                # Check TTL
                entry_ttl = ttl if ttl is not None else p.get("ttl", 300)
                
                if age_seconds < entry_ttl:
                    # Decay strength
                    decay_factor = 1.0 - (age_seconds / entry_ttl)
                    p["strength"] = p.get("strength", 1.0) * decay_factor
                    surviving.append(p)
                else:
                    expired += 1
            except (ValueError, TypeError):
                # Invalid timestamp, consider expired
                expired += 1
        
        data["active_pheromones"] = surviving
        self.write_pheromone(data)
        
        return expired
    
    # ==================== Cross-Worktree Propagation ====================
    
    def register_worktree(self, worktree_id: str, path: Path) -> None:
        """Register a worktree for propagation
        
        Args:
            worktree_id: Worktree identifier
            path: Worktree path
        """
        self._worktrees[worktree_id] = path
    
    def unregister_worktree(self, worktree_id: str) -> None:
        """Unregister a worktree
        
        Args:
            worktree_id: Worktree identifier
        """
        self._worktrees.pop(worktree_id, None)
    
    def _propagate_to_worktrees(self, entry: PheromoneEntry) -> None:
        """Propagate pheromone to all registered worktrees
        
        Args:
            entry: Pheromone entry to propagate
        """
        for worktree_id, worktree_path in self._worktrees.items():
            try:
                self._write_to_worktree(worktree_path, entry)
            except Exception:
                pass  # Don't fail on propagation errors
    
    def _write_to_worktree(self, worktree_path: Path, entry: PheromoneEntry) -> None:
        """Write pheromone to worktree's pheromone file
        
        Args:
            worktree_path: Path to worktree
            entry: Pheromone entry
        """
        pheromone_file = worktree_path / ".trellis" / "incoming_pheromones.jsonl"
        pheromone_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(pheromone_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "type": entry.type.value,
                "source": entry.source,
                "target": entry.target,
                "data": entry.data,
                "timestamp": entry.timestamp
            }, ensure_ascii=False) + "\n")
    
    # ==================== Subscription ====================
    
    def subscribe(
        self,
        callback: Callable[[PheromoneEntry], None],
        pheromone_types: Optional[list[PheromoneType]] = None
    ) -> PheromoneSubscriber:
        """Subscribe to pheromone events
        
        Args:
            callback: Callback function
            pheromone_types: Types to subscribe to (None = all)
            
        Returns:
            Subscriber instance
        """
        subscriber = PheromoneSubscriber(callback, pheromone_types)
        self._subscribers.append(subscriber)
        return subscriber
    
    def unsubscribe(self, subscriber: PheromoneSubscriber) -> None:
        """Unsubscribe from pheromone events
        
        Args:
            subscriber: Subscriber to remove
        """
        subscriber.active = False
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)
    
    def _notify_subscribers(self, entry: PheromoneEntry) -> None:
        """Notify all subscribers of new pheromone
        
        Args:
            entry: Pheromone entry
        """
        for subscriber in self._subscribers:
            subscriber.notify(entry)
    
    # ==================== Blocking Pheromones ====================
    
    def emit_blocker(
        self,
        cell_id: str,
        reason: str,
        source: str
    ) -> PheromoneEntry:
        """Emit a blocker pheromone
        
        Args:
            cell_id: Blocked cell ID
            reason: Blocker reason
            source: Source ID
            
        Returns:
            Created pheromone entry
        """
        return self.emit(
            pheromone_type=PheromoneType.BLOCKER,
            source=source,
            target=cell_id,
            data={"reason": reason, "blocked_at": datetime.now(timezone.utc).isoformat()},
            ttl=600,  # 10 minutes
            strength=1.0
        )
    
    def resolve_blocker(self, cell_id: str, source: str) -> None:
        """Resolve a blocker pheromone
        
        Args:
            cell_id: Cell ID to resolve
            source: Resolver ID
        """
        self.emit(
            pheromone_type=PheromoneType.COMPLETION,
            source=source,
            target=cell_id,
            data={"resolved": True, "resolved_at": datetime.now(timezone.utc).isoformat()},
            ttl=60
        )
        
        # Remove from active blockers
        data = self._read_pheromone()
        active = data.get("active_pheromones", [])
        
        data["active_pheromones"] = [
            p for p in active
            if not (p.get("type") == "blocker" and p.get("target") == cell_id)
        ]
        
        self.write_pheromone(data)
    
    def get_active_blockers(self) -> list[Dict[str, Any]]:
        """Get list of active blockers
        
        Returns:
            List of blocker pheromones
        """
        data = self._read_pheromone()
        active = data.get("active_pheromones", [])
        
        return [
            p for p in active
            if p.get("type") == "blocker"
        ]
    
    # ==================== History ====================
    
    def get_history(
        self,
        cell_id: Optional[str] = None,
        pheromone_type: Optional[PheromoneType] = None,
        limit: int = 100
    ) -> list[PheromoneEntry]:
        """Get pheromone history
        
        Args:
            cell_id: Filter by cell ID
            pheromone_type: Filter by type
            limit: Maximum entries to return
            
        Returns:
            List of pheromone entries
        """
        filtered = self._history
        
        if cell_id:
            filtered = [e for e in filtered if e.source == cell_id or e.target == cell_id]
        
        if pheromone_type:
            filtered = [e for e in filtered if e.type == pheromone_type]
        
        return filtered[-limit:]
    
    def clear_history(self) -> None:
        """Clear pheromone history"""
        self._history.clear()


# Global enhanced instance
_enhanced_pheromone_manager: Optional[EnhancedPheromoneManager] = None


def get_enhanced_pheromone_manager(reload: bool = False) -> EnhancedPheromoneManager:
    """Get global enhanced pheromone manager instance
    
    Args:
        reload: Force reload
        
    Returns:
        EnhancedPheromoneManager instance
    """
    global _enhanced_pheromone_manager
    
    if _enhanced_pheromone_manager is None or reload:
        _enhanced_pheromone_manager = EnhancedPheromoneManager()
    
    return _enhanced_pheromone_manager


if __name__ == "__main__":
    pm = get_pheromone_manager()
    print(f"Hive root: {pm.hive_root}")
    print(f"Pheromone file: {pm.pheromone_file}")
    print(f"Hive active: {pm.is_hive_active()}")
