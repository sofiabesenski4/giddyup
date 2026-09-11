"""Graph wiring. No I/O, no model calls — just nodes and edges."""

from __future__ import annotations

from typing import Any, Callable

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .config import RunConfig
from .nodes.code import code_node
from .nodes.plan import plan_node
from .nodes.review import review_node
from .routing import decide_after_review
from .state import PipelineState


def build_graph(
    config: RunConfig,
    plan: Callable[..., Any] = plan_node,
    code: Callable[..., Any] = code_node,
    review: Callable[..., Any] = review_node,
    emit: Callable[[dict], None] | None = None,
):
    """Wire plan → code → review with a revision loop back into code.

    The nodes are parameters so the graph's control flow can be tested without a
    model, an API key, or a repository.

    Config is bound positionally through closures rather than via keyword. The
    name ``config`` is reserved by LangGraph for the ``RunnableConfig`` it injects
    into any node that declares it, so binding it by keyword collides with that
    machinery.
    """
    graph = StateGraph(PipelineState)

    async def plan_step(state: PipelineState) -> dict:
        return await plan(state, config)

    async def code_step(state: PipelineState) -> dict:
        # Fall back to LangGraph's custom-stream writer so the REPL sees tool
        # calls as they happen. It only resolves inside a running graph, hence
        # the guard — an injected emit (or none at all) still works in tests.
        writer = emit
        if writer is None:
            try:
                writer = get_stream_writer()
            except Exception:
                writer = None
        return await code(state, config, emit=writer)

    async def review_step(state: PipelineState) -> dict:
        return await review(state, config)

    def route(state: PipelineState) -> str:
        return decide_after_review(state, config)

    graph.add_node("plan", plan_step)
    graph.add_node("code", code_step)
    graph.add_node("review", review_step)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "code")
    graph.add_edge("code", "review")
    graph.add_conditional_edges("review", route, {"code": "code", "done": END})

    return graph.compile()
