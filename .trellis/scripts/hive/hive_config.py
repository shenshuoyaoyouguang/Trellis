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

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional

# YAML is optional dependency
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class HiveConfigError(Exception):
    """Base exception for hive config"""
    pass


class ConfigValidationError(HiveConfigError):
    """Raised when config validation fails"""
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
class HiveConfig:
    """Main hive configuration
    
    Attributes:
        worker_count: Number of workers to spawn
        drone_ratio: Ratio of drones to workers (0.0-1.0)
        pheromone: Pheromone settings
        worker: Worker settings
        drone: Drone settings
        cell: Cell settings
    """
    worker_count: int = 3
    drone_ratio: float = 0.4
    pheromone: PheromoneConfig = field(default_factory=PheromoneConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    drone: DroneConfig = field(default_factory=DroneConfig)
    cell: CellConfig = field(default_factory=CellConfig)
    
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
        
        if not config_path.exists():
            return cls()  # Return defaults
        
        if not HAS_YAML:
            print("Warning: PyYAML not installed, using default config")
            return cls()
        
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        return cls._from_dict(data)
    
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
        pheromone_data = data.get("pheromone", {})
        worker_data = data.get("worker", {})
        drone_data = data.get("drone", {})
        cell_data = data.get("cell", {})
        
        pheromone = PheromoneConfig(
            file=pheromone_data.get("file", ".trellis/pheromone.json"),
            timeout=pheromone_data.get("timeout", 300),
            heartbeat_interval=pheromone_data.get("heartbeat_interval", 30)
        )
        
        worker = WorkerConfig(
            min_count=worker_data.get("min_count", 2),
            max_count=worker_data.get("max_count", 5),
            default_count=worker_data.get("default_count", 3),
            timeout=worker_data.get("timeout", 300),
            max_retries=worker_data.get("max_retries", 3)
        )
        
        drone = DroneConfig(
            ratio=drone_data.get("ratio", 0.4),
            types=drone_data.get("types", ["technical", "strategic", "security"]),
            consensus_threshold=drone_data.get("consensus_threshold", 90),
            max_iterations=drone_data.get("max_iterations", 5)
        )
        
        cell = CellConfig(
            isolation=cell_data.get("isolation", "strict"),
            worktree_base=cell_data.get("worktree_base", "../trellis-worktrees"),
            max_file_size=cell_data.get("max_file_size", 1024 * 1024),
            archive_after_hours=cell_data.get("archive_after_hours", 24)
        )
        
        config = cls(
            worker_count=data.get("worker_count", worker.default_count),
            drone_ratio=drone.ratio,
            pheromone=pheromone,
            worker=worker,
            drone=drone,
            cell=cell
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
