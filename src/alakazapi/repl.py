"""The terminal loop. The only module that reads stdin or writes stdout."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from .config import RunConfig
from .graph import build_graph
from .render import BOLD, DIM, RED, RESET, render_event, render_summary
from .state import PipelineState, new_state

BANNER = f"""{BOLD}AlakazAPI{RESET} {DIM}— plan → code → analyze → review{RESET}
{DIM}repo:     {{repo}}
coder:    {{coder}}
analyzer: {{analyzer}}
caps:     {{iterations}} iterations · ${{per_iter}}/iteration · ${{session}}/session · MCP off
type a prompt, or /exit to quit{RESET}
"""


async def run_turn(
    graph: Any,
    prompt: str,
    out: Callable[[str], None] = print,
) -> PipelineState | None:
    """Run one prompt through the graph, printing events as they stream.

    Returns the final state, or None if the user interrupted the run — an
    interrupted turn must return control to the prompt rather than tear down
    the REPL.
    """
    final: PipelineState | None = None

    try:
        async for mode, payload in graph.astream(
            new_state(prompt), stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                line = render_event(payload)
                if line is not None:
                    out(line)
            elif mode == "values":
                final = payload
    except (KeyboardInterrupt, asyncio.CancelledError):
        out(f"{DIM}  interrupted{RESET}")
        return None
    except Exception as exc:
        # Deliberately broad. This is the top-level loop: a bad API key, a
        # network blip, or any node raising must return the user to the prompt
        # rather than take the session down with it.
        out(f"{RED}  {type(exc).__name__}: {exc}{RESET}")
        return None

    if final is not None:
        out(render_summary(final))
    return final


async def repl(
    config: RunConfig,
    out: Callable[[str], None] = print,
    stub: str | None = None,
) -> None:
    """Read prompts until EOF or /exit."""
    if stub:
        from .nodes.stubs import stub_for

        graph = build_graph(config, code=stub_for(stub))
    else:
        graph = build_graph(config)
    out(
        BANNER.format(
            repo=config.repo,
            coder=f"stub:{stub}" if stub else "Claude Code (real)",
            analyzer=config.analyzer_url,
            iterations=config.max_iterations,
            per_iter=f"{config.budget_per_iteration:.2f}",
            session=f"{config.session_budget:.2f}",
        )
    )

    while True:
        try:
            prompt = (await asyncio.to_thread(input, f"{BOLD}› {RESET}")).strip()
        except (EOFError, KeyboardInterrupt):
            out("")
            return

        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return

        await run_turn(graph, prompt, out=out)
        out("")
