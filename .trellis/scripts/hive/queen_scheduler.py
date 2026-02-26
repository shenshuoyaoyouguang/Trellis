#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Queen Scheduler Module

Central orchestrator for hive concurrent agent mode.
Manages task distribution, worker coordination, and progress monitoring.

Usage:
    from queen_scheduler import QueenScheduler
    
    queen = QueenScheduler()
    queen.start()
    queen.dispatch_workers()
    status = queen.monitor_progress()
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future
from queue import Queue, Empty

from .hive_config import HiveConfig, get_config
from .cell_manager import CellManager, Cell, CellNotFoundError
from .pheromone import PheromoneManager, get_pheromone_manager
from .models import WorkerState, Worker, WorkerTask, TaskPriority, HiveError


# Configure logging
logger = logging.getLogger("hive.queen")


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None
) -> None:
    """Setup logging for hive module
    
    Args:
        level: Logging level
        log_file: Optional log file path
        format_string: Optional custom format string
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    formatter = logging.Formatter(format_string)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    handlers = [console_handler]
    
    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Configure logger
    logger.setLevel(level)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    for handler in handlers:
        logger.addHandler(handler)


class QueenSchedulerError(HiveError):
    """Exception for queen scheduler specific errors"""
    pass


class SchedulerState(Enum):
    """Scheduler states"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


# WorkerState and Worker are now imported from .models


@dataclass
class SchedulerStats:
    """Scheduler statistics"""
    total_cells: int = 0
    completed_cells: int = 0
    pending_cells: int = 0
    blocked_cells: int = 0
    active_workers: int = 0
    idle_workers: int = 0
    errors: int = 0


class QueenScheduler:
    """Central orchestrator for hive concurrent agent mode
    
    Responsibilities:
    - Global task distribution
    - Worker pool management
    - Progress monitoring
    - Blocker handling
    - Pheromone synchronization
    """
    
    # Track all instances for cleanup
    _instances: list["QueenScheduler"] = []
    _cleanup_registered = False
    
    def __init__(
        self,
        hive_root: Optional[Path] = None,
        config: Optional[HiveConfig] = None,
        max_workers: Optional[int] = None
    ):
        """Initialize queen scheduler
        
        Args:
            hive_root: Hive root directory
            config: Hive configuration
            max_workers: Override max workers from config
        """
        self.hive_root = hive_root or self._find_hive_root()
        self.project_root = self.hive_root.parent
        
        # Configuration
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.worker_count
        
        # Components
        self.cell_manager = CellManager(self.hive_root)
        self.pheromone_manager = get_pheromone_manager()
        
        # State
        self.state = SchedulerState.IDLE
        self.workers: dict[str, Worker] = {}
        self.worker_counter = 0
        
        # Threading
        self._executor: Optional[ThreadPoolExecutor] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._dispatch_lock = threading.Lock()  # Protects dispatch operations
        
        # Callbacks
        self._on_cell_complete: Optional[Callable[[str], None]] = None
        self._on_blocker: Optional[Callable[[str, str], None]] = None
        self._on_error: Optional[Callable[[str, Exception], None]] = None
        
        # Setup logging
        self._setup_logging()
        
        # Register for cleanup
        self._register_cleanup()
    
    def _setup_logging(self) -> None:
        """Setup logging based on configuration"""
        # Get log level from config
        log_level = logging.INFO
        log_file = None
        
        # Check for logging configuration in hive-config.yaml
        try:
            config_path = self.hive_root / "hive-config.yaml"
            if config_path.exists():
                try:
                    import yaml
                    with open(config_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                    logging_config = data.get("logging", {})
                    
                    # Parse log level
                    level_str = logging_config.get("level", "info").upper()
                    level_map = {
                        "DEBUG": logging.DEBUG,
                        "INFO": logging.INFO,
                        "WARN": logging.WARNING,
                        "WARNING": logging.WARNING,
                        "ERROR": logging.ERROR,
                    }
                    log_level = level_map.get(level_str, logging.INFO)
                    
                    # Get log file path if trace_dir is configured
                    trace_dir = logging_config.get("trace_dir")
                    if trace_dir:
                        log_file = self.hive_root.parent / trace_dir.lstrip("./") / "queen.log"
                except Exception:
                    pass
        except Exception:
            pass
        
        setup_logging(level=log_level, log_file=log_file)
    
    @classmethod
    def _register_cleanup(cls) -> None:
        """Register atexit handler for cleanup"""
        if not cls._cleanup_registered:
            atexit.register(cls._cleanup_all_instances)
            cls._cleanup_registered = True
    
    @classmethod
    def _cleanup_all_instances(cls) -> None:
        """Clean up all scheduler instances on exit"""
        for instance in cls._instances:
            try:
                instance._cleanup_workers(force=True)
            except Exception:
                pass
        cls._instances.clear()
    
    def _find_hive_root(self) -> Path:
        """Find hive root directory"""
        current = Path.cwd()
        while current != current.parent:
            trellis_dir = current / ".trellis"
            if trellis_dir.exists():
                return trellis_dir
            current = current.parent
        return Path.cwd() / ".trellis"
    
    # ==================== Lifecycle ====================
    
    def start(self) -> None:
        """Start the scheduler"""
        if self.state == SchedulerState.RUNNING:
            return
        
        self.state = SchedulerState.RUNNING
        self._stop_event.clear()
        
        # Register instance for cleanup
        if self not in QueenScheduler._instances:
            QueenScheduler._instances.append(self)
        
        # Initialize executor
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True
        )
        self._heartbeat_thread.start()
        
        # Initialize workers
        self._initialize_workers()
        
        # Update pheromone
        self._update_pheromone_status("active")
        
        logger.info(f"Queen scheduler started with {self.max_workers} workers")
    
    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Stop the scheduler
        
        Args:
            wait: Wait for running tasks to complete
            timeout: Maximum wait time in seconds
        """
        if self.state == SchedulerState.STOPPED:
            return
        
        self._stop_event.set()
        self.state = SchedulerState.STOPPED
        
        logger.info("Stopping queen scheduler...")
        
        # Cleanup workers
        self._cleanup_workers(wait=wait, timeout=timeout)
        
        # Stop heartbeat thread
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5.0)
        
        # Shutdown executor
        if self._executor:
            self._executor.shutdown(wait=wait, cancel_futures=not wait)
            self._executor = None
        
        # Update pheromone
        self._update_pheromone_status("inactive")
        
        # Remove from instances
        if self in QueenScheduler._instances:
            QueenScheduler._instances.remove(self)
        
        logger.info("Queen scheduler stopped")
    
    def _cleanup_workers(self, wait: bool = True, timeout: float = 30.0, force: bool = False) -> None:
        """Clean up all workers
        
        Args:
            wait: Wait for processes to terminate
            timeout: Maximum wait time
            force: Force kill if graceful shutdown fails
        """
        start_time = time.time()
        
        for worker_id, worker in list(self.workers.items()):
            self._cleanup_worker_process(worker, wait and not force, timeout / 2)
            worker.state = WorkerState.STOPPED
        
        # If force and still have processes, kill them
        if force:
            remaining_time = timeout - (time.time() - start_time)
            if remaining_time > 0:
                time.sleep(min(remaining_time, 2.0))
            
            for worker in self.workers.values():
                if worker.process and worker.process.poll() is None:
                    self._kill_process_tree(worker.process)
    
    def _cleanup_worker_process(self, worker: Worker, wait: bool = True, timeout: float = 10.0) -> None:
        """Clean up a single worker process
        
        Args:
            worker: Worker to clean up
            wait: Wait for process to terminate
            timeout: Maximum wait time
        """
        if worker.process is None:
            return
        
        try:
            # Try graceful termination first
            if worker.process.poll() is None:
                worker.process.terminate()
                
                if wait:
                    try:
                        worker.process.wait(timeout=timeout / 2)
                        logger.debug(f"Worker process {worker.id} terminated gracefully")
                    except subprocess.TimeoutExpired:
                        # Force kill if terminate didn't work
                        self._kill_process_tree(worker.process)
                        logger.warning(f"Worker process {worker.id} force killed")
                        
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug(f"Worker process cleanup error: {e}")
        finally:
            worker.process = None
    
    def _kill_process_tree(self, process: subprocess.Popen) -> None:
        """Kill a process and all its children
        
        Args:
            process: Process to kill
        """
        try:
            pid = process.pid
            
            # On Windows, use taskkill for process tree
            if sys.platform == 'win32':
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(pid)],
                    capture_output=True,
                    timeout=10
                )
            else:
                # On Unix, try to kill process group
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    process.kill()
        except Exception as e:
            logger.warning(f"Failed to kill process tree: {e}")
            # Last resort: try simple kill
            try:
                process.kill()
            except Exception:
                pass
    
    def pause(self) -> None:
        """Pause the scheduler"""
        if self.state == SchedulerState.RUNNING:
            self.state = SchedulerState.PAUSED
    
    def resume(self) -> None:
        """Resume the scheduler"""
        if self.state == SchedulerState.PAUSED:
            self.state = SchedulerState.RUNNING
    
    # ==================== Worker Management ====================
    
    def _initialize_workers(self) -> None:
        """Initialize worker pool"""
        for i in range(self.max_workers):
            worker_id = f"worker-{i+1}"
            self.workers[worker_id] = Worker(id=worker_id)
    
    def get_idle_workers(self) -> list[Worker]:
        """Get list of idle workers
        
        Returns:
            List of idle workers
        """
        return [
            w for w in self.workers.values()
            if w.state == WorkerState.IDLE
        ]
    
    def get_busy_workers(self) -> list[Worker]:
        """Get list of busy workers
        
        Returns:
            List of busy workers
        """
        return [
            w for w in self.workers.values()
            if w.state == WorkerState.BUSY
        ]
    
    def assign_cell_to_worker(self, worker: Worker, cell: dict[str, Any]) -> bool:
        """Assign a cell to a worker
        
        Args:
            worker: Worker to assign
            cell: Cell configuration
            
        Returns:
            True if assignment successful
        """
        if worker.state != WorkerState.IDLE:
            return False
        
        cell_id = cell["id"]
        worktree_path = cell.get("worktree_path")
        
        worker.cell_id = cell_id
        worker.state = WorkerState.BUSY
        worker.progress = 0
        worker.started_at = datetime.now(timezone.utc).isoformat()
        worker.last_heartbeat = worker.started_at
        worker.worktree_path = worktree_path
        
        # Update cell status
        self.cell_manager.update_cell_status(cell_id, "in_progress")
        
        # Update pheromone
        self.pheromone_manager.update_worker_status(
            worker.id,
            cell_id,
            "busy",
            progress=0
        )
        
        return True
    
    def release_worker(self, worker_id: str, success: bool = True) -> None:
        """Release a worker after task completion
        
        Args:
            worker_id: Worker ID
            success: Whether task completed successfully
        """
        worker = self.workers.get(worker_id)
        if not worker:
            return
        
        cell_id = worker.cell_id
        
        # Update cell status
        if cell_id:
            status = "completed" if success else "failed"
            self.cell_manager.update_cell_status(cell_id, status)
        
        # Reset worker
        worker.cell_id = None
        worker.state = WorkerState.IDLE
        worker.progress = 0
        worker.worktree_path = None
        
        # Update pheromone
        self.pheromone_manager.update_worker_status(
            worker_id,
            cell_id or "",
            "idle",
            progress=100 if success else 0
        )
    
    # ==================== Task Dispatch ====================
    
    def dispatch_workers(self) -> dict[str, Any]:
        """Dispatch idle workers to ready cells
        
        Thread-safe: Uses _dispatch_lock to prevent concurrent dispatch
        that could cause duplicate assignments.
        
        Returns:
            Dispatch summary
        """
        if self.state != SchedulerState.RUNNING:
            return {"dispatched": 0, "reason": "scheduler_not_running"}
        
        with self._dispatch_lock:
            idle_workers = self.get_idle_workers()
            ready_cells = self.cell_manager.get_ready_cells()
            
            dispatched = 0
            assignments = []
            
            for worker, cell in zip(idle_workers, ready_cells):
                if self.assign_cell_to_worker(worker, cell):
                    dispatched += 1
                    assignments.append({
                        "worker_id": worker.id,
                        "cell_id": cell["id"]
                    })
            
            return {
                "dispatched": dispatched,
                "assignments": assignments,
                "remaining_idle": len(self.get_idle_workers()),
                "remaining_ready": len(ready_cells) - dispatched
            }
    
    def run_cell(
        self,
        cell_id: str,
        platform: str = "claude",
        background: bool = True
    ) -> Optional[Future]:
        """Run a single cell
        
        Thread-safe: Uses _dispatch_lock for atomic worker assignment.
        
        Args:
            cell_id: Cell ID
            platform: CLI platform
            background: Run in background
            
        Returns:
            Future if background=True, else None
        """
        cell = self.cell_manager.get_cell(cell_id)
        if not cell:
            raise CellNotFoundError(f"Cell not found: {cell_id}")
        
        # Find idle worker and assign atomically
        with self._dispatch_lock:
            idle_workers = self.get_idle_workers()
            if not idle_workers:
                raise QueenSchedulerError("No idle workers available")
            
            worker = idle_workers[0]
            self.assign_cell_to_worker(worker, cell)
        
        if background and self._executor:
            return self._executor.submit(
                self._execute_cell_task,
                worker.id,
                cell,
                platform
            )
        else:
            self._execute_cell_task(worker.id, cell, platform)
            return None
    
    def _execute_cell_task(
        self,
        worker_id: str,
        cell: dict[str, Any],
        platform: str = "claude"
    ) -> dict[str, Any]:
        """Execute cell task (internal)
        
        Args:
            worker_id: Worker ID
            cell: Cell configuration
            platform: CLI platform
            
        Returns:
            Execution result
        """
        worker = self.workers.get(worker_id)
        if not worker:
            return {"success": False, "error": "worker_not_found"}
        
        cell_id = cell["id"]
        worktree_path = cell.get("worktree_path")
        
        try:
            # Build command
            task_dir = f".trellis/cells/{cell_id}"
            cmd = self._build_agent_command(platform, task_dir, worktree_path)
            
            if not cmd:
                raise QueenSchedulerError(f"Failed to build command for {platform}")
            
            # Execute
            work_dir = Path(worktree_path) if worktree_path else self.project_root
            
            process = subprocess.Popen(
                cmd,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            worker.process = process
            
            # Wait for completion
            stdout, stderr = process.communicate(timeout=self.config.worker.timeout)
            
            success = process.returncode == 0
            
            # Release worker
            self.release_worker(worker_id, success=success)
            
            # Callback
            if success and self._on_cell_complete:
                self._on_cell_complete(cell_id)
            
            return {
                "success": success,
                "cell_id": cell_id,
                "returncode": process.returncode,
                "stdout": stdout[:1000] if stdout else None,
                "stderr": stderr[:1000] if stderr else None
            }
            
        except subprocess.TimeoutExpired:
            worker.state = WorkerState.TIMEOUT
            self.release_worker(worker_id, success=False)
            return {"success": False, "error": "timeout", "cell_id": cell_id}
            
        except Exception as e:
            worker.state = WorkerState.ERROR
            self.release_worker(worker_id, success=False)
            
            if self._on_error:
                self._on_error(cell_id, e)
            
            return {"success": False, "error": str(e), "cell_id": cell_id}
    
    def _build_agent_command(
        self,
        platform: str,
        task_dir: str,
        worktree_path: Optional[str]
    ) -> Optional[list[str]]:
        """Build CLI command for agent
        
        Args:
            platform: CLI platform
            task_dir: Task directory
            worktree_path: Worktree path
            
        Returns:
            Command list or None
        """
        work_dir = Path(worktree_path) if worktree_path else self.project_root
        
        # Set current task
        current_task_file = work_dir / ".trellis" / ".current-task"
        current_task_file.parent.mkdir(parents=True, exist_ok=True)
        current_task_file.write_text(task_dir, encoding="utf-8")
        
        prompt = "Follow your agent instructions to execute the task workflow."
        
        if platform == "claude":
            return [
                "claude",
                "--dangerously-skip-permissions",
                "--verbose",
                "--print",
                prompt
            ]
        elif platform == "opencode":
            return [
                "opencode",
                "--non-interactive",
                "--json",
                prompt
            ]
        elif platform == "cursor":
            return [
                "cursor-agent",
                "--yes",
                prompt
            ]
        
        return None
    
    # ==================== Progress Monitoring ====================
    
    def monitor_progress(self) -> SchedulerStats:
        """Monitor scheduler progress
        
        Returns:
            Scheduler statistics
        """
        cells = self.cell_manager.list_cells()
        
        stats = SchedulerStats(
            total_cells=len(cells),
            completed_cells=sum(1 for c in cells if c["status"] == "completed"),
            pending_cells=sum(1 for c in cells if c["status"] == "pending"),
            blocked_cells=sum(1 for c in cells if c["status"] == "blocked"),
            active_workers=len(self.get_busy_workers()),
            idle_workers=len(self.get_idle_workers())
        )
        
        return stats
    
    def get_status(self) -> dict[str, Any]:
        """Get detailed scheduler status
        
        Returns:
            Status dictionary
        """
        stats = self.monitor_progress()
        
        return {
            "state": self.state.value,
            "max_workers": self.max_workers,
            "stats": {
                "total_cells": stats.total_cells,
                "completed_cells": stats.completed_cells,
                "pending_cells": stats.pending_cells,
                "blocked_cells": stats.blocked_cells,
                "active_workers": stats.active_workers,
                "idle_workers": stats.idle_workers
            },
            "workers": {
                w_id: {
                    "state": w.state.value,
                    "cell_id": w.cell_id,
                    "progress": w.progress,
                    "last_heartbeat": w.last_heartbeat
                }
                for w_id, w in self.workers.items()
            }
        }
    
    # ==================== Blocker Handling ====================
    
    def handle_blocker(self, cell_id: str, reason: str = "unknown") -> dict[str, Any]:
        """Handle a blocked cell
        
        Args:
            cell_id: Cell ID
            reason: Blocker reason
            
        Returns:
            Handling result
        """
        cell = self.cell_manager.get_cell(cell_id)
        if not cell:
            return {"handled": False, "error": "cell_not_found"}
        
        # Update cell status
        self.cell_manager.update_cell_status(cell_id, "blocked")
        
        # Find worker assigned to this cell
        blocked_worker = None
        for worker in self.workers.values():
            if worker.cell_id == cell_id:
                blocked_worker = worker
                break
        
        # Update worker state
        if blocked_worker:
            blocked_worker.state = WorkerState.BLOCKED
        
        # Write blocker pheromone
        self._write_blocker_pheromone(cell_id, reason)
        
        # Callback
        if self._on_blocker:
            self._on_blocker(cell_id, reason)
        
        return {
            "handled": True,
            "cell_id": cell_id,
            "reason": reason,
            "worker_id": blocked_worker.id if blocked_worker else None
        }
    
    def resolve_blocker(self, cell_id: str) -> bool:
        """Resolve a blocked cell
        
        Args:
            cell_id: Cell ID
            
        Returns:
            True if resolved successfully
        """
        cell = self.cell_manager.get_cell(cell_id)
        if not cell or cell["status"] != "blocked":
            return False
        
        # Update cell status
        self.cell_manager.update_cell_status(cell_id, "pending")
        
        # Release blocked worker
        for worker in self.workers.values():
            if worker.cell_id == cell_id:
                worker.state = WorkerState.IDLE
                break
        
        return True
    
    # ==================== Pheromone Sync ====================
    
    def coordinate_pheromone_sync(self) -> None:
        """Coordinate pheromone synchronization across all workers"""
        data = {
            "status": self.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workers": [
                {
                    "id": w.id,
                    "state": w.state.value,
                    "cell_id": w.cell_id,
                    "progress": w.progress,
                    "last_heartbeat": w.last_heartbeat
                }
                for w in self.workers.values()
            ]
        }
        
        self.pheromone_manager.write_pheromone(data)
    
    def _update_pheromone_status(self, status: str) -> None:
        """Update pheromone status"""
        data = self.pheromone_manager._read_pheromone()
        data["status"] = status
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.pheromone_manager.write_pheromone(data)
    
    def _write_blocker_pheromone(self, cell_id: str, reason: str) -> None:
        """Write blocker pheromone"""
        data = self.pheromone_manager._read_pheromone()
        
        blockers = data.get("blockers", [])
        blockers.append({
            "cell_id": cell_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        data["blockers"] = blockers
        self.pheromone_manager.write_pheromone(data)
    
    # ==================== Heartbeat ====================
    
    def _heartbeat_loop(self) -> None:
        """Heartbeat monitoring loop"""
        while not self._stop_event.is_set():
            try:
                self._check_worker_heartbeats()
                self.coordinate_pheromone_sync()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}", exc_info=True)
            
            # Wait for next heartbeat interval
            self._stop_event.wait(self.config.pheromone.heartbeat_interval)
    
    def _check_worker_heartbeats(self) -> None:
        """Check worker heartbeats and detect timeouts"""
        now = datetime.now(timezone.utc)
        timeout_seconds = self.config.pheromone.timeout
        
        for worker in self.workers.values():
            if worker.state != WorkerState.BUSY:
                continue
            
            if not worker.last_heartbeat:
                continue
            
            try:
                # Parse heartbeat time
                hb_time = datetime.fromisoformat(worker.last_heartbeat.replace('Z', '+00:00'))
                elapsed = (now - hb_time).total_seconds()
                
                if elapsed > timeout_seconds:
                    worker.state = WorkerState.TIMEOUT
                    logger.warning(
                        f"Worker {worker.id} heartbeat timeout "
                        f"(elapsed: {elapsed:.1f}s, threshold: {timeout_seconds}s)"
                    )
                    
                    # Persist heartbeat event
                    self._persist_heartbeat_event(worker, elapsed, timeout_seconds)
                    
                    if worker.cell_id:
                        self.handle_blocker(
                            worker.cell_id,
                            f"worker_timeout: {worker.id}"
                        )
            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to parse heartbeat for worker {worker.id}: {e}")
                continue
    
    def _persist_heartbeat_event(
        self,
        worker: Worker,
        elapsed: float,
        threshold: float
    ) -> None:
        """Persist heartbeat timeout event for diagnostics
        
        Args:
            worker: Worker with timeout
            elapsed: Elapsed time since last heartbeat
            threshold: Timeout threshold
        """
        try:
            events_file = self.hive_root / "heartbeat_events.jsonl"
            events_file.parent.mkdir(parents=True, exist_ok=True)
            
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": "heartbeat_timeout",
                "worker_id": worker.id,
                "cell_id": worker.cell_id,
                "elapsed_seconds": elapsed,
                "threshold_seconds": threshold,
                "worker_state": worker.state.value
            }
            
            with open(events_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"Failed to persist heartbeat event: {e}")
    
    # ==================== Callbacks ====================
    
    def on_cell_complete(self, callback: Callable[[str], None]) -> None:
        """Register callback for cell completion
        
        Args:
            callback: Callback function(cell_id)
        """
        self._on_cell_complete = callback
    
    def on_blocker(self, callback: Callable[[str, str], None]) -> None:
        """Register callback for blocker events
        
        Args:
            callback: Callback function(cell_id, reason)
        """
        self._on_blocker = callback
    
    def on_error(self, callback: Callable[[str, Exception], None]) -> None:
        """Register callback for error events
        
        Args:
            callback: Callback function(cell_id, exception)
        """
        self._on_error = callback
    
    # ==================== Context Manager ====================
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


# ==================== Global Instance ====================

_queen_scheduler: Optional[QueenScheduler] = None


def get_queen_scheduler(reload: bool = False) -> QueenScheduler:
    """Get global queen scheduler instance
    
    Args:
        reload: Force reload
        
    Returns:
        QueenScheduler instance
    """
    global _queen_scheduler
    
    if _queen_scheduler is None or reload:
        _queen_scheduler = QueenScheduler()
    
    return _queen_scheduler


def reset_queen_scheduler() -> None:
    """Reset global queen scheduler instance"""
    global _queen_scheduler
    
    if _queen_scheduler:
        _queen_scheduler.stop()
    
    _queen_scheduler = None


# ==================== CLI Interface ====================

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Queen scheduler tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")
    
    # status command
    subparsers.add_parser("status", help="Show scheduler status")
    
    # dispatch command
    dispatch_parser = subparsers.add_parser("dispatch", help="Dispatch workers")
    dispatch_parser.add_argument("--dry-run", action="store_true", help="Show what would be dispatched")
    
    # monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor progress")
    monitor_parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds")
    
    args = parser.parse_args()
    
    queen = QueenScheduler()
    
    if args.command == "status":
        status = queen.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    
    elif args.command == "dispatch":
        if args.dry_run:
            ready = queen.cell_manager.get_ready_cells()
            idle = queen.get_idle_workers()
            print(f"Ready cells: {len(ready)}")
            print(f"Idle workers: {len(idle)}")
            for cell in ready[:len(idle)]:
                print(f"  Would assign: {cell['id']}")
        else:
            queen.start()
            result = queen.dispatch_workers()
            print(json.dumps(result, indent=2, ensure_ascii=False))
            queen.stop()
    
    elif args.command == "monitor":
        queen.start()
        try:
            while True:
                stats = queen.monitor_progress()
                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
                      f"Cells: {stats.completed_cells}/{stats.total_cells} | "
                      f"Workers: {stats.active_workers} active, {stats.idle_workers} idle | "
                      f"Blocked: {stats.blocked_cells}",
                      end="", flush=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
        finally:
            queen.stop()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
