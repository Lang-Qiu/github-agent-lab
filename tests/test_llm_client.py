import json

import pytest

from src.llm_client import LLMClient, LLMClientError


class _FakeJSONResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


class _FakeStreamingResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")


def test_llm_client_from_env_reads_runtime_config(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_RETRY_BACKOFF_BASE_SECONDS", "1.5")
    monkeypatch.setenv("LLM_USE_STREAM", "0")

    client = LLMClient.from_env()

    assert client.timeout_seconds == 180
    assert client.max_retries == 2
    assert client.retry_backoff_base_seconds == pytest.approx(1.5)
    assert client.use_stream is False


def test_llm_client_retries_timeout_then_succeeds(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_MAX_RETRIES", "1")
    monkeypatch.setenv("LLM_USE_STREAM", "0")

    attempt_count = {"value": 0}

    def _fake_urlopen(request, timeout):
        attempt_count["value"] += 1
        if attempt_count["value"] == 1:
            raise TimeoutError("timed out")
        return _FakeJSONResponse(
            {
                "choices": [
                    {"message": {"content": "retry success"}},
                ]
            }
        )

    sleep_calls: list[float] = []
    monkeypatch.setattr("src.llm_client.urlopen", _fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    client = LLMClient.from_env()
    result = client.generate("hello")

    assert result == "retry success"
    assert attempt_count["value"] == 2
    assert sleep_calls == [1.0]


def test_llm_client_raises_after_retry_exhausted(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("LLM_USE_STREAM", "0")

    attempt_count = {"value": 0}

    def _fake_urlopen(request, timeout):
        attempt_count["value"] += 1
        raise TimeoutError("timed out")

    sleep_calls: list[float] = []
    monkeypatch.setattr("src.llm_client.urlopen", _fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda seconds: sleep_calls.append(seconds))

    client = LLMClient.from_env()

    with pytest.raises(LLMClientError, match="timed out"):
        client.generate("hello")

    assert attempt_count["value"] == 3
    assert sleep_calls == [1.0, 2.0]


def test_llm_client_streaming_reads_delta_content(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_USE_STREAM", "1")

    captured_stream_flag = {"value": None}

    def _fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        captured_stream_flag["value"] = body.get("stream")
        return _FakeStreamingResponse(
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
                'data: {"choices":[{"delta":{"content":" world"}}]}\n',
                'data: [DONE]\n',
            ]
        )

    monkeypatch.setattr("src.llm_client.urlopen", _fake_urlopen)

    client = LLMClient.from_env()
    result = client.generate_pr_draft("hello")

    assert result == "Hello world"
    assert captured_stream_flag["value"] is True
