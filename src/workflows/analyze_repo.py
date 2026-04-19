"""Repository analysis preparation workflow for local experiments."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


class AnalyzeInputError(ValueError):
    """User-facing input error for analyze command."""


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AnalyzeInputError(
            "Malformed URL. Use: https://github.com/<owner>/<repo>"
        )

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host != "github.com":
        raise AnalyzeInputError(
            "Only GitHub URLs are supported. "
            "Use: https://github.com/<owner>/<repo>"
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise AnalyzeInputError(
            "Missing owner/repo. Use: https://github.com/<owner>/<repo>"
        )

    owner = parts[0]
    repo = parts[1]

    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise AnalyzeInputError(
            "Missing owner/repo. Use: https://github.com/<owner>/<repo>"
        )

    return owner, repo


def prepare_local_analysis(repo_url: str) -> dict[str, str]:
    owner, repo = parse_repo_url(repo_url)
    workspace_dir = Path("playground") / "repos" / owner / repo
    workspace_existed = workspace_dir.exists()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    workspace_initialized = "reused" if workspace_existed else "created"

    return {
        "repo_url": repo_url,
        "owner": owner,
        "repo": repo,
        "workspace_dir": workspace_dir.as_posix(),
        "workspace_initialized": workspace_initialized,
        "status": "prepared",
    }


def discover_candidate_tasks(summary_file: Path) -> dict[str, object]:
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    owner = str(summary["owner"])
    repo = str(summary["repo"])
    repo_url = str(summary["repo_url"])

    tasks = [
        {
            "id": f"{repo}-task-001",
            "title": "Review repository contribution guide",
            "type": "docs",
            "priority": "medium",
            "status": "todo",
        },
        {
            "id": f"{repo}-task-002",
            "title": "Identify candidate smoke test improvements",
            "type": "test",
            "priority": "high",
            "status": "todo",
        },
        {
            "id": f"{repo}-task-003",
            "title": f"Prepare first patch plan for {owner}/{repo}",
            "type": "planning",
            "priority": "medium",
            "status": "todo",
        },
    ]

    return {
        "repo_url": repo_url,
        "owner": owner,
        "repo": repo,
        "tasks": tasks,
    }


def run_analyze_repo(repo_url: str) -> str:
    result = prepare_local_analysis(repo_url)

    output_dir = Path("playground") / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_file = output_dir / f"{result['repo']}_summary.json"
    summary_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    candidate_payload = discover_candidate_tasks(summary_file)
    candidate_file = output_dir / "candidate_tasks.json"
    candidate_file.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    task_count = len(candidate_payload["tasks"])

    return (
        "Local analysis preparation complete.\n"
        f"repo_url: {result['repo_url']}\n"
        f"owner: {result['owner']}\n"
        f"repo: {result['repo']}\n"
        f"workspace_dir: {result['workspace_dir']}\n"
        f"workspace_initialized: {result['workspace_initialized']}\n"
        f"status: {result['status']}\n"
        f"summary_file: {summary_file.as_posix()}\n"
        f"candidate_tasks_file: {candidate_file.as_posix()}\n"
        f"candidate_tasks_count: {task_count}"
    )
