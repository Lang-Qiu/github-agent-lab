import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


@pytest.mark.llm_integration
def test_pr_draft_use_llm_real_integration(tmp_path: Path, monkeypatch) -> None:
    if os.getenv("RUN_LLM_INTEGRATION") != "1":
        pytest.skip("Set RUN_LLM_INTEGRATION=1 to run real LLM integration tests.")

    required_envs = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]
    missing = [name for name in required_envs if not os.getenv(name)]
    if missing:
        pytest.skip("Missing required LLM env vars for integration test.")

    monkeypatch.chdir(tmp_path)

    analyze_result = runner.invoke(app, ["analyze", "https://github.com/owner/repo"])
    assert analyze_result.exit_code == 0

    candidate_file = tmp_path / "playground" / "outputs" / "candidate_tasks.json"
    task_id = json.loads(candidate_file.read_text(encoding="utf-8"))["tasks"][0]["id"]

    assert runner.invoke(app, ["plan", task_id]).exit_code == 0
    assert runner.invoke(app, ["patch", task_id]).exit_code == 0
    assert runner.invoke(app, ["apply", task_id]).exit_code == 0
    assert runner.invoke(app, ["validate", task_id]).exit_code == 0

    result = runner.invoke(app, ["pr-draft", task_id, "--use-llm"])
    llm_file = tmp_path / "playground" / "outputs" / "pr_draft_llm.md"

    assert result.exit_code == 0
    assert llm_file.exists()
    assert llm_file.read_text(encoding="utf-8").strip() != ""
    assert "used_llm: true" in result.stdout
