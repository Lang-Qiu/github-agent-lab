import json
from urllib.error import HTTPError

import pytest

from src.github_client import GitHubClient, GitHubClientError


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


def test_github_client_create_draft_pull_request_success(monkeypatch) -> None:
    captured = {"url": "", "method": "", "body": {}}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {
                "number": 5,
                "html_url": "https://github.com/owner/repo/pull/5",
                "state": "open",
            }
        )

    monkeypatch.setattr("src.github_client.urlopen", _fake_urlopen)

    client = GitHubClient(token="dummy", base_url="https://api.github.com")
    payload = client.create_draft_pull_request(
        owner="owner",
        repo="repo",
        title="feat: publish",
        body="draft body",
        head="feature/test",
        base="main",
    )

    assert payload["number"] == 5
    assert payload["url"] == "https://github.com/owner/repo/pull/5"
    assert captured["url"].endswith("/repos/owner/repo/pulls")
    assert captured["method"] == "POST"
    assert captured["body"]["draft"] is True
    assert captured["body"]["head"] == "feature/test"
    assert captured["body"]["base"] == "main"


def test_github_client_create_draft_pull_request_http_failure(monkeypatch) -> None:
    def _fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("src.github_client.urlopen", _fake_urlopen)

    client = GitHubClient(token="dummy", base_url="https://api.github.com")

    with pytest.raises(GitHubClientError, match="HTTP 401"):
        client.create_draft_pull_request(
            owner="owner",
            repo="repo",
            title="feat: publish",
            body="draft body",
            head="feature/test",
            base="main",
        )
