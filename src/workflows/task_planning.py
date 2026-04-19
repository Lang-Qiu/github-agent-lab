"""Minimal task planning workflow based on candidate tasks."""

from __future__ import annotations

import json
from pathlib import Path


class TaskPlanningError(ValueError):
    """User-facing input error for task planning command."""


def _read_candidate_tasks(candidate_file: Path) -> dict[str, object]:
    if not candidate_file.exists():
        raise TaskPlanningError(
            "candidate_tasks.json not found. Run analyze first."
        )

    return json.loads(candidate_file.read_text(encoding="utf-8"))


def run_task_planning(task_id: str) -> str:
    output_dir = Path("playground") / "outputs"
    candidate_file = output_dir / "candidate_tasks.json"

    payload = _read_candidate_tasks(candidate_file)
    tasks = payload.get("tasks", [])
    selected_task = None
    for task in tasks:
        if isinstance(task, dict) and task.get("id") == task_id:
            selected_task = task
            break

    if selected_task is None:
        raise TaskPlanningError(f"task_id not found: {task_id}")

    source = str(selected_task.get("source", "template"))
    issue_number_raw = selected_task.get("issue_number")
    issue_number = issue_number_raw if isinstance(issue_number_raw, int) else None
    issue_context_used = source == "github_issue" and issue_number is not None
    fallback_triggered = not issue_context_used

    if issue_context_used:
        goal = (
            f"Resolve issue #{issue_number} with a small verified change "
            f"for task {selected_task['id']}."
        )
        proposed_changes = [
            f"Implement the smallest fix for issue #{issue_number}.",
            "Add or update smoke tests to protect issue behavior.",
        ]
        target_files = [
            "src/workflows/task_planning.py",
            "tests/test_smoke.py",
        ]
        validation_steps = [
            "Run pytest -q.",
            f"Check plan output keeps issue #{issue_number} context.",
        ]
        risk_level = "medium"
    else:
        goal = f"Deliver candidate task {selected_task['id']} in a small verified step."
        proposed_changes = [
            "Implement the minimal code path for this task.",
            "Update smoke tests to verify expected behavior.",
        ]
        target_files = [
            "src/workflows/analyze_repo.py",
            "tests/test_smoke.py",
        ]
        validation_steps = [
            "Run pytest -q.",
            "Check CLI output for expected summary lines.",
        ]
        risk_level = "low"

    task_plan = {
        "task_id": str(selected_task["id"]),
        "title": str(selected_task["title"]),
        "goal": goal,
        "proposed_changes": proposed_changes,
        "target_files": target_files,
        "validation_steps": validation_steps,
        "risk_level": risk_level,
        "status": "planned",
        "source": source,
        "issue_context_used": issue_context_used,
        "fallback_triggered": fallback_triggered,
    }

    if issue_number is not None:
        task_plan["issue_number"] = issue_number

    output_dir.mkdir(parents=True, exist_ok=True)
    task_plan_file = output_dir / "task_plan.json"
    task_plan_file.write_text(
        json.dumps(task_plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return (
        "Task plan generated.\n"
        f"task_id: {task_plan['task_id']}\n"
        f"title: {task_plan['title']}\n"
        f"task_plan_issue_context_used: {'true' if issue_context_used else 'false'}\n"
        f"task_plan_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"task_plan_file: {task_plan_file.as_posix()}"
    )
