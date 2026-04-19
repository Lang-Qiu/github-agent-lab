"""Minimal end-to-end orchestration workflow for a single task."""

from __future__ import annotations

import json
from pathlib import Path

from .analyze_repo import AnalyzeInputError, parse_repo_url, run_analyze_repo
from .apply_patch import PatchApplyError, run_apply_patch
from .generate_patch import PatchGenerationError, run_generate_patch
from .pr_draft import PRDraftError, run_pr_draft
from .task_planning import TaskPlanningError, run_task_planning
from .validate_patch import ValidationError, run_validate_patch


class RunTaskError(ValueError):
    """User-facing input error for run-task command."""


def _write_run_task_result(result: dict[str, object]) -> Path:
    output_dir = Path("playground") / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    result_file = output_dir / "run_task_result.json"
    result_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result_file


def _resolve_task_id(output_dir: Path, task_id: str | None) -> str:
    if task_id:
        return task_id

    candidate_file = output_dir / "candidate_tasks.json"
    if not candidate_file.exists():
        raise TaskPlanningError(
            "candidate_tasks.json not found. Analyze step did not produce candidates."
        )

    payload = json.loads(candidate_file.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        raise TaskPlanningError("No candidate tasks found after analyze step.")

    first = tasks[0]
    if not isinstance(first, dict) or not first.get("id"):
        raise TaskPlanningError("First candidate task does not have a valid id.")

    return str(first["id"])


def run_task(repo_url: str, task_id: str | None = None) -> str:
    steps_completed: list[str] = []
    artifacts: dict[str, str] = {}
    resolved_task_id = task_id or ""
    output_dir = Path("playground") / "outputs"

    try:
        run_analyze_repo(repo_url)
        owner, repo = parse_repo_url(repo_url)
        artifacts["summary_file"] = f"playground/outputs/{repo}_summary.json"
        artifacts["candidate_tasks_file"] = "playground/outputs/candidate_tasks.json"
        steps_completed.append("analyze")

        resolved_task_id = _resolve_task_id(output_dir, task_id)

        run_task_planning(resolved_task_id)
        artifacts["task_plan_file"] = "playground/outputs/task_plan.json"
        steps_completed.append("plan")

        run_generate_patch(resolved_task_id)
        artifacts["patch_preview_file"] = "playground/outputs/patch_preview.json"
        steps_completed.append("patch")

        run_apply_patch(resolved_task_id)
        artifacts["patch_apply_result_file"] = "playground/outputs/patch_apply_result.json"
        steps_completed.append("apply")

        run_validate_patch(resolved_task_id)
        artifacts["validation_result_file"] = "playground/outputs/validation_result.json"
        steps_completed.append("validate")

        run_pr_draft(resolved_task_id)
        artifacts["pr_draft_json"] = "playground/outputs/pr_draft.json"
        artifacts["pr_draft_md"] = "playground/outputs/pr_draft.md"
        steps_completed.append("pr-draft")

    except (
        AnalyzeInputError,
        TaskPlanningError,
        PatchGenerationError,
        PatchApplyError,
        ValidationError,
        PRDraftError,
    ) as exc:
        result = {
            "repo_url": repo_url,
            "task_id": resolved_task_id,
            "steps_completed": steps_completed,
            "artifacts": artifacts,
            "passed": False,
            "status": "failed",
            "summary": f"Failed at step with error: {exc}",
        }
        result_file = _write_run_task_result(result)
        raise RunTaskError(
            f"{exc}. run_task_result: {result_file.as_posix()}"
        ) from exc

    result = {
        "repo_url": repo_url,
        "task_id": resolved_task_id,
        "steps_completed": steps_completed,
        "artifacts": artifacts,
        "passed": True,
        "status": "completed",
        "summary": f"Completed run-task pipeline with {len(steps_completed)} steps.",
    }
    result_file = _write_run_task_result(result)

    return (
        "Run task completed.\n"
        f"repo_url: {repo_url}\n"
        f"task_id: {resolved_task_id}\n"
        "status: completed\n"
        f"run_task_result_file: {result_file.as_posix()}"
    )
