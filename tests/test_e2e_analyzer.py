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

from alakazapi.graph import build_graph
from alakazapi.nodes.stubs import clean_code_node, complex_code_node
from alakazapi.state import new_state

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
