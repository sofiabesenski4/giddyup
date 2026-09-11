from alakazapi.repl import run_turn


class FakeGraph:
    """Stands in for a compiled graph, yielding the (mode, payload) pairs
    LangGraph produces for stream_mode=["custom", "values"]."""

    def __init__(self, chunks):
        self._chunks = chunks

    def astream(self, *_args, **_kwargs):
        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


async def test_prints_streamed_events_as_they_arrive():
    lines: list[str] = []
    graph = FakeGraph(
        [
            ("custom", {"type": "text", "text": "working"}),
            ("custom", {"type": "tool", "name": "Edit", "input": {"file_path": "a.py"}}),
            ("values", {"verdict": "approved", "iteration": 1, "cost_usd": 0.5}),
        ]
    )

    await run_turn(graph, "do it", out=lines.append)

    assert "working" in lines[0]
    assert "Edit" in lines[1]


async def test_returns_the_final_state():
    graph = FakeGraph([("values", {"verdict": "approved", "iteration": 2, "cost_usd": 0.5})])

    final = await run_turn(graph, "do it", out=lambda _: None)

    assert final["iteration"] == 2


async def test_closes_with_a_summary_line():
    lines: list[str] = []
    graph = FakeGraph([("values", {"verdict": "approved", "iteration": 1, "cost_usd": 0.5})])

    await run_turn(graph, "do it", out=lines.append)

    assert "$0.50" in lines[-1]


async def test_a_cancelled_turn_reports_rather_than_propagating():
    class CancellingGraph:
        def astream(self, *_a, **_k):
            async def _gen():
                raise KeyboardInterrupt
                yield  # pragma: no cover

            return _gen()

    lines: list[str] = []

    final = await run_turn(CancellingGraph(), "do it", out=lines.append)

    assert final is None
    assert any("interrupted" in line.lower() for line in lines)


async def test_a_failing_turn_reports_rather_than_killing_the_repl():
    """A bad API key, a network blip, or a node raising must return the user to
    the prompt — the REPL is a top-level loop and has nowhere to escalate to."""

    class ExplodingGraph:
        def astream(self, *_a, **_k):
            async def _gen():
                raise RuntimeError("Error code: 401 - API key is invalid.")
                yield  # pragma: no cover

            return _gen()

    lines: list[str] = []

    final = await run_turn(ExplodingGraph(), "do it", out=lines.append)

    assert final is None
    assert any("401" in line for line in lines), "the user needs to see what went wrong"


async def test_a_failing_turn_names_the_error_type():
    class ExplodingGraph:
        def astream(self, *_a, **_k):
            async def _gen():
                raise ValueError("bad config")
                yield  # pragma: no cover

            return _gen()

    lines: list[str] = []
    await run_turn(ExplodingGraph(), "do it", out=lines.append)

    assert any("ValueError" in line for line in lines)
