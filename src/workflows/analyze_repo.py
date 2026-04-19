"""Repository analysis preparation workflow for local experiments."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url)
    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) >= 2:
        owner = parts[0]
        repo = parts[1]
    elif len(parts) == 1:
        owner = "unknown-owner"
        repo = parts[0]
    else:
        owner = "unknown-owner"
        repo = "unknown-repo"

    if repo.endswith(".git"):
        repo = repo[:-4]

    return owner, repo


def prepare_local_analysis(repo_url: str) -> dict[str, str]:
    owner, repo = parse_repo_url(repo_url)

    return {
        "repo_url": repo_url,
        "owner": owner,
        "repo": repo,
        "workspace_dir": f"playground/repos/{repo}",
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
        f"status: {result['status']}\n"
        f"summary_file: {summary_file.as_posix()}"
    )
