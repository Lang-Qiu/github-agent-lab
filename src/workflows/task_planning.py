"""Minimal task planning workflow based on candidate tasks."""

from __future__ import annotations

import json
from pathlib import Path

from ..llm_client import LLMClient, LLMClientError


class TaskPlanningError(ValueError):
    """User-facing input error for task planning command."""


def _read_candidate_tasks(candidate_file: Path) -> dict[str, object]:
    if not candidate_file.exists():
        raise TaskPlanningError(
            "candidate_tasks.json not found. Run analyze first."
        )

    return json.loads(candidate_file.read_text(encoding="utf-8"))


def _select_task(payload: dict[str, object], task_id: str) -> dict[str, object]:
    tasks = payload.get("tasks", [])
    for task in tasks:
        if isinstance(task, dict) and task.get("id") == task_id:
            return task

    raise TaskPlanningError(f"task_id not found: {task_id}")


def _build_rule_task_plan(selected_task: dict[str, object]) -> dict[str, object]:
    source = str(selected_task.get("source", "template"))
    issue_number_raw = selected_task.get("issue_number")
    issue_number = issue_number_raw if isinstance(issue_number_raw, int) else None
    issue_context_used = source == "github_issue" and issue_number is not None
    rule_fallback_triggered = not issue_context_used

    if issue_context_used:
        goal = (
            f"Resolve issue #{issue_number} with a small verified change "
            f"for task {selected_task['id']}."
        )
        proposed_changes = [
            f"Implement the smallest fix for issue #{issue_number}.",
            "Add or update smoke tests to protect issue behavior.",
        ]
        target_files = [
            "src/workflows/task_planning.py",
            "tests/test_smoke.py",
        ]
        validation_steps = [
            "Run pytest -q.",
            f"Check plan output keeps issue #{issue_number} context.",
        ]
        risk_level = "medium"
    else:
        goal = f"Deliver candidate task {selected_task['id']} in a small verified step."
        proposed_changes = [
            "Implement the minimal code path for this task.",
            "Update smoke tests to verify expected behavior.",
        ]
        target_files = [
            "src/workflows/analyze_repo.py",
            "tests/test_smoke.py",
        ]
        validation_steps = [
            "Run pytest -q.",
            "Check CLI output for expected summary lines.",
        ]
        risk_level = "low"

    task_plan = {
        "task_id": str(selected_task["id"]),
        "title": str(selected_task["title"]),
        "goal": goal,
        "proposed_changes": proposed_changes,
        "target_files": target_files,
        "validation_steps": validation_steps,
        "risk_level": risk_level,
        "status": "planned",
        "source": source,
        "issue_context_used": issue_context_used,
        "fallback_triggered": rule_fallback_triggered,
    }

    if issue_number is not None:
        task_plan["issue_number"] = issue_number

    return task_plan


def _read_summary_for_llm(
    output_dir: Path,
    candidate_payload: dict[str, object],
) -> dict[str, object]:
    repo = candidate_payload.get("repo")
    summary_files = [output_dir / "summary.json"]
    if isinstance(repo, str) and repo.strip():
        summary_files.append(output_dir / f"{repo}_summary.json")

    for summary_file in summary_files:
        if summary_file.exists():
            return json.loads(summary_file.read_text(encoding="utf-8"))

    raise TaskPlanningError("summary.json not found. Run analyze first.")


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
    selected_task: dict[str, object],
    candidate_payload: dict[str, object],
    summary_payload: dict[str, object],
    issue_context_used: bool,
    issue_number: int | None,
) -> str:
    issue_context_lines = ""
    if issue_context_used and issue_number is not None:
        issue_title = ""
        issue_state = ""
        for issue in summary_payload.get("sample_open_issues", []):
            if isinstance(issue, dict) and issue.get("number") == issue_number:
                issue_title = str(issue.get("title", "")).strip()
                issue_state = str(issue.get("state", "")).strip()
                break

        if not issue_title:
            issue_title = str(selected_task.get("title", "")).strip()

        issue_context_lines = (
            f"Issue number: {issue_number}\\n"
            f"Issue title: {issue_title}\\n"
            f"Issue state: {issue_state}\\n"
        )

    return (
        "Generate a concise task planning result and return ONLY a JSON object.\\n"
        "JSON keys required: goal, proposed_changes, target_files, validation_steps, risk_level.\\n"
        "risk_level must be one of: low, medium, high.\\n"
        f"Task id: {selected_task.get('id', '')}\\n"
        f"Task title: {selected_task.get('title', '')}\\n"
        f"Task source: {selected_task.get('source', 'template')}\\n"
        f"Repository URL: {candidate_payload.get('repo_url', summary_payload.get('repo_url', ''))}\\n"
        f"Repository owner: {candidate_payload.get('owner', summary_payload.get('owner', ''))}\\n"
        f"Repository name: {candidate_payload.get('repo', summary_payload.get('repo', ''))}\\n"
        f"Workspace dir: {summary_payload.get('workspace_dir', '')}\\n"
        f"Sample open issues: {summary_payload.get('sample_open_issues', [])}\\n"
        f"{issue_context_lines}"
        "Keep each proposed change and validation step short and actionable."
    )


def _apply_llm_plan(
    rule_task_plan: dict[str, object],
    llm_content: str,
) -> dict[str, object]:
    parsed = _extract_json_object(llm_content)

    goal = str(parsed.get("goal", "")).strip()
    proposed_changes = _normalize_text_list(parsed.get("proposed_changes"))
    target_files = _normalize_text_list(parsed.get("target_files"))
    validation_steps = _normalize_text_list(parsed.get("validation_steps"))
    risk_level = str(parsed.get("risk_level", "")).strip().lower()

    if not goal:
        raise LLMClientError("LLM response format is invalid")
    if not proposed_changes:
        raise LLMClientError("LLM response format is invalid")
    if not target_files:
        raise LLMClientError("LLM response format is invalid")
    if not validation_steps:
        raise LLMClientError("LLM response format is invalid")
    if risk_level not in {"low", "medium", "high"}:
        raise LLMClientError("LLM response format is invalid")

    llm_task_plan = dict(rule_task_plan)
    llm_task_plan.update(
        {
            "goal": goal,
            "proposed_changes": proposed_changes,
            "target_files": target_files,
            "validation_steps": validation_steps,
            "risk_level": risk_level,
        }
    )
    return llm_task_plan


def run_task_planning(task_id: str, use_llm: bool = False) -> str:
    output_dir = Path("playground") / "outputs"
    candidate_file = output_dir / "candidate_tasks.json"

    payload = _read_candidate_tasks(candidate_file)
    selected_task = _select_task(payload, task_id)

    task_plan = _build_rule_task_plan(selected_task)
    used_llm = False
    llm_fallback_triggered = False
    fallback_reason = ""

    if use_llm:
        try:
            summary_payload = _read_summary_for_llm(output_dir, payload)
            issue_number_raw = task_plan.get("issue_number")
            issue_number = issue_number_raw if isinstance(issue_number_raw, int) else None
            prompt = _build_llm_prompt(
                selected_task,
                payload,
                summary_payload,
                bool(task_plan.get("issue_context_used", False)),
                issue_number,
            )
            client = LLMClient.from_env()
            llm_content = client.generate(prompt)
            task_plan = _apply_llm_plan(task_plan, llm_content)
            used_llm = True
        except (LLMClientError, TaskPlanningError) as exc:
            llm_fallback_triggered = True
            fallback_reason = str(exc)
        except Exception as exc:  # pragma: no cover - defensive safety net
            llm_fallback_triggered = True
            fallback_reason = str(exc)

    rule_fallback_triggered = bool(task_plan.get("fallback_triggered", False))
    fallback_triggered = rule_fallback_triggered or llm_fallback_triggered
    task_plan["fallback_triggered"] = fallback_triggered
    task_plan["used_llm"] = used_llm
    if llm_fallback_triggered:
        task_plan["fallback_reason"] = fallback_reason

    output_dir.mkdir(parents=True, exist_ok=True)
    task_plan_file = output_dir / "task_plan.json"
    task_plan_file.write_text(
        json.dumps(task_plan, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    message = (
        "Task plan generated.\n"
        f"task_id: {task_plan['task_id']}\n"
        f"title: {task_plan['title']}\n"
        f"task_plan_issue_context_used: {'true' if task_plan['issue_context_used'] else 'false'}\n"
        f"task_plan_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"used_llm: {'true' if used_llm else 'false'}\n"
        f"task_plan_file: {task_plan_file.as_posix()}"
    )

    if llm_fallback_triggered:
        message += f"\nfallback_reason: {fallback_reason}"

    return message
