# Sandbox Generation + Git-Scoped Changesets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the static analysis gate work by giving the sandbox its own git repository with a committed baseline, and by scoping the changeset to that repository's own history.

**Architecture:** A generator creates a throwaway Ruby repository with a clean baseline commit. `collect_ruby_files` resolves git's porcelain paths against the repository *root* rather than `config.repo`, and falls back to a full scan when the enclosing repository ignores the directory. `--repo` becomes required, so no run silently invents a sandbox.

**Tech Stack:** Python 3.14, pytest, pytest-asyncio, git CLI via `subprocess`, mise tasks.

**Spec:** `docs/superpowers/specs/2026-09-12-sandbox-generation-design.md`

## Global Constraints

- Git commits made by the generator MUST use `git -c user.name=… -c user.email=…`, never `git config` — generation must work with no global git identity and must not mutate the developer's configuration.
- The baseline app MUST pass the analyzer's thresholds (`flog_average` 20.0, `smells` 3), so any violation seen in a test is attributable to the coding pass.
- Baseline filenames MUST NOT collide with what the stub coders write: `invoice.rb`, `invoice_processor.rb`.
- `create_sandbox` is called ONLY by end-to-end system specs and its own unit test. All other tests keep using `tmp_path`.
- End-to-end system specs stay minimal: two cases that generate a sandbox, plus one that guards the baseline against the analyzer without generating one.
- This phase adds no commits beyond the generator's baseline. Per-step commits belong to the later step-execution work.
- Paths must be compared with `.resolve()` on both sides. On macOS `tmp_path` lives under `/private/var/...` and git may report the unresolved form; unresolved comparison silently breaks the `repo in absolute.parents` filter.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/giddyup/sandbox.py` (create) | Generate a git repository with a clean Ruby baseline; CLI entry |
| `src/giddyup/nodes/analyze.py` (modify) | Resolve changeset against git root; ignore-aware fallback |
| `src/giddyup/config.py` (modify) | `--repo` required; drop dead `base_dir` |
| `src/giddyup/__main__.py` (modify) | `--repo` help text |
| `mise.toml` (modify) | `sandbox` task |
| `README.md` (modify) | Onboarding step; `bypassPermissions` warning |
| `tests/test_analyze_node.py` (modify) | Changeset scoping across git topologies |
| `tests/test_sandbox.py` (create) | Generator behaviour |
| `tests/test_config.py` (modify) | `--repo` required |
| `tests/test_e2e_analyzer.py` (modify) | Two sandbox-backed system specs |

---

### Task 1: Scope the changeset to the right repository

Fixes the live bug. Independent of the generator — a reviewer can accept this alone.

**Files:**
- Modify: `src/giddyup/nodes/analyze.py:19-64`
- Test: `tests/test_analyze_node.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `_git_changed(repo: Path) -> list[Path] | None` — now returns **absolute** paths, was repo-root-relative `list[str]`. `collect_ruby_files(repo: Path) -> list[dict[str, str]]` signature unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_analyze_node.py`:

```python
import subprocess

from giddyup.nodes.analyze import collect_ruby_files


def git(repo, *args):
    """Run git with a throwaway identity so it works on a bare machine."""
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_changeset_resolves_paths_when_repo_is_a_subdirectory(tmp_path):
    project = tmp_path / "project"
    (project / "lib").mkdir(parents=True)
    git(project, "init")
    (project / "README.md").write_text("base\n")
    git(project, "add", "-A")
    git(project, "commit", "-m", "base")

    (project / "lib" / "invoice.rb").write_text("class Invoice; end\n")

    files = collect_ruby_files(project / "lib")

    assert [f["path"] for f in files] == ["invoice.rb"]


def test_changeset_falls_back_to_scanning_when_the_parent_repo_ignores_the_directory(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    git(parent, "init")
    (parent / ".gitignore").write_text("workspace/\n")
    git(parent, "add", "-A")
    git(parent, "commit", "-m", "base")

    sandbox = parent / "workspace"
    sandbox.mkdir()
    (sandbox / "invoice.rb").write_text("class Invoice; end\n")

    files = collect_ruby_files(sandbox)

    assert [f["path"] for f in files] == ["invoice.rb"]


def test_changeset_in_a_nested_repo_excludes_the_committed_baseline(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir()
    git(parent, "init")
    (parent / ".gitignore").write_text("workspace/\n")
    git(parent, "add", "-A")
    git(parent, "commit", "-m", "base")

    sandbox = parent / "workspace"
    sandbox.mkdir()
    git(sandbox, "init")
    (sandbox / "catalog.rb").write_text("class Catalog; end\n")
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-m", "baseline")

    (sandbox / "invoice.rb").write_text("class Invoice; end\n")

    files = collect_ruby_files(sandbox)

    assert [f["path"] for f in files] == ["invoice.rb"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- python -m pytest tests/test_analyze_node.py -k changeset -v`

Expected: the first two FAIL with `assert [] == ['invoice.rb']`. The first fails because porcelain reports `lib/invoice.rb` relative to the project root and it is joined onto `project/lib`, giving `project/lib/lib/invoice.rb`. The second fails because the parent repository ignores `workspace/`, so git reports nothing there and the scan fallback never fires. The third already passes — it guards the design.

- [ ] **Step 3: Rewrite `_git_changed` and the call site**

Replace `_git_changed` (currently `analyze.py:19-36`) with:

```python
def _git_changed(repo: Path) -> list[Path] | None:
    """Absolute paths git reports as added or modified, or None when git's view
    is not usable here.

    Porcelain paths are relative to the repository *root*, which is not always
    ``repo`` — a sandbox nested in another checkout, or a subdirectory of a real
    one. Resolving against the root and filtering back down to ``repo`` keeps the
    changeset correct in every topology.

    Returning None falls back to a full scan. That happens outside a repository,
    and also when the enclosing repository *ignores* ``repo``: an ignored
    directory is invisible to ``git status``, so trusting git there would report
    an empty changeset and silently disable the gate.
    """

    def run(*args: str):
        try:
            return subprocess.run(
                ["git", *args], cwd=repo, capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None

    root_proc = run("rev-parse", "--show-toplevel")
    if root_proc is None or root_proc.returncode != 0:
        return None

    root = Path(root_proc.stdout.strip()).resolve()
    repo = repo.resolve()

    if root != repo:
        ignored = run("check-ignore", "-q", str(repo))
        if ignored is not None and ignored.returncode == 0:
            return None

    status = run("status", "--porcelain", "--untracked-files=all")
    if status is None or status.returncode != 0:
        return None

    paths = []
    for line in status.stdout.splitlines():
        if len(line) > 3:
            # Rename entries read "R  old -> new"; the new path is what changed.
            rel = line[3:].split(" -> ")[-1].strip().strip('"')
            absolute = (root / rel).resolve()
            if absolute == repo or repo in absolute.parents:
                paths.append(absolute)
    return paths
```

In `collect_ruby_files`, replace the first three statements of the body (currently `analyze.py:46-51`) with:

```python
    repo = Path(repo).resolve()
    changed = _git_changed(repo)
    candidates = changed if changed is not None else sorted(repo.rglob("*.rb"))
```

The rest of the function is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- python -m pytest tests/test_analyze_node.py -v`
Expected: PASS, including the pre-existing cases in that file.

- [ ] **Step 5: Run the whole suite for regressions**

Run: `mise exec -- python -m pytest`
Expected: PASS (analyzer e2e cases skip unless `./bin/analyzer` is running).

- [ ] **Step 6: Commit**

```bash
git add src/giddyup/nodes/analyze.py tests/test_analyze_node.py
git commit -m "Scope the changeset to the repository that owns the directory"
```

---

### Task 2: The sandbox generator

**Files:**
- Create: `src/giddyup/sandbox.py`
- Create: `tests/test_sandbox.py`
- Modify: `mise.toml`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `create_sandbox(path: Path, force: bool = False) -> Path`, raising `ValueError` when a repository already exists and `force` is False. Also `main(argv: list[str] | None = None) -> int` for `python -m giddyup.sandbox`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sandbox.py`:

```python
import subprocess

import pytest

from giddyup.sandbox import create_sandbox


def git_out(repo, *args) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_creates_a_git_repository_rooted_at_the_sandbox(tmp_path):
    sandbox = create_sandbox(tmp_path / "sandbox")

    assert git_out(sandbox, "rev-parse", "--show-toplevel") == str(sandbox.resolve())


def test_commits_the_baseline_so_the_tree_is_clean(tmp_path):
    sandbox = create_sandbox(tmp_path / "sandbox")

    assert git_out(sandbox, "status", "--porcelain", "--untracked-files=all") == ""


def test_baseline_contains_ruby_that_does_not_collide_with_stub_output(tmp_path):
    sandbox = create_sandbox(tmp_path / "sandbox")

    ruby = sorted(p.name for p in sandbox.rglob("*.rb"))

    assert ruby
    assert "invoice.rb" not in ruby
    assert "invoice_processor.rb" not in ruby


def test_refuses_to_clobber_an_existing_sandbox(tmp_path):
    sandbox = create_sandbox(tmp_path / "sandbox")

    with pytest.raises(ValueError, match="already a git repository"):
        create_sandbox(sandbox)


def test_force_replaces_an_existing_sandbox(tmp_path):
    sandbox = create_sandbox(tmp_path / "sandbox")
    (sandbox / "leftover.rb").write_text("class Leftover; end\n")

    create_sandbox(sandbox, force=True)

    assert not (sandbox / "leftover.rb").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- python -m pytest tests/test_sandbox.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'giddyup.sandbox'`.

- [ ] **Step 3: Write the generator**

Create `src/giddyup/sandbox.py`:

```python
"""Generate a throwaway Ruby repository for giddyup to practise on.

The baseline commit is the point: everything the coding agent writes then shows
up as a working-tree change against it, so the analysis gate judges the agent's
diff rather than the whole directory.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Named so they cannot collide with what the stub coders write (invoice.rb,
# invoice_processor.rb) — the agent's changeset then contains only its own work.
BASELINE: dict[str, str] = {
    "README.md": "# Sandbox\n\nA practice repository generated by `mise run sandbox`.\n",
    "lib/catalog.rb": '''# frozen_string_literal: true

# A read-only list of products, keyed by SKU.
class Catalog
  def initialize(items)
    @items = items
  end

  def find(sku)
    @items[sku]
  end

  def size
    @items.size
  end
end
''',
    "lib/money.rb": '''# frozen_string_literal: true

# An amount in whole cents, kept integral to avoid floating point drift.
class Money
  attr_reader :cents

  def initialize(cents)
    @cents = cents
  end

  def add(other)
    Money.new(cents + other.cents)
  end

  def to_s
    format('$%.2f', cents / 100.0)
  end
end
''',
}

# An explicit identity keeps generation working on a machine with no global git
# config, without writing to the developer's configuration.
IDENTITY = ["-c", "user.name=giddyup sandbox", "-c", "user.email=sandbox@giddyup.invalid"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *IDENTITY, *args], cwd=repo, check=True, capture_output=True)


def create_sandbox(path: Path, force: bool = False) -> Path:
    """Create a git repository with a clean Ruby baseline already committed."""
    path = Path(path)
    if (path / ".git").exists():
        if not force:
            raise ValueError(
                f"{path} is already a git repository; pass force=True to replace it"
            )
        shutil.rmtree(path)

    path.mkdir(parents=True, exist_ok=True)
    for name, source in BASELINE.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    _git(path, "init", "--initial-branch=main")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "Baseline sandbox app")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="giddyup-sandbox",
        description="Generate a practice repository with a clean Ruby baseline.",
    )
    parser.add_argument("path", type=Path, nargs="?", default=Path("workspace"))
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing sandbox."
    )
    args = parser.parse_args(argv)

    try:
        created = create_sandbox(args.path, force=args.force)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Sandbox ready at {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mise exec -- python -m pytest tests/test_sandbox.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Add the mise task**

In `mise.toml`, after the `[tasks.setup]` block:

```toml
[tasks.sandbox]
description = "Generate a practice sandbox repository at ./workspace"
run = "python -m giddyup.sandbox workspace"
```

- [ ] **Step 6: Verify the task end to end**

Run: `rm -rf /tmp/sbx && mise exec -- python -m giddyup.sandbox /tmp/sbx`
Expected: prints `Sandbox ready at /tmp/sbx`.

Run: `cd /tmp/sbx && git log --oneline && git status --porcelain`
Expected: one commit `Baseline sandbox app`, and empty status.

- [ ] **Step 7: Commit**

```bash
git add src/giddyup/sandbox.py tests/test_sandbox.py mise.toml
git commit -m "Add a sandbox generator with a committed Ruby baseline"
```

---

### Task 3: Require `--repo`

**Files:**
- Modify: `src/giddyup/config.py:32-49`
- Modify: `src/giddyup/__main__.py:20-25`
- Modify: `tests/test_config.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `create_sandbox` from Task 2 only as a documented command, not as an import.
- Produces: `RunConfig.create(repo: Path | None, **overrides) -> RunConfig` — the `base_dir` parameter is **removed**; it existed only to site the deleted workspace default.

- [ ] **Step 1: Rewrite the config tests**

Replace the whole body of `tests/test_config.py` with:

```python
import pytest

from giddyup.config import RunConfig


def test_requires_a_repo_and_names_the_sandbox_as_the_alternative():
    with pytest.raises(ValueError, match="--repo is required"):
        RunConfig.create(repo=None)


def test_uses_the_given_repo_when_one_is_passed(tmp_path):
    target = tmp_path / "myproject"
    target.mkdir()

    config = RunConfig.create(repo=target)

    assert config.repo == target


def test_rejects_a_repo_path_that_does_not_exist(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        RunConfig.create(repo=tmp_path / "nope")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mise exec -- python -m pytest tests/test_config.py -v`
Expected: `test_requires_a_repo...` FAILS — no exception is raised, because `create` still builds `./workspace`.

- [ ] **Step 3: Rewrite `RunConfig.create`**

Replace `config.py:32-49` with:

```python
    @classmethod
    def create(cls, repo: Path | None, **overrides) -> RunConfig:
        """Build a config for an explicitly named repository.

        There is deliberately no default. The code node runs with
        ``bypassPermissions``, so the repository it works in has to be a choice
        the operator made rather than one this function invented — and a
        silently invented sandbox is how the analysis gate came to be dead by
        default, since the enclosing repository ignored it.
        """
        if repo is None:
            raise ValueError(
                "--repo is required: name the repository this session will "
                "contribute to.\n"
                "To practise against a throwaway repository instead:\n"
                "    mise run sandbox\n"
                "    mise exec -- python -m giddyup --repo ./workspace"
            )

        resolved = Path(repo).expanduser()
        if not resolved.is_dir():
            raise ValueError(f"--repo path does not exist or is not a directory: {resolved}")

        return cls(repo=resolved, **overrides)
```

- [ ] **Step 4: Update the CLI help text**

In `src/giddyup/__main__.py`, replace the `--repo` argument (lines 20-25) with:

```python
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository Claude Code works in (required). Generate a practice "
        "one with: mise run sandbox",
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `mise exec -- python -m pytest tests/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Verify the CLI failure is legible**

Run: `mise exec -- python -m giddyup`
Expected: exit status 1, and the `--repo is required` message with the two sandbox commands on stderr.

- [ ] **Step 7: Update the README**

In `README.md`, replace the line `With no --repo, it defaults to a local ./workspace/ sandbox directory.` with:

```markdown
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
```

Then update the three `--stub-code` example commands in the same file to pass `--repo ./workspace`, since they no longer run without it.

- [ ] **Step 8: Run the whole suite**

Run: `mise exec -- python -m pytest`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/giddyup/config.py src/giddyup/__main__.py tests/test_config.py README.md
git commit -m "Require --repo instead of inventing a sandbox"
```

---

### Task 4: End-to-end system specs on a generated sandbox

Two cases, per the spec. They are the only specs that generate a sandbox, and the only ones that exercise production git topology.

**Files:**
- Modify: `tests/test_e2e_analyzer.py`

**Interfaces:**
- Consumes: `create_sandbox(path) -> Path` (Task 2); the changeset scoping from Task 1.
- Produces: a `sandbox_config` fixture, alongside the existing `repo_config`.

- [ ] **Step 1: Add the fixture and the system specs**

In `tests/test_e2e_analyzer.py`, add these imports:

```python
from giddyup.nodes.analyze import _post
from giddyup.sandbox import BASELINE, create_sandbox
```

Then append:

```python
@pytest.fixture
def sandbox_config(tmp_path, config):
    """A generated sandbox: its own git repo, with a clean baseline committed.

    This is the production topology — a repository the enclosing checkout
    ignores — which tmp_path alone cannot reproduce.
    """
    sandbox = create_sandbox(tmp_path / "sandbox")
    return config.__class__(
        **{
            **config.__dict__,
            "repo": sandbox,
            "analyzer_url": ANALYZER_URL,
            "max_iterations": 3,
        }
    )


async def test_the_gate_judges_only_the_agents_diff_not_the_baseline(sandbox_config):
    events: list = []
    graph = build_graph(
        sandbox_config,
        plan=stub_plan,
        code=clean_code_node,
        review=counting_review([]),
        emit=events.append,
    )

    await graph.ainvoke(new_state("write an invoice calculator"))

    analysis = [e for e in events if e.get("type") == "analysis"]
    assert analysis[0]["verdict"] == "clean"
    reported = {f["path"] for f in analysis[0]["files"]}
    assert reported == {"invoice.rb"}, (
        f"expected only the agent's file, got {reported} — the committed "
        "baseline must not be re-judged"
    )


async def test_overcomplicated_ruby_in_a_sandbox_fails_the_gate(sandbox_config):
    events: list = []
    graph = build_graph(
        sandbox_config,
        plan=stub_plan,
        code=complex_code_node,
        review=counting_review([]),
        emit=events.append,
    )

    await graph.ainvoke(new_state("write an invoice calculator"))

    analysis = [e for e in events if e.get("type") == "analysis"]
    assert analysis[0]["verdict"] == "complex"
    assert {f["path"] for f in analysis[0]["files"]} == {"invoice_processor.rb"}


def test_the_generated_baseline_passes_the_analyzer(config):
    """Guards the constraint that every other test leans on.

    If the baseline ever drifts into violating the thresholds, a failure
    elsewhere stops being attributable to the coding pass — and in the
    scan-fallback path the baseline is analysed alongside the agent's work.
    """
    report = _post(
        f"{ANALYZER_URL}/analyze",
        {
            "files": [
                {"path": name, "source": source}
                for name, source in BASELINE.items()
                if name.endswith(".rb")
            ],
            "thresholds": {
                "flog_average": config.flog_average_limit,
                "smells": config.smells_limit,
            },
        },
    )

    assert report["verdict"] == "clean", report
```

- [ ] **Step 2: Start the analyzer**

Run: `./bin/analyzer` in a second terminal.
Verify: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9292/health` prints `200`.

Without this the new specs skip rather than fail, via the existing `pytestmark`.

- [ ] **Step 3: Run the new specs**

Run: `mise exec -- python -m pytest tests/test_e2e_analyzer.py -v`
Expected: PASS, and neither new test skipped.

The first test is the one that proves the whole change: it fails if the baseline leaks into the changeset, and it fails if the changeset comes back empty.

- [ ] **Step 4: Run the whole suite with the analyzer up**

Run: `mise exec -- python -m pytest`
Expected: PASS with zero skips.

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e_analyzer.py
git commit -m "Prove the gate judges only the agent's diff in a real sandbox"
```

---

## Verification

With `./bin/analyzer` running:

```bash
mise run test
mise run test:ruby
```

Expected: all Python tests pass with no skips; 23 Ruby runs, 0 failures.

Then confirm the documented onboarding path works from nothing:

```bash
rm -rf workspace
mise run sandbox
mise exec -- python -m giddyup --stub-code clean --repo ./workspace
```

Expected: `analysis: clean`, `approved after 1 pass` — the result that the dead gate could not produce. Confirm `git status --porcelain` at the giddyup root does not mention `workspace/`.
