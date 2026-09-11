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
    parser.add_argument(
        "--stub-code",
        choices=["clean", "complex", "improving"],
        default=None,
        help="Replace Claude Code with a stub. 'clean' passes analysis and "
        "reaches the reviewer; 'complex' never improves, so the run loops to "
        "--max-iterations; 'improving' fails once then refactors, so the run "
        "converges. Spends no agent tokens.",
    )
    parser.add_argument("--analyzer-url", default="http://localhost:9292")
    parser.add_argument("--flog-average-limit", type=float, default=20.0)
    parser.add_argument("--smells-limit", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # A stubbed coder still runs the real planner and reviewer, so the key is
    # needed either way — unless analysis short-circuits every pass, which we
    # cannot know up front.
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
            analyzer_url=args.analyzer_url,
            flog_average_limit=args.flog_average_limit,
            smells_limit=args.smells_limit,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    asyncio.run(repl(config, stub=args.stub_code))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
