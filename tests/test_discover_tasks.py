from src.workflows.discover_tasks import _normalize_llm_tasks


def test_normalize_llm_tasks_rewrites_noncanonical_template_id() -> None:
    tasks = _normalize_llm_tasks(
        [
            {
                "id": "task_1",
                "title": "Review docs",
                "type": "docs",
                "priority": "medium",
                "status": "todo",
                "source": "template",
            }
        ],
        "repo",
    )

    assert tasks[0]["id"] == "repo-task-001"


def test_normalize_llm_tasks_rewrites_noncanonical_issue_id() -> None:
    tasks = _normalize_llm_tasks(
        [
            {
                "id": "issue_7",
                "title": "Fix flaky case",
                "type": "issue",
                "priority": "high",
                "status": "todo",
                "source": "github_issue",
                "issue_number": 7,
            }
        ],
        "repo",
    )

    assert tasks[0]["id"] == "repo-issue-7"
