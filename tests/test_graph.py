from alakazapi.graph import build_graph
from alakazapi.state import new_state


def counting_code_node(calls: list):
    async def _node(state, config, **_):
        calls.append(state.get("iteration", 0))
        return {
            "transcript": f"pass {state.get('iteration', 0) + 1}",
            "iteration": state.get("iteration", 0) + 1,
            "cost_usd": state.get("cost_usd", 0.0) + 0.10,
            "session_id": "sess_1",
            "error": None,
        }

    return _node


def scripted_review_node(verdicts: list[str]):
    async def _node(state, config, **_):
        verdict = verdicts.pop(0) if verdicts else "approved"
        return {"verdict": verdict, "feedback": "more please" if verdict == "revise" else ""}

    return _node


async def stub_plan_node(state, config, **_):
    return {"plan": "THE PLAN"}


async def test_runs_plan_then_code_then_review_and_stops_on_approval(config):
    calls: list = []
    graph = build_graph(
        config,
        plan=stub_plan_node,
        code=counting_code_node(calls),
        review=scripted_review_node(["approved"]),
    )

    final = await graph.ainvoke(new_state("do it"))

    assert final["plan"] == "THE PLAN"
    assert final["verdict"] == "approved"
    assert len(calls) == 1


async def test_loops_back_into_code_when_the_reviewer_asks_for_a_revision(config):
    calls: list = []
    graph = build_graph(
        config,
        plan=stub_plan_node,
        code=counting_code_node(calls),
        review=scripted_review_node(["revise", "approved"]),
    )

    final = await graph.ainvoke(new_state("do it"))

    assert len(calls) == 2, "code node should run a second time after a revise verdict"
    assert final["iteration"] == 2


async def test_plans_only_once_no_matter_how_many_revisions(config):
    plans = []

    async def counting_plan(state, config, **_):
        plans.append(1)
        return {"plan": "THE PLAN"}

    graph = build_graph(
        config,
        plan=counting_plan,
        code=counting_code_node([]),
        review=scripted_review_node(["revise", "revise", "approved"]),
    )

    await graph.ainvoke(new_state("do it"))

    assert len(plans) == 1


async def test_stops_at_max_iterations_when_the_reviewer_never_approves(config):
    calls: list = []
    capped = config.__class__(**{**config.__dict__, "max_iterations": 2})
    graph = build_graph(
        capped,
        plan=stub_plan_node,
        code=counting_code_node(calls),
        review=scripted_review_node(["revise"] * 10),
    )

    final = await graph.ainvoke(new_state("do it"))

    assert len(calls) == 2
    assert final["iteration"] == 2


async def test_stops_immediately_when_the_code_node_reports_an_error(config):
    async def failing_code(state, config, **_):
        return {"error": "CLINotFoundError: no claude", "iteration": state.get("iteration", 0) + 1}

    graph = build_graph(
        config,
        plan=stub_plan_node,
        code=failing_code,
        review=scripted_review_node(["revise"] * 10),
    )

    final = await graph.ainvoke(new_state("do it"))

    assert final["error"] == "CLINotFoundError: no claude"
    assert final["iteration"] == 1
