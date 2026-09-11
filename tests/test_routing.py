from alakazapi.config import RunConfig
from alakazapi.routing import decide_after_review
from alakazapi.state import new_state
from pathlib import Path


def config(**kw) -> RunConfig:
    return RunConfig(repo=Path("/tmp"), **kw)


def state(**kw):
    s = new_state("do the thing")
    s.update(kw)
    return s


def test_finishes_when_the_reviewer_approves():
    assert decide_after_review(state(verdict="approved", iteration=1), config()) == "done"


def test_loops_back_to_code_when_the_reviewer_asks_for_a_revision():
    assert decide_after_review(state(verdict="revise", iteration=1), config()) == "code"


def test_stops_looping_once_max_iterations_is_reached():
    s = state(verdict="revise", iteration=3)

    assert decide_after_review(s, config(max_iterations=3)) == "done"


def test_stops_looping_when_the_session_budget_is_exhausted():
    s = state(verdict="revise", iteration=1, cost_usd=10.50)

    assert decide_after_review(s, config(session_budget=10.00)) == "done"


def test_finishes_immediately_when_a_node_recorded_an_error():
    s = state(verdict="revise", iteration=1, error="claude CLI not found")

    assert decide_after_review(s, config()) == "done"
