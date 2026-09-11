"""The Claude Code node — the only node that touches the filesystem."""

from __future__ import annotations

from typing import Any, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    query,
)

from ..config import RunConfig
from ..state import PipelineState

FIRST_PASS = """\
{plan}

Work in the repository at {repo}. When you are done, summarise what you changed."""

REVISION = """\
A reviewer rejected the previous attempt with this feedback:

{feedback}

Address it. The original task was:

{plan}"""


def build_options(state: PipelineState, config: RunConfig) -> ClaudeAgentOptions:
    """Build the SDK options for one coding pass.

    The isolation settings are not decorative. ``setting_sources`` defaults to
    ``None``, which loads every filesystem settings file including
    ``~/.claude/settings.json`` — so without the explicit ``[]`` this node would
    silently inherit the user's global MCP servers. ``skills=[]`` is the same
    story for skills.
    """
    return ClaudeAgentOptions(
        cwd=str(config.repo),
        model=config.code_model,
        permission_mode="bypassPermissions",
        mcp_servers={},
        strict_mcp_config=True,
        setting_sources=[],
        skills=[],
        max_turns=config.max_turns,
        max_budget_usd=config.budget_per_iteration,
        resume=state.get("session_id"),
    )


def build_prompt(state: PipelineState, config: RunConfig) -> str:
    plan = state.get("plan") or state["prompt"]
    if state.get("session_id") and state.get("feedback"):
        return REVISION.format(feedback=state["feedback"], plan=plan)
    return FIRST_PASS.format(plan=plan, repo=config.repo)


async def code_node(
    state: PipelineState,
    config: RunConfig,
    query_fn: Callable[..., Any] = query,
    emit: Callable[[dict], None] | None = None,
) -> dict:
    """Run one Claude Code pass and fold the outcome back into state."""
    chunks: list[str] = []
    tools: list[str] = []
    session_id = state.get("session_id")
    spent = 0.0

    def publish(event: dict) -> None:
        if emit is not None:
            emit(event)

    try:
        async for message in query_fn(prompt=build_prompt(state, config), options=build_options(state, config)):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
                        publish({"type": "text", "text": block.text})
                    elif isinstance(block, ToolUseBlock):
                        tools.append(block.name)
                        publish({"type": "tool", "name": block.name, "input": block.input})
                    elif isinstance(block, ThinkingBlock):
                        publish({"type": "thinking"})
            elif isinstance(message, ResultMessage):
                session_id = message.session_id or session_id
                spent = message.total_cost_usd or 0.0
    except ClaudeSDKError as exc:
        publish({"type": "error", "text": str(exc)})
        return {"error": f"{type(exc).__name__}: {exc}", "iteration": state.get("iteration", 0) + 1}

    return {
        "transcript": "\n".join(chunks).strip(),
        "tool_calls": tools,
        "session_id": session_id,
        "cost_usd": state.get("cost_usd", 0.0) + spent,
        "iteration": state.get("iteration", 0) + 1,
        "error": None,
    }
