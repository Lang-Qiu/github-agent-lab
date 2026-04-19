"""Minimal patch apply workflow based on task plan and patch preview."""

from __future__ import annotations

import json
from pathlib import Path


class PatchApplyError(ValueError):
    """User-facing input error for patch application command."""


def _read_json_file(file_path: Path, missing_message: str) -> dict[str, object]:
    if not file_path.exists():
        raise PatchApplyError(missing_message)

    return json.loads(file_path.read_text(encoding="utf-8"))


def _resolve_workspace_dir(output_dir: Path, task_id: str) -> tuple[Path, str]:
    if "-task-" not in task_id:
        raise PatchApplyError(f"task_id not found: {task_id}")

    repo = task_id.split("-task-", maxsplit=1)[0]
    summary_file = output_dir / f"{repo}_summary.json"
    summary = _read_json_file(
        summary_file,
        "repo summary not found. Run analyze first.",
    )

    workspace_dir = str(summary.get("workspace_dir", "")).strip()
    if not workspace_dir:
        raise PatchApplyError("workspace_dir missing in repo summary.")

    return Path(workspace_dir), workspace_dir


def _write_workspace_changes(
    workspace_path: Path,
    task_id: str,
    title: str,
    patch_preview: dict[str, object],
) -> tuple[list[str], list[str], list[str]]:
    created_files: list[str] = []
    modified_files: list[str] = []

    workspace_path.mkdir(parents=True, exist_ok=True)

    patch_log_file = workspace_path / "APPLIED_PATCH_LOG.md"
    patch_log_existed = patch_log_file.exists()
    with patch_log_file.open("a", encoding="utf-8") as file:
        if not patch_log_existed:
            file.write("# Applied Patch Log\n\n")
        file.write(f"- task_id: {task_id} | title: {title}\n")
    if patch_log_existed:
        modified_files.append(patch_log_file.as_posix())
    else:
        created_files.append(patch_log_file.as_posix())

    preview_snapshot_file = workspace_path / "patch_preview_snapshot.json"
    preview_snapshot_existed = preview_snapshot_file.exists()
    preview_snapshot_file.write_text(
        json.dumps(patch_preview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if preview_snapshot_existed:
        modified_files.append(preview_snapshot_file.as_posix())
    else:
        created_files.append(preview_snapshot_file.as_posix())

    applied_files = created_files + modified_files
    return applied_files, created_files, modified_files


def run_apply_patch(task_id: str) -> str:
    output_dir = Path("playground") / "outputs"
    task_plan_file = output_dir / "task_plan.json"
    patch_preview_file = output_dir / "patch_preview.json"

    task_plan = _read_json_file(
        task_plan_file,
        "task_plan.json not found. Run plan first.",
    )
    patch_preview = _read_json_file(
        patch_preview_file,
        "patch_preview.json not found. Run patch first.",
    )

    if str(task_plan.get("task_id")) != task_id or str(patch_preview.get("task_id")) != task_id:
        raise PatchApplyError(f"task_id not found: {task_id}")

    workspace_path, workspace_dir = _resolve_workspace_dir(output_dir, task_id)
    applied_files, created_files, modified_files = _write_workspace_changes(
        workspace_path,
        task_id,
        str(task_plan.get("title", "")),
        patch_preview,
    )

    result = {
        "task_id": task_id,
        "workspace_dir": workspace_dir,
        "applied_files": applied_files,
        "created_files": created_files,
        "modified_files": modified_files,
        "status": "applied",
        "summary": f"Applied {len(applied_files)} file changes to workspace.",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    result_file = output_dir / "patch_apply_result.json"
    result_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return (
        "Patch applied to workspace.\n"
        f"task_id: {task_id}\n"
        f"workspace_dir: {workspace_dir}\n"
        f"applied_files_count: {len(applied_files)}\n"
        f"patch_apply_result_file: {result_file.as_posix()}"
    )
