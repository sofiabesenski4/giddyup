"""The reviewer node: decide whether the coding pass actually landed."""

from __future__ import annotations

from typing import Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from ..config import RunConfig
from ..state import PipelineState


class Review(BaseModel):
    """The reviewer's structured verdict."""

    verdict: Literal["approved", "revise"] = Field(
        description="approved if the request is satisfied, revise if another pass is needed"
    )
    feedback: str = Field(
        default="", description="What still needs doing. Required when the verdict is revise."
    )


SYSTEM = """\
You review the work of a coding agent. Judge only whether the original request was \
satisfied by what the agent reports doing.

Approve if it was. Ask for a revision only when something concrete is missing, and say \
exactly what. Do not ask for polish, extra tests, or refactoring that the request did \
not call for."""

TEMPLATE = """Original request:
{prompt}

Tools the agent used: {tools}

What the agent reports doing:
{transcript}"""


def _default_llm_call(config: RunConfig) -> Callable[[str], Awaitable[Review]]:
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(model=config.planner_model, max_tokens=2000).with_structured_output(Review)

    async def _call(prompt: str) -> Review:
        return await llm.ainvoke([("system", SYSTEM), ("user", prompt)])

    return _call


async def review_node(
    state: PipelineState,
    config: RunConfig,
    llm_call: Callable[[str], Awaitable[Review]] | None = None,
) -> dict:
    """Judge the last coding pass.

    A run that errored is not worth paying a reviewer to look at — the routing
    layer will stop the loop regardless, so return a verdict without calling out.
    """
    if state.get("error"):
        return {"verdict": "revise", "feedback": state["error"]}

    call = llm_call or _default_llm_call(config)
    review = await call(
        TEMPLATE.format(
            prompt=state["prompt"],
            tools=", ".join(state.get("tool_calls") or []) or "none",
            transcript=state.get("transcript") or "(the agent produced no summary)",
        )
    )
    return {"verdict": review.verdict, "feedback": review.feedback}
