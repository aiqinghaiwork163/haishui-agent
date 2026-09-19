"""角色花名册 — 内置默认团队 + $HAISHUI_HOME/team.yaml 覆盖/扩展。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Role:
    """团队里的一个专家席位。"""

    name: str
    system: str  # 注入给该角色 worker 的人设（ephemeral prompt 片段）
    toolsets: Optional[List[str]] = None  # None = 继承默认
    model: Optional[str] = None  # None = 继承主配置
    max_iterations: int = 60
    enabled: bool = True
    # 固定分工：给了 goal 就不再由 planner 派遣，直接作为并行成员跑
    fixed_goal: Optional[str] = None

    def render_system(self, extra_context: str = "") -> str:
        parts = [self.system.strip()]
        if extra_context:
            parts.append(f"\n# 本次任务补充上下文\n{extra_context.strip()}")
        return "\n".join(parts)


@dataclass
class TeamConfig:
    """整体运行参数。"""

    max_workers: int = 3
    max_rounds: int = 2  # 规划→评审→返工 的轮数上限
    worker_timeout: int = 1500  # 单个 worker 进程超时（秒）
    critic_enabled: bool = True
    synth_enabled: bool = True
    planner_model: Optional[str] = None
    roles: List[Role] = field(default_factory=list)

    def role(self, name: str) -> Optional[Role]:
        for r in self.roles:
            if r.name == name and r.enabled:
                return r
        return None

    @property
    def active_roles(self) -> List[Role]:
        return [r for r in self.roles if r.enabled and r.fixed_goal is None]


def _haishui_home() -> Path:
    import os

    h = os.environ.get("HAISHUI_HOME")
    return Path(h) if h else Path.home() / ".haishui"


def team_config_path() -> Path:
    return _haishui_home() / "team.yaml"


# ——— 内置默认团队：一脑两手一闸 ———
_DEFAULT_ROLES = [
    Role(
        name="builder",
        system=(
            "你是团队的执行工程师。收到子任务后：动手做，不要空谈；优先用工具验证结论"
            "（跑命令、读文件、写代码）。产出=可交接的交付物+简短说明+文件路径清单。"
            "不要反问，缺信息就基于假设完成并标注假设。"
        ),
        max_iterations=80,
    ),
    Role(
        name="researcher",
        system=(
            "你是团队的调研员。负责查证据：读代码库、搜文件、查文档/知识库，输出结构化"
            "调研结论（要点列表+出处路径），不做修改类操作。"
        ),
        max_iterations=50,
    ),
    Role(
        name="critic",
        system=(
            "你是严格但公道的评审员。审查交付物：正确性、完整性、副作用。输出 JSON："
            '{"verdict": "pass|rework", "problems": [...], "advice": "一句话"}。'
            "只有实质缺陷才判 rework。"
        ),
        max_iterations=40,
    ),
    Role(
        name="synth",
        system=(
            "你是团队的合成官。把多份子任务结果整合成一份给老板的最终报告："
            "结论先行、依据其次、风险最后，中文，信息密度高。"
        ),
        max_iterations=40,
    ),
]


def _parse_roles(raw: Any) -> List[Role]:
    roles: List[Role] = []
    if not isinstance(raw, list):
        return roles
    for item in raw:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        ts = item.get("toolsets")
        roles.append(
            Role(
                name=str(item["name"]).strip(),
                system=str(item.get("system", "")).strip() or "你是团队的一员，按任务说明执行。",
                toolsets=[str(t) for t in ts] if isinstance(ts, list) else None,
                model=item.get("model"),
                max_iterations=int(item.get("max_iterations", 60)),
                enabled=bool(item.get("enabled", True)),
                fixed_goal=item.get("goal"),
            )
        )
    return roles


def load_team(path: Optional[Path] = None) -> TeamConfig:
    """读 team.yaml；缺文件/坏文件都退回内置默认团队（永不抛）。"""
    cfg = TeamConfig(roles=[Role(**{**vars(r)}) for r in _DEFAULT_ROLES])
    p = path or team_config_path()
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return cfg
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return cfg
    if not isinstance(raw, dict):
        return cfg

    tval = raw.get("team")
    team: Dict[str, Any] = tval if isinstance(tval, dict) else raw
    for key in ("max_workers", "max_rounds", "worker_timeout"):
        v = team.get(key)
        if isinstance(v, int) and v > 0:
            setattr(cfg, key, v)
    cfg.critic_enabled = bool(team.get("critic", cfg.critic_enabled))
    cfg.synth_enabled = bool(team.get("synthesize", cfg.synth_enabled))
    cfg.planner_model = team.get("planner_model")

    file_roles = _parse_roles(team.get("roles"))
    if file_roles:
        # 同名替换内置角色，新名追加
        merged: Dict[str, Role] = {r.name: r for r in cfg.roles}
        for r in file_roles:
            merged[r.name] = r
        cfg.roles = list(merged.values())
    return cfg
