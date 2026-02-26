#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cell DAG Module

Implements Directed Acyclic Graph execution for cell dependencies.
Supports topological sorting, cycle detection, and parallel layer identification.

Usage:
    from cell_dag import CellDAG
    
    dag = CellDAG()
    dag.add_cell("cell-a", dependencies=["cell-b"])
    layers = dag.get_parallel_layers()
    critical = dag.get_critical_path()
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from .hive_config import HiveConfig, get_config


class CellState(Enum):
    """Cell states in DAG"""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class CellNode:
    """Cell node in DAG"""
    id: str
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    state: CellState = CellState.PENDING
    priority: int = 0
    estimated_duration: int = 60  # Default: 60 seconds (was 0)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    level: int = 0  # Topological level
    
    def is_ready(self, completed_ids: set[str]) -> bool:
        """Check if all dependencies are satisfied
        
        Args:
            completed_ids: Set of completed cell IDs
            
        Returns:
            True if all dependencies are completed
        """
        return all(dep in completed_ids for dep in self.dependencies)
    
    def can_start(self, running_ids: set[str], completed_ids: set[str]) -> bool:
        """Check if cell can start
        
        Args:
            running_ids: Set of running cell IDs
            completed_ids: Set of completed cell IDs
            
        Returns:
            True if cell can start
        """
        return (
            self.state == CellState.PENDING and
            self.is_ready(completed_ids) and
            self.id not in running_ids
        )


# Default estimated duration for cells without explicit duration
DEFAULT_ESTIMATED_DURATION = 60  # seconds


@dataclass
class DAGStats:
    """DAG statistics"""
    total_cells: int = 0
    pending_cells: int = 0
    ready_cells: int = 0
    running_cells: int = 0
    completed_cells: int = 0
    failed_cells: int = 0
    blocked_cells: int = 0
    parallel_layers: int = 0
    critical_path_length: int = 0
    max_width: int = 0  # Maximum cells in any layer


class CycleDetectedError(Exception):
    """Raised when a cycle is detected in the DAG"""
    
    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        super().__init__(f"Cycle detected: {' -> '.join(cycle)}")


class CellNotFoundError(Exception):
    """Raised when cell is not found"""
    pass


class CellDAG:
    """Directed Acyclic Graph for cell dependency management
    
    Features:
    - Topological sorting
    - Cycle detection
    - Parallel layer identification
    - Critical path analysis
    - Execution state tracking
    """
    
    def __init__(
        self,
        hive_root: Optional[Path] = None,
        config: Optional[HiveConfig] = None
    ):
        """Initialize cell DAG
        
        Args:
            hive_root: Hive root directory
            config: Hive configuration
        """
        self.hive_root = hive_root or self._find_hive_root()
        self.config = config or get_config()
        
        # Graph structure
        self.nodes: dict[str, CellNode] = {}
        
        # State tracking
        self._completed_ids: set[str] = set()
        self._running_ids: set[str] = set()
        self._failed_ids: set[str] = set()
        
        # Cached computations
        self._topological_order: Optional[list[str]] = None
        self._parallel_layers: Optional[list[list[str]]] = None
        self._dirty = True
    
    def _find_hive_root(self) -> Path:
        """Find hive root directory"""
        current = Path.cwd()
        while current != current.parent:
            trellis_dir = current / ".trellis"
            if trellis_dir.exists():
                return trellis_dir
            current = current.parent
        return Path.cwd() / ".trellis"
    
    def _invalidate_cache(self) -> None:
        """Invalidate cached computations"""
        self._topological_order = None
        self._parallel_layers = None
        self._dirty = True
    
    # ==================== Graph Construction ====================
    
    def add_cell(
        self,
        cell_id: str,
        dependencies: Optional[list[str]] = None,
        priority: int = 0,
        estimated_duration: int = DEFAULT_ESTIMATED_DURATION
    ) -> CellNode:
        """Add a cell to the DAG
        
        Args:
            cell_id: Cell identifier
            dependencies: List of cell IDs this cell depends on
            priority: Cell priority (higher = more important)
            estimated_duration: Estimated execution time in seconds (default: 60s)
            
        Returns:
            Created cell node
        """
        if cell_id in self.nodes:
            raise ValueError(f"Cell already exists: {cell_id}")
        
        # Ensure estimated_duration is positive for meaningful critical path calculation
        if estimated_duration <= 0:
            estimated_duration = DEFAULT_ESTIMATED_DURATION
        
        node = CellNode(
            id=cell_id,
            dependencies=dependencies or [],
            priority=priority,
            estimated_duration=estimated_duration
        )
        
        self.nodes[cell_id] = node
        self._invalidate_cache()
        
        # Update dependents for existing dependency nodes
        for dep_id in node.dependencies:
            if dep_id in self.nodes:
                self.nodes[dep_id].dependents.append(cell_id)
        
        # Check if any existing nodes depend on this new node
        # This handles the case where dependencies were added before the node existed
        for existing_id, existing_node in self.nodes.items():
            if cell_id in existing_node.dependencies and cell_id not in self.nodes[existing_id].dependents:
                node.dependents.append(existing_id)
        
        return node
    
    def remove_cell(self, cell_id: str) -> bool:
        """Remove a cell from the DAG
        
        Args:
            cell_id: Cell identifier
            
        Returns:
            True if removed successfully
        """
        if cell_id not in self.nodes:
            return False
        
        node = self.nodes[cell_id]
        
        # Remove from dependents
        for dep_id in node.dependencies:
            if dep_id in self.nodes:
                self.nodes[dep_id].dependents.remove(cell_id)
        
        # Remove from dependencies
        for dependent_id in node.dependents:
            if dependent_id in self.nodes:
                self.nodes[dependent_id].dependencies.remove(cell_id)
        
        del self.nodes[cell_id]
        self._invalidate_cache()
        
        return True
    
    def update_dependencies(
        self,
        cell_id: str,
        dependencies: list[str]
    ) -> None:
        """Update cell dependencies
        
        Args:
            cell_id: Cell identifier
            dependencies: New dependency list
        """
        if cell_id not in self.nodes:
            raise CellNotFoundError(f"Cell not found: {cell_id}")
        
        node = self.nodes[cell_id]
        
        # Remove old dependents
        for dep_id in node.dependencies:
            if dep_id in self.nodes and cell_id in self.nodes[dep_id].dependents:
                self.nodes[dep_id].dependents.remove(cell_id)
        
        # Set new dependencies
        node.dependencies = dependencies
        
        # Add new dependents
        for dep_id in dependencies:
            if dep_id in self.nodes:
                self.nodes[dep_id].dependents.append(cell_id)
        
        self._invalidate_cache()
    
    # ==================== Graph Analysis ====================
    
    def detect_cycle(self) -> Optional[list[str]]:
        """Detect if there's a cycle in the DAG
        
        Returns:
            Cycle path if detected, None otherwise
        """
        visited = set()
        rec_stack = set()
        parent = {}
        
        def dfs(node_id: str) -> Optional[list[str]]:
            visited.add(node_id)
            rec_stack.add(node_id)
            
            node = self.nodes.get(node_id)
            if node:
                for dep_id in node.dependencies:
                    if dep_id not in visited:
                        parent[dep_id] = node_id
                        result = dfs(dep_id)
                        if result:
                            return result
                    elif dep_id in rec_stack:
                        # Found cycle, reconstruct path
                        cycle = [dep_id]
                        current = node_id
                        while current != dep_id:
                            cycle.append(current)
                            current = parent.get(current)
                            if current is None:
                                break
                        cycle.append(dep_id)
                        return list(reversed(cycle))
            
            rec_stack.remove(node_id)
            return None
        
        for node_id in self.nodes:
            if node_id not in visited:
                result = dfs(node_id)
                if result:
                    return result
        
        return None
    
    def topological_sort(self) -> list[str]:
        """Perform topological sort
        
        Returns:
            List of cell IDs in topological order
            
        Raises:
            CycleDetectedError: If cycle detected
        """
        if self._topological_order is not None:
            return self._topological_order
        
        # Check for cycle
        cycle = self.detect_cycle()
        if cycle:
            raise CycleDetectedError(cycle)
        
        # Kahn's algorithm
        in_degree = defaultdict(int)
        for node_id, node in self.nodes.items():
            in_degree[node_id]  # Initialize
            for dep_id in node.dependencies:
                in_degree[node_id] += 1
        
        # Find nodes with no dependencies
        queue = deque([
            node_id for node_id in self.nodes
            if len(self.nodes[node_id].dependencies) == 0
        ])
        
        result = []
        
        while queue:
            # Sort queue by priority for deterministic order
            queue = deque(sorted(queue, key=lambda x: -self.nodes[x].priority))
            
            node_id = queue.popleft()
            result.append(node_id)
            
            # Update in-degree for dependents
            node = self.nodes[node_id]
            for dep_id in node.dependents:
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)
        
        self._topological_order = result
        return result
    
    def get_parallel_layers(self) -> list[list[str]]:
        """Get cells grouped by parallel execution layers
        
        Returns:
            List of layers, each layer contains cells that can run in parallel
        """
        if self._parallel_layers is not None:
            return self._parallel_layers
        
        # Check for cycle
        cycle = self.detect_cycle()
        if cycle:
            raise CycleDetectedError(cycle)
        
        # Assign levels using BFS
        levels: dict[str, int] = {}
        queue = deque()
        
        # Find nodes with no dependencies (level 0)
        for node_id, node in self.nodes.items():
            if not node.dependencies:
                levels[node_id] = 0
                queue.append(node_id)
        
        # BFS to assign levels
        while queue:
            node_id = queue.popleft()
            node = self.nodes[node_id]
            
            for dep_id in node.dependents:
                current_level = levels.get(dep_id, -1)
                new_level = levels[node_id] + 1
                
                if new_level > current_level:
                    levels[dep_id] = new_level
                    queue.append(dep_id)
        
        # Group by level
        max_level = max(levels.values()) if levels else 0
        layers: list[list[str]] = [[] for _ in range(max_level + 1)]
        
        for node_id, level in levels.items():
            layers[level].append(node_id)
            self.nodes[node_id].level = level
        
        # Sort each layer by priority
        for layer in layers:
            layer.sort(key=lambda x: -self.nodes[x].priority)
        
        self._parallel_layers = layers
        return layers
    
    def get_critical_path(self) -> list[str]:
        """Get the critical path (longest path) in the DAG
        
        The critical path is the longest path through the DAG based on
        estimated execution times. If no durations are specified, uses
        DEFAULT_ESTIMATED_DURATION for all cells.
        
        Returns:
            List of cell IDs on the critical path
        """
        if not self.nodes:
            return []
        
        # Check for cycle
        cycle = self.detect_cycle()
        if cycle:
            raise CycleDetectedError(cycle)
        
        # Calculate longest path to each node
        dist: dict[str, int] = {}
        pred: dict[str, Optional[str]] = {}
        
        # Initialize
        for node_id in self.nodes:
            dist[node_id] = 0
            pred[node_id] = None
        
        # Process in topological order
        order = self.topological_sort()
        
        for node_id in order:
            node = self.nodes[node_id]
            # Use default duration if not set or invalid
            duration = node.estimated_duration
            if duration <= 0:
                duration = DEFAULT_ESTIMATED_DURATION
            
            for dep_id in node.dependencies:
                if dist[dep_id] + duration > dist[node_id]:
                    dist[node_id] = dist[dep_id] + duration
                    pred[node_id] = dep_id
        
        # Find node with maximum distance
        if not dist:
            return []
        
        end_node = max(dist.keys(), key=lambda x: dist[x])
        
        # Reconstruct path
        path = []
        current: Optional[str] = end_node
        
        while current is not None:
            path.append(current)
            current = pred[current]
        
        return list(reversed(path))
    
    # ==================== Execution State ====================
    
    def get_ready_cells(self) -> list[str]:
        """Get cells ready for execution
        
        Returns:
            List of cell IDs ready to run
        """
        ready = []
        
        for node_id, node in self.nodes.items():
            if node.can_start(self._running_ids, self._completed_ids):
                ready.append(node_id)
        
        # Sort by priority
        ready.sort(key=lambda x: -self.nodes[x].priority)
        
        return ready
    
    def mark_running(self, cell_id: str) -> bool:
        """Mark a cell as running
        
        Args:
            cell_id: Cell identifier
            
        Returns:
            True if marked successfully
        """
        if cell_id not in self.nodes:
            return False
        
        node = self.nodes[cell_id]
        if node.state != CellState.PENDING:
            return False
        
        node.state = CellState.RUNNING
        node.started_at = datetime.now(timezone.utc).isoformat()
        self._running_ids.add(cell_id)
        
        return True
    
    def mark_completed(self, cell_id: str) -> bool:
        """Mark a cell as completed
        
        Args:
            cell_id: Cell identifier
            
        Returns:
            True if marked successfully
        """
        if cell_id not in self.nodes:
            return False
        
        node = self.nodes[cell_id]
        node.state = CellState.COMPLETED
        node.completed_at = datetime.now(timezone.utc).isoformat()
        
        self._running_ids.discard(cell_id)
        self._completed_ids.add(cell_id)
        
        return True
    
    def mark_failed(self, cell_id: str) -> bool:
        """Mark a cell as failed
        
        Args:
            cell_id: Cell identifier
            
        Returns:
            True if marked successfully
        """
        if cell_id not in self.nodes:
            return False
        
        node = self.nodes[cell_id]
        node.state = CellState.FAILED
        
        self._running_ids.discard(cell_id)
        self._failed_ids.add(cell_id)
        
        # Mark dependents as blocked
        self._propagate_block(cell_id)
        
        return True
    
    def _propagate_block(self, cell_id: str) -> None:
        """Propagate blocked state to dependents
        
        Args:
            cell_id: Failed cell ID
        """
        queue = deque([cell_id])
        visited = set()
        
        while queue:
            current_id = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            
            node = self.nodes.get(current_id)
            if node:
                for dep_id in node.dependents:
                    dep_node = self.nodes.get(dep_id)
                    if dep_node and dep_node.state == CellState.PENDING:
                        dep_node.state = CellState.BLOCKED
                        queue.append(dep_id)
    
    def reset_cell(self, cell_id: str) -> bool:
        """Reset a cell to pending state
        
        Args:
            cell_id: Cell identifier
            
        Returns:
            True if reset successfully
        """
        if cell_id not in self.nodes:
            return False
        
        node = self.nodes[cell_id]
        node.state = CellState.PENDING
        node.started_at = None
        node.completed_at = None
        
        self._running_ids.discard(cell_id)
        self._completed_ids.discard(cell_id)
        self._failed_ids.discard(cell_id)
        
        return True
    
    # ==================== Statistics ====================
    
    def get_stats(self) -> DAGStats:
        """Get DAG statistics
        
        Returns:
            DAG statistics
        """
        layers = self.get_parallel_layers()
        critical_path = self.get_critical_path()
        
        states = defaultdict(int)
        for node in self.nodes.values():
            states[node.state] += 1
        
        return DAGStats(
            total_cells=len(self.nodes),
            pending_cells=states[CellState.PENDING],
            ready_cells=len(self.get_ready_cells()),
            running_cells=states[CellState.RUNNING],
            completed_cells=states[CellState.COMPLETED],
            failed_cells=states[CellState.FAILED],
            blocked_cells=states[CellState.BLOCKED],
            parallel_layers=len(layers),
            critical_path_length=len(critical_path),
            max_width=max(len(layer) for layer in layers) if layers else 0
        )
    
    def get_visualization_data(self) -> dict[str, Any]:
        """Get data for DAG visualization
        
        Returns:
            Visualization data structure
        """
        layers = self.get_parallel_layers()
        
        return {
            "nodes": [
                {
                    "id": node_id,
                    "state": self.nodes[node_id].state.value,
                    "level": self.nodes[node_id].level,
                    "priority": self.nodes[node_id].priority,
                    "dependencies": self.nodes[node_id].dependencies
                }
                for node_id in self.nodes
            ],
            "layers": layers,
            "edges": [
                {
                    "from": dep_id,
                    "to": node_id
                }
                for node_id, node in self.nodes.items()
                for dep_id in node.dependencies
            ],
            "critical_path": self.get_critical_path()
        }
    
    # ==================== Serialization ====================
    
    def to_dict(self) -> dict[str, Any]:
        """Convert DAG to dictionary
        
        Returns:
            Dictionary representation
        """
        return {
            "nodes": {
                node_id: {
                    "dependencies": node.dependencies,
                    "state": node.state.value,
                    "priority": node.priority,
                    "estimated_duration": node.estimated_duration,
                    "level": node.level,
                    "started_at": node.started_at,
                    "completed_at": node.completed_at
                }
                for node_id, node in self.nodes.items()
            },
            "completed_ids": list(self._completed_ids),
            "running_ids": list(self._running_ids),
            "failed_ids": list(self._failed_ids)
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CellDAG":
        """Create DAG from dictionary
        
        Args:
            data: Dictionary representation
            
        Returns:
            CellDAG instance
        """
        dag = cls()
        
        # Add nodes
        for node_id, node_data in data.get("nodes", {}).items():
            dag.add_cell(
                cell_id=node_id,
                dependencies=node_data.get("dependencies", []),
                priority=node_data.get("priority", 0),
                estimated_duration=node_data.get("estimated_duration", 0)
            )
            
            # Restore state
            node = dag.nodes[node_id]
            node.state = CellState(node_data.get("state", "pending"))
            node.level = node_data.get("level", 0)
            node.started_at = node_data.get("started_at")
            node.completed_at = node_data.get("completed_at")
        
        # Restore tracking sets
        dag._completed_ids = set(data.get("completed_ids", []))
        dag._running_ids = set(data.get("running_ids", []))
        dag._failed_ids = set(data.get("failed_ids", []))
        
        return dag
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save DAG to file
        
        Args:
            path: File path
        """
        if path is None:
            path = self.hive_root / "cell_dag.json"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "CellDAG":
        """Load DAG from file
        
        Args:
            path: File path
            
        Returns:
            CellDAG instance
        """
        if path is None:
            path = Path.cwd()
            while path != path.parent:
                dag_file = path / ".trellis" / "cell_dag.json"
                if dag_file.exists():
                    path = dag_file
                    break
                path = path.parent
            else:
                path = Path.cwd() / ".trellis" / "cell_dag.json"
        
        if not path.exists():
            return cls()
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls.from_dict(data)


# ==================== CLI Interface ====================

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cell DAG tool")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")
    
    # stats command
    subparsers.add_parser("stats", help="Show DAG statistics")
    
    # layers command
    subparsers.add_parser("layers", help="Show parallel layers")
    
    # critical command
    subparsers.add_parser("critical", help="Show critical path")
    
    # visualize command
    subparsers.add_parser("visualize", help="Show visualization data")
    
    # cycle command
    subparsers.add_parser("cycle", help="Check for cycles")
    
    args = parser.parse_args()
    
    # Load DAG from cells
    dag = CellDAG()
    
    # Try to load from cells directory
    cells_dir = dag.hive_root / "cells"
    if cells_dir.exists():
        for cell_dir in cells_dir.iterdir():
            if cell_dir.is_dir():
                config_file = cell_dir / "cell.json"
                if config_file.exists():
                    with open(config_file, 'r') as f:
                        cell_config = json.load(f)
                    
                    try:
                        dag.add_cell(
                            cell_id=cell_config["id"],
                            dependencies=cell_config.get("dependencies", []),
                            priority=cell_config.get("priority", 0)
                        )
                    except ValueError:
                        pass  # Already exists
    
    if args.command == "stats":
        stats = dag.get_stats()
        print(json.dumps({
            "total_cells": stats.total_cells,
            "pending_cells": stats.pending_cells,
            "ready_cells": stats.ready_cells,
            "running_cells": stats.running_cells,
            "completed_cells": stats.completed_cells,
            "failed_cells": stats.failed_cells,
            "blocked_cells": stats.blocked_cells,
            "parallel_layers": stats.parallel_layers,
            "critical_path_length": stats.critical_path_length,
            "max_width": stats.max_width
        }, indent=2, ensure_ascii=False))
    
    elif args.command == "layers":
        try:
            layers = dag.get_parallel_layers()
            for i, layer in enumerate(layers):
                print(f"Layer {i}: {layer}")
        except CycleDetectedError as e:
            print(f"Error: {e}")
    
    elif args.command == "critical":
        try:
            path = dag.get_critical_path()
            print(" -> ".join(path) if path else "No cells")
        except CycleDetectedError as e:
            print(f"Error: {e}")
    
    elif args.command == "visualize":
        print(json.dumps(dag.get_visualization_data(), indent=2, ensure_ascii=False))
    
    elif args.command == "cycle":
        cycle = dag.detect_cycle()
        if cycle:
            print(f"Cycle detected: {' -> '.join(cycle)}")
        else:
            print("No cycles detected")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
