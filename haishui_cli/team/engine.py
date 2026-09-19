"""Team 引擎 — 规划→派遣→评审→返工→合成 状态机。

与 delegate_task 的差异：这是**离线批量编排**（不依赖 gateway 会话），
planner/critic/synth 都走 haishui -z 子进程，崩溃隔离、全程留痕
（$HAISHUI_HOME/team-runs/<run_id>/plan.json + usage）。
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from haishui_cli.team.roster import Role, TeamConfig
from haishui_cli.team.worker import WorkerSpec, run_worker

_PLANNER_SYSTEM = (
    "你是多 agent 团队的任务规划官。把老板的目标拆成 2~{nmax} 个可并行的子任务，"
    "每个子任务指派一个角色。只输出 JSON 数组，不要解释，格式："
    '[{{"id":"t1","role":"researcher","goal":"...","depends_on":[]}},'
    '{{"id":"t2","role":"builder","goal":"...","depends_on":["t1"]}}]。'
    "依赖用 depends_on 表达（无依赖=可立即并行）。role 只能用这些名字：{roles}。"
)

_JSON_RE = re.compile(r"\[[\s\S]*\]")


def _extract_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    m = _JSON_RE.search(text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) and data else None


class TeamRun:
    """一次完整编排运行。"""

    def __init__(self, goal: str, cfg: TeamConfig, home: Path,
                 dry_run: bool = False) -> None:
        self.goal = goal.strip()
        self.cfg = cfg
        self.dry_run = dry_run
        self.run_id = time.strftime("%Y%m%d-%H%M%S")
        self.dir = home / "team-runs" / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.tasks: Dict[str, WorkerSpec] = {}
        self.log_lines: List[str] = []

    # ——— 日志 / 留痕 ———
    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self.log_lines.append(line)
        print(line, flush=True)

    def _dump_plan(self) -> None:
        payload = {
            "run_id": self.run_id, "goal": self.goal, "dry_run": self.dry_run,
            "tasks": [{k: v for k, v in vars(s).items()} for s in self.tasks.values()],
        }
        (self.dir / "plan.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # ——— 角色解析 ———
    def _pick_role(self, name: str) -> Optional[Role]:
        exact = self.cfg.role(name)
        if exact:
            return exact
        pool = self.cfg.active_roles
        if not pool:
            return None
        # planner 指派了花名册外的角色：researcher 语义优先，否则首位兜底
        return next((r for r in pool if r.name in ("builder", "researcher")), pool[0])

    # ——— 1. 规划 ———
    def plan(self) -> bool:
        names = ", ".join(r.name for r in self.cfg.active_roles)
        sys_prompt = _PLANNER_SYSTEM.format(nmax=max(2, self.cfg.max_workers + 2), roles=names)
        if self.dry_run:
            # 离线模式：不耗模型，造一个静态两任务计划，验证调度逻辑
            specs = [
                {"id": "t1", "role": "researcher", "goal": f"[dry] 调研：{self.goal}", "depends_on": []},
                {"id": "t2", "role": "builder", "goal": f"[dry] 执行：{self.goal}", "depends_on": ["t1"]},
            ]
        else:
            fake = WorkerSpec(task_id="plan", role="planner", toolsets=[],
                              context=f"目标：{self.goal}", goal=f"# 目标\n{self.goal}")
            res = run_worker(fake, sys_prompt, self.cfg.planner_model,
                             600, self.dir)
            specs = _extract_json_array(res["output"]) or []
            if not specs:
                self.log(f"❌ planner 未产出合法 JSON（原始输出前 200 字：{res['output'][:200]}）")
                return False
        def _safe_id(v: Any, idx: int) -> str:
            return re.sub(r"[^A-Za-z0-9_.-]", "_", str(v or "")).strip("_")[:40] or f"t{idx + 1}"

        ids = {_safe_id(i.get("id"), k) for k, i in enumerate(specs[:10])}
        for item in specs[:10]:
            rid = _safe_id(item.get("id"), len(self.tasks))
            role = self._pick_role(str(item.get("role", "")))
            if role is None:
                self.log(f"⚠️ 无可用角色，跳过 {rid}")
                continue
            self.tasks[rid] = WorkerSpec(
                task_id=rid, role=role.name,
                goal=str(item.get("goal", "")).strip(),
                depends_on=[str(d) for d in item.get("depends_on") or [] if str(d) in ids],
            )
        self._fix_deps()
        self.log(f"📋 计划 {len(self.tasks)} 任务：" +
                 ", ".join(f"{t.task_id}({t.role})" for t in self.tasks.values()))
        self._dump_plan()
        return bool(self.tasks)

    def _fix_deps(self) -> None:
        """过滤指向不存在任务的依赖 + 破环（保先到者）。"""
        for s in self.tasks.values():
            s.depends_on = [d for d in s.depends_on if d in self.tasks and d != s.task_id]
        seen: set = set()

        def acyclic(s: WorkerSpec) -> bool:
            if s.task_id in seen:
                return False
            seen.add(s.task_id)
            stack = list(s.depends_on)
            while stack:
                d = stack.pop()
                if d == s.task_id:
                    return False
                dep = self.tasks.get(d)
                if dep and d not in seen:
                    stack.extend(dep.depends_on)
            seen.clear()
            return True

        for s in list(self.tasks.values()):
            while s.depends_on and not acyclic(s):
                s.depends_on.pop()
                self.log(f"⚠️ {s.task_id} 依赖成环，已剪边")

    # ——— 2. 调度 ———
    def _ready(self) -> List[WorkerSpec]:
        out = []
        for s in self.tasks.values():
            if s.status != "pending":
                continue
            if all(self.tasks[d].status == "done" for d in s.depends_on):
                out.append(s)
        return out

    def _blocked_fail(self, s: WorkerSpec) -> None:
        s.status, s.error = "failed", "上游任务失败"

    def _dispatch(self, s: WorkerSpec) -> WorkerSpec:
        role = self._pick_role(s.role)
        assert role is not None
        if self.dry_run:
            s.status, s.result = "done", f"[dry-run] {role.name} 将执行：{s.goal}"
            self.log(f"🔧 (dry) {s.task_id} {s.role} ✓")
            return s
        ctx = "\n\n".join(
            f"## 来自 {d}（{self.tasks[d].role}）\n{self.tasks[d].brief_result(2000)}"
            for d in s.depends_on)
        extra = f"\n\n# 上游结论\n{ctx}" if ctx else ""
        s.toolsets = role.toolsets
        s.status, s.started_at = "running", time.time()
        res = run_worker(s, role.render_system("") + extra, role.model,
                         self.cfg.worker_timeout, self.dir)
        s.finished_at = time.time()
        s.status = "done" if res["ok"] else "failed"
        s.result, s.error = res["output"], res.get("error", "")
        self.log(f"{'✅' if s.status == 'done' else '❌'} {s.task_id}({s.role}) "
                 f"{res['seconds']}s，{len(s.result)} 字")
        self._dump_plan()
        return s

    def execute(self) -> None:
        pool = ThreadPoolExecutor(max_workers=max(1, self.cfg.max_workers))
        try:
            while any(s.status == "pending" for s in self.tasks.values()):
                ready = self._ready()
                if not ready:
                    # 死等：所有 pending 的上游都失败了 → 判失败
                    for s in list(self.tasks.values()):
                        if s.status == "pending" and not self._ready_of(s):
                            self._blocked_fail(s)
                    if all(s.status != "pending" for s in self.tasks.values()):
                        break
                    continue
                futures = {pool.submit(self._dispatch, s): s for s in ready}
                for fut in as_completed(futures):
                    fut.result()
        finally:
            pool.shutdown(wait=True)

    def _ready_of(self, s: WorkerSpec) -> bool:
        return s.status == "pending" and all(
            self.tasks[d].status == "done" for d in s.depends_on)

    # ——— 3. 评审 + 返工 ———
    def review_and_fix(self) -> None:
        if not self.cfg.critic_enabled or self.dry_run:
            return
        done = [s for s in self.tasks.values() if s.status == "done"]
        if not done:
            return
        critic = self._pick_role("critic")
        if critic is None:
            return
        for s in done:
            verdict = self._critic_one(critic, s)
            if verdict is None or verdict.get("verdict") == "pass":
                continue
            if s.attempt >= self.cfg.max_rounds:
                self.log(f"♻️ {s.task_id} 需返工但已达轮数上限，放行")
                continue
            self.log(f"🔁 critic 判 {s.task_id} rework：{str(verdict.get('advice'))[:120]}")
            s.attempt += 1
            s.status = "pending"
            s.result = ""
            role = self._pick_role(s.role) or critic
            retry_ctx = f"# 评审意见（必须修复）\n{json.dumps(verdict, ensure_ascii=False)[:1500]}"
            retry = WorkerSpec(task_id=s.task_id + f"r{s.attempt}", role=role.name,
                               goal=s.goal + f"\n\n# 上一轮产出（需改进）\n{s.brief_result(3000)}",
                               context=retry_ctx, attempt=s.attempt)
            r = self._dispatch(retry)
            s.status, s.result = r.status, r.result or s.result
            s.error = r.error
            self._dump_plan()

    def _critic_one(self, critic: Role, s: WorkerSpec) -> Optional[Dict[str, Any]]:
        fake = WorkerSpec(task_id=f"rev-{s.task_id}", role="critic", toolsets=[],
                          goal=f"# 目标\n{self.goal}\n\n# 子任务 {s.task_id}({s.role})\n"
                               f"{s.goal}\n\n# 交付\n{s.brief_result(6000)}")
        res = run_worker(fake, critic.render_system(""), critic.model,
                         600, self.dir)
        m = re.search(r"\{[\s\S]*\}", res["output"] or "")
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        return v if isinstance(v, dict) else None

    # ——— 4. 合成 ———
    def synthesize(self) -> str:
        parts = [f"# 🏁 团队报告 · {self.run_id}\n\n**目标**：{self.goal}\n"]
        if not self.cfg.synth_enabled or self.dry_run:
            for s in self.tasks.values():
                parts.append(f"\n## {s.task_id}（{s.role}，{s.status}，第{s.attempt}轮）\n"
                             f"{s.brief_result(2500)}")
            report = "".join(parts)
        else:
            synth = self._pick_role("synth")
            if synth is None:
                report = "".join(parts)
            else:
                fake = WorkerSpec(
                    task_id="final", role="synth", toolsets=[],
                    goal="\n\n".join(
                        f"## {s.task_id}（{s.role}，{s.status}）\n{s.brief_result(2500)}"
                        for s in self.tasks.values()),
                    context=f"老板的原始目标：{self.goal}")
                res = run_worker(fake, synth.render_system(
                    "把以下子任务结果整合成最终中文报告：结论先行、依据其次、风险最后。"),
                    synth.model, 900, self.dir)
                report = res["output"] if res["ok"] else "（合成失败，附原始结果）\n" + \
                    "\n\n".join(s.brief_result(1200) for s in self.tasks.values())
        (self.dir / "report.md").write_text(report, encoding="utf-8")
        return report

    # ——— 主流程 ———
    def run(self) -> int:
        t0 = time.time()
        self.log(f"🚀 team run {self.run_id} · 模式={'dry-run' if self.dry_run else 'live'}")
        if not self.plan():
            return 2
        self.execute()
        self.review_and_fix()
        report = self.synthesize()
        ok = sum(1 for s in self.tasks.values() if s.status == "done")
        self.log(f"📦 完成 {ok}/{len(self.tasks)}，用时 {round(time.time() - t0)}s · "
                 f"报告：{self.dir / 'report.md'}")
        print("\n" + report)
        return 0 if ok else 1
