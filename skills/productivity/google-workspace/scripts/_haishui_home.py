"""Resolve HAISHUI_HOME for standalone skill scripts.

Skill scripts may run outside the Haishui process (e.g. system Python,
nix env, CI) where ``haishui_constants`` is not importable.  This module
provides the same ``get_haishui_home()`` and ``display_haishui_home()``
contracts as ``haishui_constants`` without requiring it on ``sys.path``.

When ``haishui_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``haishui_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``HAISHUI_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from haishui_constants import display_haishui_home as display_haishui_home
    from haishui_constants import get_haishui_home as get_haishui_home
except (ModuleNotFoundError, ImportError):

    def get_haishui_home() -> Path:
        """Return the Haishui home directory (default: ~/.haishui).

        Mirrors ``haishui_constants.get_haishui_home()``."""
        val = os.environ.get("HAISHUI_HOME", "").strip()
        return Path(val) if val else Path.home() / ".haishui"

    def display_haishui_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``haishui_constants.display_haishui_home()``."""
        home = get_haishui_home()
        try:
            return "~/" + home.relative_to(Path.home()).as_posix()
        except ValueError:
            return str(home)
