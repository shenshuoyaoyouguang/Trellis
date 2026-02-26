#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker Pool Module

Manages worker lifecycle, task assignment, and load balancing
for hive concurrent agent mode.

Usage:
    from worker_pool import WorkerPool
    
    pool = WorkerPool(max_workers=3)
    worker = pool.assign_cell(cell_config)
    pool.monitor_heartbeat()
    idle = pool.get_idle_workers()
"""

from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue, Empty
from concurrent.futures import Future

from .hive_config import HiveConfig, get_config
from .models import WorkerState, Worker, WorkerTask, TaskPriority, HiveError


# WorkerState, TaskPriority, WorkerTask, Worker are now imported from .models


@dataclass
class PoolStats:
    """Pool statistics"""
    total_workers: int = 0
    idle_workers: int = 0
    busy_workers: int = 0
    blocked_workers: int = 0
    error_workers: int = 0
    pending_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0


class WorkerPoolError(HiveError):
    """Exception for worker pool specific errors"""
    pass


class NoIdleWorkerError(WorkerPoolError):
    """Raised when no idle worker is available"""
    pass


class TaskQueue:
    """Priority-based task queue"""
    
    def __init__(self):
        self._queues: dict[TaskPriority, list[WorkerTask]] = {
            TaskPriority.HIGH: [],
            TaskPriority.MEDIUM: [],
            TaskPriority.LOW: []
        }
        self._lock = threading.Lock()
    
    def put(self, task: WorkerTask) -> None:
        """Add task to queue"""
        with self._lock:
            self._queues[task.priority].append(task)
    
    def get(self) -> Optional[WorkerTask]:
        """Get highest priority task"""
        with self._lock:
            for priority in TaskPriority:
                if self._queues[priority]:
                    return self._queues[priority].pop(0)
        return None
    
    def peek(self) -> Optional[WorkerTask]:
        """Peek at highest priority task without removing"""
        with self._lock:
            for priority in TaskPriority:
                if self._queues[priority]:
                    return self._queues[priority][0]
        return None
    
    def size(self) -> int:
        """Get total queue size"""
        with self._lock:
            return sum(len(q) for q in self._queues.values())
    
    def clear(self) -> None:
        """Clear all tasks"""
        with self._lock:
            for q in self._queues.values():
                q.clear()


class WorkerPool:
    """Worker pool for concurrent task execution
    
    Features:
    - Dynamic worker management
    - Task priority queue
    - Heartbeat monitoring
    - Task stealing (load balancing)
    - Automatic recovery
    - Process cleanup on exit
    """
    
    # Track all instances for cleanup
    _instances: list["WorkerPool"] = []
    _cleanup_registered = False
    
    def __init__(
        self,
        max_workers: int = 3,
        min_workers: int = 1,
        config: Optional[HiveConfig] = None,
        hive_root: Optional[Path] = None
    ):
        """Initialize worker pool
        
        Args:
            max_workers: Maximum number of workers
            min_workers: Minimum number of workers
            config: Hive configuration
            hive_root: Hive root directory
        """
        self.max_workers = max_workers
        self.min_workers = min_workers
        self.config = config or get_config()
        self.hive_root = hive_root or self._find_hive_root()
        self.project_root = self.hive_root.parent
        
        # Workers
        self.workers: dict[str, Worker] = {}
        self._worker_counter = 0
        
        # Task queue
        self.task_queue = TaskQueue()
        
        # Threading
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Callbacks
        self._on_task_complete: Optional[Callable[[str, bool], None]] = None
        self._on_worker_error: Optional[Callable[[str, Exception], None]] = None
        
        # Task stealing configuration
        self.task_stealing_enabled = self.config.worker_pool.task_stealing
        
        # Register for cleanup
        self._register_cleanup()
    
    @classmethod
    def _register_cleanup(cls) -> None:
        """Register atexit handler for cleanup"""
        if not cls._cleanup_registered:
            atexit.register(cls._cleanup_all_instances)
            cls._cleanup_registered = True
    
    @classmethod
    def _cleanup_all_instances(cls) -> None:
        """Clean up all worker pool instances on exit"""
        for instance in cls._instances:
            try:
                instance._cleanup_all_workers(force=True)
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
        """Start the worker pool"""
        self._stop_event.clear()
        
        # Register instance for cleanup
        if self not in WorkerPool._instances:
            WorkerPool._instances.append(self)
        
        # Initialize minimum workers
        for _ in range(self.min_workers):
            self._spawn_worker()
        
        # Start monitor thread
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True
        )
        self._monitor_thread.start()
    
    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Stop the worker pool
        
        Args:
            wait: Wait for running tasks to complete
            timeout: Maximum wait time in seconds
        """
        self._stop_event.set()
        
        # Graceful shutdown with timeout
        self._cleanup_all_workers(wait=wait, timeout=timeout)
        
        # Wait for monitor thread
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
        
        # Remove from instances
        if self in WorkerPool._instances:
            WorkerPool._instances.remove(self)
    
    def _cleanup_all_workers(self, wait: bool = True, timeout: float = 30.0, force: bool = False) -> None:
        """Clean up all workers
        
        Args:
            wait: Wait for processes to terminate
            timeout: Maximum wait time
            force: Force kill if graceful shutdown fails
        """
        start_time = time.time()
        
        with self._lock:
            for worker_id, worker in list(self.workers.items()):
                self._cleanup_worker_process(worker, wait and not force, timeout / 2)
                worker.state = WorkerState.STOPPED
        
        # If force and still have processes, kill them
        if force:
            remaining_time = timeout - (time.time() - start_time)
            if remaining_time > 0:
                time.sleep(min(remaining_time, 2.0))
            
            with self._lock:
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
                    except subprocess.TimeoutExpired:
                        # Force kill if terminate didn't work
                        self._kill_process_tree(worker.process)
                        
        except (OSError, subprocess.SubprocessError) as e:
            # Process may already be dead
            pass
        finally:
            # Ensure process reference is cleared
            try:
                if worker.process:
                    worker.process = None
            except Exception:
                pass
    
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
        except Exception:
            # Last resort: try simple kill
            try:
                process.kill()
            except Exception:
                pass
    
    # ==================== Worker Management ====================
    
    def _spawn_worker(self) -> Worker:
        """Spawn a new worker
        
        Returns:
            New worker instance
        """
        with self._lock:
            self._worker_counter += 1
            worker_id = f"worker-{self._worker_counter}"
            
            worker = Worker(
                id=worker_id,
                state=WorkerState.IDLE,
                last_heartbeat=datetime.now(timezone.utc).isoformat()
            )
            
            self.workers[worker_id] = worker
            return worker
    
    def _remove_worker(self, worker_id: str) -> bool:
        """Remove a worker from pool
        
        Args:
            worker_id: Worker ID
            
        Returns:
            True if removed successfully
        """
        with self._lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                if worker.state == WorkerState.BUSY:
                    return False  # Cannot remove busy worker
                
                del self.workers[worker_id]
                return True
        return False
    
    def get_worker(self, worker_id: str) -> Optional[Worker]:
        """Get worker by ID
        
        Args:
            worker_id: Worker ID
            
        Returns:
            Worker instance or None
        """
        return self.workers.get(worker_id)
    
    def get_idle_workers(self) -> list[Worker]:
        """Get list of idle workers
        
        Returns:
            List of idle workers
        """
        with self._lock:
            return [w for w in self.workers.values() if w.is_idle()]
    
    def get_busy_workers(self) -> list[Worker]:
        """Get list of busy workers
        
        Returns:
            List of busy workers
        """
        with self._lock:
            return [w for w in self.workers.values() if w.is_busy()]
    
    def get_available_workers(self) -> list[Worker]:
        """Get list of available workers
        
        Returns:
            List of available workers
        """
        with self._lock:
            return [w for w in self.workers.values() if w.is_available()]
    
    # ==================== Task Assignment ====================
    
    def assign_cell(self, task: WorkerTask) -> Optional[Worker]:
        """Assign a cell task to an idle worker
        
        Args:
            task: Task to assign
            
        Returns:
            Assigned worker or None if no idle worker
        """
        with self._lock:
            # Find idle worker
            idle_workers = self.get_idle_workers()
            if not idle_workers:
                # Try to spawn new worker if under max
                if len(self.workers) < self.max_workers:
                    worker = self._spawn_worker()
                else:
                    return None
            else:
                worker = idle_workers[0]
            
            # Assign task
            worker.current_task = task
            worker.state = WorkerState.BUSY
            worker.progress = 0
            worker.started_at = datetime.now(timezone.utc).isoformat()
            worker.update_heartbeat()
            worker.worktree_path = task.worktree_path
            
            return worker
    
    def submit_task(
        self,
        task: WorkerTask,
        wait: bool = False
    ) -> Optional[Worker]:
        """Submit a task to the pool
        
        Args:
            task: Task to submit
            wait: Wait for assignment
            
        Returns:
            Assigned worker or None
        """
        worker = self.assign_cell(task)
        
        if worker is None:
            # Queue the task
            self.task_queue.put(task)
            
            if wait:
                # Wait for available worker
                timeout = 60
                start = time.time()
                while time.time() - start < timeout:
                    worker = self.assign_cell(task)
                    if worker:
                        return worker
                    time.sleep(1)
        
        return worker
    
    def release_worker(self, worker_id: str, success: bool = True) -> None:
        """Release a worker after task completion
        
        Args:
            worker_id: Worker ID
            success: Whether task completed successfully
        """
        with self._lock:
            worker = self.workers.get(worker_id)
            if not worker:
                return
            
            # Update statistics
            if success:
                worker.completed_tasks += 1
            else:
                worker.failed_tasks += 1
            
            # Reset worker state
            worker.current_task = None
            worker.state = WorkerState.IDLE
            worker.progress = 0
            worker.worktree_path = None
            worker.update_heartbeat()
            
            # Callback
            if self._on_task_complete:
                task_id = worker.current_task.cell_id if worker.current_task else worker_id
                self._on_task_complete(task_id, success)
            
            # Try to assign pending task
            pending_task = self.task_queue.get()
            if pending_task:
                self.assign_cell(pending_task)
    
    # ==================== Heartbeat Monitoring ====================
    
    def monitor_heartbeat(self) -> list[Worker]:
        """Monitor worker heartbeats
        
        Returns:
            List of timed out workers
        """
        timed_out = []
        now = datetime.now(timezone.utc)
        timeout_seconds = self.config.pheromone.timeout
        
        with self._lock:
            for worker in self.workers.values():
                if not worker.last_heartbeat:
                    continue
                
                try:
                    hb_time = datetime.fromisoformat(
                        worker.last_heartbeat.replace('Z', '+00:00')
                    )
                    elapsed = (now - hb_time).total_seconds()
                    
                    if elapsed > timeout_seconds and worker.state == WorkerState.BUSY:
                        worker.state = WorkerState.TIMEOUT
                        timed_out.append(worker)
                        
                        # Callback
                        if self._on_worker_error:
                            error = TimeoutError(
                                f"Worker {worker.id} heartbeat timeout"
                            )
                            self._on_worker_error(worker.id, error)
                except (ValueError, TypeError):
                    continue
        
        return timed_out
    
    def _monitor_loop(self) -> None:
        """Background monitoring loop"""
        while not self._stop_event.is_set():
            try:
                self.monitor_heartbeat()
                self._cleanup_stopped_workers()
                
                # Auto task stealing if enabled
                if self.task_stealing_enabled:
                    self.task_stealing()
                    
            except Exception as e:
                print(f"Monitor error: {e}", file=sys.stderr)
            
            self._stop_event.wait(self.config.pheromone.heartbeat_interval)
    
    def _cleanup_stopped_workers(self) -> None:
        """Remove stopped workers from pool"""
        with self._lock:
            stopped = [
                w_id for w_id, w in self.workers.items()
                if w.state == WorkerState.STOPPED
            ]
            
            for w_id in stopped:
                if len(self.workers) > self.min_workers:
                    del self.workers[w_id]
    
    # ==================== Load Balancing (Task Stealing) ====================
    
    def task_stealing(self) -> int:
        """Perform task stealing for load balancing
        
        Moves tasks from overloaded workers to idle workers.
        
        Returns:
            Number of tasks reassigned
        """
        reassigned = 0
        
        with self._lock:
            idle_workers = self.get_idle_workers()
            if not idle_workers:
                return 0
            
            # Check for pending tasks
            while self.task_queue.size() > 0 and idle_workers:
                task = self.task_queue.get()
                if task:
                    worker = idle_workers.pop(0)
                    self.assign_cell(task)
                    reassigned += 1
                else:
                    break
        
        return reassigned
    
    def get_load_balance(self) -> dict[str, Any]:
        """Get load balance statistics
        
        Returns:
            Load balance statistics
        """
        with self._lock:
            idle = len(self.get_idle_workers())
            busy = len(self.get_busy_workers())
            pending = self.task_queue.size()
            
            return {
                "total_workers": len(self.workers),
                "idle_workers": idle,
                "busy_workers": busy,
                "pending_tasks": pending,
                "load_ratio": busy / len(self.workers) if self.workers else 0,
                "is_balanced": idle > 0 or pending == 0
            }
    
    # ==================== Statistics ====================
    
    def get_stats(self) -> PoolStats:
        """Get pool statistics
        
        Returns:
            Pool statistics
        """
        with self._lock:
            stats = PoolStats(
                total_workers=len(self.workers),
                idle_workers=len(self.get_idle_workers()),
                busy_workers=len(self.get_busy_workers()),
                blocked_workers=sum(1 for w in self.workers.values() 
                                   if w.state == WorkerState.BLOCKED),
                error_workers=sum(1 for w in self.workers.values() 
                                 if w.state == WorkerState.ERROR),
                pending_tasks=self.task_queue.size(),
                completed_tasks=sum(w.completed_tasks for w in self.workers.values()),
                failed_tasks=sum(w.failed_tasks for w in self.workers.values())
            )
        
        return stats
    
    def get_status(self) -> dict[str, Any]:
        """Get detailed pool status
        
        Returns:
            Status dictionary
        """
        stats = self.get_stats()
        balance = self.get_load_balance()
        
        return {
            "stats": {
                "total_workers": stats.total_workers,
                "idle_workers": stats.idle_workers,
                "busy_workers": stats.busy_workers,
                "blocked_workers": stats.blocked_workers,
                "error_workers": stats.error_workers,
                "pending_tasks": stats.pending_tasks,
                "completed_tasks": stats.completed_tasks,
                "failed_tasks": stats.failed_tasks
            },
            "load_balance": balance,
            "workers": {
                w_id: {
                    "state": w.state.value,
                    "current_task": w.current_task.cell_id if w.current_task else None,
                    "progress": w.progress,
                    "completed_tasks": w.completed_tasks,
                    "failed_tasks": w.failed_tasks,
                    "last_heartbeat": w.last_heartbeat
                }
                for w_id, w in self.workers.items()
            }
        }
    
    # ==================== Callbacks ====================
    
    def on_task_complete(self, callback: Callable[[str, bool], None]) -> None:
        """Register callback for task completion
        
        Args:
            callback: Callback function(task_id, success)
        """
        self._on_task_complete = callback
    
    def on_worker_error(self, callback: Callable[[str, Exception], None]) -> None:
        """Register callback for worker errors
        
        Args:
            callback: Callback function(worker_id, exception)
        """
        self._on_worker_error = callback
    
    # ==================== Context Manager ====================
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
    
    def __len__(self) -> int:
        return len(self.workers)
    
    def __iter__(self) -> Iterator[Worker]:
        return iter(self.workers.values())


# ==================== CLI Interface ====================

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Worker pool management tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")
    
    # status command
    subparsers.add_parser("status", help="Show pool status")
    
    # stats command
    subparsers.add_parser("stats", help="Show pool statistics")
    
    # balance command
    subparsers.add_parser("balance", help="Show load balance")
    
    args = parser.parse_args()
    
    pool = WorkerPool()
    
    if args.command == "status":
        status = pool.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    
    elif args.command == "stats":
        stats = pool.get_stats()
        print(json.dumps({
            "total_workers": stats.total_workers,
            "idle_workers": stats.idle_workers,
            "busy_workers": stats.busy_workers,
            "blocked_workers": stats.blocked_workers,
            "error_workers": stats.error_workers,
            "pending_tasks": stats.pending_tasks,
            "completed_tasks": stats.completed_tasks,
            "failed_tasks": stats.failed_tasks
        }, indent=2, ensure_ascii=False))
    
    elif args.command == "balance":
        balance = pool.get_load_balance()
        print(json.dumps(balance, indent=2, ensure_ascii=False))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
