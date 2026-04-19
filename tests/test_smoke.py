import os
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


@pytest.fixture(autouse=True)
def _disable_github_remote_in_default_tests(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_API_BASE_URL", raising=False)


def test_help_command_runs() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "analyze" in result.stdout


def test_llm_test_prerequisites_are_documented() -> None:
    env_example_text = Path(".env.example").read_text(encoding="utf-8")
    readme_text = Path("README.md").read_text(encoding="utf-8")
    llm_integration_test_text = Path("tests/test_llm_integration.py").read_text(encoding="utf-8")

    required_note = "运行 llm_integration 测试前必须提供真实 LLM 环境变量"
    assert required_note in env_example_text
    assert "LLM_API_KEY" in env_example_text
    assert "LLM_BASE_URL" in env_example_text
    assert "LLM_MODEL" in env_example_text

    assert required_note in readme_text
    assert "pytest -q" in readme_text
    assert "pytest -q -m llm_integration -o addopts=\"\"" in readme_text
    assert "RUN_LLM_INTEGRATION=1" in env_example_text
    assert "run-task" in readme_text
    assert "--use-llm-discover" in readme_text
    assert "--use-llm-plan" in readme_text
    assert "--use-llm-patch" in readme_text
    assert "--use-llm-apply" in readme_text
    assert "--use-llm-validate" in readme_text
    assert "--use-llm-pr-draft" in readme_text
    assert "test_run_task_use_llm_real_integration" in llm_integration_test_text


def test_pytest_default_excludes_llm_integration_marker() -> None:
    pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[tool.pytest.ini_options]" in pyproject_text
    assert "addopts" in pyproject_text
    assert "not llm_integration" in pyproject_text


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
    assert data["repo_metadata"] is None
    assert data["sample_open_issues"] == []
    assert data["status"] == "prepared"

    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    assert candidate_data["repo_url"] == repo_url
    assert candidate_data["owner"] == "owner"
    assert candidate_data["repo"] == "repo"
    assert candidate_data["issue_context_used"] is False
    assert candidate_data["fallback_triggered"] is True
    assert isinstance(candidate_data["tasks"], list)
    assert len(candidate_data["tasks"]) > 0
    for task in candidate_data["tasks"]:
        assert "id" in task
        assert "title" in task
        assert "type" in task
        assert "priority" in task
        assert "status" in task
        assert "source" in task
        assert task["source"] == "template"
        assert "issue_number" not in task

    assert "Local analysis preparation complete" in result.stdout
    assert "owner: owner" in result.stdout
    assert "repo: repo" in result.stdout
    assert "workspace_initialized: created" in result.stdout
    assert "candidate_tasks_count:" in result.stdout
    assert "candidate_issue_context_used: false" in result.stdout
    assert "candidate_fallback_triggered: true" in result.stdout
    assert "github_remote_used: false" in result.stdout
    assert "github_fallback_triggered: false" in result.stdout
    assert "status: prepared" in result.stdout


def test_analyze_includes_github_remote_data_when_token_and_client_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            assert owner == "owner"
            assert repo == "repo"
            return {
                "full_name": "owner/repo",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 5,
            }

        def get_open_issues(self, owner: str, repo: str, limit: int = 3) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 1, "title": "Issue one", "state": "open"},
                {"number": 2, "title": "Issue two", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

    result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    summary_file = tmp_path / "playground" / "outputs" / "repo_summary.json"
    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"

    assert result.exit_code == 0
    assert summary_file.exists()
    assert candidate_file.exists()

    data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert data["repo_metadata"] == {
        "full_name": "owner/repo",
        "description": "dummy repo",
        "default_branch": "main",
        "open_issues_count": 5,
    }
    assert data["sample_open_issues"] == [
        {"number": 1, "title": "Issue one", "state": "open"},
        {"number": 2, "title": "Issue two", "state": "open"},
    ]

    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    assert candidate_data["issue_context_used"] is True
    assert candidate_data["fallback_triggered"] is False
    assert isinstance(candidate_data["tasks"], list)
    assert len(candidate_data["tasks"]) == 2
    assert candidate_data["tasks"][0]["source"] == "github_issue"
    assert candidate_data["tasks"][0]["issue_number"] == 1
    assert candidate_data["tasks"][1]["source"] == "github_issue"
    assert candidate_data["tasks"][1]["issue_number"] == 2

    assert "github_remote_used: true" in result.stdout
    assert "github_fallback_triggered: false" in result.stdout
    assert "candidate_issue_context_used: true" in result.stdout
    assert "candidate_fallback_triggered: false" in result.stdout


def test_analyze_gracefully_degrades_when_github_read_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyError(ValueError):
        pass

    def _raise_failure():
        raise DummyError("github read failed")

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        _raise_failure,
    )
    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClientError",
        DummyError,
    )

    result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    summary_file = tmp_path / "playground" / "outputs" / "repo_summary.json"
    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"

    assert result.exit_code == 0
    assert summary_file.exists()
    assert candidate_file.exists()

    data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert data["repo_metadata"] is None
    assert data["sample_open_issues"] == []

    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    assert candidate_data["issue_context_used"] is False
    assert candidate_data["fallback_triggered"] is True
    assert isinstance(candidate_data["tasks"], list)
    assert len(candidate_data["tasks"]) > 0
    for task in candidate_data["tasks"]:
        assert task["source"] == "template"
        assert "issue_number" not in task

    assert "github_remote_used: false" in result.stdout
    assert "github_fallback_triggered: true" in result.stdout
    assert "candidate_issue_context_used: false" in result.stdout
    assert "candidate_fallback_triggered: true" in result.stdout
    assert "github read failed" in result.stdout


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


def test_discover_tasks_generates_issue_aware_candidates_for_github_issue_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            return {
                "full_name": f"{owner}/{repo}",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 2,
            }

        def get_open_issues(
            self,
            owner: str,
            repo: str,
            limit: int = 3,
        ) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 1, "title": "Issue one", "state": "open"},
                {"number": 2, "title": "Issue two", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

    assert runner.invoke(app, ["analyze", "https://github.com/owner/repo"]).exit_code == 0

    result = runner.invoke(app, ["discover-tasks", "https://github.com/owner/repo"])
    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"

    assert result.exit_code == 0
    assert candidate_file.exists()

    payload = json.loads(candidate_file.read_text(encoding="utf-8"))
    assert payload["issue_context_used"] is True
    assert payload["fallback_triggered"] is False
    assert payload["used_llm"] is False
    assert isinstance(payload["tasks"], list)
    assert len(payload["tasks"]) == 2
    assert payload["tasks"][0]["source"] == "github_issue"
    assert payload["tasks"][0]["issue_number"] == 1
    assert payload["tasks"][1]["source"] == "github_issue"
    assert payload["tasks"][1]["issue_number"] == 2

    assert "Candidate task discovery complete" in result.stdout
    assert "candidate_tasks_file:" in result.stdout
    assert "candidate_issue_context_used: true" in result.stdout
    assert "candidate_fallback_triggered: false" in result.stdout
    assert "used_llm: false" in result.stdout


def test_discover_tasks_generates_template_fallback_when_no_issue_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["analyze", "https://github.com/owner/repo"]).exit_code == 0

    result = runner.invoke(app, ["discover-tasks", "https://github.com/owner/repo"])
    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"

    assert result.exit_code == 0
    assert candidate_file.exists()

    payload = json.loads(candidate_file.read_text(encoding="utf-8"))
    assert payload["issue_context_used"] is False
    assert payload["fallback_triggered"] is True
    assert payload["used_llm"] is False
    assert isinstance(payload["tasks"], list)
    assert len(payload["tasks"]) > 0
    for task in payload["tasks"]:
        assert task["source"] == "template"
        assert "issue_number" not in task

    assert "Candidate task discovery complete" in result.stdout
    assert "candidate_tasks_file:" in result.stdout
    assert "candidate_issue_context_used: false" in result.stdout
    assert "candidate_fallback_triggered: true" in result.stdout
    assert "used_llm: false" in result.stdout


def test_discover_tasks_use_llm_falls_back_to_rule_when_llm_request_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["analyze", "https://github.com/owner/repo"]).exit_code == 0

    from src.llm_client import LLMClientError

    def _raise_llm_failure():
        raise LLMClientError("Missing LLM config: LLM_API_KEY")

    monkeypatch.setattr("src.llm_client.LLMClient.from_env", _raise_llm_failure)

    result = runner.invoke(
        app,
        ["discover-tasks", "https://github.com/owner/repo", "--use-llm"],
    )
    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"

    assert result.exit_code == 0
    assert candidate_file.exists()

    payload = json.loads(candidate_file.read_text(encoding="utf-8"))
    assert payload["issue_context_used"] is False
    assert payload["fallback_triggered"] is True
    assert payload["used_llm"] is False
    assert payload["fallback_reason"] == "Missing LLM config: LLM_API_KEY"
    assert isinstance(payload["tasks"], list)
    assert len(payload["tasks"]) > 0

    assert "Candidate task discovery complete" in result.stdout
    assert "candidate_tasks_file:" in result.stdout
    assert "candidate_issue_context_used: false" in result.stdout
    assert "candidate_fallback_triggered: true" in result.stdout
    assert "used_llm: false" in result.stdout
    assert "fallback_reason: Missing LLM config: LLM_API_KEY" in result.stdout


def test_plan_generates_issue_aware_task_plan_for_github_issue_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            return {
                "full_name": f"{owner}/{repo}",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 1,
            }

        def get_open_issues(
            self,
            owner: str,
            repo: str,
            limit: int = 3,
        ) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 7, "title": "Fix flaky planner output", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

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
    assert "issue #7" in task_plan["goal"].lower()
    assert "proposed_changes" in task_plan
    assert isinstance(task_plan["proposed_changes"], list)
    assert len(task_plan["proposed_changes"]) > 0
    assert "target_files" in task_plan
    assert isinstance(task_plan["target_files"], list)
    assert len(task_plan["target_files"]) > 0
    assert "validation_steps" in task_plan
    assert isinstance(task_plan["validation_steps"], list)
    assert len(task_plan["validation_steps"]) > 0
    assert "risk_level" in task_plan
    assert "status" in task_plan
    assert task_plan["status"] == "planned"
    assert task_plan["source"] == "github_issue"
    assert task_plan["issue_number"] == 7
    assert task_plan["issue_context_used"] is True
    assert task_plan["fallback_triggered"] is False
    assert task_plan["used_llm"] is False
    assert ("fallback_reason" not in task_plan) or (task_plan["fallback_reason"] == "")

    assert "Task plan generated" in plan_result.stdout
    assert "task_plan_issue_context_used: true" in plan_result.stdout
    assert "task_plan_fallback_triggered: false" in plan_result.stdout
    assert "used_llm: false" in plan_result.stdout
    assert "task_plan.json" in plan_result.stdout


def test_plan_generates_template_fallback_for_non_issue_source(
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
    assert task_plan["source"] == "template"
    assert task_plan["issue_context_used"] is False
    assert task_plan["fallback_triggered"] is True
    assert task_plan["used_llm"] is False
    assert ("fallback_reason" not in task_plan) or (task_plan["fallback_reason"] == "")
    assert ("issue_number" not in task_plan) or (task_plan["issue_number"] is None)

    assert "Task plan generated" in plan_result.stdout
    assert "task_plan_issue_context_used: false" in plan_result.stdout
    assert "task_plan_fallback_triggered: true" in plan_result.stdout
    assert "used_llm: false" in plan_result.stdout
    assert "task_plan_file:" in plan_result.stdout


def test_plan_use_llm_falls_back_to_rule_when_llm_request_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    from src.llm_client import LLMClientError

    def _raise_llm_failure():
        raise LLMClientError("Missing LLM config: LLM_API_KEY")

    monkeypatch.setattr("src.llm_client.LLMClient.from_env", _raise_llm_failure)

    plan_result = runner.invoke(app, ["plan", task_id, "--use-llm"])
    task_plan_file = tmp_path / "playground" / "outputs" / "task_plan.json"

    assert plan_result.exit_code == 0
    assert task_plan_file.exists()

    task_plan = json.loads(task_plan_file.read_text(encoding="utf-8"))
    assert task_plan["task_id"] == task_id
    assert task_plan["source"] == "template"
    assert task_plan["issue_context_used"] is False
    assert task_plan["fallback_triggered"] is True
    assert task_plan["used_llm"] is False
    assert task_plan["fallback_reason"] == "Missing LLM config: LLM_API_KEY"

    assert "Task plan generated" in plan_result.stdout
    assert "task_plan_file:" in plan_result.stdout
    assert "task_plan_issue_context_used: false" in plan_result.stdout
    assert "task_plan_fallback_triggered: true" in plan_result.stdout
    assert "used_llm: false" in plan_result.stdout
    assert "fallback_reason: Missing LLM config: LLM_API_KEY" in plan_result.stdout


def test_plan_rejects_invalid_task_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    result = runner.invoke(app, ["plan", "non-existent-task-id"])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "task_id not found" in result.stdout
    assert "Traceback" not in result.stdout


def test_patch_generates_issue_aware_preview_for_github_issue_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            return {
                "full_name": f"{owner}/{repo}",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 1,
            }

        def get_open_issues(
            self,
            owner: str,
            repo: str,
            limit: int = 3,
        ) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 7, "title": "Fix flaky planner output", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

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
    assert patch_preview["title"] == candidate_data["tasks"][0]["title"]
    assert "target_files" in patch_preview
    assert isinstance(patch_preview["target_files"], list)
    assert len(patch_preview["target_files"]) > 0
    assert patch_preview["patch_strategy"] == "issue-context-preview"
    assert "planned_edits" in patch_preview
    assert isinstance(patch_preview["planned_edits"], list)
    assert len(patch_preview["planned_edits"]) > 0
    assert "validation_steps" in patch_preview
    assert isinstance(patch_preview["validation_steps"], list)
    assert len(patch_preview["validation_steps"]) > 0
    assert patch_preview["status"] == "preview_generated"
    assert patch_preview["source"] == "github_issue"
    assert patch_preview["issue_number"] == 7
    assert patch_preview["issue_context_used"] is True
    assert patch_preview["fallback_triggered"] is False
    assert patch_preview["used_llm"] is False
    assert ("fallback_reason" not in patch_preview) or (patch_preview["fallback_reason"] == "")

    assert "Patch preview generated" in patch_result.stdout
    assert "patch_issue_context_used: true" in patch_result.stdout
    assert "patch_fallback_triggered: false" in patch_result.stdout
    assert "used_llm: false" in patch_result.stdout
    assert "patch_preview.json" in patch_result.stdout


def test_patch_generates_template_fallback_for_non_issue_source(
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
    assert patch_preview["title"] == candidate_data["tasks"][0]["title"]
    assert "target_files" in patch_preview
    assert "patch_strategy" in patch_preview
    assert patch_preview["patch_strategy"] == "minimal-rule-based-preview"
    assert "planned_edits" in patch_preview
    assert "validation_steps" in patch_preview
    assert patch_preview["status"] == "preview_generated"
    assert patch_preview["source"] == "template"
    assert patch_preview["issue_context_used"] is False
    assert patch_preview["fallback_triggered"] is True
    assert patch_preview["used_llm"] is False
    assert ("fallback_reason" not in patch_preview) or (patch_preview["fallback_reason"] == "")
    assert ("issue_number" not in patch_preview) or (patch_preview["issue_number"] is None)

    assert "Patch preview generated" in patch_result.stdout
    assert "patch_issue_context_used: false" in patch_result.stdout
    assert "patch_fallback_triggered: true" in patch_result.stdout
    assert "used_llm: false" in patch_result.stdout
    assert "patch_preview_file:" in patch_result.stdout


def test_patch_use_llm_falls_back_to_rule_when_llm_request_fails(
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

    from src.llm_client import LLMClientError

    def _raise_llm_failure():
        raise LLMClientError("Missing LLM config: LLM_API_KEY")

    monkeypatch.setattr("src.llm_client.LLMClient.from_env", _raise_llm_failure)

    patch_result = runner.invoke(app, ["patch", task_id, "--use-llm"])
    patch_file = tmp_path / "playground" / "outputs" / "patch_preview.json"

    assert patch_result.exit_code == 0
    assert patch_file.exists()

    patch_preview = json.loads(patch_file.read_text(encoding="utf-8"))
    assert patch_preview["task_id"] == task_id
    assert patch_preview["source"] == "template"
    assert patch_preview["issue_context_used"] is False
    assert patch_preview["fallback_triggered"] is True
    assert patch_preview["used_llm"] is False
    assert patch_preview["fallback_reason"] == "Missing LLM config: LLM_API_KEY"

    assert "Patch preview generated" in patch_result.stdout
    assert "patch_preview_file:" in patch_result.stdout
    assert "patch_issue_context_used: false" in patch_result.stdout
    assert "patch_fallback_triggered: true" in patch_result.stdout
    assert "used_llm: false" in patch_result.stdout
    assert "fallback_reason: Missing LLM config: LLM_API_KEY" in patch_result.stdout


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


def test_apply_generates_issue_aware_result_for_github_issue_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            return {
                "full_name": f"{owner}/{repo}",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 1,
            }

        def get_open_issues(
            self,
            owner: str,
            repo: str,
            limit: int = 3,
        ) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 7, "title": "Fix flaky planner output", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

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
    assert payload["source"] == "github_issue"
    assert payload["issue_number"] == 7
    assert payload["issue_context_used"] is True
    assert payload["fallback_triggered"] is False
    assert payload["used_llm"] is False
    assert ("fallback_reason" not in payload) or (payload["fallback_reason"] == "")

    for file_path in payload["applied_files"]:
        assert (tmp_path / file_path).exists()

    patch_log_file = tmp_path / "playground" / "repos" / "owner" / "repo" / "APPLIED_PATCH_LOG.md"
    assert patch_log_file.exists()
    assert "issue #7" in patch_log_file.read_text(encoding="utf-8").lower()

    assert "Patch applied to workspace" in apply_result.stdout
    assert "patch_apply_issue_context_used: true" in apply_result.stdout
    assert "patch_apply_fallback_triggered: false" in apply_result.stdout
    assert "used_llm: false" in apply_result.stdout
    assert "patch_apply_result.json" in apply_result.stdout


def test_apply_generates_template_fallback_for_non_issue_source(
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
    assert payload["source"] == "template"
    assert payload["issue_context_used"] is False
    assert payload["fallback_triggered"] is True
    assert payload["used_llm"] is False
    assert ("fallback_reason" not in payload) or (payload["fallback_reason"] == "")
    assert ("issue_number" not in payload) or (payload["issue_number"] is None)

    for file_path in payload["applied_files"]:
        assert (tmp_path / file_path).exists()

    assert "Patch applied to workspace" in apply_result.stdout
    assert "patch_apply_issue_context_used: false" in apply_result.stdout
    assert "patch_apply_fallback_triggered: true" in apply_result.stdout
    assert "used_llm: false" in apply_result.stdout
    assert "patch_apply_result_file:" in apply_result.stdout


def test_apply_use_llm_uses_llm_summary_when_request_succeeds(
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

    class DummyLLMClient:
        def generate(self, prompt: str) -> str:
            assert "Task ID" in prompt
            return json.dumps(
                {
                    "summary": "LLM apply summary for task execution.",
                }
            )

    monkeypatch.setattr(
        "src.workflows.apply_patch.LLMClient.from_env",
        lambda: DummyLLMClient(),
    )

    apply_result = runner.invoke(app, ["apply", task_id, "--use-llm"])
    apply_result_file = tmp_path / "playground" / "outputs" / "patch_apply_result.json"

    assert apply_result.exit_code == 0
    assert apply_result_file.exists()

    payload = json.loads(apply_result_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert payload["used_llm"] is True
    assert payload["summary"] == "LLM apply summary for task execution."
    assert ("fallback_reason" not in payload) or (payload["fallback_reason"] == "")

    assert "Patch applied to workspace" in apply_result.stdout
    assert "used_llm: true" in apply_result.stdout
    assert "patch_apply_result_file:" in apply_result.stdout


def test_apply_use_llm_falls_back_to_rule_when_llm_request_fails(
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

    from src.llm_client import LLMClientError

    def _raise_llm_failure():
        raise LLMClientError("Missing LLM config: LLM_API_KEY")

    monkeypatch.setattr("src.workflows.apply_patch.LLMClient.from_env", _raise_llm_failure)

    apply_result = runner.invoke(app, ["apply", task_id, "--use-llm"])
    apply_result_file = tmp_path / "playground" / "outputs" / "patch_apply_result.json"

    assert apply_result.exit_code == 0
    assert apply_result_file.exists()

    payload = json.loads(apply_result_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert payload["used_llm"] is False
    assert payload["fallback_reason"] == "Missing LLM config: LLM_API_KEY"

    assert "Patch applied to workspace" in apply_result.stdout
    assert "used_llm: false" in apply_result.stdout
    assert "fallback_reason: Missing LLM config: LLM_API_KEY" in apply_result.stdout
    assert "patch_apply_result_file:" in apply_result.stdout


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


def test_validate_generates_issue_aware_validation_result_for_github_issue_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            return {
                "full_name": f"{owner}/{repo}",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 1,
            }

        def get_open_issues(
            self,
            owner: str,
            repo: str,
            limit: int = 3,
        ) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 7, "title": "Fix flaky planner output", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

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
    assert payload["source"] == "github_issue"
    assert payload["issue_number"] == 7
    assert payload["issue_context_used"] is True
    assert payload["fallback_triggered"] is False
    assert payload["used_llm"] is False
    assert ("fallback_reason" not in payload) or (payload["fallback_reason"] == "")

    assert "Validation completed" in validate_result.stdout
    assert "validation_issue_context_used: true" in validate_result.stdout
    assert "validation_fallback_triggered: false" in validate_result.stdout
    assert "used_llm: false" in validate_result.stdout
    assert "validation_result.json" in validate_result.stdout


def test_validate_generates_template_fallback_for_non_issue_source(
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
    assert payload["source"] == "template"
    assert payload["issue_context_used"] is False
    assert payload["fallback_triggered"] is True
    assert payload["used_llm"] is False
    assert ("fallback_reason" not in payload) or (payload["fallback_reason"] == "")
    assert ("issue_number" not in payload) or (payload["issue_number"] is None)

    assert "Validation completed" in validate_result.stdout
    assert "validation_issue_context_used: false" in validate_result.stdout
    assert "validation_fallback_triggered: true" in validate_result.stdout
    assert "used_llm: false" in validate_result.stdout
    assert "validation_result.json" in validate_result.stdout


def test_validate_use_llm_uses_llm_summary_and_steps_when_request_succeeds(
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

    class DummyLLMClient:
        def generate(self, prompt: str) -> str:
            assert "Task ID" in prompt
            return json.dumps(
                {
                    "summary": "LLM validation summary for verified apply output.",
                    "validation_steps": [
                        "LLM reviewed checked files and found no mismatches.",
                        "LLM confirmed validation evidence is consistent.",
                    ],
                }
            )

    monkeypatch.setattr(
        "src.workflows.validate_patch.LLMClient.from_env",
        lambda: DummyLLMClient(),
    )

    validate_result = runner.invoke(app, ["validate", task_id, "--use-llm"])
    validation_file = tmp_path / "playground" / "outputs" / "validation_result.json"

    assert validate_result.exit_code == 0
    assert validation_file.exists()

    payload = json.loads(validation_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert payload["used_llm"] is True
    assert payload["summary"] == "LLM validation summary for verified apply output."
    assert payload["validation_steps"] == [
        "LLM reviewed checked files and found no mismatches.",
        "LLM confirmed validation evidence is consistent.",
    ]
    assert ("fallback_reason" not in payload) or (payload["fallback_reason"] == "")

    assert "Validation completed" in validate_result.stdout
    assert "used_llm: true" in validate_result.stdout
    assert "validation_result_file:" in validate_result.stdout


def test_validate_use_llm_falls_back_to_rule_when_llm_request_fails(
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

    from src.llm_client import LLMClientError

    def _raise_llm_failure():
        raise LLMClientError("Missing LLM config: LLM_API_KEY")

    monkeypatch.setattr("src.workflows.validate_patch.LLMClient.from_env", _raise_llm_failure)

    validate_result = runner.invoke(app, ["validate", task_id, "--use-llm"])
    validation_file = tmp_path / "playground" / "outputs" / "validation_result.json"

    assert validate_result.exit_code == 0
    assert validation_file.exists()

    payload = json.loads(validation_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert payload["used_llm"] is False
    assert payload["fallback_reason"] == "Missing LLM config: LLM_API_KEY"

    assert "Validation completed" in validate_result.stdout
    assert "used_llm: false" in validate_result.stdout
    assert "fallback_reason: Missing LLM config: LLM_API_KEY" in validate_result.stdout
    assert "validation_result_file:" in validate_result.stdout


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
    assert payload["source"] == "template"
    assert payload["issue_context_used"] is False
    assert payload["fallback_triggered"] is True
    assert payload["used_llm"] is False
    assert ("fallback_reason" not in payload) or (payload["fallback_reason"] == "")
    assert ("issue_number" not in payload) or (payload["issue_number"] is None)

    assert "Validation completed" in validate_result.stdout
    assert "status: failed" in validate_result.stdout
    assert "validation_issue_context_used: false" in validate_result.stdout
    assert "validation_fallback_triggered: true" in validate_result.stdout
    assert "used_llm: false" in validate_result.stdout


def test_pr_draft_generates_issue_aware_rule_draft_for_github_issue_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            return {
                "full_name": f"{owner}/{repo}",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 1,
            }

        def get_open_issues(
            self,
            owner: str,
            repo: str,
            limit: int = 3,
        ) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 7, "title": "Fix flaky planner output", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0
    assert runner.invoke(app, ["validate", task_id]).exit_code == 0

    pr_result = runner.invoke(app, ["pr-draft", task_id])
    pr_json = tmp_path / "playground" / "outputs" / "pr_draft.json"
    pr_md = tmp_path / "playground" / "outputs" / "pr_draft.md"
    pr_llm_md = tmp_path / "playground" / "outputs" / "pr_draft_llm.md"

    assert pr_result.exit_code == 0
    assert pr_json.exists()
    assert pr_md.exists()
    assert not pr_llm_md.exists()

    payload = json.loads(pr_json.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert "title" in payload
    assert "summary" in payload
    assert "changes" in payload
    assert "validation" in payload
    assert "risks" in payload
    assert "status" in payload
    assert payload["source"] == "github_issue"
    assert payload["issue_number"] == 7
    assert payload["issue_context_used"] is True
    assert payload["fallback_triggered"] is False

    markdown = pr_md.read_text(encoding="utf-8")
    assert "# PR Draft" in markdown
    assert "issue-aware" in markdown.lower()
    assert "issue #7" in markdown.lower()
    assert "## Changes" in markdown
    assert "## Validation" in markdown
    assert ("## Risks" in markdown) or ("## Notes" in markdown)

    assert "PR draft generated" in pr_result.stdout
    assert "used_llm: false" in pr_result.stdout
    assert "rule_issue_context_used: true" in pr_result.stdout
    assert "rule_fallback_triggered: false" in pr_result.stdout
    assert "pr_draft.json" in pr_result.stdout
    assert "pr_draft.md" in pr_result.stdout


def test_pr_draft_generates_template_fallback_rule_draft_for_non_issue_source(
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
    assert runner.invoke(app, ["validate", task_id]).exit_code == 0

    pr_result = runner.invoke(app, ["pr-draft", task_id])
    pr_json = tmp_path / "playground" / "outputs" / "pr_draft.json"
    pr_md = tmp_path / "playground" / "outputs" / "pr_draft.md"
    pr_llm_md = tmp_path / "playground" / "outputs" / "pr_draft_llm.md"

    assert pr_result.exit_code == 0
    assert pr_json.exists()
    assert pr_md.exists()
    assert not pr_llm_md.exists()

    payload = json.loads(pr_json.read_text(encoding="utf-8"))
    assert payload["task_id"] == task_id
    assert "title" in payload
    assert "summary" in payload
    assert "changes" in payload
    assert "validation" in payload
    assert "risks" in payload
    assert "status" in payload
    assert payload["source"] == "template"
    assert payload["issue_context_used"] is False
    assert payload["fallback_triggered"] is True
    assert ("issue_number" not in payload) or (payload["issue_number"] is None)

    markdown = pr_md.read_text(encoding="utf-8")
    assert "# PR Draft" in markdown
    assert task_id in markdown
    assert "template fallback" in markdown.lower()
    assert "## Changes" in markdown
    assert "## Validation" in markdown
    assert ("## Risks" in markdown) or ("## Notes" in markdown)

    assert "PR draft generated" in pr_result.stdout
    assert "used_llm: false" in pr_result.stdout
    assert "rule_issue_context_used: false" in pr_result.stdout
    assert "rule_fallback_triggered: true" in pr_result.stdout
    assert "pr_draft.json" in pr_result.stdout
    assert "pr_draft.md" in pr_result.stdout


def test_pr_draft_rejects_invalid_task_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0
    assert runner.invoke(app, ["validate", task_id]).exit_code == 0

    result = runner.invoke(app, ["pr-draft", "non-existent-task-id"])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "task_id not found" in result.stdout
    assert "Traceback" not in result.stdout


@pytest.mark.llm_integration
def test_pr_draft_use_llm_falls_back_when_real_llm_request_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    if os.getenv("RUN_LLM_INTEGRATION") != "1":
        pytest.skip("Set RUN_LLM_INTEGRATION=1 to run llm_integration tests.")

    monkeypatch.chdir(tmp_path)

    required_envs = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]
    missing = [name for name in required_envs if not os.getenv(name, "").strip()]
    assert not missing, (
        "Missing required real LLM env vars before pytest: "
        + ", ".join(missing)
    )

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    candidate_data = json.loads(candidate_file.read_text(encoding="utf-8"))
    task_id = candidate_data["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0
    assert runner.invoke(app, ["validate", task_id]).exit_code == 0

    monkeypatch.setenv("LLM_API_KEY", os.getenv("LLM_API_KEY", "").strip())
    monkeypatch.setenv("LLM_MODEL", os.getenv("LLM_MODEL", "").strip())
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")

    result = runner.invoke(app, ["pr-draft", task_id, "--use-llm"])
    pr_json = tmp_path / "playground" / "outputs" / "pr_draft.json"
    pr_md = tmp_path / "playground" / "outputs" / "pr_draft.md"
    pr_llm_md = tmp_path / "playground" / "outputs" / "pr_draft_llm.md"

    assert result.exit_code == 0
    assert pr_json.exists()
    assert pr_json.read_text(encoding="utf-8").strip() != ""
    assert pr_md.exists()
    assert pr_md.read_text(encoding="utf-8").strip() != ""
    assert not pr_llm_md.exists()
    assert "used_llm: false" in result.stdout
    assert "fallback_triggered: true" in result.stdout
    assert "fallback_reason:" in result.stdout


def test_run_task_generates_template_fallback_summary_for_non_issue_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    repo_url = "https://github.com/owner/repo"
    task_id = "repo-task-001"

    result = runner.invoke(app, ["run-task", repo_url, task_id])
    run_task_file = tmp_path / "playground" / "outputs" / "run_task_result.json"

    assert result.exit_code == 0
    assert run_task_file.exists()

    payload = json.loads(run_task_file.read_text(encoding="utf-8"))
    assert payload["repo_url"] == repo_url
    assert payload["task_id"] == task_id
    assert isinstance(payload["steps_completed"], list)
    assert payload["steps_completed"] == [
        "analyze",
        "plan",
        "patch",
        "apply",
        "validate",
        "pr-draft",
    ]
    assert isinstance(payload["artifacts"], dict)
    assert payload["passed"] is True
    assert payload["status"] == "completed"
    assert "summary" in payload
    assert payload["source"] == "template"
    assert payload["issue_context_used"] is False
    assert ("issue_number" not in payload) or (payload["issue_number"] is None)
    assert payload["final_validation_passed"] is True
    assert isinstance(payload["fallback_summary"], dict)
    assert payload["fallback_summary"]["planning"] is True
    assert payload["fallback_summary"]["patch"] is True
    assert payload["fallback_summary"]["apply"] is True
    assert payload["fallback_summary"]["validate"] is True
    assert payload["fallback_summary"]["pr_draft"] is True
    assert payload["llm_steps_requested"] == {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    assert payload["llm_steps_used"] == {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    assert payload["llm_steps_fallback"] == {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    assert payload["final_discover_used_llm"] is False
    assert payload["final_plan_used_llm"] is False
    assert payload["final_patch_used_llm"] is False
    assert payload["final_apply_used_llm"] is False
    assert payload["final_validate_used_llm"] is False
    assert payload["final_pr_draft_used_llm"] is False

    for artifact_path in payload["artifacts"].values():
        assert (tmp_path / str(artifact_path)).exists()

    assert "Run task completed" in result.stdout
    assert "status: completed" in result.stdout
    assert "run_task_issue_context_used: false" in result.stdout
    assert "run_task_issue_number: none" in result.stdout
    assert "run_task_fallback_summary:" in result.stdout
    assert "run_task_llm_steps_requested:" in result.stdout
    assert "run_task_llm_steps_used:" in result.stdout
    assert "run_task_llm_steps_fallback:" in result.stdout
    assert "run_task_result.json" in result.stdout


def test_run_task_succeeds_when_requested_llm_steps_fall_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    from src.llm_client import LLMClientError

    def _raise_llm_failure():
        raise LLMClientError("Missing LLM config: LLM_API_KEY")

    monkeypatch.setattr("src.llm_client.LLMClient.from_env", _raise_llm_failure)

    repo_url = "https://github.com/owner/repo"
    result = runner.invoke(
        app,
        [
            "run-task",
            repo_url,
            "repo-task-001",
            "--use-llm-discover",
            "--use-llm-plan",
            "--use-llm-patch",
            "--use-llm-apply",
            "--use-llm-validate",
            "--use-llm-pr-draft",
        ],
    )
    run_task_file = tmp_path / "playground" / "outputs" / "run_task_result.json"

    assert result.exit_code == 0
    assert run_task_file.exists()

    payload = json.loads(run_task_file.read_text(encoding="utf-8"))
    assert payload["repo_url"] == repo_url
    assert payload["task_id"] == "repo-task-001"
    assert payload["status"] == "completed"
    assert payload["passed"] is True
    assert payload["llm_steps_requested"] == {
        "discover": True,
        "plan": True,
        "patch": True,
        "apply": True,
        "validate": True,
        "pr_draft": True,
    }
    assert payload["llm_steps_used"] == {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    assert payload["llm_steps_fallback"] == {
        "discover": True,
        "plan": True,
        "patch": True,
        "apply": True,
        "validate": True,
        "pr_draft": True,
    }
    assert payload["final_discover_used_llm"] is False
    assert payload["final_plan_used_llm"] is False
    assert payload["final_patch_used_llm"] is False
    assert payload["final_apply_used_llm"] is False
    assert payload["final_validate_used_llm"] is False
    assert payload["final_pr_draft_used_llm"] is False

    assert "status: completed" in result.stdout
    assert "run_task_llm_steps_requested:" in result.stdout
    assert "run_task_llm_steps_used:" in result.stdout
    assert "run_task_llm_steps_fallback:" in result.stdout
    assert "run_task_result_file:" in result.stdout


def test_run_task_generates_issue_aware_summary_for_github_issue_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    class DummyClient:
        def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
            return {
                "full_name": f"{owner}/{repo}",
                "description": "dummy repo",
                "default_branch": "main",
                "open_issues_count": 1,
            }

        def get_open_issues(
            self,
            owner: str,
            repo: str,
            limit: int = 3,
        ) -> list[dict[str, object]]:
            assert limit == 3
            return [
                {"number": 7, "title": "Fix flaky planner output", "state": "open"},
            ]

    monkeypatch.setattr(
        "src.workflows.analyze_repo.GitHubClient.from_env",
        lambda: DummyClient(),
    )

    result = runner.invoke(app, ["run-task", "https://github.com/owner/repo"])
    run_task_file = tmp_path / "playground" / "outputs" / "run_task_result.json"

    assert result.exit_code == 0
    assert run_task_file.exists()

    payload = json.loads(run_task_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == "repo-issue-7"
    assert payload["status"] == "completed"
    assert payload["passed"] is True
    assert payload["source"] == "github_issue"
    assert payload["issue_number"] == 7
    assert payload["issue_context_used"] is True
    assert payload["final_validation_passed"] is True
    assert payload["steps_completed"] == [
        "analyze",
        "plan",
        "patch",
        "apply",
        "validate",
        "pr-draft",
    ]
    assert payload["fallback_summary"]["planning"] is False
    assert payload["fallback_summary"]["patch"] is False
    assert payload["fallback_summary"]["apply"] is False
    assert payload["fallback_summary"]["validate"] is False
    assert payload["fallback_summary"]["pr_draft"] is False
    assert payload["llm_steps_requested"] == {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    assert payload["llm_steps_used"] == {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    assert payload["llm_steps_fallback"] == {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    assert payload["final_discover_used_llm"] is False
    assert payload["final_plan_used_llm"] is False
    assert payload["final_patch_used_llm"] is False
    assert payload["final_apply_used_llm"] is False
    assert payload["final_validate_used_llm"] is False
    assert payload["final_pr_draft_used_llm"] is False

    assert "run_task_issue_context_used: true" in result.stdout
    assert "run_task_issue_number: 7" in result.stdout
    assert "run_task_fallback_summary:" in result.stdout
    assert "run_task_llm_steps_requested:" in result.stdout
    assert "run_task_llm_steps_used:" in result.stdout
    assert "run_task_llm_steps_fallback:" in result.stdout
    assert "run_task_result_file:" in result.stdout


def test_run_task_cli_uses_typer_compatible_optional_annotation() -> None:
    cli_source = Path("src/cli.py").read_text(encoding="utf-8")

    assert "task_id: str | None" not in cli_source


def test_run_task_auto_selects_first_candidate_task_when_task_id_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run-task", "https://github.com/owner/repo"])
    run_task_file = tmp_path / "playground" / "outputs" / "run_task_result.json"

    assert result.exit_code == 0
    assert run_task_file.exists()

    payload = json.loads(run_task_file.read_text(encoding="utf-8"))
    assert payload["task_id"] == "repo-task-001"
    assert payload["status"] == "completed"
    assert payload["passed"] is True
    assert payload["source"] == "template"
    assert payload["issue_context_used"] is False
    assert payload["final_validation_passed"] is True
    assert isinstance(payload["fallback_summary"], dict)
    assert payload["steps_completed"] == [
        "analyze",
        "plan",
        "patch",
        "apply",
        "validate",
        "pr-draft",
    ]


def test_run_task_rejects_invalid_task_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["run-task", "https://github.com/owner/repo", "non-existent-task-id"],
    )
    run_task_file = tmp_path / "playground" / "outputs" / "run_task_result.json"

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "task_id not found" in result.stdout
    assert "Traceback" not in result.stdout
    assert run_task_file.exists()

    payload = json.loads(run_task_file.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert payload["steps_completed"] == ["analyze"]
    assert "source" in payload
    assert "issue_context_used" in payload
    assert "fallback_summary" in payload
    assert "final_validation_passed" in payload
    assert "llm_steps_requested" in payload
    assert "llm_steps_used" in payload
    assert "llm_steps_fallback" in payload
    assert "final_discover_used_llm" in payload
    assert "final_plan_used_llm" in payload
    assert "final_patch_used_llm" in payload
    assert "final_apply_used_llm" in payload
    assert "final_validate_used_llm" in payload
    assert "final_pr_draft_used_llm" in payload


def test_run_task_stops_when_a_step_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["run-task", "https://gitlab.com/owner/repo", "repo-task-001"],
    )
    run_task_file = tmp_path / "playground" / "outputs" / "run_task_result.json"

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "Only GitHub URLs are supported" in result.stdout
    assert "Traceback" not in result.stdout
    assert run_task_file.exists()

    payload = json.loads(run_task_file.read_text(encoding="utf-8"))
    assert payload["repo_url"] == "https://gitlab.com/owner/repo"
    assert payload["task_id"] == "repo-task-001"
    assert payload["steps_completed"] == []
    assert payload["passed"] is False
    assert payload["status"] == "failed"
    assert "source" in payload
    assert "issue_context_used" in payload
    assert "fallback_summary" in payload
    assert "final_validation_passed" in payload
