"""Team worker — 每个子任务是一次隔离的 ``haishui -z`` 子进程调用。

用子进程而非进程内 AIAgent：崩溃隔离、超时可控、并发无共享状态、
每个 worker 拿到独立的 role persona 注入。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class WorkerSpec:
    """一个待执行的派遣。"""

    task_id: str
    role: str
    goal: str
    context: str = ""
    depends_on: List[str] = field(default_factory=list)
    toolsets: Optional[List[str]] = None  # 子进程 -t 白名单；None=继承全局
    attempt: int = 1
    status: str = "pending"  # pending|running|done|failed
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0

    def brief_result(self, limit: int = 4000) -> str:
        r = self.result or self.error or ""
        return r if len(r) <= limit else r[:limit] + "\n…(截断)"


def haishui_bin() -> List[str]:
    """当前可执行对应的 haishui 入口（源码树 venv 或 PATH）。"""
    exe = Path(sys.executable)
    cand = exe.parent / "haishui"
    if cand.exists():
        return [str(cand)]
    return [sys.executable, "-m", "haishui_cli.main"]


def run_worker(spec: WorkerSpec, role_system: str, model: Optional[str],
               timeout: int, usage_dir: Path) -> Dict[str, Any]:
    """执行一次派遣，返回 {ok, output, exit_code, seconds}。线程安全（纯子进程）。"""
    prompt = spec.goal if not spec.context else f"{spec.goal}\n\n# 背景与上游结果\n{spec.context}"
    env = dict(os.environ)
    # 双通道注入人设：env 供 cli/gateway 消费；-z 路径不读该 env（oneshot 的
    # ephemeral prompt 只装 skills），所以同时前置进 prompt，保证 worker 必戴面具。
    if role_system:
        env["HAISHUI_EPHEMERAL_SYSTEM_PROMPT"] = role_system
        prompt = f"# 你的角色（严格遵守，禁止执行角色外动作）\n{role_system}\n\n# 本次任务\n{prompt}"
    env.pop("HAISHUI_SESSION_NAME", None)
    cmd = haishui_bin() + ["-z", prompt, "--usage-file",
                           str(usage_dir / f"{spec.task_id}.a{spec.attempt}.json")]
    if spec.toolsets:
        cmd += ["-t", ",".join(spec.toolsets)]
    if model:
        cmd += ["-m", model]
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
            stdin=subprocess.DEVNULL,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        ok = proc.returncode == 0 and bool(out)
        return {"ok": ok, "output": out or err, "exit_code": proc.returncode,
                "seconds": round(time.time() - t0, 1)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "", "exit_code": -1,
                "seconds": round(time.time() - t0, 1), "error": f"超时 {timeout}s"}
    except Exception as exc:  # noqa: BLE001 — 引擎侧兜底，任何异常都要变任务失败
        return {"ok": False, "output": "", "exit_code": -1,
                "seconds": round(time.time() - t0, 1), "error": str(exc)}
