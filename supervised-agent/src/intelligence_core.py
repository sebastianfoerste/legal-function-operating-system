from __future__ import annotations

import re

BANNED_WORDS = [
    "delve",
    "leverage",
    "unleash",
    "tapestry",
    "testament",
    "game changer",
    "transformative journey",
    "leverage synergies",
    "in today's fast-paced world",
    "ready for the future of",
    "excited to share",
]


def apply_language_standards(text: str) -> str:
    """Replace promotional filler with plain legal-operations language."""

    replacements = {
        r"\bleverage synergies\b": "coordinate work",
        r"\bdelve\b": "review",
        r"\bleverage\b": "use",
        r"\bunleash\b": "release",
        r"\btapestry\b": "structure",
        r"\btestament\b": "evidence",
        r"\bgame changer\b": "material change",
        r"\btransformative journey\b": "implementation",
        r"\bin today's fast-paced world\b": "in current practice",
        r"\bready for the future of\b": "prepared for",
        r"\bexcited to share\b": "sharing",
    }

    cleaned = text
    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def apply_2026_standards(text: str) -> str:
    """Backward-compatible alias used by older tests and integrations."""

    return apply_language_standards(text)
