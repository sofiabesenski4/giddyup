"""End-to-end through the real graph against a live Ruby analyzer.

Only the Claude Code coder is stubbed. The analyzer is the real service over
HTTP, so these tests prove that static analysis genuinely distinguishes clean
from overcomplicated Ruby — not that a fake said it did.

Skipped automatically when the analyzer is not running:
    ./bin/analyzer
"""

import json
import urllib.error
import urllib.request

import pytest

from giddyup.graph import build_graph
from giddyup.nodes.analyze import _post
from giddyup.nodes.stubs import clean_code_node, complex_code_node
from giddyup.sandbox import BASELINE, create_sandbox
from giddyup.state import new_state

ANALYZER_URL = "http://localhost:9292"


def analyzer_running() -> bool:
    try:
        with urllib.request.urlopen(f"{ANALYZER_URL}/health", timeout=2) as r:
            return json.loads(r.read())["status"] == "ok"
    except (OSError, urllib.error.URLError, ValueError, KeyError):
        return False


pytestmark = pytest.mark.skipif(
    not analyzer_running(), reason="Ruby analyzer not running (start it with ./bin/analyzer)"
)


@pytest.fixture
def repo_config(tmp_path, config):
    return config.__class__(
        **{**config.__dict__, "repo": tmp_path, "analyzer_url": ANALYZER_URL, "max_iterations": 3}
    )


async def stub_plan(state, config, **_):
    return {"plan": "write an invoice calculator"}


def counting_review(calls):
    async def _review(state, config, **_):
        calls.append(state.get("iteration"))
        return {"verdict": "approved", "feedback": ""}

    return _review


async def test_clean_ruby_passes_analysis_and_reaches_the_reviewer(repo_config):
    reviewed: list = []
    events: list = []
    graph = build_graph(
        repo_config,
        plan=stub_plan,
        code=clean_code_node,
        review=counting_review(reviewed),
        emit=events.append,
    )

    final = await graph.ainvoke(new_state("build an invoice calculator"))

    assert final["analysis_verdict"] == "clean"
    assert reviewed == [1], "clean code should reach the reviewer exactly once"
    assert final["verdict"] == "approved"
    assert final["iteration"] == 1


async def test_overcomplicated_ruby_fails_analysis_and_returns_to_the_coder(repo_config):
    reviewed: list = []
    events: list = []
    graph = build_graph(
        repo_config,
        plan=stub_plan,
        code=complex_code_node,
        review=counting_review(reviewed),
        emit=events.append,
    )

    final = await graph.ainvoke(new_state("build an invoice calculator"))

    assert final["analysis_verdict"] == "complex"
    assert reviewed == [], "the reviewer must never be reached when analysis fails"
    assert final["iteration"] == 3, "should loop back into code until max_iterations"


async def test_the_coder_is_told_what_was_wrong(repo_config):
    graph = build_graph(
        repo_config, plan=stub_plan, code=complex_code_node, review=counting_review([])
    )

    final = await graph.ainvoke(new_state("build an invoice calculator"))

    feedback = final["feedback"]
    assert "invoice_processor.rb" in feedback
    assert "flog_average" in feedback or "smells" in feedback
    assert "limit" in feedback


async def test_the_real_analyzer_measured_the_real_file(repo_config):
    graph = build_graph(
        repo_config, plan=stub_plan, code=complex_code_node, review=counting_review([])
    )

    final = await graph.ainvoke(new_state("x"))

    measured = final["analysis"]["files"][0]
    assert measured["flog_average"] > 20, "the tangled stub should score badly on flog"
    assert measured["smells"] > 3


# ---- convergence ---------------------------------------------------------

from giddyup.nodes.stubs import improving_code_node  # noqa: E402


async def test_the_refactored_stub_actually_passes_the_real_analyzer(repo_config):
    """The point of the improving stub is that the second version is genuinely
    clean by the analyzer's own measure — not merely different."""
    reviewed: list = []
    graph = build_graph(
        repo_config, plan=stub_plan, code=improving_code_node, review=counting_review(reviewed)
    )

    final = await graph.ainvoke(new_state("build an invoice calculator"))

    assert final["analysis_verdict"] == "clean"
    assert final["analysis"]["files"][0]["flog_average"] <= 20
    assert final["analysis"]["files"][0]["smells"] <= 3


async def test_the_run_converges_on_the_second_pass(repo_config):
    reviewed: list = []
    graph = build_graph(
        repo_config, plan=stub_plan, code=improving_code_node, review=counting_review(reviewed)
    )

    final = await graph.ainvoke(new_state("build an invoice calculator"))

    assert final["iteration"] == 2, "one failing pass, then one that passes"
    assert reviewed == [2], "the reviewer should be reached once, after the refactor"
    assert final["verdict"] == "approved"


async def test_the_failing_first_pass_still_hands_back_violations(repo_config):
    """Convergence must not skip the feedback step — the coder is told what was
    wrong before it gets the chance to fix it."""
    seen: list = []

    async def capture_feedback(state, config, **kwargs):
        seen.append(state.get("feedback", ""))
        return await improving_code_node(state, config, **kwargs)

    graph = build_graph(
        repo_config, plan=stub_plan, code=capture_feedback, review=counting_review([])
    )

    await graph.ainvoke(new_state("build an invoice calculator"))

    assert seen[0] == "", "nothing to report before the first pass"
    assert "invoice_processor.rb" in seen[1], "the second pass should see the violations"


# ---- sandbox topology -----------------------------------------------------


@pytest.fixture
def sandbox_config(tmp_path, config):
    """A generated sandbox: its own git repo, with a clean baseline committed.

    This is the production topology — a repository the enclosing checkout
    ignores — which tmp_path alone cannot reproduce.
    """
    sandbox = create_sandbox(tmp_path / "sandbox")
    return config.__class__(
        **{
            **config.__dict__,
            "repo": sandbox,
            "analyzer_url": ANALYZER_URL,
            "max_iterations": 3,
        }
    )


async def test_the_gate_judges_only_the_agents_diff_not_the_baseline(sandbox_config):
    events: list = []
    graph = build_graph(
        sandbox_config,
        plan=stub_plan,
        code=clean_code_node,
        review=counting_review([]),
        emit=events.append,
    )

    await graph.ainvoke(new_state("write an invoice calculator"))

    analysis = [e for e in events if e.get("type") == "analysis"]
    assert analysis[0]["verdict"] == "clean"
    reported = {f["path"] for f in analysis[0]["files"]}
    assert reported == {"invoice.rb"}, (
        f"expected only the agent's file, got {reported} — the committed "
        "baseline must not be re-judged"
    )


async def test_overcomplicated_ruby_in_a_sandbox_fails_the_gate(sandbox_config):
    events: list = []
    graph = build_graph(
        sandbox_config,
        plan=stub_plan,
        code=complex_code_node,
        review=counting_review([]),
        emit=events.append,
    )

    await graph.ainvoke(new_state("write an invoice calculator"))

    analysis = [e for e in events if e.get("type") == "analysis"]
    assert analysis[0]["verdict"] == "complex"
    assert {f["path"] for f in analysis[0]["files"]} == {"invoice_processor.rb"}


def test_the_generated_baseline_passes_the_analyzer(config):
    """Guards the constraint that every other test leans on.

    If the baseline ever drifts into violating the thresholds, a failure
    elsewhere stops being attributable to the coding pass — and in the
    scan-fallback path the baseline is analysed alongside the agent's work.
    """
    report = _post(
        f"{ANALYZER_URL}/analyze",
        {
            "files": [
                {"path": name, "source": source}
                for name, source in BASELINE.items()
                if name.endswith(".rb")
            ],
            "thresholds": {
                "flog_average": config.flog_average_limit,
                "smells": config.smells_limit,
            },
        },
    )

    assert report["verdict"] == "clean", report
