"""Haishui Team — 多 agent 自编排引擎。

把一个大目标自动拆解成任务图，派给一队专家子 agent（每个是一次隔离的
``haishui -z`` 进程）并行执行，评审不过自动返工，最后合成报告。

模块：
  roster  — 角色花名册（team.yaml + 内置默认）
  engine  — 规划 → 派遣 → 评审 → 合成 状态机
"""

from haishui_cli.team.roster import Role, TeamConfig, load_team  # noqa: F401

__all__ = ["Role", "TeamConfig", "load_team"]
