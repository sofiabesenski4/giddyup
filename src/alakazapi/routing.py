"""The conditional edge out of the review node."""

from __future__ import annotations

from typing import Literal

from .config import RunConfig
from .state import PipelineState

Route = Literal["code", "done"]


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
