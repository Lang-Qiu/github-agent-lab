"""Candidate task discovery workflow based on analysis summary artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from ..llm_client import LLMClient, LLMClientError


class DiscoverTasksError(ValueError):
    """User-facing input error for discover-tasks command."""


def _parse_repo_url(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DiscoverTasksError(
            "Malformed URL. Use: https://github.com/<owner>/<repo>"
        )

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host != "github.com":
        raise DiscoverTasksError(
            "Only GitHub URLs are supported. "
            "Use: https://github.com/<owner>/<repo>"
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise DiscoverTasksError(
            "Missing owner/repo. Use: https://github.com/<owner>/<repo>"
        )

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise DiscoverTasksError(
            "Missing owner/repo. Use: https://github.com/<owner>/<repo>"
        )

    return owner, repo


def _read_summary_payload(output_dir: Path, repo_url: str) -> dict[str, object]:
    _, repo = _parse_repo_url(repo_url)
    summary_candidates = [
        output_dir / "summary.json",
        output_dir / f"{repo}_summary.json",
    ]

    for summary_file in summary_candidates:
        if summary_file.exists():
            return json.loads(summary_file.read_text(encoding="utf-8"))

    raise DiscoverTasksError("summary.json not found. Run analyze first.")


def discover_candidate_tasks(summary_payload: dict[str, object]) -> dict[str, object]:
    owner = str(summary_payload.get("owner", "")).strip()
    repo = str(summary_payload.get("repo", "")).strip()
    repo_url = str(summary_payload.get("repo_url", "")).strip()
    if not owner or not repo or not repo_url:
        raise DiscoverTasksError("summary.json is invalid. Run analyze first.")

    sample_open_issues = summary_payload.get("sample_open_issues") or []

    issue_tasks: list[dict[str, object]] = []
    for issue in sample_open_issues:
        if not isinstance(issue, dict):
            continue

        number = issue.get("number")
        title = issue.get("title")
        if not isinstance(number, int) or not title:
            continue

        issue_tasks.append(
            {
                "id": f"{repo}-issue-{number}",
                "title": f"Address issue #{number}: {title}",
                "type": "issue",
                "priority": "high",
                "status": "todo",
                "source": "github_issue",
                "issue_number": number,
            }
        )

    issue_context_used = len(issue_tasks) > 0
    fallback_triggered = not issue_context_used

    if issue_context_used:
        tasks = issue_tasks
    else:
        tasks = [
            {
                "id": f"{repo}-task-001",
                "title": "Review repository contribution guide",
                "type": "docs",
                "priority": "medium",
                "status": "todo",
                "source": "template",
            },
            {
                "id": f"{repo}-task-002",
                "title": "Identify candidate smoke test improvements",
                "type": "test",
                "priority": "high",
                "status": "todo",
                "source": "template",
            },
            {
                "id": f"{repo}-task-003",
                "title": f"Prepare first patch plan for {owner}/{repo}",
                "type": "planning",
                "priority": "medium",
                "status": "todo",
                "source": "template",
            },
        ]

    return {
        "repo_url": repo_url,
        "owner": owner,
        "repo": repo,
        "issue_context_used": issue_context_used,
        "fallback_triggered": fallback_triggered,
        "used_llm": False,
        "tasks": tasks,
    }


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
    summary_payload: dict[str, object],
    rule_payload: dict[str, object],
) -> str:
    issue_context_used = bool(rule_payload.get("issue_context_used", False))
    issue_note = ""
    if issue_context_used:
        issue_note = (
            "Issue context is available. Prefer github_issue tasks that map to "
            "open issues when possible.\\n"
        )

    return (
        "Generate candidate tasks and return ONLY a JSON object with a `tasks` array.\\n"
        "Each task requires: id, title, type, priority, status, source.\\n"
        "Optional: issue_number for github_issue tasks.\\n"
        "priority must be one of: low, medium, high.\\n"
        "status should normally be: todo.\\n"
        f"repo_url: {summary_payload.get('repo_url', '')}\\n"
        f"owner: {summary_payload.get('owner', '')}\\n"
        f"repo: {summary_payload.get('repo', '')}\\n"
        f"repo_metadata: {summary_payload.get('repo_metadata', None)}\\n"
        f"sample_open_issues: {summary_payload.get('sample_open_issues', [])}\\n"
        f"{issue_note}"
        "Keep task titles concise and actionable."
    )


def _normalize_llm_tasks(tasks_raw: object, repo: str) -> list[dict[str, object]]:
    if not isinstance(tasks_raw, list):
        raise LLMClientError("LLM response format is invalid")

    tasks: list[dict[str, object]] = []
    for index, item in enumerate(tasks_raw, start=1):
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "")).strip()
        if not title:
            continue

        issue_number_raw = item.get("issue_number")
        issue_number = issue_number_raw if isinstance(issue_number_raw, int) else None

        source_raw = str(item.get("source", "")).strip()
        if source_raw in {"github_issue", "template"}:
            source = source_raw
        else:
            source = "github_issue" if issue_number is not None else "template"

        canonical_issue_id = (
            f"{repo}-issue-{issue_number}" if issue_number is not None else ""
        )
        canonical_task_id = f"{repo}-task-{index:03d}"

        task_id_raw = str(item.get("id", "")).strip()
        if source == "github_issue" and issue_number is not None:
            if task_id_raw.startswith(f"{repo}-issue-"):
                task_id = task_id_raw
            else:
                task_id = canonical_issue_id
        else:
            if task_id_raw.startswith(f"{repo}-task-"):
                task_id = task_id_raw
            else:
                task_id = canonical_task_id

        priority = str(item.get("priority", "")).strip().lower()
        if priority not in {"low", "medium", "high"}:
            priority = "medium"

        status = str(item.get("status", "")).strip().lower() or "todo"
        task_type = str(item.get("type", "")).strip() or "task"

        task_payload: dict[str, object] = {
            "id": task_id,
            "title": title,
            "type": task_type,
            "priority": priority,
            "status": status,
            "source": source,
        }
        if issue_number is not None:
            task_payload["issue_number"] = issue_number

        tasks.append(task_payload)

    if not tasks:
        raise LLMClientError("LLM response format is invalid")

    return tasks


def _apply_llm_tasks(
    rule_payload: dict[str, object],
    llm_content: str,
) -> dict[str, object]:
    parsed = _extract_json_object(llm_content)
    repo = str(rule_payload["repo"])
    tasks = _normalize_llm_tasks(parsed.get("tasks"), repo)
    issue_context_used = any(
        task.get("source") == "github_issue" and isinstance(task.get("issue_number"), int)
        for task in tasks
    )

    llm_payload = dict(rule_payload)
    llm_payload["tasks"] = tasks
    llm_payload["issue_context_used"] = issue_context_used
    llm_payload["fallback_triggered"] = not issue_context_used
    return llm_payload


def run_discover_tasks(repo_url: str, use_llm: bool = False) -> str:
    output_dir = Path("playground") / "outputs"
    summary_payload = _read_summary_payload(output_dir, repo_url)

    candidate_payload = discover_candidate_tasks(summary_payload)
    used_llm = False
    llm_fallback_triggered = False
    fallback_reason = ""

    if use_llm:
        try:
            client = LLMClient.from_env()
            prompt = _build_llm_prompt(summary_payload, candidate_payload)
            llm_content = client.generate(prompt)
            candidate_payload = _apply_llm_tasks(candidate_payload, llm_content)
            used_llm = True
        except LLMClientError as exc:
            llm_fallback_triggered = True
            fallback_reason = str(exc)
        except Exception as exc:  # pragma: no cover - defensive safety net
            llm_fallback_triggered = True
            fallback_reason = str(exc)

    rule_fallback_triggered = bool(candidate_payload.get("fallback_triggered", False))
    fallback_triggered = rule_fallback_triggered or llm_fallback_triggered
    candidate_payload["fallback_triggered"] = fallback_triggered
    candidate_payload["used_llm"] = used_llm
    if llm_fallback_triggered:
        candidate_payload["fallback_reason"] = fallback_reason

    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_file = output_dir / "candidate_tasks.json"
    candidate_file.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    message = (
        "Candidate task discovery complete.\n"
        f"repo_url: {candidate_payload['repo_url']}\n"
        f"owner: {candidate_payload['owner']}\n"
        f"repo: {candidate_payload['repo']}\n"
        f"candidate_tasks_count: {len(candidate_payload['tasks'])}\n"
        f"candidate_issue_context_used: {'true' if candidate_payload['issue_context_used'] else 'false'}\n"
        f"candidate_fallback_triggered: {'true' if fallback_triggered else 'false'}\n"
        f"used_llm: {'true' if used_llm else 'false'}\n"
        f"candidate_tasks_file: {candidate_file.as_posix()}"
    )

    if llm_fallback_triggered:
        message += f"\nfallback_reason: {fallback_reason}"

    return message