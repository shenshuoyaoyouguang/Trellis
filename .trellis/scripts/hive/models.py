#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hive Models Module

Unified data models for hive concurrent agent mode.
This module provides shared dataclasses and enums to ensure consistency
across all hive components.

Usage:
    from hive.models import Worker, WorkerState, WorkerTask, TaskPriority
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HiveError(Exception):
    """Base exception for all hive-related errors.
    
    All hive-specific exceptions should inherit from this class
    to enable unified error handling across modules.
    """
    pass


class WorkerState(Enum):
    """Worker lifecycle states.
    
    State transitions:
    IDLE -> BUSY (assigned task)
    BUSY -> IDLE (task completed)
    BUSY -> ERROR (task failed)
    BUSY -> TIMEOUT (heartbeat lost)
    BUSY -> BLOCKED (dependency blocked)
    * -> STOPPED (manual stop)
    """
    IDLE = "idle"
    BUSY = "busy"
    BLOCKED = "blocked"
    ERROR = "error"
    TIMEOUT = "timeout"
    STOPPED = "stopped"


class TaskPriority(Enum):
    """Task priority levels for scheduling.
    
    Higher priority tasks are scheduled first when multiple
    tasks are ready for execution.
    """
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class WorkerTask:
    """Task definition for worker execution.
    
    Represents a unit of work to be executed by a worker bee.
    Each task is associated with a cell and contains execution
    parameters and metadata.
    
    Attributes:
        cell_id: Unique identifier for the cell this task belongs to
        description: Human-readable task description
        priority: Task priority for scheduling
        worktree_path: Path to the isolated worktree for this task
        platform: Agent platform (e.g., 'claude', 'cursor')
        timeout: Maximum execution time in seconds
        inputs: List of input file paths or data references
        outputs: List of expected output file paths
        created_at: ISO timestamp of task creation
    """
    cell_id: str
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    worktree_path: Optional[str] = None
    platform: str = "claude"
    timeout: int = 300
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Worker:
    """Worker representation in the hive.
    
    A worker (工蜂) is an execution unit that processes tasks.
    Workers maintain their own state, track progress, and
    communicate via the pheromone system.
    
    Attributes:
        id: Unique worker identifier
        state: Current lifecycle state
        cell_id: ID of cell being processed (for backward compatibility)
        current_task: Currently assigned task, if any
        progress: Task progress percentage (0-100)
        started_at: ISO timestamp when worker started
        last_heartbeat: ISO timestamp of last heartbeat
        completed_tasks: Number of successfully completed tasks
        failed_tasks: Number of failed tasks
        process: Subprocess handle for the worker process
        worktree_path: Path to the worker's isolated worktree
    """
    id: str
    state: WorkerState = WorkerState.IDLE
    cell_id: Optional[str] = None
    current_task: Optional[WorkerTask] = None
    progress: int = 0
    started_at: Optional[str] = None
    last_heartbeat: Optional[str] = None
    completed_tasks: int = 0
    failed_tasks: int = 0
    process: Optional[subprocess.Popen] = None
    worktree_path: Optional[str] = None
    
    def update_heartbeat(self) -> None:
        """Update heartbeat timestamp to current time."""
        self.last_heartbeat = datetime.now(timezone.utc).isoformat()
    
    def is_idle(self) -> bool:
        """Check if worker is idle and available for new tasks."""
        return self.state == WorkerState.IDLE
    
    def is_busy(self) -> bool:
        """Check if worker is currently executing a task."""
        return self.state == WorkerState.BUSY
    
    def is_available(self) -> bool:
        """Check if worker is available for new task assignment.
        
        Workers in IDLE, ERROR, or TIMEOUT states can accept new tasks.
        """
        return self.state in (WorkerState.IDLE, WorkerState.ERROR, WorkerState.TIMEOUT)
    
    def assign_task(self, task: WorkerTask) -> None:
        """Assign a new task to this worker.
        
        Args:
            task: The task to assign
            
        Raises:
            HiveError: If worker is not available for new tasks
        """
        if not self.is_available():
            raise HiveError(f"Worker {self.id} is not available (state: {self.state.value})")
        
        self.current_task = task
        self.cell_id = task.cell_id
        self.state = WorkerState.BUSY
        self.progress = 0
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.update_heartbeat()
    
    def complete_task(self, success: bool = True) -> None:
        """Mark current task as completed.
        
        Args:
            success: Whether the task completed successfully
        """
        if success:
            self.completed_tasks += 1
            self.state = WorkerState.IDLE
        else:
            self.failed_tasks += 1
            self.state = WorkerState.ERROR
        
        self.current_task = None
        self.cell_id = None
        self.progress = 0
    
    def to_dict(self) -> dict:
        """Convert worker to dictionary representation.
        
        Note: process handle is excluded as it's not serializable.
        """
        return {
            "id": self.id,
            "state": self.state.value,
            "cell_id": self.cell_id,
            "current_task": self.current_task.__dict__ if self.current_task else None,
            "progress": self.progress,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "worktree_path": self.worktree_path,
        }


# Re-export for convenience
__all__ = [
    "HiveError",
    "WorkerState",
    "TaskPriority", 
    "WorkerTask",
    "Worker",
]
