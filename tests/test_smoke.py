from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


def test_help_command_runs() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "analyze" in result.stdout


def test_analyze_placeholder_message() -> None:
    repo_url = "https://github.com/owner/repo"
    result = runner.invoke(app, ["analyze", repo_url])

    assert result.exit_code == 0
    assert repo_url in result.stdout
    assert "placeholder" in result.stdout.lower()
