# AlakazAPI — Design

**Date:** 2026-09-11
**Status:** Approved

## Purpose

A LangGraph pipeline that uses Claude Code as an executing node, driven from a terminal
REPL. The user types a prompt; the graph plans it, executes it with Claude Code against a
real repository, reviews the result, and loops if the review asks for another pass.

## Architecture

Three layers that do not reach into each other's internals:

- `repl.py` — async terminal loop. Reads a prompt, invokes the graph, renders streamed
  output. Knows nothing about Claude Code.
- `graph.py` — `build_graph(config)` returns a compiled `StateGraph`. Pure wiring.
- `nodes/` — three independently testable `async (state) -> dict` functions.

```
START → plan → code → review → ┬─ approved / budget hit / max iters → END
                     ↑         └─ revise ──┐
                     └────────────────────-┘
```

The revise edge targets `code`, not `plan`, and resumes the same Claude Code session via
`resume=session_id`. Claude keeps its context rather than re-reading the repo each pass.

### Nodes

| Node | Model | Role |
|---|---|---|
| `plan` | Sonnet 5 | Turn the raw prompt into a concrete task spec |
| `code` | Opus 5 | Execute the spec via `claude_agent_sdk.query()` |
| `review` | Sonnet 5 | Structured verdict: `approved` or `revise` + feedback |

## The Claude Code node

```python
ClaudeAgentOptions(
    cwd=config.repo,
    model=config.code_model,
    permission_mode="bypassPermissions",
    mcp_servers={},
    strict_mcp_config=True,
    setting_sources=[],
    skills=[],
    max_turns=config.max_turns,
    max_budget_usd=config.budget_per_iteration,
    resume=state.get("session_id"),
)
```

**Isolation, verified against SDK 0.2.152:** `setting_sources` defaults to `None`, which
loads *all* filesystem settings including `~/.claude/settings.json`. Passing `[]` is
therefore required to keep the user's global MCP servers out of the node. `skills=[]`
does the same for skills, whose default (`None`) also defers to CLI defaults.

## Guardrails

`bypassPermissions` against a real repo is a live blade, so the guardrails are structural
rather than interactive:

- Per-iteration spend cap (`max_budget_usd`), default $2.00
- Cumulative session cap that aborts the loop, default $10.00
- `max_turns` per iteration, default 30
- `max_iterations` on the review loop, default 3
- `--repo` defaults to a local `./workspace/` sandbox rather than the cwd

## Streaming

The code node emits text and tool-call events through LangGraph's `get_stream_writer()`;
the REPL consumes `graph.astream(..., stream_mode="custom")`. Rendering stays entirely in
`repl.py`, so nodes are testable without a terminal.

## Error handling

SDK failures (`CLINotFoundError`, `ProcessError`, `CLIConnectionError`) are caught inside
the node and returned as an `error` field in state, routing straight to END with a
readable message. A failed run never kills the REPL. Ctrl-C cancels the in-flight graph
task and returns to the prompt.

## Testing

TDD throughout, with `claude_agent_sdk.query` faked at the boundary. Tests cover graph
wiring (loop fires on `revise`, terminates at `max_iterations`), budget accounting, error
routing, and that the options object really does disable MCP. No test spends money or
touches a real repository.
