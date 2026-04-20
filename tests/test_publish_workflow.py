import json
from pathlib import Path

import pytest

from src.workflows.publish_result import PublishResultError, run_publish


REPO_URL = "https://github.com/owner/repo"


def _write_minimal_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "playground" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_payload = {
        "repo_url": REPO_URL,
        "owner": "owner",
        "repo": "repo",
        "workspace_dir": "playground/repos/owner/repo",
    }
    (output_dir / "repo_summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    run_task_payload = {
        "repo_url": REPO_URL,
        "task_id": "repo-task-001",
        "status": "completed",
    }
    (output_dir / "run_task_result.json").write_text(
        json.dumps(run_task_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_run_publish_success_path_writes_publish_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_artifacts(tmp_path)

    monkeypatch.setattr(
        "src.workflows.publish_result.PublishClient",
        lambda: object(),
    )
    monkeypatch.setattr(
        "src.workflows.publish_result.prepare_local_publish",
        lambda workspace_dir, task_id, branch_name: {
            "workspace_dir": workspace_dir,
            "branch_name": "feature/test",
            "commit_sha": "abc123",
            "committed": True,
            "has_changes": True,
        },
    )
    monkeypatch.setattr(
        "src.workflows.publish_result.push_prepared_branch",
        lambda workspace_dir, branch_name, commit_sha, publish_client, remote_name="origin": {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pushed": True,
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "src.workflows.publish_result.create_draft_pr_step",
        lambda repo_url, branch_name, base_branch, publish_client, output_dir: {
            "pr_created": True,
            "pr_url": "https://github.com/owner/repo/pull/99",
            "errors": [],
        },
    )

    message = run_publish(REPO_URL, draft_pr=True)

    result_file = tmp_path / "playground" / "outputs" / "publish_result.json"
    assert result_file.exists()
    payload = json.loads(result_file.read_text(encoding="utf-8"))

    assert payload["status"] == "completed"
    assert payload["task_id"] == "repo-task-001"
    assert payload["branch_name"] == "feature/test"
    assert payload["commit_sha"] == "abc123"
    assert payload["pushed"] is True
    assert payload["pr_created"] is True
    assert payload["pr_url"].endswith("/99")
    assert payload["draft_pr"] is True
    assert isinstance(payload["errors"], list)

    assert "Publish completed" in message
    assert "publish_result_file:" in message


def test_run_publish_handles_push_failure_after_commit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_artifacts(tmp_path)

    monkeypatch.setattr("src.workflows.publish_result.PublishClient", lambda: object())
    monkeypatch.setattr(
        "src.workflows.publish_result.prepare_local_publish",
        lambda workspace_dir, task_id, branch_name: {
            "workspace_dir": workspace_dir,
            "branch_name": "feature/test",
            "commit_sha": "abc123",
            "committed": True,
            "has_changes": True,
        },
    )
    monkeypatch.setattr(
        "src.workflows.publish_result.push_prepared_branch",
        lambda workspace_dir, branch_name, commit_sha, publish_client, remote_name="origin": {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pushed": False,
            "errors": ["fatal: auth failed"],
        },
    )

    called = {"value": False}

    def _fake_create_pr(*args, **kwargs):
        called["value"] = True
        return {"pr_created": True, "pr_url": "x", "errors": []}

    monkeypatch.setattr("src.workflows.publish_result.create_draft_pr_step", _fake_create_pr)

    message = run_publish(REPO_URL, draft_pr=True)

    payload = json.loads((tmp_path / "playground" / "outputs" / "publish_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["pushed"] is False
    assert payload["pr_created"] is False
    assert payload["commit_sha"] == "abc123"
    assert "auth failed" in payload["errors"][0].lower()
    assert called["value"] is False
    assert "status: failed" in message


def test_run_publish_handles_pr_failure_after_push(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_artifacts(tmp_path)

    monkeypatch.setattr("src.workflows.publish_result.PublishClient", lambda: object())
    monkeypatch.setattr(
        "src.workflows.publish_result.prepare_local_publish",
        lambda workspace_dir, task_id, branch_name: {
            "workspace_dir": workspace_dir,
            "branch_name": "feature/test",
            "commit_sha": "abc123",
            "committed": True,
            "has_changes": True,
        },
    )
    monkeypatch.setattr(
        "src.workflows.publish_result.push_prepared_branch",
        lambda workspace_dir, branch_name, commit_sha, publish_client, remote_name="origin": {
            "branch_name": branch_name,
            "commit_sha": commit_sha,
            "pushed": True,
            "errors": [],
        },
    )
    monkeypatch.setattr(
        "src.workflows.publish_result.create_draft_pr_step",
        lambda repo_url, branch_name, base_branch, publish_client, output_dir: {
            "pr_created": False,
            "pr_url": "",
            "errors": ["HTTP 422"],
        },
    )

    message = run_publish(REPO_URL, draft_pr=True)

    payload = json.loads((tmp_path / "playground" / "outputs" / "publish_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "partial"
    assert payload["pushed"] is True
    assert payload["pr_created"] is False
    assert payload["pr_url"] == ""
    assert "HTTP 422" in payload["errors"][0]
    assert "status: partial" in message


def test_run_publish_writes_result_when_no_changes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_artifacts(tmp_path)

    monkeypatch.setattr("src.workflows.publish_result.PublishClient", lambda: object())

    def _raise_no_changes(workspace_dir, task_id, branch_name):
        raise PublishResultError("No local changes to publish.")

    monkeypatch.setattr("src.workflows.publish_result.prepare_local_publish", _raise_no_changes)

    with pytest.raises(PublishResultError, match="No local changes"):
        run_publish(REPO_URL, draft_pr=True)

    payload = json.loads((tmp_path / "playground" / "outputs" / "publish_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["pushed"] is False
    assert payload["pr_created"] is False
    assert payload["errors"]


def test_run_publish_writes_result_when_branch_is_protected(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_artifacts(tmp_path)

    monkeypatch.setattr("src.workflows.publish_result.PublishClient", lambda: object())

    def _raise_protected(workspace_dir, task_id, branch_name):
        raise PublishResultError("Protected branch is not allowed for publish: main")

    monkeypatch.setattr("src.workflows.publish_result.prepare_local_publish", _raise_protected)

    with pytest.raises(PublishResultError, match="Protected branch"):
        run_publish(REPO_URL, branch_name="main", draft_pr=True)

    payload = json.loads((tmp_path / "playground" / "outputs" / "publish_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["pushed"] is False
    assert payload["pr_created"] is False
    assert payload["errors"]
