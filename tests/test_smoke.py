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
    workspace_path = tmp_path / "playground" / "repos" / "owner" / "repo"

    assert result.exit_code == 0
    assert summary_file.exists()
    assert workspace_path.exists()
    assert workspace_path.is_dir()

    data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert data["repo_url"] == repo_url
    assert data["owner"] == "owner"
    assert data["repo"] == "repo"
    assert data["workspace_dir"] == "playground/repos/owner/repo"
    assert data["workspace_initialized"] == "created"
    assert data["status"] == "prepared"

    assert "Local analysis preparation complete" in result.stdout
    assert "owner: owner" in result.stdout
    assert "repo: repo" in result.stdout
    assert "workspace_initialized: created" in result.stdout
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
