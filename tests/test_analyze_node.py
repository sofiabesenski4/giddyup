import subprocess

from giddyup.nodes.analyze import analyze_node, collect_ruby_files, format_violations
from giddyup.state import new_state


def git_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


def git(repo, *args):
    """Run git with a throwaway identity so it works on a bare machine."""
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def write(path, name, body="class X\nend\n"):
    f = path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)
    return f


# ---- collecting the files to analyse -------------------------------------

def test_collects_ruby_files_changed_in_the_working_tree(tmp_path):
    git_repo(tmp_path)
    write(tmp_path, "app/invoice.rb", "class Invoice\nend\n")

    files = collect_ruby_files(tmp_path)

    assert [f["path"] for f in files] == ["app/invoice.rb"]
    assert "class Invoice" in files[0]["source"]


def test_ignores_files_that_are_not_ruby(tmp_path):
    git_repo(tmp_path)
    write(tmp_path, "notes.md", "# hi")
    write(tmp_path, "app.rb", "class A\nend\n")

    assert [f["path"] for f in collect_ruby_files(tmp_path)] == ["app.rb"]


def test_judges_only_what_changed_not_the_whole_codebase(tmp_path):
    git_repo(tmp_path)
    write(tmp_path, "old.rb", "class Old\nend\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=tmp_path, check=True,
    )
    write(tmp_path, "new.rb", "class New\nend\n")

    assert [f["path"] for f in collect_ruby_files(tmp_path)] == ["new.rb"]


def test_falls_back_to_all_ruby_files_outside_a_git_repo(tmp_path):
    write(tmp_path, "a.rb")

    assert [f["path"] for f in collect_ruby_files(tmp_path)] == ["a.rb"]


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


# ---- the node ------------------------------------------------------------

def fake_post(response, capture=None):
    def _post(url, payload):
        if capture is not None:
            capture["url"] = url
            capture["payload"] = payload
        return response

    return _post


async def test_passes_through_when_the_change_touched_no_ruby(tmp_path, config):
    git_repo(tmp_path)
    cfg = config.__class__(**{**config.__dict__, "repo": tmp_path})

    def should_not_be_called(url, payload):
        raise AssertionError("analyzer must not be called when no Ruby changed")

    update = await analyze_node(new_state("x"), cfg, post=should_not_be_called)

    assert update["analysis_verdict"] == "skipped"


async def test_records_a_clean_verdict(tmp_path, config):
    git_repo(tmp_path)
    write(tmp_path, "a.rb")
    cfg = config.__class__(**{**config.__dict__, "repo": tmp_path})

    update = await analyze_node(
        new_state("x"), cfg, post=fake_post({"verdict": "clean", "files": []})
    )

    assert update["analysis_verdict"] == "clean"


async def test_records_violations_as_feedback_for_the_coding_agent(tmp_path, config):
    git_repo(tmp_path)
    write(tmp_path, "a.rb")
    cfg = config.__class__(**{**config.__dict__, "repo": tmp_path})
    response = {
        "verdict": "complex",
        "files": [
            {
                "path": "a.rb",
                "flog_average": 51.0,
                "smells": 9,
                "violations": [
                    {"rule": "flog_average", "message": "average method complexity is 51.0"}
                ],
            }
        ],
    }

    update = await analyze_node(new_state("x"), cfg, post=fake_post(response))

    assert update["analysis_verdict"] == "complex"
    assert "a.rb" in update["feedback"]
    assert "51.0" in update["feedback"]


async def test_an_unreachable_analyzer_does_not_break_the_pipeline(tmp_path, config):
    git_repo(tmp_path)
    write(tmp_path, "a.rb")
    cfg = config.__class__(**{**config.__dict__, "repo": tmp_path})

    def refuse(url, payload):
        raise OSError("connection refused")

    update = await analyze_node(new_state("x"), cfg, post=refuse)

    assert update["analysis_verdict"] == "skipped"
    # The node must leave `error` untouched rather than setting it to None:
    # clearing it would wipe a genuine failure recorded by the code node.
    assert "error" not in update, "an unreachable analyzer is not a pipeline error"


async def test_sends_the_configured_thresholds(tmp_path, config):
    git_repo(tmp_path)
    write(tmp_path, "a.rb")
    cfg = config.__class__(**{**config.__dict__, "repo": tmp_path, "flog_average_limit": 5})
    capture: dict = {}

    await analyze_node(
        new_state("x"), cfg, post=fake_post({"verdict": "clean", "files": []}, capture)
    )

    assert capture["payload"]["thresholds"]["flog_average"] == 5


# ---- feedback formatting -------------------------------------------------

def test_formatted_feedback_names_the_file_and_the_rule():
    text = format_violations(
        [{"path": "a.rb", "violations": [{"rule": "smells", "message": "9 code smells"}]}]
    )

    assert "a.rb" in text
    assert "9 code smells" in text


def test_formatted_feedback_skips_files_that_passed():
    text = format_violations(
        [
            {"path": "good.rb", "violations": []},
            {"path": "bad.rb", "violations": [{"rule": "smells", "message": "too many"}]},
        ]
    )

    assert "good.rb" not in text
    assert "bad.rb" in text
