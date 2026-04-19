"""Minimal patch preview generation workflow based on task plans."""

from __future__ import annotations

import json
from pathlib import Path


class PatchGenerationError(ValueError):
    """User-facing input error for patch generation command."""


def _read_task_plan(task_plan_file: Path) -> dict[str, object]:
    if not task_plan_file.exists():
        raise PatchGenerationError(
            "task_plan.json not found. Run plan first."
        )

    return json.loads(task_plan_file.read_text(encoding="utf-8"))


def run_generate_patch(task_id: str) -> str:
    output_dir = Path("playground") / "outputs"
    task_plan_file = output_dir / "task_plan.json"
    task_plan = _read_task_plan(task_plan_file)

    if str(task_plan.get("task_id")) != task_id:
        raise PatchGenerationError(f"task_id not found: {task_id}")

    source = str(task_plan.get("source", "template"))
    issue_context_flag = bool(task_plan.get("issue_context_used", False))
    issue_number_raw = task_plan.get("issue_number")
    issue_number = issue_number_raw if isinstance(issue_number_raw, int) else None
    issue_context_used = (
        source == "github_issue" and issue_context_flag and issue_number is not None
    )
    fallback_triggered = not issue_context_used

    if issue_context_used:
        patch_strategy = "issue-context-preview"
        planned_edits = [
            f"Implement minimal fix flow for issue #{issue_number}.",
            "Keep patch focused on issue-relevant files and behaviors.",
        ]
    else:
        patch_strategy = "minimal-rule-based-preview"
        planned_edits = [
            "Create focused edits only on listed target files.",
            "Keep changes small and independently testable.",
        ]

    patch_preview = {
        "task_id": str(task_plan["task_id"]),
        "title": str(task_plan["title"]),
        "target_files": list(task_plan.get("target_files", [])),
        "patch_strategy": patch_strategy,
        "planned_edits": planned_edits,
        "validation_steps": list(task_plan.get("validation_steps", [])),
        "status": "preview_generated",
        "source": source,
        "issue_context_used": issue_context_used,
        "fallback_triggered": fallback_triggered,
    }

    if issue_number is not None:
        patch_preview["issue_number"] = issue_number

    output_dir.mkdir(parents=True, exist_ok=True)
    patch_preview_file = output_dir / "patch_preview.json"
    patch_preview_file.write_text(
        json.dumps(patch_preview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return (
        "Patch preview generated.\n"
        f"task_id: {patch_preview['task_id']}\n"
        f"title: {patch_preview['title']}\n"
        f"patch_issue_context_used: {'true' if issue_context_used else 'false'}\n"
        f"patch_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"patch_preview_file: {patch_preview_file.as_posix()}"
    )
