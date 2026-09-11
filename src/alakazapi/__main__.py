"""CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .config import DEFAULT_CODE_MODEL, DEFAULT_PLANNER_MODEL, RunConfig
from .repl import repl


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="alakazapi",
        description="A LangGraph pipeline that uses Claude Code as an executing node.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository Claude Code works in (default: ./workspace sandbox)",
    )
    parser.add_argument("--code-model", default=DEFAULT_CODE_MODEL)
    parser.add_argument("--planner-model", default=DEFAULT_PLANNER_MODEL)
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--budget-per-iteration", type=float, default=2.00)
    parser.add_argument("--session-budget", type=float, default=10.00)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set — the planner and reviewer nodes need it.",
            file=sys.stderr,
        )
        return 1

    try:
        config = RunConfig.create(
            repo=args.repo,
            code_model=args.code_model,
            planner_model=args.planner_model,
            max_turns=args.max_turns,
            max_iterations=args.max_iterations,
            budget_per_iteration=args.budget_per_iteration,
            session_budget=args.session_budget,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    asyncio.run(repl(config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
