import pytest

from alakazapi.nodes.stubs import clean_code_node, complex_code_node, stub_for
from alakazapi.state import new_state


@pytest.fixture
def repo_config(tmp_path, config):
    return config.__class__(**{**config.__dict__, "repo": tmp_path})


async def test_clean_stub_writes_ruby_into_the_repo(tmp_path, repo_config):
    await clean_code_node(new_state("x"), repo_config)

    written = list(tmp_path.rglob("*.rb"))
    assert written, "the stub must write real Ruby for the analyzer to read"


async def test_complex_stub_writes_ruby_into_the_repo(tmp_path, repo_config):
    await complex_code_node(new_state("x"), repo_config)

    assert list(tmp_path.rglob("*.rb"))


async def test_stubs_cost_nothing(repo_config):
    update = await complex_code_node(new_state("x"), repo_config)

    assert update["cost_usd"] == 0.0


async def test_stubs_match_the_real_nodes_return_shape(repo_config):
    update = await clean_code_node(new_state("x"), repo_config)

    assert set(update) >= {
        "transcript", "tool_calls", "session_id", "cost_usd", "iteration", "error"
    }
    assert update["error"] is None


async def test_stubs_advance_the_iteration_counter(repo_config):
    state = new_state("x")
    state["iteration"] = 1

    update = await clean_code_node(state, repo_config)

    assert update["iteration"] == 2


async def test_complex_stub_stays_complex_across_revisions(tmp_path, repo_config):
    state = new_state("x")
    await complex_code_node(state, repo_config)
    first = (tmp_path / "invoice_processor.rb").read_text()

    state["iteration"] = 1
    state["feedback"] = "too complicated, simplify it"
    await complex_code_node(state, repo_config)

    assert (tmp_path / "invoice_processor.rb").read_text() == first, (
        "the complex stub must not improve, so the loop is observable"
    )


async def test_stubs_report_the_tools_a_real_agent_would_have_used(repo_config):
    update = await clean_code_node(new_state("x"), repo_config)

    assert "Write" in update["tool_calls"]


async def test_stub_for_selects_by_name():
    assert stub_for("clean") is clean_code_node
    assert stub_for("complex") is complex_code_node


def test_stub_for_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="unknown stub"):
        stub_for("banana")


async def test_stubs_emit_events_like_the_real_node(repo_config):
    events: list = []

    await clean_code_node(new_state("x"), repo_config, emit=events.append)

    assert {e["type"] for e in events} == {"text", "tool"}
