from giddyup.graph import build_graph
from giddyup.state import new_state


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


def stub_analyze_node(verdict="clean", calls=None):
    async def _node(state, config, **_):
        if calls is not None:
            calls.append(state.get("iteration", 0))
        return {"analysis_verdict": verdict, "analysis": {}}

    return _node


async def test_runs_plan_then_code_then_review_and_stops_on_approval(config):
    calls: list = []
    graph = build_graph(
        config,
        plan=stub_plan_node,
        code=counting_code_node(calls),
        analyze=stub_analyze_node(),
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
        analyze=stub_analyze_node(),
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
        analyze=stub_analyze_node(),
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
        analyze=stub_analyze_node(),
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
        analyze=stub_analyze_node(),
        review=scripted_review_node(["revise"] * 10),
    )

    final = await graph.ainvoke(new_state("do it"))

    assert final["error"] == "CLINotFoundError: no claude"
    assert final["iteration"] == 1


# ---- the static analysis gate --------------------------------------------

async def test_complex_analysis_returns_to_the_coder_without_paying_the_reviewer(config):
    code_calls: list = []
    reviewed = []

    async def counting_review(state, config, **_):
        reviewed.append(1)
        return {"verdict": "approved", "feedback": ""}

    capped = config.__class__(**{**config.__dict__, "max_iterations": 2})
    graph = build_graph(
        capped,
        plan=stub_plan_node,
        code=counting_code_node(code_calls),
        analyze=stub_analyze_node("complex"),
        review=counting_review,
    )

    final = await graph.ainvoke(new_state("do it"))

    assert len(code_calls) == 2, "complex analysis should drive another coding pass"
    assert reviewed == [], "the reviewer must be skipped entirely when analysis fails"
    assert final["analysis_verdict"] == "complex"


async def test_clean_analysis_reaches_the_reviewer(config):
    reviewed = []

    async def counting_review(state, config, **_):
        reviewed.append(1)
        return {"verdict": "approved", "feedback": ""}

    graph = build_graph(
        config,
        plan=stub_plan_node,
        code=counting_code_node([]),
        analyze=stub_analyze_node("clean"),
        review=counting_review,
    )

    final = await graph.ainvoke(new_state("do it"))

    assert reviewed == [1]
    assert final["verdict"] == "approved"


async def test_analysis_runs_on_every_coding_pass(config):
    analysed: list = []
    graph = build_graph(
        config,
        plan=stub_plan_node,
        code=counting_code_node([]),
        analyze=stub_analyze_node("clean", analysed),
        review=scripted_review_node(["revise", "approved"]),
    )

    await graph.ainvoke(new_state("do it"))

    assert len(analysed) == 2, "each coding pass should be re-analysed"
