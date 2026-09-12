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


def make_unrelated_git_repo(path, subject):
    path.mkdir(parents=True, exist_ok=True)
    (path / "sentinel.txt").write_text("keep me\n")
    identity = ["-c", "user.name=someone else", "-c", "user.email=someone@example.invalid"]
    subprocess.run(
        ["git", "init", "--initial-branch=main"], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", *identity, "add", "-A"], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", *identity, "commit", "-m", subject], cwd=path, check=True, capture_output=True
    )


def test_force_refuses_to_delete_a_git_repo_that_is_not_a_generated_sandbox(tmp_path):
    other = tmp_path / "other"
    make_unrelated_git_repo(other, "Some unrelated project")

    with pytest.raises(ValueError, match="not a generated sandbox"):
        create_sandbox(other, force=True)

    assert (other / "sentinel.txt").exists()


def test_force_refuses_on_a_non_git_non_empty_directory(tmp_path):
    stray = tmp_path / "stray"
    stray.mkdir()
    (stray / "keep.txt").write_text("keep me\n")

    with pytest.raises(ValueError, match="not a generated sandbox"):
        create_sandbox(stray, force=True)

    assert (stray / "keep.txt").exists()


def test_force_refuses_to_delete_a_subdirectory_of_a_generated_sandbox(tmp_path):
    sandbox = create_sandbox(tmp_path / "sandbox")
    subdir = sandbox / "userdata"
    subdir.mkdir()
    sentinel = subdir / "precious.txt"
    sentinel.write_text("keep me\n")
    (subdir / ".git").mkdir()

    with pytest.raises(ValueError, match="not a generated sandbox"):
        create_sandbox(subdir, force=True)

    assert sentinel.exists()


def test_force_still_succeeds_on_a_real_sandbox_after_an_extra_commit(tmp_path):
    sandbox = create_sandbox(tmp_path / "sandbox")
    (sandbox / "extra.rb").write_text("class Extra; end\n")
    identity = ["-c", "user.name=someone else", "-c", "user.email=someone@example.invalid"]
    subprocess.run(
        ["git", *identity, "add", "-A"], cwd=sandbox, check=True, capture_output=True
    )
    subprocess.run(
        ["git", *identity, "commit", "-m", "Extra work"],
        cwd=sandbox,
        check=True,
        capture_output=True,
    )

    create_sandbox(sandbox, force=True)

    assert not (sandbox / "extra.rb").exists()
