"""Minimal LLM client for PR draft generation."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMClientError(ValueError):
    """User-facing error for LLM configuration and request failures."""


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "LLMClient":
        api_key = os.getenv("LLM_API_KEY", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()

        missing = []
        if not api_key:
            missing.append("LLM_API_KEY")
        if not base_url:
            missing.append("LLM_BASE_URL")
        if not model:
            missing.append("LLM_MODEL")

        if missing:
            missing_str = ", ".join(missing)
            raise LLMClientError(f"Missing LLM config: {missing_str}")

        return cls(api_key=api_key, base_url=base_url, model=model)

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def generate_pr_draft(self, prompt: str) -> str:
        if not prompt.strip():
            raise LLMClientError("Prompt must not be empty")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant that writes concise pull request drafts.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "stream": False,
        }

        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url=self._chat_completions_url(),
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_data = response.read().decode("utf-8")
        except HTTPError as exc:
            raise LLMClientError(f"LLM request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise LLMClientError(f"LLM request failed: {exc.reason}") from exc
        except Exception as exc:  # pragma: no cover - defensive safety net
            raise LLMClientError(f"LLM request failed: {exc}") from exc

        try:
            parsed = json.loads(response_data)
            content = parsed["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMClientError("LLM response format is invalid") from exc

        content_str = str(content).strip()
        if not content_str:
            raise LLMClientError("LLM response content is empty")

        return content_str

    def generate(self, prompt: str) -> str:
        """Backward-compatible alias for the old placeholder interface."""
        return self.generate_pr_draft(prompt)
