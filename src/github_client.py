"""Lightweight read-only GitHub client for repository metadata fetching."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubClientError(ValueError):
    """User-facing error for GitHub read-only client failures."""


class GitHubClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        timeout_seconds: int = 20,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "GitHubClient":
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            raise GitHubClientError("Missing GitHub config: GITHUB_TOKEN")

        base_url = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com").strip()
        return cls(token=token, base_url=base_url)

    def _request_json(
        self,
        url: str,
        *,
        method: str,
        payload: dict[str, object] | None = None,
    ) -> object:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = Request(
            url=url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "github-agent-lab",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            raise GitHubClientError(f"GitHub request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise GitHubClientError(f"GitHub request failed: {exc.reason}") from exc
        except Exception as exc:  # pragma: no cover - defensive safety net
            raise GitHubClientError(f"GitHub request failed: {exc}") from exc

        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise GitHubClientError("GitHub response format is invalid") from exc

    def _get_json(self, url: str) -> object:
        return self._request_json(url, method="GET")

    def get_repo_metadata(self, owner: str, repo: str) -> dict[str, object]:
        payload = self._get_json(f"{self.base_url}/repos/{owner}/{repo}")
        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub repository payload is invalid")

        return {
            "full_name": str(payload.get("full_name", f"{owner}/{repo}")),
            "description": payload.get("description"),
            "default_branch": str(payload.get("default_branch", "")),
            "open_issues_count": int(payload.get("open_issues_count", 0)),
        }

    def get_open_issues(self, owner: str, repo: str, limit: int = 3) -> list[dict[str, object]]:
        params = urlencode({"state": "open", "per_page": limit})
        payload = self._get_json(f"{self.base_url}/repos/{owner}/{repo}/issues?{params}")
        if not isinstance(payload, list):
            raise GitHubClientError("GitHub issues payload is invalid")

        issues: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if "pull_request" in item:
                continue
            issues.append(
                {
                    "number": int(item.get("number", 0)),
                    "title": str(item.get("title", "")),
                    "state": str(item.get("state", "")),
                }
            )
            if len(issues) >= limit:
                break

        return issues

    def create_draft_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, object]:
        if not title.strip():
            raise GitHubClientError("Draft PR title must not be empty")
        if not head.strip() or not base.strip():
            raise GitHubClientError("Draft PR head/base must not be empty")

        payload = self._request_json(
            f"{self.base_url}/repos/{owner}/{repo}/pulls",
            method="POST",
            payload={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": True,
            },
        )

        if not isinstance(payload, dict):
            raise GitHubClientError("GitHub pull request payload is invalid")

        number_raw = payload.get("number")
        html_url_raw = payload.get("html_url")
        if not isinstance(number_raw, int):
            raise GitHubClientError("GitHub pull request payload is invalid")
        if not isinstance(html_url_raw, str) or not html_url_raw.strip():
            raise GitHubClientError("GitHub pull request payload is invalid")

        return {
            "number": number_raw,
            "url": html_url_raw.strip(),
            "state": str(payload.get("state", "")),
        }
