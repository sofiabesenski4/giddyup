from giddyup.render import render_event, render_summary
from giddyup.state import new_state


def test_renders_claude_text_as_plain_output():
    assert render_event({"type": "text", "text": "hello"}) == "hello"


def test_renders_a_tool_call_with_its_name():
    line = render_event({"type": "tool", "name": "Edit", "input": {"file_path": "/a/b.py"}})

    assert "Edit" in line
    assert "b.py" in line


def test_renders_a_bash_tool_call_with_the_command():
    line = render_event({"type": "tool", "name": "Bash", "input": {"command": "pytest -q"}})

    assert "pytest -q" in line


def test_tool_call_detail_is_truncated_so_one_call_cannot_flood_the_terminal():
    line = render_event({"type": "tool", "name": "Write", "input": {"content": "x" * 500}})

    assert len(line) < 200


def test_ignores_events_it_has_no_rendering_for():
    assert render_event({"type": "thinking"}) is None


def test_summary_reports_cost_and_iterations():
    state = new_state("x")
    state.update(iteration=2, cost_usd=1.2345, verdict="approved")

    summary = render_summary(state)

    assert "$1.23" in summary
    assert "2" in summary
    assert "approved" in summary


def test_summary_leads_with_the_error_when_the_run_failed():
    state = new_state("x")
    state.update(iteration=1, cost_usd=0.0, error="CLINotFoundError: no claude")

    assert "CLINotFoundError: no claude" in render_summary(state)


# ---- analysis events -----------------------------------------------------

def test_renders_a_clean_analysis_verdict():
    line = render_event({"type": "analysis", "verdict": "clean", "detail": "2 file(s)"})

    assert "clean" in line
    assert "2 file(s)" in line


def test_renders_a_complex_verdict_with_the_violations():
    line = render_event(
        {
            "type": "analysis",
            "verdict": "complex",
            "detail": "1 file(s)",
            "files": [
                {
                    "path": "a.rb",
                    "violations": [{"rule": "smells", "message": "9 code smells (limit 3)"}],
                }
            ],
        }
    )

    assert "a.rb" in line
    assert "9 code smells" in line


def test_a_clean_verdict_does_not_list_files():
    line = render_event(
        {"type": "analysis", "verdict": "clean", "detail": "1 file(s)",
         "files": [{"path": "a.rb", "violations": []}]}
    )

    assert "a.rb" not in line
