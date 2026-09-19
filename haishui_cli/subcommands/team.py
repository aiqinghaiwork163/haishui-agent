"""``haishui team`` — 多 agent 自编排：拆目标、派专家、评审返工、合成报告。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def cmd_team(args: argparse.Namespace) -> int:
    """team 子命令入口（run / show-roster）。"""
    from haishui_cli.team.roster import load_team, team_config_path
    from haishui_cli.team.engine import TeamRun

    home = Path(os.environ.get("HAISHUI_HOME") or (Path.home() / ".haishui"))
    cfg = load_team(Path(args.config) if getattr(args, "config", None) else None)

    if args.team_command == "show-roster":
        src = team_config_path()
        print(f"📇 team.yaml: {src}{'（已加载）' if src.exists() else '（不存在，用内置默认）'}")
        print(f"workers={cfg.max_workers} rounds={cfg.max_rounds} "
              f"critic={cfg.critic_enabled} synth={cfg.synth_enabled}")
        for r in cfg.roles:
            flag = "✅" if r.enabled else "⛔"
            fixed = f" [固定任务: {r.fixed_goal[:30]}…]" if r.fixed_goal else ""
            print(f"  {flag} {r.name:12s} model={r.model or '(继承)':8s} "
                  f"iter={r.max_iterations}{fixed}")
            print(f"     {r.system[:88]}…")
        return 0

    goal = " ".join(args.goal).strip()
    if not goal:
        print("用法：haishui team run \"目标\" [--dry-run]", file=sys.stderr)
        return 2
    if args.model:
        cfg.planner_model = args.model
    if args.workers:
        cfg.max_workers = args.workers
    return TeamRun(goal, cfg, home, dry_run=args.dry_run).run()


def build_team_parser(subparsers) -> None:
    """Attach the ``team`` subcommand tree."""
    team_parser = subparsers.add_parser(
        "team",
        help="Multi-agent orchestration: plan → parallel workers → review → synthesis",
        description="Haishui Team — 把大目标自动拆解给一队专家子 agent（每个是一次隔离的 "
                    "haishui -z 进程）并行执行；评审不过自动返工；最后合成中文报告。"
                    "花名册可被 $HAISHUI_HOME/team.yaml 覆盖/扩展。")
    team_sub = team_parser.add_subparsers(dest="team_command")

    run_p = team_sub.add_parser("run", help="Run a goal through the team")
    run_p.add_argument("goal", nargs="*", help="目标描述")
    run_p.add_argument("--dry-run", action="store_true",
                       help="离线模式：静态计划 + 假 worker，只验证调度（不耗模型）")
    run_p.add_argument("--config", default=None, help="自定义 team.yaml 路径")
    run_p.add_argument("--workers", type=int, default=0, help="并行 worker 上限（覆盖花名册）")
    run_p.add_argument("--model", default=None, help="planner 使用的模型（覆盖默认）")
    run_p.set_defaults(func=cmd_team)

    roster_p = team_sub.add_parser("show-roster", help="Show roles & knobs")
    roster_p.set_defaults(func=cmd_team)

    team_parser.set_defaults(func=lambda a: (team_parser.print_help(), 0)[1])
