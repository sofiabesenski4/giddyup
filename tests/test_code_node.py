import pytest
from claude_agent_sdk import CLINotFoundError

from giddyup.nodes.code import build_options, code_node
from giddyup.state import new_state
from conftest import assistant, fake_query, result, text, tool_use


def test_options_disable_mcp_servers_and_filesystem_settings(config):
    options = build_options(new_state("x"), config)

    assert options.mcp_servers == {}
    assert options.strict_mcp_config is True
    # The SDK default of None loads ~/.claude/settings.json, which would drag
    # the user's global MCP servers and skills into the sandbox.
    assert options.setting_sources == []
    assert options.skills == []


def test_options_carry_the_guardrails_from_config(config):
    options = build_options(new_state("x"), config)

    assert options.permission_mode == "bypassPermissions"
    assert options.max_turns == config.max_turns
    assert options.max_budget_usd == config.budget_per_iteration
    assert str(options.cwd) == str(config.repo)


def test_first_pass_starts_a_fresh_session(config):
    assert build_options(new_state("x"), config).resume is None


def test_revision_pass_resumes_the_existing_session(config):
    state = new_state("x")
    state["session_id"] = "sess_abc"

    assert build_options(state, config).resume == "sess_abc"


async def test_collects_claude_text_into_the_transcript(config):
    state = new_state("build a thing")
    state["plan"] = "PLAN"

    update = await code_node(
        state, config, query_fn=fake_query([assistant(text("did it")), result()])
    )

    assert update["transcript"] == "did it"
    assert update["error"] is None


async def test_records_the_tools_claude_used(config):
    update = await code_node(
        new_state("x"),
        config,
        query_fn=fake_query([assistant(tool_use("Edit"), tool_use("Bash")), result()]),
    )

    assert update["tool_calls"] == ["Edit", "Bash"]


async def test_captures_the_session_id_so_a_revision_can_resume_it(config):
    update = await code_node(
        new_state("x"), config, query_fn=fake_query([result(session_id="sess_xyz")])
    )

    assert update["session_id"] == "sess_xyz"


async def test_accumulates_cost_across_loop_iterations(config):
    state = new_state("x")
    state["cost_usd"] = 1.50

    update = await code_node(state, config, query_fn=fake_query([result(cost=0.75)]))

    assert update["cost_usd"] == pytest.approx(2.25)


async def test_counts_each_pass_so_the_loop_can_terminate(config):
    state = new_state("x")
    state["iteration"] = 2

    update = await code_node(state, config, query_fn=fake_query([result()]))

    assert update["iteration"] == 3


async def test_sends_the_plan_on_the_first_pass(config):
    state = new_state("original ask")
    state["plan"] = "THE PLAN"
    capture: dict = {}

    await code_node(state, config, query_fn=fake_query([result()], capture))

    assert "THE PLAN" in capture["prompt"]


async def test_sends_reviewer_feedback_on_a_revision_pass(config):
    state = new_state("original ask")
    state["plan"] = "THE PLAN"
    state["session_id"] = "sess_abc"
    state["feedback"] = "you forgot the error case"
    capture: dict = {}

    await code_node(state, config, query_fn=fake_query([result()], capture))

    assert "you forgot the error case" in capture["prompt"]


async def test_records_a_missing_cli_as_an_error_instead_of_raising(config):
    def exploding_query(*, prompt, options=None, **_):
        raise CLINotFoundError("claude not found")

    update = await code_node(new_state("x"), config, query_fn=exploding_query)

    assert "claude not found" in update["error"]
