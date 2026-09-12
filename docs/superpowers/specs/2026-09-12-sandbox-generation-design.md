# Sandbox Generation + Git-Scoped Changesets — Design

**Date:** 2026-09-12
**Status:** Approved
**Amends `--repo` contract in:** 2026-09-11-alakazapi-design.md

## Purpose

The static analysis gate is dead in the default configuration. A run started
without `--repo` writes into `./workspace/`, which is gitignored by the giddyup
repository that contains it, so the gate reports `no Ruby changed` and every
coding pass goes unjudged.

Two faults compound in `collect_ruby_files`:

1. **Ignored sandbox.** `_git_changed` asks the *parent* repository what changed.
   `workspace/` is in `.gitignore`, so the agent's output never appears.
2. **Path relativity.** `git status --porcelain` reports paths relative to the
   repository *root*, but they are joined onto `config.repo`. When those differ,
   every candidate resolves to a path that does not exist.

Either fault alone is enough to empty the changeset. Fixing `.gitignore` does not
help, because fault 2 is independent of ignore rules.

The suite did not catch this because `tmp_path` is not inside any git repository,
so `_git_changed` returns `None` and the `rglob` fallback masks both faults. The
tests structurally cannot reach the topology where the bug lives.

## Approach

Give the sandbox its own git repository with a committed baseline, and scope the
changeset to that repository's own history.

```
giddyup/                     ← .gitignore contains "workspace/"
├── .git/
└── workspace/               ← invisible to giddyup
    ├── .git/                ← its own root
    ├── lib/catalog.rb       ← committed baseline
    └── invoice.rb           ← agent output, the whole changeset
```

Verified: the parent reports a clean tree, while inside the sandbox
`git rev-parse --show-toplevel` resolves to the sandbox and `git status` reports
only the agent's file. Because the sandbox is its own root, `config.repo` and the
git root coincide and fault 2 cannot arise there.

## The generator

`src/giddyup/sandbox.py` exposes one function:

```python
def create_sandbox(path: Path, force: bool = False) -> Path
```

It creates the directory, runs `git init`, writes a small **clean** Ruby app, and
makes a single baseline commit. It refuses to clobber an existing sandbox unless
`force` is set.

The commit uses `git -c user.name=… -c user.email=…` rather than `git config`, so
generation works on a machine with no global git identity and never mutates the
developer's configuration.

Baseline files are named so they cannot collide with what the stub coders write
(`invoice.rb`, `invoice_processor.rb`); the agent's changeset then contains
exactly its own output. The baseline must pass the analyzer's thresholds, so that
any violation observed in a test is attributable to the coding pass.

A `mise run sandbox` task generates `./workspace/` for local use.

## Commit policy

The generator writes the baseline commit. **This phase adds no commits of its
own**: the changeset is the working-tree diff against the baseline.

Commits during a run are deliberately left to a later phase. A commit node — which
commits a completed step, marks it done in the plan, and advances to the next
planned step — is specified separately and depends on the plan becoming structured
data. See `2026-09-12-step-execution-design.md` (to be written).

**Known interim limitation.** Until that node lands, an earlier REPL turn's output
is still uncommitted when a later turn runs, so the later turn's changeset
re-includes it and the agent is re-judged on finished work. The escape hatch is
regenerating the sandbox. This is a temporary property of shipping the sandbox
first, not a design position — per-step commits resolve it properly by scoping the
working-tree diff to the step in flight.

## `--repo` becomes required

`RunConfig.create(repo=None)` no longer creates `./workspace/`. It raises, naming
the repository the session will contribute to and pointing at the sandbox as the
practice target.

This removes a documented structural guardrail. The original design lists
"`--repo` defaults to a local `./workspace/` sandbox rather than the cwd" among
the protections that exist because "`bypassPermissions` against a real repo is a
live blade" — the guardrails are structural precisely because nothing prompts the
operator mid-run. The trade is deliberate:

- **Gained:** no silent writes. Nothing happens until the operator names a target,
  and an unconfigured run fails loudly instead of quietly exercising a dead gate.
- **Lost:** the normal path now points a permissions-bypassed agent at a real
  repository.

The docstring must be updated to state the new rationale, and the README must
carry the `bypassPermissions` warning.

## The analyze fix

`_git_changed` resolves the repository root and joins porcelain paths onto that
root rather than onto `config.repo`, then keeps only the paths lying under
`config.repo` and re-relativizes them for the payload.

This fixes fault 2 in every topology — nested repository, subdirectory of a real
repository, or plain repository — rather than only in the sandbox case. `None` is
returned only when there is genuinely no repository, preserving the existing
`rglob` fallback.

## Testing

Sandbox generation is confined to **end-to-end system specs**, which stay
deliberately few. Generating a repository per test is the most expensive fixture
in the suite and earns its cost only where real git topology is the thing under
test.

| Level | Fixture | Covers |
|---|---|---|
| System (2–3 cases) | `create_sandbox()` into `tmp_path` | Real topology: clean passes the gate, overcomplicated fails and feeds violations back |
| Unit | Inline `git init`, no generator | Path relativity and nested-repo scoping in `collect_ruby_files` |
| Unit | `tmp_path` | Everything else, unchanged |

The existing seven analyzer e2e cases are mostly assertions about analyzer output
and feedback content, not about topology. Those stay on `tmp_path`; only the small
number that genuinely exercise the sandbox move.

The regression test goes in **first** and must fail against today's
`collect_ruby_files`: build a parent repository that ignores a nested sandbox,
write Ruby into the sandbox, and assert the changeset contains it. That is the
test the current suite could not express.

The generator's own unit test calls `create_sandbox` once — unavoidable, and the
only generator use outside the system specs.

## README

- Remove "With no `--repo`, it defaults to a local `./workspace/` sandbox
  directory," which becomes false.
- Document `mise run sandbox` as the onboarding step, then `--repo ./workspace`.
- Warn that the code node runs with permissions bypassed against whatever
  `--repo` names.
