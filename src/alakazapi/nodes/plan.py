"""The planner node: turn a loose prompt into a concrete task spec."""

from __future__ import annotations

from typing import Awaitable, Callable

from ..config import RunConfig
from ..state import PipelineState

SYSTEM = """\
You turn a developer's informal request into a concrete task spec for a coding agent \
that has filesystem and shell access to a repository.

Write numbered steps. Be specific about files and commands where you can infer them. \
Do not write the code yourself, and do not pad the spec with caveats. \
If the request is already precise, restate it and stop."""

TEMPLATE = """Repository: {repo}

Request:
{prompt}"""


def _default_llm_call(config: RunConfig) -> Callable[[str], Awaitable[str]]:
    from langchain_anthropic import ChatAnthropic

    llm = ChatAnthropic(model=config.planner_model, max_tokens=2000)

    async def _call(prompt: str) -> str:
        response = await llm.ainvoke([("system", SYSTEM), ("user", prompt)])
        return response.text() if callable(getattr(response, "text", None)) else str(response.content)

    return _call


async def plan_node(
    state: PipelineState,
    config: RunConfig,
    llm_call: Callable[[str], Awaitable[str]] | None = None,
) -> dict:
    call = llm_call or _default_llm_call(config)
    plan = await call(TEMPLATE.format(repo=config.repo, prompt=state["prompt"]))
    return {"plan": plan}
