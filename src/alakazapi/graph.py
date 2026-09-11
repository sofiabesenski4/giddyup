"""Graph wiring. No I/O, no model calls — just nodes and edges."""

from __future__ import annotations

from typing import Any, Callable

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .config import RunConfig
from .nodes.analyze import analyze_node
from .nodes.code import code_node
from .nodes.plan import plan_node
from .nodes.review import review_node
from .routing import decide_after_analysis, decide_after_review
from .state import PipelineState


def build_graph(
    config: RunConfig,
    plan: Callable[..., Any] = plan_node,
    code: Callable[..., Any] = code_node,
    analyze: Callable[..., Any] = analyze_node,
    review: Callable[..., Any] = review_node,
    emit: Callable[[dict], None] | None = None,
):
    """Wire plan → code → analyze → review, with two ways back into code.

    Static analysis short-circuits past the reviewer when the code fails its
    thresholds, so a failing loop costs no model tokens and the coder gets the
    violations directly.

    The nodes are parameters so the control flow can be tested without a model,
    an API key, an analyzer, or a repository.
    """
    graph = StateGraph(PipelineState)

    def writer() -> Callable[[dict], None] | None:
        # LangGraph's stream writer only resolves inside a running graph, hence
        # the guard — an injected emit (or none at all) still works in tests.
        if emit is not None:
            return emit
        try:
            return get_stream_writer()
        except Exception:
            return None

    async def plan_step(state: PipelineState) -> dict:
        return await plan(state, config)

    async def code_step(state: PipelineState) -> dict:
        return await code(state, config, emit=writer())

    async def analyze_step(state: PipelineState) -> dict:
        return await analyze(state, config, emit=writer())

    async def review_step(state: PipelineState) -> dict:
        return await review(state, config)

    graph.add_node("plan", plan_step)
    graph.add_node("code", code_step)
    graph.add_node("analyze", analyze_step)
    graph.add_node("review", review_step)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "code")
    graph.add_edge("code", "analyze")
    graph.add_conditional_edges(
        "analyze",
        lambda state: decide_after_analysis(state, config),
        {"code": "code", "review": "review", "done": END},
    )
    graph.add_conditional_edges(
        "review",
        lambda state: decide_after_review(state, config),
        {"code": "code", "done": END},
    )

    return graph.compile()
