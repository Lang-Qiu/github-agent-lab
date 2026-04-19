"""Minimal workspace validation workflow based on patch apply results."""

from __future__ import annotations

import json
from pathlib import Path


class ValidationError(ValueError):
    """User-facing input error for validation command."""


def _read_json_file(file_path: Path, missing_message: str) -> dict[str, object]:
    if not file_path.exists():
        raise ValidationError(missing_message)

    return json.loads(file_path.read_text(encoding="utf-8"))


def run_validate_patch(task_id: str) -> str:
    output_dir = Path("playground") / "outputs"
    apply_result_file = output_dir / "patch_apply_result.json"

    apply_result = _read_json_file(
        apply_result_file,
        "patch_apply_result.json not found. Run apply first.",
    )

    if str(apply_result.get("task_id")) != task_id:
        raise ValidationError(f"task_id not found: {task_id}")

    workspace_dir = str(apply_result.get("workspace_dir", "")).strip()
    if not workspace_dir:
        raise ValidationError("workspace_dir missing in patch_apply_result.json")

    source_raw = str(apply_result.get("source", "template"))
    issue_context_flag = bool(apply_result.get("issue_context_used", False))
    issue_number_raw = apply_result.get("issue_number")
    issue_number = issue_number_raw if isinstance(issue_number_raw, int) else None
    issue_context_used = (
        source_raw == "github_issue"
        and issue_context_flag
        and issue_number is not None
    )
    fallback_triggered = not issue_context_used
    source = "github_issue" if issue_context_used else "template"

    checked_files = [str(path) for path in apply_result.get("applied_files", [])]
    missing_files = [path for path in checked_files if not Path(path).exists()]

    if issue_context_used:
        validation_steps = [
            "Load patch_apply_result.json with issue context",
            f"Verify issue #{issue_number} applied files exist in workspace",
            "Write validation_result.json",
        ]
    else:
        validation_steps = [
            "Load patch_apply_result.json",
            "Verify applied files exist in workspace",
            "Write validation_result.json",
        ]

    passed = len(missing_files) == 0
    status = "passed" if passed else "failed"

    result = {
        "task_id": task_id,
        "workspace_dir": workspace_dir,
        "checked_files": checked_files,
        "missing_files": missing_files,
        "validation_steps": validation_steps,
        "passed": passed,
        "status": status,
        "summary": (
            f"Validated {len(checked_files)} files; "
            f"missing {len(missing_files)} files."
        ),
        "source": source,
        "issue_context_used": issue_context_used,
        "fallback_triggered": fallback_triggered,
    }

    if issue_context_used and issue_number is not None:
        result["issue_number"] = issue_number

    output_dir.mkdir(parents=True, exist_ok=True)
    validation_file = output_dir / "validation_result.json"
    validation_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return (
        "Validation completed.\n"
        f"task_id: {task_id}\n"
        f"status: {status}\n"
        f"checked_files_count: {len(checked_files)}\n"
        f"missing_files_count: {len(missing_files)}\n"
        f"validation_issue_context_used: {'true' if issue_context_used else 'false'}\n"
        f"validation_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"validation_result_file: {validation_file.as_posix()}"
    )
