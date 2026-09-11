# AlakazAPI

A LangGraph pipeline that uses **Claude Code** (via `claude-agent-sdk`) as an executing
node, driven from a terminal REPL.

```
START → plan → code → review → ┬─ approved / budget hit / max iters → END
                     ↑         └─ revise ──┐
                     └────────────────────-┘
```

- **plan** — a cheap model turns your prompt into a concrete task spec.
- **code** — Claude Code executes it against a real repo. The only node that touches your filesystem.
- **review** — a cheap model judges the result and either approves or sends feedback back to `code`.

The revise edge loops back to `code`, not `plan`: it resumes the *same* Claude Code
session, so Claude keeps its context instead of re-reading the repo each pass.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...
```

The `claude` CLI must be on your PATH — the Agent SDK runs it as a subprocess.

## Run

```bash
.venv/bin/python -m alakazapi --repo ~/some/project
```

With no `--repo`, it defaults to a local `./workspace/` sandbox directory.

## Safety

The code node runs `permission_mode="bypassPermissions"` — full auto, no approval
prompts. Guardrails are structural rather than interactive:

| Guardrail | Default | Flag |
|---|---|---|
| Per-iteration spend cap | $2.00 | `--budget-per-iteration` |
| Cumulative session cap | $10.00 | `--session-budget` |
| Agent turns per iteration | 30 | `--max-turns` |
| Review loop iterations | 3 | `--max-iterations` |

**MCP servers are off.** The node passes `mcp_servers={}`, `strict_mcp_config=True`,
`setting_sources=[]` and `skills=[]`. That last pair matters: the SDK default
(`setting_sources=None`) loads `~/.claude/settings.json`, so without it the node would
silently inherit your global MCP servers and skills.

## Tests

```bash
.venv/bin/python -m pytest
```

No test spends money or touches a real repo — the SDK is faked at the boundary.
