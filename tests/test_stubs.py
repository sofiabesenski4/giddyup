import pytest

from giddyup.nodes.stubs import clean_code_node, complex_code_node, stub_for
from giddyup.state import new_state


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


# ---- the improving stub --------------------------------------------------

from giddyup.nodes.stubs import improving_code_node  # noqa: E402


async def test_improving_stub_starts_out_complex(tmp_path, repo_config):
    await improving_code_node(new_state("x"), repo_config)

    source = (tmp_path / "invoice_processor.rb").read_text()
    assert "elsif opts[:region]" in source, "the first pass should be the tangled version"


async def test_improving_stub_rewrites_cleanly_on_the_second_pass(tmp_path, repo_config):
    state = new_state("x")
    await improving_code_node(state, repo_config)

    state["iteration"] = 1
    state["feedback"] = "average method complexity is 80.6 (limit 20.0)"
    await improving_code_node(state, repo_config)

    source = (tmp_path / "invoice_processor.rb").read_text()
    assert "elsif opts[:region]" not in source, "the second pass should be refactored"


async def test_improving_stub_replaces_the_same_file_rather_than_adding_one(tmp_path, repo_config):
    state = new_state("x")
    await improving_code_node(state, repo_config)
    state["iteration"] = 1
    await improving_code_node(state, repo_config)

    # A second file would leave the tangled version on disk for the analyzer
    # to find, and the run could never converge.
    assert [p.name for p in tmp_path.rglob("*.rb")] == ["invoice_processor.rb"]


async def test_improving_stub_acknowledges_the_feedback_it_was_given(repo_config):
    state = new_state("x")
    state["iteration"] = 1
    state["feedback"] = "9 code smells (limit 3)"

    update = await improving_code_node(state, repo_config)

    assert "refactor" in update["transcript"].lower()


async def test_stub_for_selects_the_improving_stub():
    assert stub_for("improving") is improving_code_node
