#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Hive System modules

Tests for:
- QueenScheduler
- WorkerPool
- CellDAG
- EnhancedPheromoneManager
"""

import json
import os
import sys
import tempfile
import threading
import time
import importlib.util
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import Mock, patch, MagicMock

# Resolve paths
_project_root = Path(__file__).parent.parent.parent
_scripts_path = _project_root / ".trellis" / "scripts"
_hive_path = _scripts_path / "hive"

# Add scripts directory to path
if str(_scripts_path) not in sys.path:
    sys.path.insert(0, str(_scripts_path))


def _load_module_from_path(module_name: str, file_path: Path):
    """Load a module directly from file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Load hive modules
_hive_init = _hive_path / "__init__.py"
if _hive_init.exists():
    _load_module_from_path("hive", _hive_init)

_load_module_from_path("hive.models", _hive_path / "models.py")
_load_module_from_path("hive.cell_dag", _hive_path / "cell_dag.py")
_load_module_from_path("hive.worker_pool", _hive_path / "worker_pool.py")
_load_module_from_path("hive.pheromone", _hive_path / "pheromone.py")

# Now import from loaded modules
from hive.models import Worker, WorkerState, WorkerTask, TaskPriority, HiveError
from hive.cell_dag import CellDAG, CellNode, CellState, CycleDetectedError
from hive.worker_pool import WorkerPool
from hive.pheromone import (
    PheromoneManager, EnhancedPheromoneManager, PheromoneType, 
    PheromoneEntry, PheromoneSubscriber
)


class TestModels(TestCase):
    """Tests for unified models module"""
    
    def test_worker_state_enum_values(self):
        """Test WorkerState enum has all required values"""
        self.assertEqual(WorkerState.IDLE.value, "idle")
        self.assertEqual(WorkerState.BUSY.value, "busy")
        self.assertEqual(WorkerState.BLOCKED.value, "blocked")
        self.assertEqual(WorkerState.ERROR.value, "error")
        self.assertEqual(WorkerState.TIMEOUT.value, "timeout")
        self.assertEqual(WorkerState.STOPPED.value, "stopped")
    
    def test_task_priority_enum_values(self):
        """Test TaskPriority enum ordering"""
        self.assertEqual(TaskPriority.HIGH.value, 1)
        self.assertEqual(TaskPriority.MEDIUM.value, 2)
        self.assertEqual(TaskPriority.LOW.value, 3)
        self.assertTrue(TaskPriority.HIGH.value < TaskPriority.MEDIUM.value)
    
    def test_worker_task_creation(self):
        """Test WorkerTask dataclass creation"""
        task = WorkerTask(
            cell_id="cell-1",
            description="Test task",
            priority=TaskPriority.HIGH
        )
        
        self.assertEqual(task.cell_id, "cell-1")
        self.assertEqual(task.description, "Test task")
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(task.timeout, 300)  # default
    
    def test_worker_creation(self):
        """Test Worker dataclass creation"""
        worker = Worker(id="worker-1")
        
        self.assertEqual(worker.id, "worker-1")
        self.assertEqual(worker.state, WorkerState.IDLE)
        self.assertIsNone(worker.current_task)
        self.assertEqual(worker.completed_tasks, 0)
        self.assertEqual(worker.failed_tasks, 0)
    
    def test_worker_state_checks(self):
        """Test Worker state check methods"""
        worker = Worker(id="worker-1")
        
        self.assertTrue(worker.is_idle())
        self.assertFalse(worker.is_busy())
        self.assertTrue(worker.is_available())
        
        worker.state = WorkerState.BUSY
        self.assertFalse(worker.is_idle())
        self.assertTrue(worker.is_busy())
        self.assertFalse(worker.is_available())
    
    def test_worker_assign_task(self):
        """Test Worker task assignment"""
        worker = Worker(id="worker-1")
        task = WorkerTask(cell_id="cell-1")
        
        worker.assign_task(task)
        
        self.assertEqual(worker.state, WorkerState.BUSY)
        self.assertEqual(worker.current_task, task)
        self.assertEqual(worker.cell_id, "cell-1")
        self.assertIsNotNone(worker.started_at)
    
    def test_worker_assign_task_not_available(self):
        """Test Worker task assignment fails when not available"""
        worker = Worker(id="worker-1", state=WorkerState.BUSY)
        task = WorkerTask(cell_id="cell-1")
        
        with self.assertRaises(HiveError):
            worker.assign_task(task)
    
    def test_worker_complete_task_success(self):
        """Test Worker completing task successfully"""
        worker = Worker(id="worker-1")
        task = WorkerTask(cell_id="cell-1")
        worker.assign_task(task)
        
        worker.complete_task(success=True)
        
        self.assertEqual(worker.state, WorkerState.IDLE)
        self.assertEqual(worker.completed_tasks, 1)
        self.assertIsNone(worker.current_task)
    
    def test_worker_complete_task_failure(self):
        """Test Worker completing task with failure"""
        worker = Worker(id="worker-1")
        task = WorkerTask(cell_id="cell-1")
        worker.assign_task(task)
        
        worker.complete_task(success=False)
        
        self.assertEqual(worker.state, WorkerState.ERROR)
        self.assertEqual(worker.failed_tasks, 1)
    
    def test_worker_update_heartbeat(self):
        """Test Worker heartbeat update"""
        worker = Worker(id="worker-1")
        
        self.assertIsNone(worker.last_heartbeat)
        
        worker.update_heartbeat()
        
        self.assertIsNotNone(worker.last_heartbeat)
    
    def test_worker_to_dict(self):
        """Test Worker serialization"""
        worker = Worker(id="worker-1", state=WorkerState.BUSY)
        
        data = worker.to_dict()
        
        self.assertEqual(data["id"], "worker-1")
        self.assertEqual(data["state"], "busy")
        self.assertIn("completed_tasks", data)
        self.assertNotIn("process", data)  # process should be excluded
    
    def test_hive_error_base_class(self):
        """Test HiveError can be raised and caught"""
        with self.assertRaises(HiveError):
            raise HiveError("Test error")


class TestCellDAG(TestCase):
    """Tests for CellDAG"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.dag = CellDAG()
    
    def test_add_cell(self):
        """Test adding a cell to the DAG"""
        node = self.dag.add_cell("cell-1")
        
        self.assertEqual(node.id, "cell-1")
        self.assertIn("cell-1", self.dag.nodes)
        self.assertEqual(node.state, CellState.PENDING)
    
    def test_add_cell_with_dependencies(self):
        """Test adding a cell with dependencies"""
        self.dag.add_cell("cell-a")
        self.dag.add_cell("cell-b")
        node = self.dag.add_cell("cell-c", dependencies=["cell-a", "cell-b"])
        
        self.assertEqual(len(node.dependencies), 2)
        self.assertIn("cell-c", self.dag.nodes["cell-a"].dependents)
        self.assertIn("cell-c", self.dag.nodes["cell-b"].dependents)
    
    def test_detect_no_cycle(self):
        """Test cycle detection with no cycle"""
        self.dag.add_cell("cell-a")
        self.dag.add_cell("cell-b", dependencies=["cell-a"])
        self.dag.add_cell("cell-c", dependencies=["cell-b"])
        
        cycle = self.dag.detect_cycle()
        self.assertIsNone(cycle)
    
    def test_detect_cycle(self):
        """Test cycle detection with a cycle"""
        self.dag.add_cell("cell-a", dependencies=["cell-c"])
        self.dag.add_cell("cell-b", dependencies=["cell-a"])
        self.dag.add_cell("cell-c", dependencies=["cell-b"])
        
        cycle = self.dag.detect_cycle()
        self.assertIsNotNone(cycle)
        self.assertIn("cell-a", cycle)
        self.assertIn("cell-b", cycle)
        self.assertIn("cell-c", cycle)
    
    def test_topological_sort(self):
        """Test topological sort"""
        self.dag.add_cell("cell-c", dependencies=["cell-a", "cell-b"])
        self.dag.add_cell("cell-a")
        self.dag.add_cell("cell-b", dependencies=["cell-a"])
        
        order = self.dag.topological_sort()
        
        # cell-a must come before cell-b and cell-c
        # cell-b must come before cell-c
        self.assertLess(order.index("cell-a"), order.index("cell-b"))
        self.assertLess(order.index("cell-a"), order.index("cell-c"))
        self.assertLess(order.index("cell-b"), order.index("cell-c"))
    
    def test_topological_sort_with_cycle_raises(self):
        """Test that topological sort raises on cycle"""
        self.dag.add_cell("cell-a", dependencies=["cell-b"])
        self.dag.add_cell("cell-b", dependencies=["cell-a"])
        
        with self.assertRaises(CycleDetectedError):
            self.dag.topological_sort()
    
    def test_get_parallel_layers(self):
        """Test parallel layer identification"""
        self.dag.add_cell("cell-a")
        self.dag.add_cell("cell-b")
        self.dag.add_cell("cell-c", dependencies=["cell-a", "cell-b"])
        
        layers = self.dag.get_parallel_layers()
        
        self.assertEqual(len(layers), 2)
        self.assertIn("cell-a", layers[0])
        self.assertIn("cell-b", layers[0])
        self.assertIn("cell-c", layers[1])
    
    def test_get_critical_path(self):
        """Test critical path calculation"""
        self.dag.add_cell("cell-a", estimated_duration=10)
        self.dag.add_cell("cell-b", dependencies=["cell-a"], estimated_duration=20)
        self.dag.add_cell("cell-c", dependencies=["cell-a"], estimated_duration=5)
        self.dag.add_cell("cell-d", dependencies=["cell-b"], estimated_duration=15)
        
        path = self.dag.get_critical_path()
        
        # Critical path should be: cell-a -> cell-b -> cell-d (longest)
        self.assertEqual(path[0], "cell-a")
        self.assertIn("cell-b", path)
        self.assertIn("cell-d", path)
    
    def test_get_ready_cells(self):
        """Test getting ready cells"""
        self.dag.add_cell("cell-a")
        self.dag.add_cell("cell-b")
        self.dag.add_cell("cell-c", dependencies=["cell-a"])
        
        ready = self.dag.get_ready_cells()
        
        self.assertIn("cell-a", ready)
        self.assertIn("cell-b", ready)
        self.assertNotIn("cell-c", ready)
        
        # Mark cell-a as completed
        self.dag.mark_running("cell-a")
        self.dag.mark_completed("cell-a")
        
        ready = self.dag.get_ready_cells()
        self.assertIn("cell-c", ready)
    
    def test_mark_completed(self):
        """Test marking cell as completed"""
        self.dag.add_cell("cell-1")
        
        self.dag.mark_running("cell-1")
        self.assertTrue(self.dag.mark_completed("cell-1"))
        
        self.assertEqual(self.dag.nodes["cell-1"].state, CellState.COMPLETED)
        self.assertIn("cell-1", self.dag._completed_ids)
    
    def test_mark_failed_propagates_block(self):
        """Test that failed cell blocks dependents"""
        self.dag.add_cell("cell-a")
        self.dag.add_cell("cell-b", dependencies=["cell-a"])
        self.dag.add_cell("cell-c", dependencies=["cell-b"])
        
        self.dag.mark_running("cell-a")
        self.dag.mark_failed("cell-a")
        
        # cell-b and cell-c should be blocked
        self.assertEqual(self.dag.nodes["cell-a"].state, CellState.FAILED)
        self.assertEqual(self.dag.nodes["cell-b"].state, CellState.BLOCKED)
        self.assertEqual(self.dag.nodes["cell-c"].state, CellState.BLOCKED)
    
    def test_serialization(self):
        """Test DAG serialization"""
        self.dag.add_cell("cell-a", priority=10)
        self.dag.add_cell("cell-b", dependencies=["cell-a"])
        self.dag.mark_running("cell-a")
        self.dag.mark_completed("cell-a")
        
        data = self.dag.to_dict()
        loaded = CellDAG.from_dict(data)
        
        self.assertEqual(len(loaded.nodes), 2)
        self.assertIn("cell-a", loaded._completed_ids)
        self.assertEqual(loaded.nodes["cell-b"].dependencies, ["cell-a"])


class TestWorkerPool(TestCase):
    """Tests for WorkerPool"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.pool = WorkerPool(max_workers=3, min_workers=1)
    
    def tearDown(self):
        """Clean up after tests"""
        self.pool.stop()
    
    def test_initialization(self):
        """Test pool initialization"""
        self.assertEqual(self.pool.max_workers, 3)
        self.assertEqual(self.pool.min_workers, 1)
    
    def test_start_creates_workers(self):
        """Test that start creates minimum workers"""
        self.pool.start()
        
        self.assertGreaterEqual(len(self.pool.workers), self.pool.min_workers)
    
    def test_get_idle_workers(self):
        """Test getting idle workers"""
        self.pool.start()
        
        idle = self.pool.get_idle_workers()
        self.assertEqual(len(idle), len(self.pool.workers))
    
    def test_assign_cell(self):
        """Test assigning a cell to worker"""
        self.pool.start()
        
        task = WorkerTask(
            cell_id="cell-1",
            description="Test task"
        )
        
        worker = self.pool.assign_cell(task)
        
        self.assertIsNotNone(worker)
        self.assertEqual(worker.state, WorkerState.BUSY)
        self.assertEqual(worker.current_task, task)
    
    def test_assign_cell_when_no_idle(self):
        """Test assignment when no idle workers"""
        self.pool.max_workers = 1
        self.pool.start()
        
        # Assign first task
        task1 = WorkerTask(cell_id="cell-1")
        worker1 = self.pool.assign_cell(task1)
        
        # Try to assign second task
        task2 = WorkerTask(cell_id="cell-2")
        worker2 = self.pool.assign_cell(task2)
        
        self.assertIsNotNone(worker1)
        self.assertIsNone(worker2)
    
    def test_release_worker(self):
        """Test releasing a worker"""
        self.pool.start()
        
        task = WorkerTask(cell_id="cell-1")
        worker = self.pool.assign_cell(task)
        
        self.pool.release_worker(worker.id, success=True)
        
        self.assertEqual(worker.state, WorkerState.IDLE)
        self.assertEqual(worker.completed_tasks, 1)
        self.assertIsNone(worker.current_task)
    
    def test_task_queue(self):
        """Test task queue operations"""
        task1 = WorkerTask(cell_id="cell-1", priority=TaskPriority.HIGH)
        task2 = WorkerTask(cell_id="cell-2", priority=TaskPriority.LOW)
        task3 = WorkerTask(cell_id="cell-3", priority=TaskPriority.MEDIUM)
        
        self.pool.task_queue.put(task2)
        self.pool.task_queue.put(task1)
        self.pool.task_queue.put(task3)
        
        # Should get highest priority first
        first = self.pool.task_queue.get()
        self.assertEqual(first.cell_id, "cell-1")
    
    def test_get_stats(self):
        """Test getting pool statistics"""
        self.pool.start()
        
        task = WorkerTask(cell_id="cell-1")
        self.pool.assign_cell(task)
        
        stats = self.pool.get_stats()
        
        self.assertEqual(stats.total_workers, len(self.pool.workers))
        self.assertEqual(stats.busy_workers, 1)
        self.assertGreaterEqual(stats.idle_workers, 0)


class TestEnhancedPheromoneManager(TestCase):
    """Tests for EnhancedPheromoneManager"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.hive_root = Path(self.temp_dir) / ".trellis"
        self.hive_root.mkdir(parents=True)
        self.pm = EnhancedPheromoneManager(self.hive_root)
    
    def tearDown(self):
        """Clean up after tests"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_emit_pheromone(self):
        """Test emitting a pheromone"""
        entry = self.pm.emit(
            pheromone_type=PheromoneType.PROGRESS,
            source="worker-1",
            data={"progress": 50}
        )
        
        self.assertEqual(entry.type, PheromoneType.PROGRESS)
        self.assertEqual(entry.source, "worker-1")
        self.assertEqual(entry.data["progress"], 50)
    
    def test_emit_blocker(self):
        """Test emitting a blocker pheromone"""
        entry = self.pm.emit_blocker(
            cell_id="cell-1",
            reason="dependency missing",
            source="worker-1"
        )
        
        self.assertEqual(entry.type, PheromoneType.BLOCKER)
        self.assertEqual(entry.target, "cell-1")
    
    def test_subscription(self):
        """Test pheromone subscription"""
        received = []
        
        def callback(entry):
            received.append(entry)
        
        subscriber = self.pm.subscribe(callback, [PheromoneType.PROGRESS])
        
        self.pm.emit(PheromoneType.PROGRESS, "worker-1", {})
        self.pm.emit(PheromoneType.BLOCKER, "worker-1", {})
        
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].type, PheromoneType.PROGRESS)
        
        self.pm.unsubscribe(subscriber)
    
    def test_decay_pheromones(self):
        """Test pheromone decay"""
        # Emit with short TTL
        self.pm.emit(
            pheromone_type=PheromoneType.PROGRESS,
            source="worker-1",
            data={},
            ttl=1  # 1 second
        )
        
        # Wait for decay
        time.sleep(1.5)
        
        expired = self.pm.decay_pheromones()
        
        self.assertGreater(expired, 0)
    
    def test_resolve_blocker(self):
        """Test resolving a blocker"""
        self.pm.emit_blocker("cell-1", "test", "worker-1")
        
        # Check blocker exists
        blockers = self.pm.get_active_blockers()
        self.assertEqual(len(blockers), 1)
        
        # Resolve it
        self.pm.resolve_blocker("cell-1", "worker-1")
        
        # Check blocker removed
        blockers = self.pm.get_active_blockers()
        self.assertEqual(len(blockers), 0)
    
    def test_history(self):
        """Test pheromone history"""
        for i in range(5):
            self.pm.emit(
                pheromone_type=PheromoneType.PROGRESS,
                source=f"worker-{i}",
                data={}
            )
        
        history = self.pm.get_history()
        
        self.assertGreaterEqual(len(history), 5)
    
    def test_worktree_registration(self):
        """Test worktree registration for propagation"""
        worktree_path = Path(self.temp_dir) / "worktree"
        worktree_path.mkdir()
        
        self.pm.register_worktree("wt-1", worktree_path)
        
        self.assertIn("wt-1", self.pm._worktrees)
        
        self.pm.unregister_worktree("wt-1")
        
        self.assertNotIn("wt-1", self.pm._worktrees)


class TestPheromoneSubscriber(TestCase):
    """Tests for PheromoneSubscriber"""
    
    def test_should_receive_all_types(self):
        """Test subscriber receiving all types"""
        received = []
        
        def callback(entry):
            received.append(entry)
        
        subscriber = PheromoneSubscriber(callback)
        
        entry = PheromoneEntry(
            type=PheromoneType.PROGRESS,
            source="test",
            target=None,
            data={},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        self.assertTrue(subscriber.should_receive(entry))
        subscriber.notify(entry)
        self.assertEqual(len(received), 1)
    
    def test_should_receive_specific_types(self):
        """Test subscriber receiving specific types only"""
        received = []
        
        def callback(entry):
            received.append(entry)
        
        subscriber = PheromoneSubscriber(
            callback, 
            [PheromoneType.PROGRESS, PheromoneType.HEARTBEAT]
        )
        
        progress_entry = PheromoneEntry(
            type=PheromoneType.PROGRESS,
            source="test",
            target=None,
            data={},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        blocker_entry = PheromoneEntry(
            type=PheromoneType.BLOCKER,
            source="test",
            target=None,
            data={},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        self.assertTrue(subscriber.should_receive(progress_entry))
        self.assertFalse(subscriber.should_receive(blocker_entry))
    
    def test_inactive_subscriber(self):
        """Test inactive subscriber doesn't receive"""
        received = []
        
        def callback(entry):
            received.append(entry)
        
        subscriber = PheromoneSubscriber(callback)
        subscriber.active = False
        
        entry = PheromoneEntry(
            type=PheromoneType.PROGRESS,
            source="test",
            target=None,
            data={},
            timestamp="2024-01-01T00:00:00Z"
        )
        
        self.assertFalse(subscriber.should_receive(entry))


if __name__ == "__main__":
    main()
