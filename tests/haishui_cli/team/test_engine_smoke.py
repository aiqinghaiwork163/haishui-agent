"""Smoke tests for haishui_cli.team.engine — 规划 JSON 解析、dry-run 调度、依赖破环。

全部离线：不 spawn `haishui -z` 子进程（dry-run 分支 / 直接操作 tasks 字典），
不触网、不读真实 ~/.haishui。
"""

from __future__ import annotations

import json

import pytest

from haishui_cli.team.engine import TeamRun, _extract_json_array
from haishui_cli.team.roster import Role, TeamConfig
from haishui_cli.team.worker import WorkerSpec


def _cfg() -> TeamConfig:
    """最小花名册：dry-run 静态计划只用到 researcher / builder 两个角色。"""
    return TeamConfig(
        max_workers=2,
        critic_enabled=False,
        synth_enabled=False,
        roles=[
            Role(name="researcher", system="你是调研员。"),
            Role(name="builder", system="你是执行工程师。"),
        ],
    )


def _graph_has_cycle(tasks: dict) -> bool:
    """独立实现的三色 DFS 环检测，避免和被测代码用同一套逻辑自证。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in tasks}

    def visit(tid: str) -> bool:
        color[tid] = GRAY
        for d in tasks[tid].depends_on:
            if d not in tasks:
                continue
            if color[d] == GRAY:
                return True
            if color[d] == WHITE and visit(d):
                return True
        color[tid] = BLACK
        return False

    return any(color[t] == WHITE and visit(t) for t in tasks)


class TestExtractJsonArray:
    """_extract_json_array：合法 JSON 数组解析 / 各种非法输入返回 None。"""

    def test_valid_array_with_surrounding_text(self):
        text = (
            "好的，计划如下：\n"
            '[{"id":"t1","role":"researcher","goal":"调研","depends_on":[]},'
            '{"id":"t2","role":"builder","goal":"实现","depends_on":["t1"]}]'
            "\n以上。"
        )
        data = _extract_json_array(text)
        assert data is not None
        assert isinstance(data, list) and len(data) == 2
        assert data[0]["id"] == "t1"
        assert data[1]["depends_on"] == ["t1"]

    def test_valid_array_only(self):
        assert _extract_json_array('[{"id": "t1"}]') == [{"id": "t1"}]

    @pytest.mark.parametrize(
        "bad",
        [
            None,                              # 空输入
            "",                                # 空串
            "抱歉，我无法完成任务。",             # 完全没有数组
            "[{not valid json}]",              # 有方括号但内容非法
            "[{\"id\": \"t1\",]",              # 尾逗号 / 截断
            "这是一个对象 {\"id\":\"t1\"} 不是数组",  # 只有对象没有数组
            "[]",                              # 合法但空的数组 → 视为无效计划
        ],
        ids=["none", "empty", "no-array", "garbage-inside",
             "truncated", "object-not-array", "empty-array"],
    )
    def test_invalid_inputs_return_none(self, bad):
        assert _extract_json_array(bad) is None


class TestTeamRunDryRun:
    """dry-run：plan() 造静态两任务计划，execute() 应全部调度为 done。"""

    def test_plan_then_execute_all_done(self, tmp_path):
        run = TeamRun(goal="做一个冒烟 demo", cfg=_cfg(), home=tmp_path,
                      dry_run=True)

        assert run.plan() is True
        assert set(run.tasks) == {"t1", "t2"}
        assert run.tasks["t1"].role == "researcher"
        assert run.tasks["t2"].role == "builder"
        assert run.tasks["t2"].depends_on == ["t1"]  # 依赖保留
        # 留痕：plan.json 落盘
        dumped = json.loads((run.dir / "plan.json").read_text(encoding="utf-8"))
        assert dumped["dry_run"] is True
        assert len(dumped["tasks"]) == 2

        run.execute()

        assert run.tasks, "计划里必须有任务"
        assert all(s.status == "done" for s in run.tasks.values())
        assert all("dry-run" in s.result for s in run.tasks.values())
        # 依赖顺序：t2 是在 t1 完成之后才派遣的（两者都 done 即调度闭环成立）
        assert run.tasks["t1"].status == run.tasks["t2"].status == "done"

    def test_full_run_returns_zero(self, tmp_path):
        """run() 端到端（dry-run）：exit code 0，report.md 生成。"""
        run = TeamRun(goal="端到端冒烟", cfg=_cfg(), home=tmp_path,
                      dry_run=True)
        assert run.run() == 0
        assert all(s.status == "done" for s in run.tasks.values())
        assert (run.dir / "report.md").exists()


class TestFixDepsBreaksCycles:
    """_fix_deps：依赖成环时必须剪边，剪完保持全图无环。"""

    def test_mutual_cycle_is_cut(self, tmp_path):
        run = TeamRun(goal="破环", cfg=_cfg(), home=tmp_path, dry_run=True)
        run.tasks = {
            "t1": WorkerSpec(task_id="t1", role="researcher", goal="a",
                             depends_on=["t2"]),
            "t2": WorkerSpec(task_id="t2", role="builder", goal="b",
                             depends_on=["t1"]),
        }
        edges_before = sum(len(s.depends_on) for s in run.tasks.values())

        run._fix_deps()

        edges_after = sum(len(s.depends_on) for s in run.tasks.values())
        assert edges_after < edges_before, "成环的边必须被剪掉"
        assert not _graph_has_cycle(run.tasks), "剪边后不允许仍有环"
        assert any("剪边" in line for line in run.log_lines), "剪边要有日志留痕"

    def test_three_node_cycle_keeps_acyclic_path(self, tmp_path):
        """a→b→c→a 三节点环：只破坏环，合法依赖仍可用，execute 不再死锁。"""
        run = TeamRun(goal="破环", cfg=_cfg(), home=tmp_path, dry_run=True)
        run.tasks = {
            "a": WorkerSpec(task_id="a", role="researcher", goal="1",
                            depends_on=["b"]),
            "b": WorkerSpec(task_id="b", role="builder", goal="2",
                            depends_on=["c"]),
            "c": WorkerSpec(task_id="c", role="builder", goal="3",
                            depends_on=["a"]),
        }

        run._fix_deps()

        assert not _graph_has_cycle(run.tasks)
        assert any("剪边" in line for line in run.log_lines)
        # 破环后调度必须能收敛：dry-run 全 done 即证明没有死等
        run.execute()
        assert all(s.status == "done" for s in run.tasks.values())

    def test_dangling_and_self_deps_filtered(self, tmp_path):
        """非环噪音：指向不存在任务/自己的依赖先被过滤，不误报剪边。"""
        run = TeamRun(goal="过滤", cfg=_cfg(), home=tmp_path, dry_run=True)
        run.tasks = {
            "t1": WorkerSpec(task_id="t1", role="researcher", goal="x",
                             depends_on=["ghost", "t1", "t2"]),
            "t2": WorkerSpec(task_id="t2", role="builder", goal="y",
                             depends_on=[]),
        }

        run._fix_deps()

        assert run.tasks["t1"].depends_on == ["t2"]
        assert not any("剪边" in line for line in run.log_lines)
