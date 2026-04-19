"""Repository analysis preparation workflow for local experiments."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

from ..github_client import GitHubClient, GitHubClientError
from .discover_tasks import discover_candidate_tasks


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


def run_analyze_repo(repo_url: str) -> str:
    result = prepare_local_analysis(repo_url)
    owner = result["owner"]
    repo = result["repo"]

    repo_metadata: dict[str, object] | None = None
    sample_open_issues: list[dict[str, object]] = []
    github_remote_used = False
    github_fallback_triggered = False
    github_fallback_reason = ""

    if os.getenv("GITHUB_TOKEN", "").strip():
        try:
            github_client = GitHubClient.from_env()
            repo_metadata = github_client.get_repo_metadata(owner, repo)
            sample_open_issues = github_client.get_open_issues(owner, repo, limit=3)
            github_remote_used = True
        except GitHubClientError as exc:
            github_fallback_triggered = True
            github_fallback_reason = str(exc)

    output_dir = Path("playground") / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_file = output_dir / f"{result['repo']}_summary.json"
    summary_payload = {
        **result,
        "repo_metadata": repo_metadata,
        "sample_open_issues": sample_open_issues,
    }
    summary_file.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    candidate_payload = discover_candidate_tasks(summary_payload)
    candidate_file = output_dir / "candidate_tasks.json"
    candidate_file.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    task_count = len(candidate_payload["tasks"])

    message = (
        "Local analysis preparation complete.\n"
        f"repo_url: {result['repo_url']}\n"
        f"owner: {result['owner']}\n"
        f"repo: {result['repo']}\n"
        f"workspace_dir: {result['workspace_dir']}\n"
        f"workspace_initialized: {result['workspace_initialized']}\n"
        f"github_remote_used: {'true' if github_remote_used else 'false'}\n"
        f"github_fallback_triggered: {'true' if github_fallback_triggered else 'false'}\n"
        f"status: {result['status']}\n"
        f"summary_file: {summary_file.as_posix()}\n"
        f"candidate_tasks_file: {candidate_file.as_posix()}\n"
        f"candidate_tasks_count: {task_count}\n"
        f"candidate_issue_context_used: {'true' if candidate_payload['issue_context_used'] else 'false'}\n"
        f"candidate_fallback_triggered: {'true' if candidate_payload['fallback_triggered'] else 'false'}"
    )

    if github_fallback_triggered:
        message += f"\ngithub_fallback_reason: {github_fallback_reason}"

    return message
