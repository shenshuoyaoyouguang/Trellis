#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pytest configuration for hive tests
"""

import sys
from pathlib import Path

# Add scripts directory to path
_project_root = Path(__file__).parent.parent.parent
_scripts_path = _project_root / ".trellis" / "scripts"
if str(_scripts_path) not in sys.path:
    sys.path.insert(0, str(_scripts_path))
