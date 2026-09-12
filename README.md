# Giddyup

A LangGraph pipeline that uses **Claude Code** (via `claude-agent-sdk`) as an executing
node, driven from a terminal REPL.

```
START → plan → code → analyze → review → ┬─ approved → END
                ↑         │              └─ revise ─┐
                │         └─ violations ────────────┤
                └───────────────────────────────────┘
```

- **plan** — a cheap model turns your prompt into a concrete task spec.
- **code** — Claude Code executes it against a real repo. The only node that touches your filesystem.
- **analyze** — a Ruby microservice scores the changed Ruby with flog and reek.
- **review** — a cheap model judges the result and either approves or sends feedback back to `code`.

Both revise edges loop back to `code`, not `plan`. The code node resumes the *same*
Claude Code session, so Claude keeps its context instead of re-reading the repo.

**Analysis short-circuits past the reviewer.** Code that fails its thresholds goes
straight back to the coder carrying the concrete violations, so a failing loop costs
zero model tokens and the agent gets something actionable rather than a bare rejection.

## The analyzer service

A Rack/Puma service in `services/analyzer/` that uses flog and reek as Ruby *libraries*
rather than shelling out to their CLIs. Start it with:

```bash
mise run analyzer
```

`POST /analyze` takes file contents, not paths, so the boundary makes no
shared-filesystem assumption. Thresholds live on the Ruby side — the analyzer owns the
definition of "clean":

| Gate | Default | clean sample | complex sample |
|---|---|---|---|
| flog per-method average | ≤ 20 | 2.6 | 51.0 |
| reek smells per file | ≤ 3 | 1 | 9 |

The 3-smell allowance is deliberate: clean Ruby still scores 1 (`IrresponsibleModule`),
so a zero gate would reject good code.

Ruby is pinned with **mise** (`mise.toml`, 4.0.6) and gems are vendored with **bundler**
into `services/analyzer/vendor/bundle`. No system Ruby, no system gems, and no system
Python either — the interpreter comes from mise and the packages from `.venv`.

## Exercising the pipeline without Claude Code tokens

```bash
mise run analyzer                                                       # terminal 1
mise exec -- python -m giddyup --repo ./workspace --stub-code clean     # passes analysis, reaches review
mise exec -- python -m giddyup --repo ./workspace --stub-code complex   # fails analysis, loops to max-iterations
mise exec -- python -m giddyup --repo ./workspace --stub-code improving # fails once, refactors, converges
```

| Stub | First pass | Then | Ends |
|---|---|---|---|
| `clean` | flog 1.6, 1 smell | — | approved after 1 pass |
| `complex` | flog 80.6, 13 smells | never improves | loops to `--max-iterations` |
| `improving` | flog 80.6, 13 smells | flog 3.3, 1 smell | approved after 2 passes |

The stubs write real Ruby into the repo, so the analyzer has genuine input. `complex`
makes the loop back into `code` observable; `improving` shows it converging, replacing
the same file so the tangled version cannot linger and block the run.

## Install

Toolchain versions are pinned in `mise.toml` (Python 3.14.7, Ruby 4.0.6):

```bash
mise install        # fetch both interpreters
mise run setup      # install Python deps into the mise-managed venv
export ANTHROPIC_API_KEY=sk-ant-...
```

mise creates and activates `.venv` itself, so there is no manual `python -m venv`
step and no `.venv/bin/` prefixes below. A venv is still required — mise pins the
*interpreter* but has no package isolation of its own, so without one `pip` would
write into the shared 3.14.7 install every other project using it would see. It is
the counterpart of bundler's `vendor/bundle`, not of mise itself.

If you run `eval "$(mise activate zsh)"` in your shell, plain `python` and `pytest`
resolve correctly inside this directory. Otherwise prefix commands with
`mise exec --`, or use the `mise run` tasks below.

The `claude` CLI must be on your PATH — the Agent SDK runs it as a subprocess.

## Run

```bash
mise exec -- python -m giddyup --repo ~/some/project
```

`--repo` is required. The code node runs Claude Code with `bypassPermissions`
against whatever it names, so the target is always an explicit choice.

To practise against a throwaway repository instead of real code:

```bash
mise run sandbox                                           # creates ./workspace
mise exec -- python -m giddyup --repo ./workspace
```

The sandbox is its own git repository with a clean Ruby baseline already
committed. That baseline is what makes the analysis gate meaningful: everything
the agent writes shows up as a change against it, so the gate judges the agent's
diff rather than the whole directory.

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
mise run test        # python
mise run test:ruby   # ruby
```

`mise tasks` lists everything: `setup`, `analyzer`, `test`, `test:ruby`.

No test spends money — the Claude Code SDK is faked at its boundary. The end-to-end
tests in `tests/test_e2e_analyzer.py` run against the *real* analyzer over HTTP and skip
automatically when it is not running.
