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


def run_analyze_repo(repo_url: str) -> str:
    result = prepare_local_analysis(repo_url)

    output_dir = Path("playground") / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_file = output_dir / f"{result['repo']}_summary.json"
    summary_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return (
        "Local analysis preparation complete.\n"
        f"repo_url: {result['repo_url']}\n"
        f"owner: {result['owner']}\n"
        f"repo: {result['repo']}\n"
        f"workspace_dir: {result['workspace_dir']}\n"
        f"workspace_initialized: {result['workspace_initialized']}\n"
        f"status: {result['status']}\n"
        f"summary_file: {summary_file.as_posix()}"
    )
