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
