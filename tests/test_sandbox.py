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
