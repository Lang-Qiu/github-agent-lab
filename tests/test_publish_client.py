from types import SimpleNamespace

import pytest

from src.github_client import GitHubClientError
from src.workflows.publish_client import PublishClient, PublishClientError


def test_publish_client_verify_remote_repo_success() -> None:
    class DummyGitHubClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            assert owner == "owner"
            assert repo == "repo"
            return {"full_name": "owner/repo", "default_branch": "main"}

    client = PublishClient(github_client=DummyGitHubClient())

    payload = client.verify_remote_repo("https://github.com/owner/repo")

    assert payload["full_name"] == "owner/repo"


def test_publish_client_push_branch_success(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []

    def _fake_run(command, capture_output, text, check):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("src.workflows.publish_client.subprocess.run", _fake_run)

    client = PublishClient(github_client=object())
    result = client.push_branch(tmp_path.as_posix(), "feature/test")

    assert result["pushed"] is True
    assert result["branch_name"] == "feature/test"
    assert commands == [["git", "-C", tmp_path.as_posix(), "push", "-u", "origin", "feature/test"]]


def test_publish_client_push_branch_failure(monkeypatch, tmp_path) -> None:
    def _fake_run(command, capture_output, text, check):
        return SimpleNamespace(returncode=1, stdout="", stderr="fatal: auth failed")

    monkeypatch.setattr("src.workflows.publish_client.subprocess.run", _fake_run)

    client = PublishClient(github_client=object())

    with pytest.raises(PublishClientError, match="fatal: auth failed"):
        client.push_branch(tmp_path.as_posix(), "feature/test")


def test_publish_client_create_draft_pr_success() -> None:
    class DummyGitHubClient:
        def create_draft_pull_request(
            self,
            owner: str,
            repo: str,
            title: str,
            body: str,
            head: str,
            base: str,
        ) -> dict[str, object]:
            assert owner == "owner"
            assert repo == "repo"
            assert head == "feature/test"
            assert base == "main"
            return {"url": "https://github.com/owner/repo/pull/1", "number": 1}

    client = PublishClient(github_client=DummyGitHubClient())

    payload = client.create_draft_pr(
        repo_url="https://github.com/owner/repo",
        title="test title",
        body="test body",
        head="feature/test",
        base="main",
    )

    assert payload["url"] == "https://github.com/owner/repo/pull/1"


def test_publish_client_create_draft_pr_failure() -> None:
    class DummyGitHubClient:
        def create_draft_pull_request(
            self,
            owner: str,
            repo: str,
            title: str,
            body: str,
            head: str,
            base: str,
        ) -> dict[str, object]:
            raise GitHubClientError("GitHub request failed with HTTP 401")

    client = PublishClient(github_client=DummyGitHubClient())

    with pytest.raises(PublishClientError, match="HTTP 401"):
        client.create_draft_pr(
            repo_url="https://github.com/owner/repo",
            title="test title",
            body="test body",
            head="feature/test",
            base="main",
        )
