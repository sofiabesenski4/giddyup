from giddyup.nodes.plan import plan_node
from giddyup.nodes.review import Review, review_node
from giddyup.state import new_state


def recorder(returns):
    """An injectable stand-in for the LLM call that records its prompt."""
    seen: dict = {}

    async def _call(prompt: str):
        seen["prompt"] = prompt
        return returns

    return _call, seen


async def test_plan_node_returns_the_planners_task_spec(config):
    call, _ = recorder("1. read the file\n2. fix the bug")

    update = await plan_node(new_state("fix the bug"), config, llm_call=call)

    assert update["plan"] == "1. read the file\n2. fix the bug"


async def test_plan_node_passes_the_users_prompt_to_the_planner(config):
    call, seen = recorder("spec")

    await plan_node(new_state("make the tests pass"), config, llm_call=call)

    assert "make the tests pass" in seen["prompt"]


async def test_review_node_reports_an_approval(config):
    call, _ = recorder(Review(verdict="approved", feedback=""))
    state = new_state("x")
    state["transcript"] = "I fixed it"

    update = await review_node(state, config, llm_call=call)

    assert update["verdict"] == "approved"


async def test_review_node_reports_a_revision_with_feedback(config):
    call, _ = recorder(Review(verdict="revise", feedback="tests still fail"))
    state = new_state("x")
    state["transcript"] = "I sort of fixed it"

    update = await review_node(state, config, llm_call=call)

    assert update["verdict"] == "revise"
    assert update["feedback"] == "tests still fail"


async def test_review_node_shows_the_reviewer_what_claude_actually_did(config):
    call, seen = recorder(Review(verdict="approved", feedback=""))
    state = new_state("fix the bug")
    state["transcript"] = "edited main.py"
    state["tool_calls"] = ["Edit"]

    await review_node(state, config, llm_call=call)

    assert "edited main.py" in seen["prompt"]
    assert "fix the bug" in seen["prompt"]


async def test_review_node_does_not_spend_money_reviewing_a_failed_run(config):
    called = False

    async def should_not_run(prompt):
        nonlocal called
        called = True
        return Review(verdict="approved", feedback="")

    state = new_state("x")
    state["error"] = "CLINotFoundError: claude not found"

    update = await review_node(state, config, llm_call=should_not_run)

    assert called is False
    assert update["verdict"] == "revise"
