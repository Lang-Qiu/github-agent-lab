"""Minimal patch apply workflow based on task plan and patch preview."""

from __future__ import annotations

import json
from pathlib import Path

from ..llm_client import LLMClient, LLMClientError


class PatchApplyError(ValueError):
    """User-facing input error for patch application command."""


def _read_json_file(file_path: Path, missing_message: str) -> dict[str, object]:
    if not file_path.exists():
        raise PatchApplyError(missing_message)

    return json.loads(file_path.read_text(encoding="utf-8"))


def _resolve_workspace_dir(output_dir: Path, task_id: str) -> tuple[Path, str, dict[str, object]]:
    repo = ""
    if "-task-" in task_id:
        repo = task_id.split("-task-", maxsplit=1)[0]
    elif "-issue-" in task_id:
        repo = task_id.split("-issue-", maxsplit=1)[0]

    if not repo:
        raise PatchApplyError(f"task_id not found: {task_id}")

    summary_file = output_dir / f"{repo}_summary.json"
    summary = _read_json_file(
        summary_file,
        "repo summary not found. Run analyze first.",
    )

    workspace_dir = str(summary.get("workspace_dir", "")).strip()
    if not workspace_dir:
        raise PatchApplyError("workspace_dir missing in repo summary.")

    return Path(workspace_dir), workspace_dir, summary


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


def _extract_json_object(content: str) -> dict[str, object]:
    text = content.strip()
    if not text:
        raise LLMClientError("LLM response content is empty")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMClientError("LLM response format is invalid")
        parsed = json.loads(text[start : end + 1])

    if not isinstance(parsed, dict):
        raise LLMClientError("LLM response format is invalid")

    return parsed


def _build_llm_prompt(
    task_plan: dict[str, object],
    patch_preview: dict[str, object],
    summary_payload: dict[str, object],
    applied_files: list[str],
    issue_context_used: bool,
    issue_number: int | None,
) -> str:
    issue_context_line = ""
    if issue_context_used and issue_number is not None:
        issue_context_line = f"Issue number: {issue_number}\\n"

    return (
        "Generate an apply result summary and return ONLY a JSON object.\\n"
        "JSON keys required: summary.\\n"
        "summary must be a concise plain string.\\n"
        f"Task ID: {task_plan.get('task_id', '')}\\n"
        f"Task Title: {task_plan.get('title', '')}\\n"
        f"Task Source: {task_plan.get('source', 'template')}\\n"
        f"Patch strategy: {patch_preview.get('patch_strategy', '')}\\n"
        f"Planned edits: {patch_preview.get('planned_edits', [])}\\n"
        f"Applied files: {applied_files}\\n"
        f"Workspace dir: {summary_payload.get('workspace_dir', '')}\\n"
        f"Repo metadata: {summary_payload.get('repo_metadata', None)}\\n"
        f"Sample open issues: {summary_payload.get('sample_open_issues', [])}\\n"
        f"{issue_context_line}"
        "Keep summary practical and execution-focused."
    )


def _extract_llm_summary(content: str) -> str:
    parsed = _extract_json_object(content)
    summary = str(parsed.get("summary", "")).strip()
    if not summary:
        raise LLMClientError("LLM response format is invalid")
    return summary


def run_apply_patch(task_id: str, use_llm: bool = False) -> str:
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

    task_source = str(task_plan.get("source", "template"))
    preview_source = str(patch_preview.get("source", "template"))
    task_issue_context = bool(task_plan.get("issue_context_used", False))
    preview_issue_context = bool(patch_preview.get("issue_context_used", False))
    task_issue_number_raw = task_plan.get("issue_number")
    preview_issue_number_raw = patch_preview.get("issue_number")
    task_issue_number = (
        task_issue_number_raw if isinstance(task_issue_number_raw, int) else None
    )
    preview_issue_number = (
        preview_issue_number_raw if isinstance(preview_issue_number_raw, int) else None
    )

    issue_context_used = (
        task_source == "github_issue"
        and preview_source == "github_issue"
        and task_issue_context
        and preview_issue_context
        and task_issue_number is not None
        and preview_issue_number == task_issue_number
    )
    rule_fallback_triggered = not issue_context_used
    source = "github_issue" if issue_context_used else "template"

    workspace_path, workspace_dir, summary_payload = _resolve_workspace_dir(output_dir, task_id)
    applied_files, created_files, modified_files = _write_workspace_changes(
        workspace_path,
        task_id,
        str(task_plan.get("title", "")),
        patch_preview,
    )

    used_llm = False
    llm_fallback_triggered = False
    fallback_reason = ""
    result_summary = f"Applied {len(applied_files)} file changes to workspace."

    if use_llm:
        try:
            prompt = _build_llm_prompt(
                task_plan,
                patch_preview,
                summary_payload,
                applied_files,
                issue_context_used,
                task_issue_number,
            )
            client = LLMClient.from_env()
            llm_content = client.generate(prompt)
            result_summary = _extract_llm_summary(llm_content)
            used_llm = True
        except LLMClientError as exc:
            llm_fallback_triggered = True
            fallback_reason = str(exc)
        except Exception as exc:  # pragma: no cover - defensive safety net
            llm_fallback_triggered = True
            fallback_reason = str(exc)

    fallback_triggered = rule_fallback_triggered or llm_fallback_triggered

    result = {
        "task_id": task_id,
        "workspace_dir": workspace_dir,
        "applied_files": applied_files,
        "created_files": created_files,
        "modified_files": modified_files,
        "status": "applied",
        "summary": result_summary,
        "source": source,
        "issue_context_used": issue_context_used,
        "fallback_triggered": fallback_triggered,
        "used_llm": used_llm,
    }

    if issue_context_used and task_issue_number is not None:
        result["issue_number"] = task_issue_number
    if llm_fallback_triggered:
        result["fallback_reason"] = fallback_reason

    output_dir.mkdir(parents=True, exist_ok=True)
    result_file = output_dir / "patch_apply_result.json"
    result_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    message = (
        "Patch applied to workspace.\n"
        f"task_id: {task_id}\n"
        f"workspace_dir: {workspace_dir}\n"
        f"applied_files_count: {len(applied_files)}\n"
        f"patch_apply_issue_context_used: {'true' if issue_context_used else 'false'}\n"
        f"patch_apply_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"used_llm: {'true' if used_llm else 'false'}\n"
        f"patch_apply_result_file: {result_file.as_posix()}"
    )

    if llm_fallback_triggered:
        message += f"\nfallback_reason: {fallback_reason}"

    return message
