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

    @classmethod
    def create(cls, repo: Path | None, base_dir: Path | None = None, **overrides) -> RunConfig:
        """Build a config, defaulting to a local sandbox when no repo is named.

        Falling back to a dedicated ``workspace/`` directory rather than the cwd
        means a run started without ``--repo`` cannot touch anything real.
        """
        base = Path(base_dir) if base_dir is not None else Path.cwd()

        if repo is None:
            resolved = base / "workspace"
            resolved.mkdir(parents=True, exist_ok=True)
        else:
            resolved = Path(repo).expanduser()
            if not resolved.is_dir():
                raise ValueError(f"--repo path does not exist or is not a directory: {resolved}")

        return cls(repo=resolved, **overrides)
