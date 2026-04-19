"""Minimal PR draft generation workflow based on existing artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from ..llm_client import LLMClient, LLMClientError


class PRDraftError(ValueError):
    """User-facing input error for PR draft command."""


def _read_json_file(file_path: Path, missing_message: str) -> dict[str, object]:
    if not file_path.exists():
        raise PRDraftError(missing_message)

    return json.loads(file_path.read_text(encoding="utf-8"))


def _ensure_task_id(payload: dict[str, object], task_id: str) -> None:
    if str(payload.get("task_id")) != task_id:
        raise PRDraftError(f"task_id not found: {task_id}")


def _build_llm_prompt(
    task_plan: dict[str, object],
    patch_preview: dict[str, object],
    patch_apply_result: dict[str, object],
    validation_result: dict[str, object],
) -> str:
    return (
        "Generate a concise pull request draft in Markdown.\n"
        f"Task ID: {task_plan.get('task_id', '')}\n"
        f"Title: {task_plan.get('title', '')}\n"
        f"Goal: {task_plan.get('goal', '')}\n"
        f"Target files: {patch_preview.get('target_files', [])}\n"
        f"Planned edits: {patch_preview.get('planned_edits', [])}\n"
        f"Applied files: {patch_apply_result.get('applied_files', [])}\n"
        f"Validation status: {validation_result.get('status', '')}\n"
        f"Validation summary: {validation_result.get('summary', '')}\n"
        "Include: summary, key changes, validation evidence, risks."
    )


def _resolve_rule_context(
    task_plan: dict[str, object],
    patch_preview: dict[str, object],
    patch_apply_result: dict[str, object],
    validation_result: dict[str, object],
) -> tuple[str, int | None, bool, bool]:
    payloads = [task_plan, patch_preview, patch_apply_result, validation_result]

    sources = [str(item.get("source", "template")) for item in payloads]
    issue_flags = [bool(item.get("issue_context_used", False)) for item in payloads]

    issue_numbers_raw = [item.get("issue_number") for item in payloads]
    issue_numbers = [num for num in issue_numbers_raw if isinstance(num, int)]

    issue_number: int | None = None
    if issue_numbers and len(issue_numbers) == len(payloads):
        first = issue_numbers[0]
        if all(num == first for num in issue_numbers):
            issue_number = first

    issue_context_used = (
        all(source == "github_issue" for source in sources)
        and all(issue_flags)
        and issue_number is not None
    )
    fallback_triggered = not issue_context_used
    source = "github_issue" if issue_context_used else "template"

    return source, issue_number, issue_context_used, fallback_triggered


def run_pr_draft(task_id: str, use_llm: bool = False) -> str:
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

    source, issue_number, issue_context_used, rule_fallback_triggered = _resolve_rule_context(
        task_plan,
        patch_preview,
        patch_apply_result,
        validation_result,
    )

    passed = bool(validation_result.get("passed", False))
    status = "ready" if passed else "needs_attention"
    risks = [
        "Validation did not fully pass. Review missing files before opening PR."
    ] if not passed else ["Low risk for this minimal local draft."]

    if issue_context_used and issue_number is not None:
        summary = (
            f"Prepare issue-aware PR for issue #{issue_number} "
            f"using local generated artifacts."
        )
    else:
        summary = f"Prepare PR for task {task_id} using local generated artifacts."

    draft = {
        "task_id": task_id,
        "title": str(task_plan.get("title", "Untitled task")),
        "summary": summary,
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
        "source": source,
        "issue_context_used": issue_context_used,
        "fallback_triggered": rule_fallback_triggered,
    }

    if issue_context_used and issue_number is not None:
        draft["issue_number"] = issue_number

    draft_json_file = output_dir / "pr_draft.json"
    draft_md_file = output_dir / "pr_draft.md"
    draft_llm_file = output_dir / "pr_draft_llm.md"

    draft_json_file.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    mode_label = "issue-aware" if issue_context_used else "template fallback"
    issue_line = (
        f"- issue: issue #{issue_number}\n" if issue_context_used and issue_number is not None else ""
    )

    markdown = (
        "# PR Draft\n\n"
        "## Context\n"
        f"- mode: {mode_label}\n"
        f"- source: {draft['source']}\n"
        f"- issue_context_used: {draft['issue_context_used']}\n"
        f"- fallback_triggered: {draft['fallback_triggered']}\n"
        f"{issue_line}\n"
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

    used_llm = False
    fallback_triggered = False
    fallback_reason = ""

    if use_llm:
        try:
            client = LLMClient.from_env()
            prompt = _build_llm_prompt(
                task_plan,
                patch_preview,
                patch_apply_result,
                validation_result,
            )
            llm_markdown = client.generate_pr_draft(prompt)
            draft_llm_file.write_text(llm_markdown.strip() + "\n", encoding="utf-8")
            used_llm = True
        except LLMClientError as exc:
            fallback_triggered = True
            fallback_reason = str(exc)
        except Exception as exc:  # pragma: no cover - defensive safety net
            fallback_triggered = True
            fallback_reason = str(exc)

    message = (
        "PR draft generated.\n"
        f"task_id: {task_id}\n"
        f"status: {status}\n"
        f"rule_issue_context_used: {'true' if issue_context_used else 'false'}\n"
        f"rule_fallback_triggered: {'true' if rule_fallback_triggered else 'false'}\n"
        f"used_llm: {'true' if used_llm else 'false'}\n"
        f"fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"pr_draft_json: {draft_json_file.as_posix()}\n"
        f"pr_draft_md: {draft_md_file.as_posix()}"
    )

    if used_llm:
        message += f"\npr_draft_llm_md: {draft_llm_file.as_posix()}"
    if fallback_triggered:
        message += f"\nfallback_reason: {fallback_reason}"

    return message
