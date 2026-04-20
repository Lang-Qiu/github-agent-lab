"""Minimal LLM client for PR draft generation."""

from __future__ import annotations

import json
import os
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMClientError(ValueError):
    """User-facing error for LLM configuration and request failures."""


class LLMClientTimeoutError(LLMClientError):
    """Retryable timeout error for LLM requests."""


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: int = 120,
        max_retries: int = 1,
        retry_backoff_base_seconds: float = 1.0,
        use_stream: bool = True,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, min(max_retries, 2))
        self.retry_backoff_base_seconds = max(retry_backoff_base_seconds, 0.0)
        self.use_stream = use_stream

    @staticmethod
    def _env_int(
        name: str,
        default: int,
        *,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            value = default
        else:
            try:
                value = int(raw)
            except ValueError as exc:
                raise LLMClientError(
                    f"Invalid LLM config: {name} must be an integer"
                ) from exc

        if min_value is not None and value < min_value:
            raise LLMClientError(
                f"Invalid LLM config: {name} must be >= {min_value}"
            )
        if max_value is not None and value > max_value:
            raise LLMClientError(
                f"Invalid LLM config: {name} must be <= {max_value}"
            )

        return value

    @staticmethod
    def _env_float(name: str, default: float, *, min_value: float | None = None) -> float:
        raw = os.getenv(name, "").strip()
        if not raw:
            value = default
        else:
            try:
                value = float(raw)
            except ValueError as exc:
                raise LLMClientError(
                    f"Invalid LLM config: {name} must be a number"
                ) from exc

        if min_value is not None and value < min_value:
            raise LLMClientError(
                f"Invalid LLM config: {name} must be >= {min_value}"
            )

        return value

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name, "").strip().lower()
        if not raw:
            return default

        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False

        raise LLMClientError(
            f"Invalid LLM config: {name} must be true/false or 1/0"
        )

    @classmethod
    def from_env(cls) -> "LLMClient":
        api_key = os.getenv("LLM_API_KEY", "").strip()
        base_url = os.getenv("LLM_BASE_URL", "").strip()
        model = os.getenv("LLM_MODEL", "").strip()
        timeout_seconds = cls._env_int(
            "LLM_TIMEOUT_SECONDS",
            default=120,
            min_value=1,
        )
        max_retries = cls._env_int(
            "LLM_MAX_RETRIES",
            default=1,
            min_value=0,
            max_value=2,
        )
        retry_backoff_base_seconds = cls._env_float(
            "LLM_RETRY_BACKOFF_BASE_SECONDS",
            default=1.0,
            min_value=0.0,
        )
        use_stream = cls._env_bool("LLM_USE_STREAM", default=True)

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

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_base_seconds=retry_backoff_base_seconds,
            use_stream=use_stream,
        )

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    @staticmethod
    def _is_timeout_error(error: object) -> bool:
        if isinstance(error, (TimeoutError, socket.timeout)):
            return True

        message = str(error).lower()
        return "timed out" in message or "timeout" in message

    @staticmethod
    def _extract_content_from_parsed_response(parsed: object) -> str:
        if not isinstance(parsed, dict):
            raise LLMClientError("LLM response format is invalid")

        try:
            content = parsed["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMClientError("LLM response format is invalid") from exc

        content_str = str(content).strip()
        if not content_str:
            raise LLMClientError("LLM response content is empty")

        return content_str

    @classmethod
    def _extract_non_stream_content(cls, response_data: str) -> str:
        try:
            parsed = json.loads(response_data)
        except Exception as exc:
            raise LLMClientError("LLM response format is invalid") from exc

        return cls._extract_content_from_parsed_response(parsed)

    @staticmethod
    def _extract_stream_chunk(parsed: object) -> str:
        if not isinstance(parsed, dict):
            return ""

        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return ""

        delta = first_choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                return content

        message = first_choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content

        return ""

    @classmethod
    def _extract_stream_content(cls, response: object) -> str:
        chunks: list[str] = []
        passthrough_lines: list[str] = []

        for raw_line in response:
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
            line = line.strip()
            if not line:
                continue

            if not line.startswith("data:"):
                passthrough_lines.append(line)
                continue

            data_part = line[5:].strip()
            if data_part == "[DONE]":
                break

            try:
                parsed = json.loads(data_part)
            except json.JSONDecodeError as exc:
                raise LLMClientError("LLM response format is invalid") from exc

            chunk = cls._extract_stream_chunk(parsed)
            if chunk:
                chunks.append(chunk)

        content = "".join(chunks).strip()
        if content:
            return content

        if passthrough_lines:
            return cls._extract_non_stream_content("".join(passthrough_lines))

        raise LLMClientError("LLM response content is empty")

    def _request_once(self, prompt: str) -> str:
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
            "stream": self.use_stream,
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
                if self.use_stream:
                    return self._extract_stream_content(response)

                response_data = response.read().decode("utf-8")
                return self._extract_non_stream_content(response_data)
        except HTTPError as exc:
            raise LLMClientError(f"LLM request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            if self._is_timeout_error(exc.reason):
                raise LLMClientTimeoutError(f"LLM request timed out: {exc.reason}") from exc
            raise LLMClientError(f"LLM request failed: {exc.reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMClientTimeoutError(f"LLM request timed out: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive safety net
            if self._is_timeout_error(exc):
                raise LLMClientTimeoutError(f"LLM request timed out: {exc}") from exc
            raise LLMClientError(f"LLM request failed: {exc}") from exc

    def generate_pr_draft(self, prompt: str) -> str:
        if not prompt.strip():
            raise LLMClientError("Prompt must not be empty")

        total_attempts = self.max_retries + 1
        last_timeout_error: LLMClientTimeoutError | None = None

        for attempt in range(total_attempts):
            try:
                return self._request_once(prompt)
            except LLMClientTimeoutError as exc:
                last_timeout_error = exc
                if attempt >= self.max_retries:
                    raise exc

                delay_seconds = self.retry_backoff_base_seconds * (2 ** attempt)
                if delay_seconds > 0:
                    time.sleep(delay_seconds)

        if last_timeout_error is not None:
            raise last_timeout_error

        raise LLMClientError("LLM request failed: unknown error")

    def generate(self, prompt: str) -> str:
        """Backward-compatible alias for the old placeholder interface."""
        return self.generate_pr_draft(prompt)
