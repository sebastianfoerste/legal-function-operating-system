from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from src.intelligence_core import apply_language_standards

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised only when optional SDK is absent
    anthropic = None  # type: ignore[assignment]

# The external model prepares matter intake and risk findings for a lawyer's review, so it
# runs above Opus 5.5's "medium" default.
EXTERNAL_MODEL_EFFORT = "high"
# Thinking tokens count against max_tokens; this leaves room for thinking plus a short reply
# without a streaming request.
EXTERNAL_MODEL_MAX_TOKENS = 16000
# A classifier decline is retried server-side on the model Anthropic recommends for that
# refusal category, so a false positive does not end the request.
SERVER_SIDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class TextResponse:
    text: str


def generate_mock_response(model: str, contents: str) -> str:
    """Return deterministic local responses for demo and CI runs."""

    content_lower = contents.lower()
    if "matter" in content_lower or "intake" in content_lower:
        return json.dumps(
            {
                "title": "Enterprise customer DPA review",
                "matter_type": "privacy",
                "urgency": "high",
                "routing": "privacy counsel and security reviewer",
            },
            indent=2,
        )
    if "risk" in content_lower or "assessment" in content_lower:
        return json.dumps(
            {
                "findings": [
                    {
                        "category": "privacy",
                        "severity": "medium",
                        "summary": "Personal data processing terms require review.",
                    }
                ],
                "export_allowed": False,
            },
            indent=2,
        )
    return "Local legal-ops demo response. Human review remains required before export."


class ClaudeModelsProxy:
    """Proxy for optional Claude calls with deterministic local fallback."""

    def __init__(self, real_client: Any | None = None):
        self.real_client = real_client

    def generate_content(self, model: str, contents: str, **kwargs: Any) -> TextResponse:
        if self.real_client:
            try:
                output_config = {"effort": EXTERNAL_MODEL_EFFORT, **kwargs.pop("output_config", {})}
                response = self.real_client.beta.messages.create(
                    model=model,
                    max_tokens=EXTERNAL_MODEL_MAX_TOKENS,
                    messages=[{"role": "user", "content": contents}],
                    output_config=output_config,
                    fallbacks="default",
                    betas=[SERVER_SIDE_FALLBACK_BETA],
                    **kwargs,
                )
                # A refusal arrives as HTTP 200, so the SDK raises nothing for it.
                if response.stop_reason == "refusal":
                    category = response.stop_details.category if response.stop_details else None
                    raise RuntimeError(f"request refused (category: {category})")
                text = "".join(block.text for block in response.content if block.type == "text")
                if text:
                    return TextResponse(apply_language_standards(text))
            except Exception as exc:
                print(f"[claude_client] External model unavailable: {exc}")
        return TextResponse(apply_language_standards(generate_mock_response(model, contents)))


class ClaudeClientProxy:
    """Small wrapper that keeps external model use optional."""

    def __init__(self) -> None:
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        external_enabled = os.getenv("LEGAL_AGENT_EXTERNAL_MODEL_ENABLED", "").lower() == "true"
        self.real_client = None

        if anthropic is not None and anthropic_api_key and external_enabled:
            self.real_client = anthropic.Anthropic(api_key=anthropic_api_key)
            self.models = ClaudeModelsProxy(self.real_client)
        else:
            self.models = ClaudeModelsProxy(None)


client = ClaudeClientProxy()
