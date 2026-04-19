"""Minimal end-to-end orchestration workflow for a single task."""

from __future__ import annotations

import json
from pathlib import Path

from .analyze_repo import AnalyzeInputError, parse_repo_url, run_analyze_repo
from .apply_patch import PatchApplyError, run_apply_patch
from .discover_tasks import DiscoverTasksError, run_discover_tasks
from .generate_patch import PatchGenerationError, run_generate_patch
from .pr_draft import PRDraftError, run_pr_draft
from .task_planning import TaskPlanningError, run_task_planning
from .validate_patch import ValidationError, run_validate_patch


class RunTaskError(ValueError):
    """User-facing input error for run-task command."""


def _read_json_if_exists(file_path: Path) -> dict[str, object] | None:
    if not file_path.exists():
        return None

    return json.loads(file_path.read_text(encoding="utf-8"))


def _extract_fallback_flag(payload: dict[str, object] | None) -> bool | None:
    if payload is None:
        return None

    value = payload.get("fallback_triggered")
    if isinstance(value, bool):
        return value

    return None


def _extract_used_llm_from_message(message: str) -> bool:
    return "used_llm: true" in message.lower()


def _extract_llm_fallback_from_message(message: str) -> bool:
    return "fallback_reason:" in message


def _build_run_task_context(output_dir: Path) -> dict[str, object]:
    task_plan = _read_json_if_exists(output_dir / "task_plan.json")
    patch_preview = _read_json_if_exists(output_dir / "patch_preview.json")
    patch_apply_result = _read_json_if_exists(output_dir / "patch_apply_result.json")
    validation_result = _read_json_if_exists(output_dir / "validation_result.json")
    pr_draft = _read_json_if_exists(output_dir / "pr_draft.json")

    payloads: list[dict[str, object]] = [
        payload
        for payload in [task_plan, patch_preview, patch_apply_result, validation_result, pr_draft]
        if payload is not None
    ]

    issue_aware = False
    issue_number: int | None = None
    if len(payloads) == 5:
        sources_ok = all(str(payload.get("source", "template")) == "github_issue" for payload in payloads)
        flags_ok = all(bool(payload.get("issue_context_used", False)) for payload in payloads)
        issue_numbers = [payload.get("issue_number") for payload in payloads]
        if all(isinstance(number, int) for number in issue_numbers):
            first = int(issue_numbers[0])
            if all(int(number) == first for number in issue_numbers):
                issue_number = first
                issue_aware = sources_ok and flags_ok

    source = "github_issue" if issue_aware else "template"

    validation_passed: bool | None = None
    if isinstance(validation_result, dict) and isinstance(validation_result.get("passed"), bool):
        validation_passed = bool(validation_result.get("passed"))

    fallback_summary = {
        "planning": _extract_fallback_flag(task_plan),
        "patch": _extract_fallback_flag(patch_preview),
        "apply": _extract_fallback_flag(patch_apply_result),
        "validate": _extract_fallback_flag(validation_result),
        "pr_draft": _extract_fallback_flag(pr_draft),
    }

    return {
        "source": source,
        "issue_number": issue_number,
        "issue_context_used": issue_aware,
        "fallback_summary": fallback_summary,
        "final_validation_passed": validation_passed,
    }


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


def run_task(
    repo_url: str,
    task_id: str | None = None,
    use_llm_discover: bool = False,
    use_llm_plan: bool = False,
    use_llm_patch: bool = False,
    use_llm_apply: bool = False,
    use_llm_validate: bool = False,
    use_llm_pr_draft: bool = False,
) -> str:
    steps_completed: list[str] = []
    artifacts: dict[str, str] = {}
    resolved_task_id = task_id or ""
    output_dir = Path("playground") / "outputs"

    llm_steps_requested = {
        "discover": use_llm_discover,
        "plan": use_llm_plan,
        "patch": use_llm_patch,
        "apply": use_llm_apply,
        "validate": use_llm_validate,
        "pr_draft": use_llm_pr_draft,
    }
    llm_steps_used = {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }
    llm_steps_fallback = {
        "discover": False,
        "plan": False,
        "patch": False,
        "apply": False,
        "validate": False,
        "pr_draft": False,
    }

    try:
        run_analyze_repo(repo_url)
        owner, repo = parse_repo_url(repo_url)
        artifacts["summary_file"] = f"playground/outputs/{repo}_summary.json"
        artifacts["candidate_tasks_file"] = "playground/outputs/candidate_tasks.json"
        steps_completed.append("analyze")

        if use_llm_discover:
            discover_message = run_discover_tasks(repo_url, use_llm=True)
            llm_steps_used["discover"] = _extract_used_llm_from_message(discover_message)
            llm_steps_fallback["discover"] = _extract_llm_fallback_from_message(discover_message)
            steps_completed.append("discover-tasks")

        resolved_task_id = _resolve_task_id(output_dir, task_id)

        plan_message = run_task_planning(resolved_task_id, use_llm=use_llm_plan)
        llm_steps_used["plan"] = _extract_used_llm_from_message(plan_message)
        llm_steps_fallback["plan"] = _extract_llm_fallback_from_message(plan_message)
        artifacts["task_plan_file"] = "playground/outputs/task_plan.json"
        steps_completed.append("plan")

        patch_message = run_generate_patch(resolved_task_id, use_llm=use_llm_patch)
        llm_steps_used["patch"] = _extract_used_llm_from_message(patch_message)
        llm_steps_fallback["patch"] = _extract_llm_fallback_from_message(patch_message)
        artifacts["patch_preview_file"] = "playground/outputs/patch_preview.json"
        steps_completed.append("patch")

        apply_message = run_apply_patch(resolved_task_id, use_llm=use_llm_apply)
        llm_steps_used["apply"] = _extract_used_llm_from_message(apply_message)
        llm_steps_fallback["apply"] = _extract_llm_fallback_from_message(apply_message)
        artifacts["patch_apply_result_file"] = "playground/outputs/patch_apply_result.json"
        steps_completed.append("apply")

        validate_message = run_validate_patch(resolved_task_id, use_llm=use_llm_validate)
        llm_steps_used["validate"] = _extract_used_llm_from_message(validate_message)
        llm_steps_fallback["validate"] = _extract_llm_fallback_from_message(validate_message)
        artifacts["validation_result_file"] = "playground/outputs/validation_result.json"
        steps_completed.append("validate")

        pr_draft_message = run_pr_draft(resolved_task_id, use_llm=use_llm_pr_draft)
        llm_steps_used["pr_draft"] = _extract_used_llm_from_message(pr_draft_message)
        llm_steps_fallback["pr_draft"] = _extract_llm_fallback_from_message(pr_draft_message)
        artifacts["pr_draft_json"] = "playground/outputs/pr_draft.json"
        artifacts["pr_draft_md"] = "playground/outputs/pr_draft.md"
        steps_completed.append("pr-draft")

    except (
        AnalyzeInputError,
        DiscoverTasksError,
        TaskPlanningError,
        PatchGenerationError,
        PatchApplyError,
        ValidationError,
        PRDraftError,
    ) as exc:
        context = _build_run_task_context(output_dir)
        result = {
            "repo_url": repo_url,
            "task_id": resolved_task_id,
            "steps_completed": steps_completed,
            "artifacts": artifacts,
            "passed": False,
            "status": "failed",
            "summary": f"Failed at step with error: {exc}",
            "source": context["source"],
            "issue_number": context["issue_number"],
            "issue_context_used": context["issue_context_used"],
            "fallback_summary": context["fallback_summary"],
            "final_validation_passed": context["final_validation_passed"],
            "llm_steps_requested": llm_steps_requested,
            "llm_steps_used": llm_steps_used,
            "llm_steps_fallback": llm_steps_fallback,
            "final_discover_used_llm": llm_steps_used["discover"],
            "final_plan_used_llm": llm_steps_used["plan"],
            "final_patch_used_llm": llm_steps_used["patch"],
            "final_apply_used_llm": llm_steps_used["apply"],
            "final_validate_used_llm": llm_steps_used["validate"],
            "final_pr_draft_used_llm": llm_steps_used["pr_draft"],
        }
        result_file = _write_run_task_result(result)
        raise RunTaskError(
            f"{exc}. run_task_result: {result_file.as_posix()}"
        ) from exc

    context = _build_run_task_context(output_dir)
    result = {
        "repo_url": repo_url,
        "task_id": resolved_task_id,
        "steps_completed": steps_completed,
        "artifacts": artifacts,
        "passed": True,
        "status": "completed",
        "summary": f"Completed run-task pipeline with {len(steps_completed)} steps.",
        "source": context["source"],
        "issue_number": context["issue_number"],
        "issue_context_used": context["issue_context_used"],
        "fallback_summary": context["fallback_summary"],
        "final_validation_passed": context["final_validation_passed"],
        "llm_steps_requested": llm_steps_requested,
        "llm_steps_used": llm_steps_used,
        "llm_steps_fallback": llm_steps_fallback,
        "final_discover_used_llm": llm_steps_used["discover"],
        "final_plan_used_llm": llm_steps_used["plan"],
        "final_patch_used_llm": llm_steps_used["patch"],
        "final_apply_used_llm": llm_steps_used["apply"],
        "final_validate_used_llm": llm_steps_used["validate"],
        "final_pr_draft_used_llm": llm_steps_used["pr_draft"],
    }
    result_file = _write_run_task_result(result)

    issue_number_text = str(context["issue_number"]) if context["issue_number"] is not None else "none"
    fallback_summary_text = json.dumps(context["fallback_summary"], ensure_ascii=False)
    llm_steps_requested_text = json.dumps(llm_steps_requested, ensure_ascii=False)
    llm_steps_used_text = json.dumps(llm_steps_used, ensure_ascii=False)
    llm_steps_fallback_text = json.dumps(llm_steps_fallback, ensure_ascii=False)

    return (
        "Run task completed.\n"
        f"repo_url: {repo_url}\n"
        f"task_id: {resolved_task_id}\n"
        "status: completed\n"
        f"run_task_issue_context_used: {'true' if context['issue_context_used'] else 'false'}\n"
        f"run_task_issue_number: {issue_number_text}\n"
        f"run_task_fallback_summary: {fallback_summary_text}\n"
        f"run_task_llm_steps_requested: {llm_steps_requested_text}\n"
        f"run_task_llm_steps_used: {llm_steps_used_text}\n"
        f"run_task_llm_steps_fallback: {llm_steps_fallback_text}\n"
        f"run_task_result_file: {result_file.as_posix()}"
    )
