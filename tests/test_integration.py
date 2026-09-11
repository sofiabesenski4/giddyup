"""End-to-end wiring: the real nodes, the real graph, only the SDK and the
planner/reviewer model calls faked at their boundaries."""

from functools import partial

from alakazapi.graph import build_graph
from alakazapi.nodes.code import code_node
from alakazapi.nodes.plan import plan_node
from alakazapi.nodes.review import Review, review_node
from alakazapi.state import new_state
from conftest import assistant, fake_query, result, text, tool_use


async def test_a_full_run_plans_codes_reviews_and_reports_cost(config):
    verdicts = [Review(verdict="revise", feedback="no tests"), Review(verdict="approved", feedback="")]

    async def planner(_prompt):
        return "1. edit main.py"

    async def reviewer(_prompt):
        return verdicts.pop(0)

    events: list[dict] = []
    graph = build_graph(
        config,
        plan=partial(plan_node, llm_call=planner),
        code=partial(
            code_node,
            query_fn=fake_query(
                [assistant(text("done"), tool_use("Edit", file_path="main.py")), result(cost=0.40)]
            ),
        ),
        review=partial(review_node, llm_call=reviewer),
        emit=events.append,
    )

    final = await graph.ainvoke(new_state("fix main.py"))

    assert final["plan"] == "1. edit main.py"
    assert final["verdict"] == "approved"
    assert final["iteration"] == 2, "should have looped once after the revise verdict"
    assert final["cost_usd"] == 0.80, "cost accumulates across both passes"
    assert final["session_id"] == "sess_1"
    assert {e["type"] for e in events} == {"text", "tool"}
