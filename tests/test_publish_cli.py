from typer.testing import CliRunner

from src.cli import app


runner = CliRunner()


def test_publish_command_success(monkeypatch) -> None:
    def _fake_run_publish(repo_url: str, task_id=None, branch_name=None, draft_pr=False, base_branch="main"):
        assert repo_url == "https://github.com/owner/repo"
        assert branch_name == "feature/test"
        assert draft_pr is True
        return "Publish completed.\nstatus: completed\npublish_result_file: playground/outputs/publish_result.json"

    monkeypatch.setattr("src.cli.run_publish", _fake_run_publish)

    result = runner.invoke(
        app,
        ["publish", "https://github.com/owner/repo", "--branch", "feature/test", "--draft-pr"],
    )

    assert result.exit_code == 0
    assert "Publish completed" in result.stdout
    assert "publish_result_file:" in result.stdout


def test_publish_command_handles_workflow_error(monkeypatch) -> None:
    from src.workflows.publish_result import PublishResultError

    def _raise_error(repo_url: str, task_id=None, branch_name=None, draft_pr=False, base_branch="main"):
        raise PublishResultError("No local changes to publish.")

    monkeypatch.setattr("src.cli.run_publish", _raise_error)

    result = runner.invoke(app, ["publish", "https://github.com/owner/repo", "--draft-pr"])

    assert result.exit_code == 1
    assert "Error: No local changes to publish." in result.stdout
    assert "Traceback" not in result.stdout
