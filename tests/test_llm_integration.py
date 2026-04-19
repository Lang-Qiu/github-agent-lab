import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()
pytestmark = pytest.mark.llm_integration


def _require_llm_integration_enabled() -> None:
    if os.getenv("RUN_LLM_INTEGRATION") != "1":
        pytest.skip("Set RUN_LLM_INTEGRATION=1 to run llm_integration tests.")


def _require_real_llm_env() -> dict[str, str]:
    required_envs = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]
    missing = [name for name in required_envs if not os.getenv(name, "").strip()]
    assert not missing, (
        "Missing required real LLM env vars before pytest: "
        + ", ".join(missing)
    )
    return {name: os.getenv(name, "").strip() for name in required_envs}


def test_pr_draft_use_llm_real_integration(tmp_path: Path, monkeypatch) -> None:
    _require_llm_integration_enabled()
    _require_real_llm_env()

    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    task_id = json.loads(candidate_file.read_text(encoding="utf-8"))["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0
    assert runner.invoke(app, ["validate", task_id]).exit_code == 0

    result = None
    for _ in range(3):
        current = runner.invoke(app, ["pr-draft", task_id, "--use-llm"])
        result = current
        if (
            current.exit_code == 0
            and "used_llm: true" in current.stdout
            and "fallback_triggered: false" in current.stdout
        ):
            break

    assert result is not None
    pr_json = tmp_path / "playground" / "outputs" / "pr_draft.json"
    pr_md = tmp_path / "playground" / "outputs" / "pr_draft.md"
    llm_file = tmp_path / "playground" / "outputs" / "pr_draft_llm.md"

    assert result.exit_code == 0
    assert pr_json.exists()
    assert pr_json.read_text(encoding="utf-8").strip() != ""
    assert pr_md.exists()
    assert pr_md.read_text(encoding="utf-8").strip() != ""
    assert llm_file.exists(), result.stdout
    assert llm_file.read_text(encoding="utf-8").strip() != ""
    assert "used_llm: true" in result.stdout
    assert "fallback_triggered: false" in result.stdout


def test_run_task_use_llm_real_integration(tmp_path: Path, monkeypatch) -> None:
    _require_llm_integration_enabled()
    _require_real_llm_env()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "run-task",
            "https://github.com/owner/repo",
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
    assert isinstance(payload["llm_steps_used"], dict)
    assert isinstance(payload["llm_steps_fallback"], dict)
    assert "final_discover_used_llm" in payload
    assert "final_plan_used_llm" in payload
    assert "final_patch_used_llm" in payload
    assert "final_apply_used_llm" in payload
    assert "final_validate_used_llm" in payload
    assert "final_pr_draft_used_llm" in payload

    assert "run_task_llm_steps_requested:" in result.stdout
    assert "run_task_llm_steps_used:" in result.stdout
    assert "run_task_llm_steps_fallback:" in result.stdout
