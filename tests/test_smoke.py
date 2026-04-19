import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


def test_help_command_runs() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "analyze" in result.stdout


def test_analyze_prepares_local_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    repo_url = "https://github.com/owner/repo"
    result = runner.invoke(app, ["analyze", repo_url])
    summary_file = tmp_path / "playground" / "outputs" / "repo_summary.json"
    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    workspace_path = tmp_path / "playground" / "repos" / "owner" / "repo"

    assert result.exit_code == 0
    assert summary_file.exists()
    assert candidate_file.exists()
    assert workspace_path.exists()
    assert workspace_path.is_dir()

    data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert data["repo_url"] == repo_url
    assert data["owner"] == "owner"
    assert data["repo"] == "repo"
    assert data["workspace_dir"] == "playground/repos/owner/repo"
    assert data["workspace_initialized"] == "created"
    assert data["status"] == "prepared"

    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    assert candidate_data["repo_url"] == repo_url
    assert candidate_data["owner"] == "owner"
    assert candidate_data["repo"] == "repo"
    assert isinstance(candidate_data["tasks"], list)
    assert len(candidate_data["tasks"]) > 0
    for task in candidate_data["tasks"]:
        assert "id" in task
        assert "title" in task
        assert "type" in task
        assert "priority" in task
        assert "status" in task

    assert "Local analysis preparation complete" in result.stdout
    assert "owner: owner" in result.stdout
    assert "repo: repo" in result.stdout
    assert "workspace_initialized: created" in result.stdout
    assert "candidate_tasks_count:" in result.stdout
    assert "status: prepared" in result.stdout


def test_analyze_reuses_existing_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    repo_url = "https://github.com/owner/repo"
    first_result = runner.invoke(app, ["analyze", repo_url])
    second_result = runner.invoke(app, ["analyze", repo_url])

    summary_file = tmp_path / "playground" / "outputs" / "repo_summary.json"
    workspace_path = tmp_path / "playground" / "repos" / "owner" / "repo"

    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert workspace_path.exists()
    assert summary_file.exists()

    data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert data["workspace_dir"] == "playground/repos/owner/repo"
    assert data["workspace_initialized"] == "reused"
    assert data["status"] == "prepared"

    assert "workspace_initialized: created" in first_result.stdout
    assert "workspace_initialized: reused" in second_result.stdout


@pytest.mark.parametrize(
    ("repo_url", "expected_error"),
    [
        (
            "https://gitlab.com/owner/repo",
            "Only GitHub URLs are supported",
        ),
        (
            "https://github.com/owner",
            "Missing owner/repo",
        ),
        (
            "not a url",
            "Malformed URL",
        ),
    ],
)
def test_analyze_rejects_invalid_urls(
    tmp_path: Path,
    monkeypatch,
    repo_url: str,
    expected_error: str,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["analyze", repo_url])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert expected_error in result.stdout
    assert "Traceback" not in result.stdout
    assert not (tmp_path / "playground" / "outputs").exists()


def test_plan_generates_task_plan_for_valid_task_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    plan_result = runner.invoke(app, ["plan", task_id])
    task_plan_file = tmp_path / "playground" / "outputs" / "task_plan.json"

    assert plan_result.exit_code == 0
    assert task_plan_file.exists()

    task_plan = json.loads(task_plan_file.read_text(encoding="utf-8"))
    assert task_plan["task_id"] == task_id
    assert task_plan["title"] == candidate_data["tasks"][0]["title"]
    assert "goal" in task_plan
    assert "proposed_changes" in task_plan
    assert "target_files" in task_plan
    assert "validation_steps" in task_plan
    assert "risk_level" in task_plan
    assert "status" in task_plan

    assert "Task plan generated" in plan_result.stdout
    assert "task_plan.json" in plan_result.stdout


def test_plan_rejects_invalid_task_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    result = runner.invoke(app, ["plan", "non-existent-task-id"])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "task_id not found" in result.stdout
    assert "Traceback" not in result.stdout


def test_patch_generates_preview_for_valid_task_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    plan_result = runner.invoke(app, ["plan", task_id])
    assert plan_result.exit_code == 0

    patch_result = runner.invoke(app, ["patch", task_id])
    patch_file = tmp_path / "playground" / "outputs" / "patch_preview.json"

    assert patch_result.exit_code == 0
    assert patch_file.exists()

    patch_preview = json.loads(patch_file.read_text(encoding="utf-8"))
    assert patch_preview["task_id"] == task_id
    assert "title" in patch_preview
    assert "target_files" in patch_preview
    assert "patch_strategy" in patch_preview
    assert "planned_edits" in patch_preview
    assert "validation_steps" in patch_preview
    assert "status" in patch_preview

    assert "Patch preview generated" in patch_result.stdout
    assert "patch_preview.json" in patch_result.stdout


def test_patch_rejects_invalid_task_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    plan_result = runner.invoke(app, ["plan", task_id])
    assert plan_result.exit_code == 0

    result = runner.invoke(app, ["patch", "non-existent-task-id"])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "task_id not found" in result.stdout
    assert "Traceback" not in result.stdout


def test_apply_generates_result_and_writes_workspace_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    plan_result = runner.invoke(app, ["plan", task_id])
    assert plan_result.exit_code == 0

    patch_result = runner.invoke(app, ["patch", task_id])
    assert patch_result.exit_code == 0

    apply_result = runner.invoke(app, ["apply", task_id])
    apply_result_file = tmp_path / "playground" / "outputs" / "patch_apply_result.json"

    assert apply_result.exit_code == 0
    assert apply_result_file.exists()

    payload = json.loads(apply_result_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert payload["workspace_dir"] == "playground/repos/owner/repo"
    assert isinstance(payload["applied_files"], list)
    assert isinstance(payload["created_files"], list)
    assert isinstance(payload["modified_files"], list)
    assert len(payload["applied_files"]) > 0
    assert payload["status"] == "applied"
    assert "summary" in payload

    for file_path in payload["applied_files"]:
        assert (tmp_path / file_path).exists()

    assert "Patch applied to workspace" in apply_result.stdout
    assert "patch_apply_result.json" in apply_result.stdout


def test_apply_rejects_invalid_task_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    plan_result = runner.invoke(app, ["plan", task_id])
    assert plan_result.exit_code == 0

    patch_result = runner.invoke(app, ["patch", task_id])
    assert patch_result.exit_code == 0

    result = runner.invoke(app, ["apply", "non-existent-task-id"])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "task_id not found" in result.stdout
    assert "Traceback" not in result.stdout


def test_validate_generates_validation_result_for_valid_task_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0

    validate_result = runner.invoke(app, ["validate", task_id])
    validation_file = tmp_path / "playground" / "outputs" / "validation_result.json"

    assert validate_result.exit_code == 0
    assert validation_file.exists()

    payload = json.loads(validation_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert payload["workspace_dir"] == "playground/repos/owner/repo"
    assert isinstance(payload["checked_files"], list)
    assert isinstance(payload["missing_files"], list)
    assert isinstance(payload["validation_steps"], list)
    assert payload["passed"] is True
    assert payload["status"] == "passed"
    assert "summary" in payload

    assert "Validation completed" in validate_result.stdout
    assert "validation_result.json" in validate_result.stdout


def test_validate_rejects_invalid_task_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0

    result = runner.invoke(app, ["validate", "non-existent-task-id"])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "task_id not found" in result.stdout
    assert "Traceback" not in result.stdout


def test_validate_fails_when_workspace_file_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0

    apply_file = tmp_path / "playground" / "outputs" / "patch_apply_result.json"
    apply_payload = json.loads(apply_file.read_text(encoding="utf-8"))
    missing_target = tmp_path / apply_payload["applied_files"][0]
    missing_target.unlink()

    validate_result = runner.invoke(app, ["validate", task_id])
    validation_file = tmp_path / "playground" / "outputs" / "validation_result.json"

    assert validate_result.exit_code == 0
    assert validation_file.exists()

    payload = json.loads(validation_file.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert apply_payload["applied_files"][0] in payload["missing_files"]

    assert "Validation completed" in validate_result.stdout
    assert "status: failed" in validate_result.stdout
