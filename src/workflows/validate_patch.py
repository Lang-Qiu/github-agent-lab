"""Minimal workspace validation workflow based on patch apply results."""

from __future__ import annotations

import json
from pathlib import Path

from ..llm_client import LLMClient, LLMClientError


class ValidationError(ValueError):
    """User-facing input error for validation command."""


def _read_json_file(file_path: Path, missing_message: str) -> dict[str, object]:
    if not file_path.exists():
        raise ValidationError(missing_message)

    return json.loads(file_path.read_text(encoding="utf-8"))


def _read_optional_json(file_path: Path) -> dict[str, object] | None:
    if not file_path.exists():
        return None

    return json.loads(file_path.read_text(encoding="utf-8"))


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


def _build_llm_prompt(
    task_id: str,
    apply_result: dict[str, object],
    patch_preview: dict[str, object] | None,
    task_plan: dict[str, object] | None,
    issue_context_used: bool,
    issue_number: int | None,
    checked_files: list[str],
    missing_files: list[str],
    passed: bool,
    status: str,
) -> str:
    issue_line = ""
    if issue_context_used and issue_number is not None:
        issue_line = f"Issue number: {issue_number}\\n"

    return (
        "Generate validation output and return ONLY a JSON object.\\n"
        "JSON keys required: summary, validation_steps.\\n"
        "summary must be a concise string; validation_steps must be a non-empty array of strings.\\n"
        f"Task ID: {task_id}\\n"
        f"Workspace dir: {apply_result.get('workspace_dir', '')}\\n"
        f"Apply summary: {apply_result.get('summary', '')}\\n"
        f"Apply source: {apply_result.get('source', 'template')}\\n"
        f"Patch strategy: {None if patch_preview is None else patch_preview.get('patch_strategy', '')}\\n"
        f"Patch planned edits: {None if patch_preview is None else patch_preview.get('planned_edits', [])}\\n"
        f"Task plan goal: {None if task_plan is None else task_plan.get('goal', '')}\\n"
        f"Checked files: {checked_files}\\n"
        f"Missing files: {missing_files}\\n"
        f"Passed: {passed}\\n"
        f"Status: {status}\\n"
        f"{issue_line}"
        "Keep text practical and verification-oriented."
    )


def _extract_llm_validation_payload(content: str) -> tuple[str, list[str]]:
    parsed = _extract_json_object(content)
    summary = str(parsed.get("summary", "")).strip()
    validation_steps = _normalize_text_list(parsed.get("validation_steps"))

    if not summary:
        raise LLMClientError("LLM response format is invalid")
    if not validation_steps:
        raise LLMClientError("LLM response format is invalid")

    return summary, validation_steps


def run_validate_patch(task_id: str, use_llm: bool = False) -> str:
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
    rule_fallback_triggered = not issue_context_used
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
    summary = (
        f"Validated {len(checked_files)} files; "
        f"missing {len(missing_files)} files."
    )

    used_llm = False
    llm_fallback_triggered = False
    fallback_reason = ""

    if use_llm:
        try:
            patch_preview = _read_optional_json(output_dir / "patch_preview.json")
            task_plan = _read_optional_json(output_dir / "task_plan.json")
            prompt = _build_llm_prompt(
                task_id,
                apply_result,
                patch_preview,
                task_plan,
                issue_context_used,
                issue_number,
                checked_files,
                missing_files,
                passed,
                status,
            )
            client = LLMClient.from_env()
            llm_content = client.generate(prompt)
            summary, validation_steps = _extract_llm_validation_payload(llm_content)
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
        "checked_files": checked_files,
        "missing_files": missing_files,
        "validation_steps": validation_steps,
        "passed": passed,
        "status": status,
        "summary": summary,
        "source": source,
        "issue_context_used": issue_context_used,
        "fallback_triggered": fallback_triggered,
        "used_llm": used_llm,
    }

    if issue_context_used and issue_number is not None:
        result["issue_number"] = issue_number
    if llm_fallback_triggered:
        result["fallback_reason"] = fallback_reason

    output_dir.mkdir(parents=True, exist_ok=True)
    validation_file = output_dir / "validation_result.json"
    validation_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    message = (
        "Validation completed.\n"
        f"task_id: {task_id}\n"
        f"status: {status}\n"
        f"checked_files_count: {len(checked_files)}\n"
        f"missing_files_count: {len(missing_files)}\n"
        f"validation_issue_context_used: {'true' if issue_context_used else 'false'}\n"
        f"validation_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"used_llm: {'true' if used_llm else 'false'}\n"
        f"validation_result_file: {validation_file.as_posix()}"
    )

    if llm_fallback_triggered:
        message += f"\nfallback_reason: {fallback_reason}"

    return message
