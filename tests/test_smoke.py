import json
from pathlib import Path

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

    assert result.exit_code == 0
    assert summary_file.exists()

    data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert data["repo_url"] == repo_url
    assert data["owner"] == "owner"
    assert data["repo"] == "repo"
    assert data["workspace_dir"] == "playground/repos/repo"
    assert data["status"] == "prepared"

    assert "Local analysis preparation complete" in result.stdout
    assert "owner: owner" in result.stdout
    assert "repo: repo" in result.stdout
    assert "status: prepared" in result.stdout
