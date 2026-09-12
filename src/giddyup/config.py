"""Run configuration and its guardrail defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_PLANNER_MODEL = "claude-sonnet-5"
DEFAULT_CODE_MODEL = "claude-opus-5"


@dataclass(frozen=True)
class RunConfig:
    """Everything a single REPL session needs to know.

    The budget fields are the guardrails that stand in for interactive approval:
    the code node runs with ``bypassPermissions``, so nothing prompts the user
    mid-run and the limits have to be structural.
    """

    repo: Path
    code_model: str = DEFAULT_CODE_MODEL
    planner_model: str = DEFAULT_PLANNER_MODEL
    max_turns: int = 30
    max_iterations: int = 3
    budget_per_iteration: float = 2.00
    session_budget: float = 10.00
    analyzer_url: str = "http://localhost:9292"
    flog_average_limit: float = 20.0
    smells_limit: int = 3

    @classmethod
    def create(cls, repo: Path | None, **overrides) -> RunConfig:
        """Build a config for an explicitly named repository.

        There is deliberately no default. The code node runs with
        ``bypassPermissions``, so the repository it works in has to be a choice
        the operator made rather than one this function invented — and a
        silently invented sandbox is how the analysis gate came to be dead by
        default, since the enclosing repository ignored it.
        """
        if repo is None:
            raise ValueError(
                "--repo is required: name the repository this session will "
                "contribute to.\n"
                "To practise against a throwaway repository instead:\n"
                "    mise run sandbox\n"
                "    mise exec -- python -m giddyup --repo ./workspace"
            )

        resolved = Path(repo).expanduser()
        if not resolved.is_dir():
            raise ValueError(f"--repo path does not exist or is not a directory: {resolved}")

        return cls(repo=resolved, **overrides)
