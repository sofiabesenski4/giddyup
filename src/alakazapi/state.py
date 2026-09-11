"""The state threaded through the graph."""

from __future__ import annotations

from typing import Literal, TypedDict

Verdict = Literal["approved", "revise"]


class PipelineState(TypedDict, total=False):
    """One REPL turn's worth of state.

    ``session_id`` is what makes the review loop cheap: it is the Claude Code
    session, so a revision resumes the existing conversation instead of paying
    to re-read the repository.
    """

    prompt: str
    plan: str
    transcript: str
    tool_calls: list[str]
    verdict: Verdict
    feedback: str
    iteration: int
    cost_usd: float
    session_id: str | None
    error: str | None


def new_state(prompt: str) -> PipelineState:
    return PipelineState(
        prompt=prompt,
        plan="",
        transcript="",
        tool_calls=[],
        verdict="revise",
        feedback="",
        iteration=0,
        cost_usd=0.0,
        session_id=None,
        error=None,
    )
