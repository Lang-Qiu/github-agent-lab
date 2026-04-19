"""Minimal patch preview generation workflow based on task plans."""

from __future__ import annotations

import json
from pathlib import Path

from ..llm_client import LLMClient, LLMClientError


class PatchGenerationError(ValueError):
    """User-facing input error for patch generation command."""


def _read_task_plan(task_plan_file: Path) -> dict[str, object]:
    if not task_plan_file.exists():
        raise PatchGenerationError(
            "task_plan.json not found. Run plan first."
        )

    return json.loads(task_plan_file.read_text(encoding="utf-8"))


def _read_optional_json(file_path: Path) -> dict[str, object] | None:
    if not file_path.exists():
        return None

    return json.loads(file_path.read_text(encoding="utf-8"))


def _read_optional_summary(
    output_dir: Path,
    candidate_payload: dict[str, object] | None,
) -> dict[str, object] | None:
    summary_json = output_dir / "summary.json"
    if summary_json.exists():
        return json.loads(summary_json.read_text(encoding="utf-8"))

    if isinstance(candidate_payload, dict):
        repo = candidate_payload.get("repo")
        if isinstance(repo, str) and repo.strip():
            repo_summary = output_dir / f"{repo}_summary.json"
            if repo_summary.exists():
                return json.loads(repo_summary.read_text(encoding="utf-8"))

    summary_files = sorted(output_dir.glob("*_summary.json"))
    if summary_files:
        return json.loads(summary_files[0].read_text(encoding="utf-8"))

    return None


def _build_rule_patch_preview(task_plan: dict[str, object]) -> dict[str, object]:
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

    return patch_preview


def _normalize_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                items.append(text)
        return items

    if isinstance(value, str) and value.strip():
        return [value.strip()]

    return []


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
    summary_payload: dict[str, object] | None,
    candidate_payload: dict[str, object] | None,
    issue_context_used: bool,
    issue_number: int | None,
) -> str:
    issue_context_lines = ""
    if issue_context_used and issue_number is not None:
        issue_context_lines = (
            f"Issue number: {issue_number}\\n"
            "Issue context is available. Keep preview edits focused on issue-relevant files.\\n"
        )

    return (
        "Generate a concise patch preview and return ONLY a JSON object.\\n"
        "JSON keys required: target_files, patch_strategy, planned_edits, validation_steps.\\n"
        "target_files/planned_edits/validation_steps must be non-empty arrays of strings.\\n"
        f"Task ID: {task_plan.get('task_id', '')}\\n"
        f"Task Title: {task_plan.get('title', '')}\\n"
        f"Task Goal: {task_plan.get('goal', '')}\\n"
        f"Task Source: {task_plan.get('source', 'template')}\\n"
        f"Rule target_files: {task_plan.get('target_files', [])}\\n"
        f"Rule validation_steps: {task_plan.get('validation_steps', [])}\\n"
        f"Summary repo_metadata: {None if summary_payload is None else summary_payload.get('repo_metadata')}\\n"
        f"Summary sample_open_issues: {None if summary_payload is None else summary_payload.get('sample_open_issues', [])}\\n"
        f"Candidate tasks context: {None if candidate_payload is None else candidate_payload.get('tasks', [])}\\n"
        f"{issue_context_lines}"
        "Keep strategy short and edits actionable."
    )


def _apply_llm_patch_preview(
    rule_patch_preview: dict[str, object],
    llm_content: str,
) -> dict[str, object]:
    parsed = _extract_json_object(llm_content)

    target_files = _normalize_text_list(parsed.get("target_files"))
    patch_strategy = str(parsed.get("patch_strategy", "")).strip()
    planned_edits = _normalize_text_list(parsed.get("planned_edits"))
    validation_steps = _normalize_text_list(parsed.get("validation_steps"))

    if not target_files:
        raise LLMClientError("LLM response format is invalid")
    if not patch_strategy:
        raise LLMClientError("LLM response format is invalid")
    if not planned_edits:
        raise LLMClientError("LLM response format is invalid")
    if not validation_steps:
        raise LLMClientError("LLM response format is invalid")

    llm_patch_preview = dict(rule_patch_preview)
    llm_patch_preview.update(
        {
            "target_files": target_files,
            "patch_strategy": patch_strategy,
            "planned_edits": planned_edits,
            "validation_steps": validation_steps,
        }
    )
    return llm_patch_preview


def run_generate_patch(task_id: str, use_llm: bool = False) -> str:
    output_dir = Path("playground") / "outputs"
    task_plan_file = output_dir / "task_plan.json"
    task_plan = _read_task_plan(task_plan_file)

    if str(task_plan.get("task_id")) != task_id:
        raise PatchGenerationError(f"task_id not found: {task_id}")

    patch_preview = _build_rule_patch_preview(task_plan)
    used_llm = False
    llm_fallback_triggered = False
    fallback_reason = ""

    if use_llm:
        try:
            candidate_payload = _read_optional_json(output_dir / "candidate_tasks.json")
            summary_payload = _read_optional_summary(output_dir, candidate_payload)
            issue_number_raw = patch_preview.get("issue_number")
            issue_number = issue_number_raw if isinstance(issue_number_raw, int) else None
            prompt = _build_llm_prompt(
                task_plan,
                summary_payload,
                candidate_payload,
                bool(patch_preview.get("issue_context_used", False)),
                issue_number,
            )
            client = LLMClient.from_env()
            llm_content = client.generate(prompt)
            patch_preview = _apply_llm_patch_preview(patch_preview, llm_content)
            used_llm = True
        except LLMClientError as exc:
            llm_fallback_triggered = True
            fallback_reason = str(exc)
        except Exception as exc:  # pragma: no cover - defensive safety net
            llm_fallback_triggered = True
            fallback_reason = str(exc)

    rule_fallback_triggered = bool(patch_preview.get("fallback_triggered", False))
    fallback_triggered = rule_fallback_triggered or llm_fallback_triggered
    patch_preview["fallback_triggered"] = fallback_triggered
    patch_preview["used_llm"] = used_llm
    if llm_fallback_triggered:
        patch_preview["fallback_reason"] = fallback_reason

    output_dir.mkdir(parents=True, exist_ok=True)
    patch_preview_file = output_dir / "patch_preview.json"
    patch_preview_file.write_text(
        json.dumps(patch_preview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    message = (
        "Patch preview generated.\n"
        f"task_id: {patch_preview['task_id']}\n"
        f"title: {patch_preview['title']}\n"
        f"patch_issue_context_used: {'true' if patch_preview['issue_context_used'] else 'false'}\n"
        f"patch_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"used_llm: {'true' if used_llm else 'false'}\n"
        f"patch_preview_file: {patch_preview_file.as_posix()}"
    )

    if llm_fallback_triggered:
        message += f"\nfallback_reason: {fallback_reason}"

    return message
