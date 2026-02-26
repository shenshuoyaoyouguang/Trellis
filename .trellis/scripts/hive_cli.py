#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hive CLI - Unified Command Line Interface for Hive Concurrent Agent Mode

This script provides a unified entry point for all hive operations,
ensuring proper module path resolution regardless of the current working directory.

Usage:
    # From project root
    python .trellis/scripts/hive_cli.py queen status
    
    # From any directory
    python /path/to/.trellis/scripts/hive_cli.py cell list
    
    # With Python module syntax
    python -m hive_cli queen status

Commands:
    queen <action>   - Queen scheduler operations
        status           Show scheduler status
        start            Start the scheduler
        stop             Stop the scheduler
        dispatch         Dispatch workers to available cells
    
    cell <action>    - Cell management operations
        list             List all cells
        show <id>        Show cell details
        create <id>      Create a new cell
        complete <id>    Mark cell as completed
        
    pheromone <action> - Pheromone trail operations
        show             Show active pheromone trails
        clear            Clear all trails
        trace <id>       Show trail for specific cell
    
    config <action>  - Configuration operations
        show             Show current configuration
        validate         Validate configuration file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Setup module path before importing hive modules
_hive_dir = Path(__file__).parent / "hive"
_scripts_dir = Path(__file__).parent

for _p in [str(_hive_dir), str(_scripts_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Import hive modules (after path setup)
from hive import (
    HiveConfig,
    get_config,
    PheromoneManager,
    get_pheromone_manager,
)


def cmd_queen_status(args):
    """Display queen scheduler status"""
    try:
        from hive import QueenScheduler
        queen = QueenScheduler()
        status = queen.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error getting queen status: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_queen_start(args):
    """Start the queen scheduler"""
    try:
        from hive import QueenScheduler
        queen = QueenScheduler()
        queen.start()
        print("Queen scheduler started")
    except Exception as e:
        print(f"Error starting queen scheduler: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_queen_stop(args):
    """Stop the queen scheduler"""
    try:
        from hive import QueenScheduler
        queen = QueenScheduler()
        queen.stop()
        print("Queen scheduler stopped")
    except Exception as e:
        print(f"Error stopping queen scheduler: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_queen_dispatch(args):
    """Dispatch workers to available cells"""
    try:
        from hive import QueenScheduler
        queen = QueenScheduler()
        result = queen.dispatch_workers()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error dispatching workers: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_cell_list(args):
    """List all cells"""
    try:
        from hive import CellManager
        cm = CellManager()
        cells = cm.list_cells(status=args.status)
        print(json.dumps(cells, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error listing cells: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_cell_show(args):
    """Show cell details"""
    try:
        from hive import CellManager
        cm = CellManager()
        cell = cm.get_cell(args.cell_id)
        print(json.dumps(cell.to_dict() if hasattr(cell, 'to_dict') else str(cell), 
                        indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error showing cell: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_pheromone_show(args):
    """Show active pheromone trails"""
    try:
        pm = get_pheromone_manager()
        trails = pm.get_active_trails()
        print(json.dumps(trails, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error showing pheromone trails: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_pheromone_clear(args):
    """Clear all pheromone trails"""
    try:
        pm = get_pheromone_manager()
        pm.clear_all()
        print("All pheromone trails cleared")
    except Exception as e:
        print(f"Error clearing trails: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_show(args):
    """Show current configuration"""
    try:
        config = get_config()
        print(json.dumps(config.to_dict() if hasattr(config, 'to_dict') else str(config),
                        indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error showing config: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_validate(args):
    """Validate configuration file"""
    try:
        config = get_config()
        config.validate()
        print("Configuration is valid")
    except Exception as e:
        print(f"Configuration validation failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Hive CLI - Unified Command Line Interface for Hive Concurrent Agent Mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest="module", help="Module commands")

    # Queen scheduler commands
    queen_parser = subparsers.add_parser("queen", help="Queen scheduler operations")
    queen_sub = queen_parser.add_subparsers(dest="command", help="Queen commands")
    
    queen_status = queen_sub.add_parser("status", help="Show scheduler status")
    queen_status.set_defaults(func=cmd_queen_status)
    
    queen_start = queen_sub.add_parser("start", help="Start the scheduler")
    queen_start.set_defaults(func=cmd_queen_start)
    
    queen_stop = queen_sub.add_parser("stop", help="Stop the scheduler")
    queen_stop.set_defaults(func=cmd_queen_stop)
    
    queen_dispatch = queen_sub.add_parser("dispatch", help="Dispatch workers")
    queen_dispatch.set_defaults(func=cmd_queen_dispatch)

    # Cell management commands
    cell_parser = subparsers.add_parser("cell", help="Cell management operations")
    cell_sub = cell_parser.add_subparsers(dest="command", help="Cell commands")
    
    cell_list = cell_sub.add_parser("list", help="List all cells")
    cell_list.add_argument("--status", help="Filter by status (pending/running/completed)")
    cell_list.set_defaults(func=cmd_cell_list)
    
    cell_show = cell_sub.add_parser("show", help="Show cell details")
    cell_show.add_argument("cell_id", help="Cell ID to show")
    cell_show.set_defaults(func=cmd_cell_show)

    # Pheromone commands
    pheromone_parser = subparsers.add_parser("pheromone", help="Pheromone trail operations")
    pheromone_sub = pheromone_parser.add_subparsers(dest="command", help="Pheromone commands")
    
    pheromone_show = pheromone_sub.add_parser("show", help="Show active trails")
    pheromone_show.set_defaults(func=cmd_pheromone_show)
    
    pheromone_clear = pheromone_sub.add_parser("clear", help="Clear all trails")
    pheromone_clear.set_defaults(func=cmd_pheromone_clear)

    # Config commands
    config_parser = subparsers.add_parser("config", help="Configuration operations")
    config_sub = config_parser.add_subparsers(dest="command", help="Config commands")
    
    config_show = config_sub.add_parser("show", help="Show configuration")
    config_show.set_defaults(func=cmd_config_show)
    
    config_validate = config_sub.add_parser("validate", help="Validate configuration")
    config_validate.set_defaults(func=cmd_config_validate)

    args = parser.parse_args()
    
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
