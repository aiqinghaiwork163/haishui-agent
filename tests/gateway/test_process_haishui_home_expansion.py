"""Gateway identity-file readers expand a literal ``~`` in HAISHUI_HOME.

``python -m gateway.run`` never passes through the CLI's ``normalize_haishui_home_env()``, so the
process-level home readers (PID/lock/status, lifecycle ledger, heartbeat) must expand on their own
or a fish-style ``HAISHUI_HOME='~/.haishui'`` lands the identity files under ``<cwd>/~/.haishui``.
"""

from pathlib import Path

import pytest

from gateway import lifecycle_ledger, shutdown_watchdog, status


@pytest.mark.parametrize(
    "reader",
    [status._get_process_haishui_home, lifecycle_ledger._process_haishui_home,
     shutdown_watchdog._process_haishui_home],
    ids=["status", "lifecycle_ledger", "shutdown_watchdog"],
)
def test_process_home_readers_expand_literal_tilde(reader, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HAISHUI_HOME", "~/.x")
    assert reader() == tmp_path / ".x"
    assert reader().is_absolute()
    monkeypatch.setenv("HAISHUI_HOME", str(tmp_path / ".abs"))
    assert reader() == Path(tmp_path / ".abs")
