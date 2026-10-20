import importlib.util
import re
import unittest
from pathlib import Path

from legal_function_os.design_tokens import TOKENS_CSS

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"(--[a-z-]+):(#[0-9a-f]{6})")
AGENT_COPY = ROOT / "supervised-agent" / "src" / "pilot" / "design_tokens.py"


def _contrast(foreground: str, background: str) -> float:
    def luminance(colour: str) -> float:
        channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _themes() -> list[dict[str, str]]:
    return [dict(TOKEN.findall(block)) for block in TOKENS_CSS.split("@media")]


class DesignTokenTests(unittest.TestCase):
    def test_agent_copy_matches_the_parent_tokens(self) -> None:
        spec = importlib.util.spec_from_file_location("agent_design_tokens", AGENT_COPY)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.TOKENS_CSS, TOKENS_CSS)

    def test_tokens_load_no_font_or_remote_resource(self) -> None:
        for forbidden in ("http", "url(", "@import", "@font-face"):
            self.assertNotIn(forbidden, TOKENS_CSS)

    def test_both_themes_meet_wcag_aa_contrast(self) -> None:
        backgrounds = ("--bg", "--surface", "--panel", "--ok-bg", "--warn-bg", "--bad-bg")
        for theme in _themes():
            for text in ("--ink", "--muted", "--accent", "--ok", "--warn", "--bad"):
                for background in backgrounds:
                    ratio = _contrast(theme[text], theme[background])
                    self.assertGreaterEqual(ratio, 4.5, f"{text} on {background}: {ratio:.2f}")
            for edge in ("--focus", "--pill-line"):
                for background in ("--bg", "--surface"):
                    self.assertGreaterEqual(_contrast(theme[edge], theme[background]), 3.0)
            self.assertGreaterEqual(_contrast(theme["--on-accent"], theme["--accent"]), 4.5)


if __name__ == "__main__":
    unittest.main()
