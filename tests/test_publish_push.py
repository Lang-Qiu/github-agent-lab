from types import SimpleNamespace

from src.workflows.publish_client import PublishClientError
from src.workflows.publish_result import push_prepared_branch


def test_push_prepared_branch_success(monkeypatch, tmp_path) -> None:
    def _fake_run_git(workspace_dir: str, args: list[str]):
        assert workspace_dir == tmp_path.as_posix()
        if args[:3] == ["remote", "get-url", "origin"]:
            return SimpleNamespace(returncode=0, stdout="https://github.com/owner/repo.git\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    class DummyPublishClient:
        def push_branch(self, workspace_dir: str, branch_name: str, remote_name: str = "origin"):
            assert workspace_dir == tmp_path.as_posix()
            assert branch_name == "feature/test"
            assert remote_name == "origin"
            return {"branch_name": branch_name, "pushed": True}

    monkeypatch.setattr("src.workflows.publish_result._run_git_command", _fake_run_git)

    result = push_prepared_branch(
        workspace_dir=tmp_path.as_posix(),
        branch_name="feature/test",
        commit_sha="abc123",
        publish_client=DummyPublishClient(),
    )

    assert result["pushed"] is True
    assert result["branch_name"] == "feature/test"
    assert result["commit_sha"] == "abc123"
    assert result["errors"] == []


def test_push_prepared_branch_handles_missing_remote(monkeypatch, tmp_path) -> None:
    class DummyPublishClient:
        def __init__(self) -> None:
            self.called = False

        def push_branch(self, workspace_dir: str, branch_name: str, remote_name: str = "origin"):
            self.called = True
            return {"branch_name": branch_name, "pushed": True}

    client = DummyPublishClient()

    def _fake_run_git(workspace_dir: str, args: list[str]):
        if args[:3] == ["remote", "get-url", "origin"]:
            return SimpleNamespace(returncode=2, stdout="", stderr="No such remote")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("src.workflows.publish_result._run_git_command", _fake_run_git)

    result = push_prepared_branch(
        workspace_dir=tmp_path.as_posix(),
        branch_name="feature/test",
        commit_sha="abc123",
        publish_client=client,
    )

    assert result["pushed"] is False
    assert result["commit_sha"] == "abc123"
    assert client.called is False
    assert "remote 'origin'" in result["errors"][0].lower()


def test_push_prepared_branch_handles_auth_failure(monkeypatch, tmp_path) -> None:
    def _fake_run_git(workspace_dir: str, args: list[str]):
        if args[:3] == ["remote", "get-url", "origin"]:
            return SimpleNamespace(returncode=0, stdout="https://github.com/owner/repo.git\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    class DummyPublishClient:
        def push_branch(self, workspace_dir: str, branch_name: str, remote_name: str = "origin"):
            raise PublishClientError("fatal: Authentication failed")

    monkeypatch.setattr("src.workflows.publish_result._run_git_command", _fake_run_git)

    result = push_prepared_branch(
        workspace_dir=tmp_path.as_posix(),
        branch_name="feature/test",
        commit_sha="abc123",
        publish_client=DummyPublishClient(),
    )

    assert result["pushed"] is False
    assert result["commit_sha"] == "abc123"
    assert "authentication failed" in result["errors"][0].lower()
