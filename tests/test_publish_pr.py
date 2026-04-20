import json
from pathlib import Path

from src.workflows.publish_client import PublishClientError
from src.workflows.publish_result import create_draft_pr_step


def test_create_draft_pr_step_success_uses_markdown_body(tmp_path: Path) -> None:
    output_dir = tmp_path / "playground" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pr_draft.md").write_text("# Draft Body\n\nHello PR", encoding="utf-8")

    class DummyPublishClient:
        def create_draft_pr(
            self,
            repo_url: str,
            title: str,
            body: str,
            head: str,
            base: str,
        ) -> dict[str, object]:
            assert "Hello PR" in body
            assert head == "feature/test"
            assert base == "main"
            return {"url": "https://github.com/owner/repo/pull/10", "number": 10}

    result = create_draft_pr_step(
        repo_url="https://github.com/owner/repo",
        branch_name="feature/test",
        base_branch="main",
        publish_client=DummyPublishClient(),
        output_dir=output_dir,
    )

    assert result["pr_created"] is True
    assert result["pr_url"] == "https://github.com/owner/repo/pull/10"
    assert result["errors"] == []


def test_create_draft_pr_step_failure_is_graceful(tmp_path: Path) -> None:
    output_dir = tmp_path / "playground" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pr_draft.md").write_text("# Draft Body\n\nHello PR", encoding="utf-8")

    class DummyPublishClient:
        def create_draft_pr(
            self,
            repo_url: str,
            title: str,
            body: str,
            head: str,
            base: str,
        ) -> dict[str, object]:
            raise PublishClientError("GitHub request failed with HTTP 422")

    result = create_draft_pr_step(
        repo_url="https://github.com/owner/repo",
        branch_name="feature/test",
        base_branch="main",
        publish_client=DummyPublishClient(),
        output_dir=output_dir,
    )

    assert result["pr_created"] is False
    assert result["pr_url"] == ""
    assert "HTTP 422" in result["errors"][0]


def test_create_draft_pr_step_falls_back_to_json_payload(tmp_path: Path) -> None:
    output_dir = tmp_path / "playground" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "task_id": "repo-task-001",
        "title": "Fix docs",
        "summary": "Improve documentation wording",
        "status": "ready",
    }
    (output_dir / "pr_draft.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    class DummyPublishClient:
        def create_draft_pr(
            self,
            repo_url: str,
            title: str,
            body: str,
            head: str,
            base: str,
        ) -> dict[str, object]:
            assert title == "Fix docs"
            assert "Improve documentation wording" in body
            return {"url": "https://github.com/owner/repo/pull/11", "number": 11}

    result = create_draft_pr_step(
        repo_url="https://github.com/owner/repo",
        branch_name="feature/test",
        base_branch="main",
        publish_client=DummyPublishClient(),
        output_dir=output_dir,
    )

    assert result["pr_created"] is True
    assert result["pr_url"].endswith("/11")


def test_create_draft_pr_step_uses_default_when_no_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "playground" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    class DummyPublishClient:
        def create_draft_pr(
            self,
            repo_url: str,
            title: str,
            body: str,
            head: str,
            base: str,
        ) -> dict[str, object]:
            assert title == "chore: publish local contribution"
            assert "No local PR draft artifact found" in body
            return {"url": "https://github.com/owner/repo/pull/12", "number": 12}

    result = create_draft_pr_step(
        repo_url="https://github.com/owner/repo",
        branch_name="feature/test",
        base_branch="main",
        publish_client=DummyPublishClient(),
        output_dir=output_dir,
    )

    assert result["pr_created"] is True
    assert result["pr_url"].endswith("/12")
