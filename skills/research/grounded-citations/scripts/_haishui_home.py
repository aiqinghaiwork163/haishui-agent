"""Resolve HAISHUI_HOME for standalone skill scripts.

Skill scripts may run outside the Haishui process (system Python, nix env,
CI) where ``haishui_constants`` is not importable.  This module provides the
same ``get_haishui_home()`` contract without requiring it on ``sys.path``.

When ``haishui_constants`` IS available it is used directly so profile
resolution and any future enhancements are picked up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from haishui_constants import get_haishui_home as get_haishui_home
except (ModuleNotFoundError, ImportError):

    def get_haishui_home() -> Path:
        """Return the Haishui home directory (default: ``~/.haishui``)."""
        val = os.environ.get("HAISHUI_HOME", "").strip()
        return Path(val) if val else Path.home() / ".haishui"
