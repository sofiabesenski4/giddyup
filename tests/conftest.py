from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from alakazapi.config import RunConfig


@pytest.fixture
def config(tmp_path) -> RunConfig:
    return RunConfig(repo=tmp_path)


def assistant(*blocks) -> AssistantMessage:
    return AssistantMessage(content=list(blocks), model="claude-opus-5")


def text(s: str) -> TextBlock:
    return TextBlock(text=s)


def tool_use(name: str, **kw) -> ToolUseBlock:
    return ToolUseBlock(id="tu_1", name=name, input=kw)


def result(session_id: str = "sess_1", cost: float = 0.0) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=10,
        duration_api_ms=8,
        is_error=False,
        num_turns=1,
        session_id=session_id,
        total_cost_usd=cost,
    )


def fake_query(messages, capture: dict | None = None):
    """Build a stand-in for claude_agent_sdk.query that yields `messages`."""

    async def _query(*, prompt, options=None, **_):
        if capture is not None:
            capture["prompt"] = prompt
            capture["options"] = options
        for m in messages:
            yield m

    return _query
