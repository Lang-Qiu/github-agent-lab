"""Helpers for local repository workspace paths."""

from pathlib import Path


def get_repo_workspace(base_dir: str, repo_url: str) -> Path:
    repo_name = repo_url.rstrip("/").split("/")[-1] or "unknown-repo"
    sanitized = repo_name.replace(".git", "").replace(" ", "-")
    return Path(base_dir) / sanitized
