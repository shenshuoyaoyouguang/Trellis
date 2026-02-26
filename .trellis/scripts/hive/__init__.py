#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hive Concurrent Agent Mode - Core Modules

This package provides the core functionality for hive concurrent agent mode:
- pheromone: Inter-agent communication via pheromone traces
- cell_manager: Cell lifecycle management
- drone_validator: Multi-dimensional cross-validation
- hive_config: Configuration management

Usage:
    from hive import PheromoneManager, CellManager, DroneValidator, HiveConfig
    
    # Initialize
    config = HiveConfig.load()
    pm = PheromoneManager()
    cm = CellManager()
    dv = DroneValidator()

Cross-directory execution:
    This module can be executed from any directory. The __init__.py automatically
    sets up the correct sys.path for imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure hive directory is in sys.path for relative imports
# This allows the module to work when executed from any directory
_hive_dir = Path(__file__).parent.resolve()
_scripts_dir = _hive_dir.parent.resolve()

# Add directories to sys.path if not already present
for _p in [str(_hive_dir), str(_scripts_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Lazy imports to avoid circular dependencies
__all__ = [
    # Models
    "WorkerState",
    "Worker",
    "WorkerTask",
    "TaskPriority",
    "HiveError",
    # Core modules
    "PheromoneManager",
    "CellManager", 
    "DroneValidator",
    "HiveConfig",
    "QueenScheduler",
    "WorkerPool",
    "CellDAG",
    # Helper functions
    "get_config",
    "reset_config",
    "get_pheromone_manager",
]


def __getattr__(name: str):
    """Lazy import for modules"""
    # Models
    if name == "WorkerState":
        from .models import WorkerState
        return WorkerState
    elif name == "Worker":
        from .models import Worker
        return Worker
    elif name == "WorkerTask":
        from .models import WorkerTask
        return WorkerTask
    elif name == "TaskPriority":
        from .models import TaskPriority
        return TaskPriority
    elif name == "HiveError":
        from .models import HiveError
        return HiveError
    # Core modules
    elif name == "PheromoneManager":
        from .pheromone import PheromoneManager
        return PheromoneManager
    elif name == "get_pheromone_manager":
        from .pheromone import get_pheromone_manager
        return get_pheromone_manager
    elif name == "CellManager":
        from .cell_manager import CellManager
        return CellManager
    elif name == "DroneValidator":
        from .drone_validator import DroneValidator
        return DroneValidator
    elif name == "HiveConfig":
        from .hive_config import HiveConfig
        return HiveConfig
    elif name == "QueenScheduler":
        from .queen_scheduler import QueenScheduler
        return QueenScheduler
    elif name == "WorkerPool":
        from .worker_pool import WorkerPool
        return WorkerPool
    elif name == "CellDAG":
        from .cell_dag import CellDAG
        return CellDAG
    elif name == "get_config":
        from .hive_config import get_config
        return get_config
    elif name == "reset_config":
        from .hive_config import reset_config
        return reset_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")