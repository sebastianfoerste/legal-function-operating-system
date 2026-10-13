import json
from typing import Any

import anthropic
import httpx2

from src.claude_client import ClaudeClientProxy, ClaudeModelsProxy, client, generate_mock_response
from src.config import CLAUDE_OPUS_5_5


def _canned_message(stop_reason: str, content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": CLAUDE_OPUS_5_5,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 12, "output_tokens": 34},
    }


def _recording_proxy(reply: dict[str, Any], captured: list[httpx2.Request]) -> ClaudeModelsProxy:
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=reply)

    real_client = anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return ClaudeModelsProxy(real_client)


def test_claude_client_uses_local_mock_by_default() -> None:
    response = client.models.generate_content(
        model=CLAUDE_OPUS_5_5, contents="Assess matter intake"
    )
    payload = json.loads(response.text)
    assert payload["matter_type"] == "privacy"


def test_mock_response_stays_legal_ops_scoped() -> None:
    text = generate_mock_response(CLAUDE_OPUS_5_5, "risk assessment")
    payload = json.loads(text)
    assert "findings" in payload
    assert payload["export_allowed"] is False


def test_missing_anthropic_key_falls_back_to_local_mock(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LEGAL_AGENT_EXTERNAL_MODEL_ENABLED", "true")

    proxy = ClaudeClientProxy()

    assert proxy.real_client is None
    response = proxy.models.generate_content(model=CLAUDE_OPUS_5_5, contents="risk assessment")
    assert json.loads(response.text)["export_allowed"] is False


def test_anthropic_key_and_opt_in_enable_external_client(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LEGAL_AGENT_EXTERNAL_MODEL_ENABLED", "true")

    assert isinstance(ClaudeClientProxy().real_client, anthropic.Anthropic)


def test_external_request_targets_opus_5_5_with_supported_parameters() -> None:
    captured: list[httpx2.Request] = []
    reply = _canned_message(
        "end_turn",
        [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": '{"matter_type": "employment"}'},
        ],
    )
    proxy = _recording_proxy(reply, captured)

    response = proxy.generate_content(model=CLAUDE_OPUS_5_5, contents="Assess matter intake")

    assert json.loads(response.text) == {"matter_type": "employment"}
    (request,) = captured
    body = json.loads(request.content)
    assert request.url.path == "/v1/messages"
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 16000
    assert body["output_config"] == {"effort": "high"}
    assert body["messages"] == [{"role": "user", "content": "Assess matter intake"}]
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in request.headers["anthropic-beta"]
    assert "tool_choice" not in body
    assert "thinking" not in body
    assert not {"temperature", "top_p", "top_k"} & body.keys()


def test_refusal_falls_back_to_local_mock(capsys) -> None:
    captured: list[httpx2.Request] = []
    reply = _canned_message("refusal", [])
    reply["stop_details"] = {"type": "refusal", "category": "cyber", "explanation": None}
    proxy = _recording_proxy(reply, captured)

    response = proxy.generate_content(model=CLAUDE_OPUS_5_5, contents="risk assessment")

    assert len(captured) == 1
    assert json.loads(response.text)["export_allowed"] is False
    assert "request refused (category: cyber)" in capsys.readouterr().out
