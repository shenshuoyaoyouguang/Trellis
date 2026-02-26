#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hive Configuration Module

Centralized configuration management for hive concurrent agent mode.
Loads settings from hive-config.yaml and provides unified access.

Usage:
    from hive_config import HiveConfig

    config = HiveConfig.load()
    worker_count = config.worker_count
"""

from __future__ import annotations

import logging
import os
import re
import warnings
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional

# Configure logger
logger = logging.getLogger("hive.config")

# YAML is optional dependency
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class ConfigLoadStatus(Enum):
    """Configuration load status"""
    SUCCESS = "success"               # Loaded from file successfully
    DEFAULTS = "defaults"             # Using default values (no file)
    FALLBACK = "fallback"             # YAML missing, using defaults
    VALIDATION_ERROR = "validation"   # Validation failed


class HiveConfigError(Exception):
    """Base exception for hive config"""
    pass


class ConfigValidationError(HiveConfigError):
    """Raised when config validation fails"""
    pass


class ConfigLoadWarning(UserWarning):
    """Warning for configuration loading issues"""
    pass


@dataclass
class PheromoneConfig:
    """Pheromone communication settings"""
    file: str = ".trellis/pheromone.json"
    timeout: int = 300
    heartbeat_interval: int = 30


@dataclass
class WorkerConfig:
    """Worker settings"""
    min_count: int = 2
    max_count: int = 5
    default_count: int = 3
    timeout: int = 300
    max_retries: int = 3


@dataclass
class SwarmConfig:
    """Swarm settings"""
    drone_ratio: float = 0.4
    scout_count: int = 1


@dataclass
class DroneConfig:
    """Drone validator settings"""
    ratio: float = 0.4
    types: list[str] = field(default_factory=lambda: ["technical", "strategic", "security"])
    consensus_threshold: int = 90
    max_iterations: int = 5


@dataclass
class CellConfig:
    """Cell settings"""
    isolation: str = "strict"
    worktree_base: str = "../trellis-worktrees"
    max_file_size: int = 1024 * 1024  # 1MB
    archive_after_hours: int = 24


@dataclass
class QueenConfig:
    """Queen scheduler settings"""
    heartbeat_interval: int = 30
    max_concurrent_cells: int = 3
    timeout_minutes: int = 60
    auto_decay_monitor: bool = True


@dataclass
class WorkerPoolConfig:
    """Worker pool settings"""
    min_workers: int = 2
    max_workers: int = 5
    default_workers: int = 3
    task_stealing: bool = True
    worker_timeout: int = 300
    max_retries: int = 3


@dataclass
class DAGConfig:
    """DAG executor settings"""
    enable_cycle_detection: bool = True
    parallel_layer_limit: int = 5
    enable_critical_path: bool = True
    persist_state: bool = True


@dataclass
class HiveConfig:
    """Main hive configuration

    Attributes:
        worker_count: Number of workers to spawn
        drone_ratio: Ratio of drones to workers (0.0-1.0)
        pheromone: Pheromone settings
        worker: Worker settings
        drone: Drone settings
        cell: Cell settings
        queen: Queen scheduler settings
        worker_pool: Worker pool settings
        dag: DAG executor settings
        _load_status: Configuration load status (internal)
        _config_path: Path to loaded config file (internal)
    """
    worker_count: int = 3
    drone_ratio: float = 0.4
    pheromone: PheromoneConfig = field(default_factory=PheromoneConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    drone: DroneConfig = field(default_factory=DroneConfig)
    cell: CellConfig = field(default_factory=CellConfig)
    queen: QueenConfig = field(default_factory=QueenConfig)
    worker_pool: WorkerPoolConfig = field(default_factory=WorkerPoolConfig)
    dag: DAGConfig = field(default_factory=DAGConfig)
    _load_status: ConfigLoadStatus = field(default=ConfigLoadStatus.DEFAULTS, repr=False)
    _config_path: Optional[Path] = field(default=None, repr=False)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "HiveConfig":
        """Load configuration from file

        Args:
            config_path: Path to config file, defaults to .trellis/hive-config.yaml

        Returns:
            HiveConfig instance
        """
        if config_path is None:
            config_path = cls._find_config_path()

        # Case 1: Config file doesn't exist
        if not config_path.exists():
            logger.debug(f"Config file not found: {config_path}, using defaults")
            config = cls()
            config._load_status = ConfigLoadStatus.DEFAULTS
            config._config_path = config_path
            return config

        # Case 2: YAML not available
        if not HAS_YAML:
            # Use warnings.warn for programmatic handling
            warnings.warn(
                "PyYAML not installed, using default configuration. "
                "Install with: pip install pyyaml",
                ConfigLoadWarning,
                stacklevel=2
            )
            # Also log for visibility
            logger.warning(
                "PyYAML not installed, cannot load configuration from %s. "
                "Using default values. Install PyYAML with: pip install pyyaml",
                config_path
            )
            config = cls()
            config._load_status = ConfigLoadStatus.FALLBACK
            config._config_path = config_path
            return config

        # Case 3: Load from YAML file
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            config = cls._from_dict(data)
            config._load_status = ConfigLoadStatus.SUCCESS
            config._config_path = config_path
            
            logger.info("Loaded configuration from %s", config_path)
            return config
            
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML configuration: %s", e)
            warnings.warn(
                f"Failed to parse configuration file: {e}. Using defaults.",
                ConfigLoadWarning,
                stacklevel=2
            )
            config = cls()
            config._load_status = ConfigLoadStatus.VALIDATION_ERROR
            config._config_path = config_path
            return config

    @property
    def load_status(self) -> ConfigLoadStatus:
        """Get configuration load status
        
        Returns:
            Current load status
        """
        return self._load_status

    @property
    def config_path(self) -> Optional[Path]:
        """Get configuration file path
        
        Returns:
            Path to config file or None if using defaults
        """
        return self._config_path

    def is_using_defaults(self) -> bool:
        """Check if using default configuration
        
        Returns:
            True if using defaults (no file loaded)
        """
        return self._load_status in (
            ConfigLoadStatus.DEFAULTS,
            ConfigLoadStatus.FALLBACK
        )

    def get_load_summary(self) -> dict[str, Any]:
        """Get summary of configuration loading
        
        Returns:
            Dictionary with load status information
        """
        return {
            "status": self._load_status.value,
            "config_path": str(self._config_path) if self._config_path else None,
            "yaml_available": HAS_YAML,
            "using_defaults": self.is_using_defaults(),
            "worker_count": self.worker_count,
            "drone_ratio": self.drone_ratio
        }

    @classmethod
    def _find_config_path(cls) -> Path:
        """Find config file path"""
        current = Path.cwd()
        while current != current.parent:
            config_file = current / ".trellis" / "hive-config.yaml"
            if config_file.exists():
                return config_file
            current = current.parent
        return Path.cwd() / ".trellis" / "hive-config.yaml"

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "HiveConfig":
        """Create config from dictionary

        Args:
            data: Configuration dictionary

        Returns:
            HiveConfig instance
        """
        # Extract nested configs
        swarm_data = data.get("swarm", {})
        pheromone_data = data.get("pheromone", {})
        worker_data = data.get("worker", {})
        drone_data = data.get("drone", {})
        cell_data = data.get("cell", {})
        worktree_data = data.get("worktree", {})

        # Handle swarm.worker_count structure
        swarm_worker_count = swarm_data.get("worker_count", {})

        pheromone = PheromoneConfig(
            file=pheromone_data.get("file", ".trellis/pheromone.json"),
            timeout=pheromone_data.get("timeout", 300),
            heartbeat_interval=pheromone_data.get("heartbeat_interval", 30)
        )

        worker = WorkerConfig(
            min_count=swarm_worker_count.get("min", worker_data.get("min_count", 2)),
            max_count=swarm_worker_count.get("max", worker_data.get("max_count", 5)),
            default_count=swarm_worker_count.get("default", worker_data.get("default_count", 3)),
            timeout=worker_data.get("timeout", 300),
            max_retries=worker_data.get("max_retries", 3)
        )

        # Get drone ratio from swarm.drone_ratio first, then fallback
        drone_ratio_from_swarm = swarm_data.get("drone_ratio", 0.4)

        drone = DroneConfig(
            ratio=drone_ratio_from_swarm,
            types=drone_data.get("types", ["technical", "strategic", "security"]),
            consensus_threshold=drone_data.get("consensus_threshold", 90),
            max_iterations=drone_data.get("max_iterations", 5)
        )

        # Get worktree base from worktree.dir if available
        worktree_base = worktree_data.get("dir", cell_data.get("worktree_base", "../trellis-worktrees"))

        cell = CellConfig(
            isolation=cell_data.get("isolation", "strict"),
            worktree_base=worktree_base,
            max_file_size=cell_data.get("max_file_size", 1024 * 1024),
            archive_after_hours=cell_data.get("archive_after_hours", 24)
        )
        
        # Parse queen config
        queen_data = data.get("queen", {})
        queen = QueenConfig(
            heartbeat_interval=queen_data.get("heartbeat_interval", 30),
            max_concurrent_cells=queen_data.get("max_concurrent_cells", 3),
            timeout_minutes=queen_data.get("timeout_minutes", 60),
            auto_decay_monitor=queen_data.get("auto_decay_monitor", True)
        )
        
        # Parse worker_pool config
        worker_pool_data = data.get("worker_pool", {})
        worker_pool = WorkerPoolConfig(
            min_workers=worker_pool_data.get("min_workers", 2),
            max_workers=worker_pool_data.get("max_workers", 5),
            default_workers=worker_pool_data.get("default_workers", 3),
            task_stealing=worker_pool_data.get("task_stealing", True),
            worker_timeout=worker_pool_data.get("worker_timeout", 300),
            max_retries=worker_pool_data.get("max_retries", 3)
        )
        
        # Parse DAG config
        dag_data = data.get("dag", {})
        dag = DAGConfig(
            enable_cycle_detection=dag_data.get("enable_cycle_detection", True),
            parallel_layer_limit=dag_data.get("parallel_layer_limit", 5),
            enable_critical_path=dag_data.get("enable_critical_path", True),
            persist_state=dag_data.get("persist_state", True)
        )

        config = cls(
            worker_count=data.get("worker_count", worker.default_count),
            drone_ratio=drone_ratio_from_swarm,
            pheromone=pheromone,
            worker=worker,
            drone=drone,
            cell=cell,
            queen=queen,
            worker_pool=worker_pool,
            dag=dag
        )

        config.validate()
        return config

    def validate(self) -> None:
        """Validate configuration

        Raises:
            ConfigValidationError: If validation fails
        """
        # Validate worker count
        if not self.worker.min_count <= self.worker_count <= self.worker.max_count:
            raise ConfigValidationError(
                f"worker_count must be between {self.worker.min_count} and "
                f"{self.worker.max_count}, got {self.worker_count}"
            )

        # Validate drone ratio
        if not 0.0 <= self.drone_ratio <= 1.0:
            raise ConfigValidationError(
                f"drone_ratio must be between 0.0 and 1.0, got {self.drone_ratio}"
            )

        # Validate consensus threshold
        if not 0 <= self.drone.consensus_threshold <= 100:
            raise ConfigValidationError(
                f"consensus_threshold must be between 0 and 100, "
                f"got {self.drone.consensus_threshold}"
            )

        # Validate isolation level
        if self.cell.isolation not in ("strict", "relaxed"):
            raise ConfigValidationError(
                f"cell.isolation must be 'strict' or 'relaxed', "
                f"got {self.cell.isolation}"
            )

    def get_drone_count(self) -> int:
        """Calculate number of drones based on worker count and ratio

        Returns:
            Number of drones
        """
        return max(1, int(self.worker_count * self.drone_ratio))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary

        Returns:
            Configuration dictionary
        """
        return {
            "worker_count": self.worker_count,
            "drone_ratio": self.drone_ratio,
            "pheromone": {
                "file": self.pheromone.file,
                "timeout": self.pheromone.timeout,
                "heartbeat_interval": self.pheromone.heartbeat_interval
            },
            "worker": {
                "min_count": self.worker.min_count,
                "max_count": self.worker.max_count,
                "default_count": self.worker.default_count,
                "timeout": self.worker.timeout,
                "max_retries": self.worker.max_retries
            },
            "drone": {
                "ratio": self.drone.ratio,
                "types": self.drone.types,
                "consensus_threshold": self.drone.consensus_threshold,
                "max_iterations": self.drone.max_iterations
            },
            "cell": {
                "isolation": self.cell.isolation,
                "worktree_base": self.cell.worktree_base,
                "max_file_size": self.cell.max_file_size,
                "archive_after_hours": self.cell.archive_after_hours
            },
            "queen": {
                "heartbeat_interval": self.queen.heartbeat_interval,
                "max_concurrent_cells": self.queen.max_concurrent_cells,
                "timeout_minutes": self.queen.timeout_minutes,
                "auto_decay_monitor": self.queen.auto_decay_monitor
            },
            "worker_pool": {
                "min_workers": self.worker_pool.min_workers,
                "max_workers": self.worker_pool.max_workers,
                "default_workers": self.worker_pool.default_workers,
                "task_stealing": self.worker_pool.task_stealing,
                "worker_timeout": self.worker_pool.worker_timeout,
                "max_retries": self.worker_pool.max_retries
            },
            "dag": {
                "enable_cycle_detection": self.dag.enable_cycle_detection,
                "parallel_layer_limit": self.dag.parallel_layer_limit,
                "enable_critical_path": self.dag.enable_critical_path,
                "persist_state": self.dag.persist_state
            }
        }

    def save(self, config_path: Optional[Path] = None) -> None:
        """Save configuration to file

        Args:
            config_path: Path to save config
        """
        if config_path is None:
            config_path = self._find_config_path()

        if not HAS_YAML:
            raise HiveConfigError("PyYAML required to save config")

        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)


# Global config instance (lazy loaded)
_config: Optional[HiveConfig] = None


def get_config(reload: bool = False) -> HiveConfig:
    """Get global config instance

    Args:
        reload: Force reload from file

    Returns:
        HiveConfig instance
    """
    global _config

    if _config is None or reload:
        _config = HiveConfig.load()

    return _config


def reset_config() -> None:
    """Reset global config instance"""
    global _config
    _config = None


# ==================== CLI Interface ====================

def main():
    """CLI entry point"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Hive configuration tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # show command
    subparsers.add_parser("show", help="Show current config")

    # validate command
    subparsers.add_parser("validate", help="Validate config")

    args = parser.parse_args()

    if args.command == "show":
        config = get_config()
        print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))

    elif args.command == "validate":
        try:
            config = get_config()
            config.validate()
            print("Configuration is valid")
        except ConfigValidationError as e:
            print(f"Configuration error: {e}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
