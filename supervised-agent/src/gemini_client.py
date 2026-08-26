from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from src.intelligence_core import apply_language_standards

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised only when optional SDK is absent
    genai = None  # type: ignore[assignment]


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


class GeminiModelsProxy:
    """Proxy for optional Gemini calls with deterministic local fallback."""

    def __init__(self, real_models: Any | None = None):
        self.real_models = real_models

    def generate_content(self, model: str, contents: str, **kwargs: Any) -> TextResponse:
        if self.real_models:
            try:
                response = self.real_models.generate_content(
                    model=model, contents=contents, **kwargs
                )
                if response and response.text:
                    return TextResponse(apply_language_standards(response.text))
            except Exception as exc:  # pragma: no cover - depends on external SDK state
                print(f"[gemini_client] External model unavailable: {exc}")
        return TextResponse(apply_language_standards(generate_mock_response(model, contents)))


class GeminiClientProxy:
    """Small wrapper that keeps external model use optional."""

    def __init__(self) -> None:
        google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        external_enabled = os.getenv("LEGAL_AGENT_EXTERNAL_MODEL_ENABLED", "").lower() == "true"
        self.real_client = None

        if genai is not None and google_api_key and external_enabled:
            self.real_client = genai.Client(api_key=google_api_key)
            self.models = GeminiModelsProxy(self.real_client.models)
        else:
            self.models = GeminiModelsProxy(None)


client = GeminiClientProxy()
