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


# ---- the analysis gate ---------------------------------------------------

from alakazapi.routing import decide_after_analysis  # noqa: E402


def test_complex_code_goes_straight_back_to_the_coder_skipping_the_reviewer():
    s = state(analysis_verdict="complex", iteration=1)

    assert decide_after_analysis(s, config()) == "code"


def test_clean_code_proceeds_to_the_reviewer():
    s = state(analysis_verdict="clean", iteration=1)

    assert decide_after_analysis(s, config()) == "review"


def test_skipped_analysis_proceeds_to_the_reviewer():
    s = state(analysis_verdict="skipped", iteration=1)

    assert decide_after_analysis(s, config()) == "review"


def test_complex_code_stops_rather_than_looping_past_max_iterations():
    s = state(analysis_verdict="complex", iteration=3)

    assert decide_after_analysis(s, config(max_iterations=3)) == "done"


def test_complex_code_stops_when_the_session_budget_is_exhausted():
    s = state(analysis_verdict="complex", iteration=1, cost_usd=10.5)

    assert decide_after_analysis(s, config(session_budget=10.0)) == "done"


def test_an_errored_run_stops_without_reaching_the_reviewer():
    s = state(analysis_verdict="clean", iteration=1, error="boom")

    assert decide_after_analysis(s, config()) == "done"
