"""Minimal publish client abstraction for git push and draft PR creation."""

from __future__ import annotations

import subprocess

from ..github_client import GitHubClient, GitHubClientError
from .analyze_repo import parse_repo_url


class PublishClientError(ValueError):
    """User-facing input error for publish client operations."""


class PublishClient:
    def __init__(self, github_client: object | None = None) -> None:
        self._github_client = github_client

    def _client(self) -> object:
        if self._github_client is not None:
            return self._github_client
        return GitHubClient.from_env()

    def verify_remote_repo(self, repo_url: str) -> dict[str, object]:
        owner, repo = parse_repo_url(repo_url)
        client = self._client()

        try:
            payload = client.get_repo_metadata(owner, repo)
        except GitHubClientError as exc:
            raise PublishClientError(str(exc)) from exc

        if not isinstance(payload, dict):
            raise PublishClientError("GitHub repository payload is invalid")

        return payload

    def push_branch(
        self,
        workspace_dir: str,
        branch_name: str,
        remote_name: str = "origin",
    ) -> dict[str, object]:
        command = [
            "git",
            "-C",
            workspace_dir,
            "push",
            "-u",
            remote_name,
            branch_name,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            reason = result.stderr.strip() or result.stdout.strip() or "git push failed"
            raise PublishClientError(f"git push failed: {reason}")

        return {
            "branch_name": branch_name,
            "pushed": True,
        }

    def create_draft_pr(
        self,
        repo_url: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, object]:
        owner, repo = parse_repo_url(repo_url)
        client = self._client()

        try:
            payload = client.create_draft_pull_request(
                owner=owner,
                repo=repo,
                title=title,
                body=body,
                head=head,
                base=base,
            )
        except GitHubClientError as exc:
            raise PublishClientError(str(exc)) from exc

        if not isinstance(payload, dict):
            raise PublishClientError("GitHub pull request payload is invalid")

        return payload
