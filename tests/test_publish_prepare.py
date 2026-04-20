from types import SimpleNamespace

import pytest

from src.workflows.publish_result import PublishResultError, prepare_local_publish


def test_prepare_local_publish_with_changes_creates_branch_and_commit(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []

    def _fake_run(command, capture_output, text, check):
        commands.append(command)
        if command[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout=" M src/file.py\n", stderr="")
        if command[-3:] == ["--abbrev-ref", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
        if command[-4:-1] == ["--verify", "--quiet", "refs/heads/feature/test"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if command[-2:] == ["checkout", "-b"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[-2:] == ["add", "-A"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[-2] == "-m":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[-2:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")
        if command[-3:] == ["checkout", "-b", "feature/test"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("src.workflows.publish_result.subprocess.run", _fake_run)

    payload = prepare_local_publish(
        workspace_dir=tmp_path.as_posix(),
        task_id="repo-task-001",
        branch_name="feature/test",
    )

    assert payload["branch_name"] == "feature/test"
    assert payload["commit_sha"] == "abc123"
    assert payload["committed"] is True
    assert payload["has_changes"] is True


def test_prepare_local_publish_fails_when_no_changes(monkeypatch, tmp_path) -> None:
    commands: list[list[str]] = []

    def _fake_run(command, capture_output, text, check):
        commands.append(command)
        if command[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("src.workflows.publish_result.subprocess.run", _fake_run)

    with pytest.raises(PublishResultError, match="No local changes"):
        prepare_local_publish(
            workspace_dir=tmp_path.as_posix(),
            task_id="repo-task-001",
            branch_name="feature/test",
        )

    assert len(commands) == 1


def test_prepare_local_publish_blocks_protected_branch(monkeypatch, tmp_path) -> None:
    def _fake_run(command, capture_output, text, check):
        if command[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout=" M src/file.py\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("src.workflows.publish_result.subprocess.run", _fake_run)

    with pytest.raises(PublishResultError, match="Protected branch"):
        prepare_local_publish(
            workspace_dir=tmp_path.as_posix(),
            task_id="repo-task-001",
            branch_name="main",
        )


def test_prepare_local_publish_generates_default_branch_name(monkeypatch, tmp_path) -> None:
    def _fake_run(command, capture_output, text, check):
        if command[-2:] == ["status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout=" M src/file.py\n", stderr="")
        if command[-3:] == ["--abbrev-ref", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="feature/existing\n", stderr="")
        if command[-2:] == ["add", "-A"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[-2] == "-m":
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[-2:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("src.workflows.publish_result.subprocess.run", _fake_run)

    payload = prepare_local_publish(
        workspace_dir=tmp_path.as_posix(),
        task_id="repo-task-001",
        branch_name=None,
    )

    assert payload["branch_name"] == "publish/repo-task-001"
