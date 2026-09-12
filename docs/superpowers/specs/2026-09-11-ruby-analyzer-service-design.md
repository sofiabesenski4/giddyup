# Ruby Analyzer Service + Stub Coder Nodes — Design

**Date:** 2026-09-11
**Status:** Approved
**Supersedes graph shape in:** 2026-09-11-alakazapi-design.md

## Purpose

Two goals, one change:

1. End-to-end exercise of the pipeline without spending Claude Code tokens, via
   stubbed coder nodes that produce known-clean and known-overcomplicated Ruby.
2. A static analysis gate between the coder and the reviewer, implemented as a
   separate Ruby microservice using native Ruby analysis libraries.

## Architecture

```
┌─ alakazapi (Python) ──────────────┐      ┌─ analyzer (Ruby) ─────────┐
│  plan → code → analyze → review   │─────▶│  POST /analyze            │
│                   │               │ HTTP │  GET  /health             │
│                   └── client ─────┘◀─────│  flog · reek · flay       │
└───────────────────────────────────┘ JSON └───────────────────────────┘
```

The analyzer calls flog, reek, and flay as Ruby **libraries** (`Flog.new`,
`Reek::Examiner`), not as shelled-out CLIs. That is what makes it a native Ruby
service rather than a wrapper around command-line tools.

Rack + Puma serve it. Sinatra is not used — two endpoints do not justify the
dependency.

## Graph shape

```
START → plan → code → analyze → review → ┬─ approved → END
                ↑         │              └─ revise ─┐
                │         └─ violations ────────────┤
                └──────────────────────────────────-┘
```

`analyze` short-circuits **past** the reviewer when the code fails its
thresholds, routing straight back to `code`. Two consequences, both intended:

- A failing loop costs zero model tokens and is fully deterministic.
- The coding agent receives the concrete violations and metrics, so a revision
  pass has something actionable to work from rather than a bare rejection.

Static analysis can therefore veto code the reviewer might have accepted. That
is the intended trade: cheap objective gating before expensive subjective review.

## Toolchain

No system Ruby and no system gems.

- `mise.toml` at the repo root pins Ruby 4.0.6.
- `.ruby-version` holds the same value; the service's Gemfile reads it via
  `ruby file: "../../.ruby-version"` so the two cannot drift.
- `services/analyzer/.bundle/config` sets `BUNDLE_PATH: vendor/bundle`, keeping
  gems inside the service directory.
- Every Ruby command runs as `mise exec -- bundle exec ...`.

This also resolves a real hazard found during exploration: of 18 rbenv Rubies on
this machine, the globally active one (3.3.3) was the only one lacking these
gems, so an ambient `flog` call failed with `command not found`. A pinned
version plus a committed lockfile removes the ambiguity.

## Service contract

`POST /analyze` takes file **contents**, not paths:

```json
{"files": [{"path": "invoice.rb", "source": "class Invoice\n..."}]}
```

Contents rather than paths keeps this a genuine service boundary — no shared
filesystem assumption, so the analyzer can move into a container without a
protocol change.

Response:

```json
{"verdict": "clean",
 "files": [{"path": "invoice.rb",
            "flog_total": 10.5, "flog_average": 2.6,
            "smells": 1, "smell_types": ["IrresponsibleModule"],
            "violations": []}]}
```

`verdict` is `clean` or `complex`. Thresholds live on the Ruby side: the
analyzer owns the definition of "clean", and Python only reports the verdict it
is given.

## Thresholds

Measured against representative samples rather than invented:

| Gate | Default | clean sample | complex sample |
|---|---|---|---|
| flog per-method average | <= 20 | 2.6 | 80.6 |
| reek smells per file | <= 3 | 1 | 13 |

The 3-smell allowance is deliberate. The clean sample already scores 1
(`IrresponsibleModule`), so a zero-smell gate would reject good code.

## Python side

`nodes/analyze.py` is a thin HTTP client over stdlib `urllib` — two JSON calls
do not warrant a new dependency. It collects `.rb` files from the repo, posts
them, and folds the verdict and violations into state.

Degradation is explicit: if no analyzer answers the health check, the node
records `analysis: skipped (analyzer unavailable)` and passes through to review.
A missing service must not break the pipeline. Likewise, a coding pass that
touched no Ruby skips analysis entirely.

## Stub coder nodes

`nodes/stubs.py` provides `clean_code_node` and `complex_code_node`, selected
with `--stub-code clean|complex`. Both write real Ruby files into the repo —
the analyzer needs genuine input, otherwise the end-to-end test is theatre — and
both mimic the real node's return shape (transcript, tool_calls, iteration,
zero cost) so nothing downstream can distinguish them.

The complex stub stays complex across revisions, so a `--stub-code complex` run
loops until `max_iterations`, making the re-entry into `code` observable.

## Testing

**Ruby:** minitest over the scoring and threshold logic directly, plus a
Rack::Test request spec for the endpoints.

**Python:** unit tests with the HTTP layer faked, then end-to-end tests through
the real graph against a live analyzer. Those skip automatically when the
service is not running, so the suite stays green on a machine without Ruby.
