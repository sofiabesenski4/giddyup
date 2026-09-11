"""The conditional edge out of the review node."""

from __future__ import annotations

from typing import Literal

from .config import RunConfig
from .state import PipelineState

Route = Literal["code", "done"]
AnalysisRoute = Literal["code", "review", "done"]


def decide_after_review(state: PipelineState, config: RunConfig) -> Route:
    """Decide whether to run another coding pass or stop.

    Every stopping condition other than approval is a guardrail, so they are
    checked before the verdict: an errored or over-budget run must not be able
    to talk its way into another iteration.
    """
    if state.get("error"):
        return "done"
    if state.get("cost_usd", 0.0) >= config.session_budget:
        return "done"
    if state.get("iteration", 0) >= config.max_iterations:
        return "done"
    if state.get("verdict") == "approved":
        return "done"
    return "code"


def _must_stop(state: PipelineState, config: RunConfig) -> bool:
    """The guardrails that outrank any verdict."""
    return bool(
        state.get("error")
        or state.get("cost_usd", 0.0) >= config.session_budget
        or state.get("iteration", 0) >= config.max_iterations
    )


def decide_after_analysis(state: PipelineState, config: RunConfig) -> AnalysisRoute:
    """Decide where static analysis sends the run.

    Code that fails its thresholds goes straight back to the coder with the
    violations attached, skipping the reviewer entirely: the failure is already
    objective, so paying a model to restate it would be waste.
    """
    if _must_stop(state, config):
        return "done"
    if state.get("analysis_verdict") == "complex":
        return "code"
    return "review"
