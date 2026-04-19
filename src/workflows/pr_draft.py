"""Minimal PR draft generation workflow based on existing artifacts."""

from __future__ import annotations

import json
from pathlib import Path


class PRDraftError(ValueError):
    """User-facing input error for PR draft command."""


def _read_json_file(file_path: Path, missing_message: str) -> dict[str, object]:
    if not file_path.exists():
        raise PRDraftError(missing_message)

    return json.loads(file_path.read_text(encoding="utf-8"))


def _ensure_task_id(payload: dict[str, object], task_id: str) -> None:
    if str(payload.get("task_id")) != task_id:
        raise PRDraftError(f"task_id not found: {task_id}")


def run_pr_draft(task_id: str) -> str:
    output_dir = Path("playground") / "outputs"
    task_plan = _read_json_file(
        output_dir / "task_plan.json",
        "task_plan.json not found. Run plan first.",
    )
    patch_preview = _read_json_file(
        output_dir / "patch_preview.json",
        "patch_preview.json not found. Run patch first.",
    )
    patch_apply_result = _read_json_file(
        output_dir / "patch_apply_result.json",
        "patch_apply_result.json not found. Run apply first.",
    )
    validation_result = _read_json_file(
        output_dir / "validation_result.json",
        "validation_result.json not found. Run validate first.",
    )

    _ensure_task_id(task_plan, task_id)
    _ensure_task_id(patch_preview, task_id)
    _ensure_task_id(patch_apply_result, task_id)
    _ensure_task_id(validation_result, task_id)

    passed = bool(validation_result.get("passed", False))
    status = "ready" if passed else "needs_attention"
    risks = [
        "Validation did not fully pass. Review missing files before opening PR."
    ] if not passed else ["Low risk for this minimal local draft."]

    draft = {
        "task_id": task_id,
        "title": str(task_plan.get("title", "Untitled task")),
        "summary": (
            f"Prepare PR for task {task_id} using local generated artifacts."
        ),
        "changes": {
            "target_files": list(patch_preview.get("target_files", [])),
            "planned_edits": list(patch_preview.get("planned_edits", [])),
            "applied_files": list(patch_apply_result.get("applied_files", [])),
        },
        "validation": {
            "passed": passed,
            "status": str(validation_result.get("status", "unknown")),
            "summary": str(validation_result.get("summary", "")),
        },
        "risks": risks,
        "status": status,
    }

    draft_json_file = output_dir / "pr_draft.json"
    draft_md_file = output_dir / "pr_draft.md"

    draft_json_file.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown = (
        "# PR Draft\n\n"
        f"## Task\n- task_id: {draft['task_id']}\n- title: {draft['title']}\n\n"
        f"## Summary\n{draft['summary']}\n\n"
        "## Changes\n"
        f"- target_files: {len(draft['changes']['target_files'])}\n"
        f"- planned_edits: {len(draft['changes']['planned_edits'])}\n"
        f"- applied_files: {len(draft['changes']['applied_files'])}\n\n"
        "## Validation\n"
        f"- passed: {draft['validation']['passed']}\n"
        f"- status: {draft['validation']['status']}\n"
        f"- summary: {draft['validation']['summary']}\n\n"
        "## Risks\n"
        + "\n".join(f"- {item}" for item in draft["risks"])
        + "\n\n"
        f"## Status\n{draft['status']}\n"
    )
    draft_md_file.write_text(markdown, encoding="utf-8")

    return (
        "PR draft generated.\n"
        f"task_id: {task_id}\n"
        f"status: {status}\n"
        f"pr_draft_json: {draft_json_file.as_posix()}\n"
        f"pr_draft_md: {draft_md_file.as_posix()}"
    )
