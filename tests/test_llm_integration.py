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
