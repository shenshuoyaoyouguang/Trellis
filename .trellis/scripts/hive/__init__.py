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
"""

from __future__ import annotations

# Lazy imports to avoid circular dependencies
__all__ = [
    "PheromoneManager",
    "CellManager", 
    "DroneValidator",
    "HiveConfig",
    "get_config",
    "reset_config",
]


def __getattr__(name: str):
    """Lazy import for modules"""
    if name == "PheromoneManager":
        from .pheromone import PheromoneManager
        return PheromoneManager
    elif name == "CellManager":
        from .cell_manager import CellManager
        return CellManager
    elif name == "DroneValidator":
        from .drone_validator import DroneValidator
        return DroneValidator
    elif name == "HiveConfig":
        from .hive_config import HiveConfig
        return HiveConfig
    elif name == "get_config":
        from .hive_config import get_config
        return get_config
    elif name == "reset_config":
        from .hive_config import reset_config
        return reset_config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")