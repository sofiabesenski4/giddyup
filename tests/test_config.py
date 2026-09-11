from pathlib import Path

from alakazapi.config import RunConfig


def test_defaults_to_local_workspace_sandbox_when_no_repo_given(tmp_path):
    config = RunConfig.create(repo=None, base_dir=tmp_path)

    assert config.repo == tmp_path / "workspace"
    assert config.repo.is_dir()


def test_uses_the_given_repo_when_one_is_passed(tmp_path):
    target = tmp_path / "myproject"
    target.mkdir()

    config = RunConfig.create(repo=target, base_dir=tmp_path)

    assert config.repo == target


def test_rejects_a_repo_path_that_does_not_exist(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="does not exist"):
        RunConfig.create(repo=tmp_path / "nope", base_dir=tmp_path)
