"""Guards for haishui_cli._startup_fast — the pre-import version fast path.

Two invariants, each of which has been broken before:

1. IMPORT WEIGHT: _startup_fast must stay stdlib-only. The whole point of
   the module is to run before main.py's heavy import wall; one careless
   ``from haishui_cli.config import ...`` silently makes `haishui --version`
   slow again for everyone (the regression would be invisible — everything
   still works, just 40x slower).

2. OUTPUT PARITY / LIVENESS: the fast path must actually produce version
   output and exit 0 in a real subprocess, on and off Termux. This is the
   test that would have caught eb4040242, which changed the canonical
   version output to reference the PROJECT_ROOT module constant inside the
   fast function — a name that doesn't exist yet at the fast exit point —
   NameError-ing the Termux fast path in production for weeks.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Modules that must NEVER be imported by the fast path. Each one either
# pulls yaml/argparse/logging config or is itself a god-module.
_FORBIDDEN_MODULES = (
    "haishui_cli.config",
    "haishui_cli.main",
    "yaml",
    "argparse",
    "cli",
    "run_agent",
    "model_tools",
    "httpx",
    "openai",
)


def test_startup_fast_import_weight():
    """Importing _startup_fast must not drag in any heavy module."""
    probe = (
        "import sys, json\n"
        "import haishui_cli._startup_fast\n"
        "print(json.dumps(sorted(sys.modules.keys())))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    loaded = set(json.loads(result.stdout))
    offenders = [m for m in _FORBIDDEN_MODULES if m in loaded]
    assert not offenders, (
        f"haishui_cli._startup_fast imported heavy modules: {offenders} — "
        "the fast path must stay stdlib-only (see module docstring)."
    )


def _run_version(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_overrides}
    env.pop("HAISHUI_DEV", None)
    return subprocess.run(
        [sys.executable, "-m", "haishui_cli.main", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
        env=env,
    )


def test_fast_version_parity_off_termux(tmp_path):
    home = tmp_path / ".haishui"
    home.mkdir()
    result = _run_version({"HAISHUI_HOME": str(home), "TERMUX_VERSION": ""})
    assert result.returncode == 0, result.stderr
    out = result.stdout
    for field in ("Haishui Agent v", "Install directory:", "Python:", "OpenAI SDK:"):
        assert field in out, f"fast --version output missing {field!r}:\n{out}"


def test_fast_version_parity_on_termux(tmp_path):
    """The historical Termux path — the one eb4040242 broke."""
    home = tmp_path / ".haishui"
    home.mkdir()
    result = _run_version(
        {"HAISHUI_HOME": str(home), "TERMUX_VERSION": "0.118"}
    )
    assert result.returncode == 0, result.stderr
    assert "Haishui Agent v" in result.stdout
    assert "Traceback" not in result.stderr


def test_fast_version_reports_install_method_stamp(tmp_path):
    home = tmp_path / ".haishui"
    home.mkdir()
    (home / ".install_method").write_text("git\n", encoding="utf-8")
    result = _run_version({"HAISHUI_HOME": str(home), "TERMUX_VERSION": ""})
    assert result.returncode == 0, result.stderr
    assert "Install method: git" in result.stdout


def test_literal_tilde_haishui_home_expands_before_any_reader(tmp_path):
    """A literal ``~`` in HAISHUI_HOME (fish, or any quoted value) is expanded at process entry.

    Before the fix ``Path("~/.x")`` was relative, so the real CLI resolved it against cwd and
    scaffolded a full home under ``<cwd>/~/.x``. The negative assertion on cwd is the
    reporter's own acceptance criterion.
    """
    fake_home = tmp_path / "home"
    cwd = tmp_path / "project"
    fake_home.mkdir()
    cwd.mkdir()
    env = {**os.environ, "HOME": str(fake_home), "USERPROFILE": str(fake_home), "HAISHUI_HOME": "~/.x"}
    env.pop("HAISHUI_DEV", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "haishui_cli.main", "config", "path"],
        capture_output=True, text=True, timeout=120, cwd=cwd, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(fake_home / ".x" / "config.yaml")
    assert not (cwd / "~").exists(), sorted(p.name for p in cwd.iterdir())

    # Raw-reader observable: the ~30 ``os.environ["HAISHUI_HOME"]`` readers in haishui_cli/ never
    # call the resolver, so the entry-point hunk in main.py (not haishui_constants) must have
    # rewritten the env var by the time the module import finishes.
    probe = subprocess.run(
        [sys.executable, "-c", "import haishui_cli.main, os; print(os.environ['HAISHUI_HOME'])"],
        capture_output=True, text=True, timeout=120, cwd=cwd, env=env,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip() == str(fake_home / ".x")


def test_normalize_haishui_home_env_rewrites_tilde_and_leaves_absolute_alone(tmp_path, monkeypatch):
    from haishui_cli import _startup_fast

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HAISHUI_HOME", "~/.x")
    _startup_fast.normalize_haishui_home_env()
    assert os.environ["HAISHUI_HOME"] == str(tmp_path / ".x")

    monkeypatch.setenv("HAISHUI_HOME", str(tmp_path / "abs"))
    _startup_fast.normalize_haishui_home_env()
    assert os.environ["HAISHUI_HOME"] == str(tmp_path / "abs")

    monkeypatch.delenv("HAISHUI_HOME")
    _startup_fast.normalize_haishui_home_env()
    assert "HAISHUI_HOME" not in os.environ
