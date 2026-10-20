"""One colour and type token set for the generated HTML pages.

Plain CSS custom properties, light and dark, with no font to load. The supervised
agent keeps a byte-identical copy in ``supervised-agent/src/pilot/design_tokens.py``
because it may not import this package outside the pilot bridge; ``tests/
test_design_tokens.py`` fails when the two drift. See docs/adr/0001-design-tokens.md.

Contrast, checked against WCAG 2.2 AA: every text token is at least 4.5:1 on
``--bg``, ``--surface``, ``--panel`` and the three state backgrounds; ``--focus``
and ``--pill-line`` are at least 3:1 on ``--bg`` and ``--surface``, in both themes.
"""

TOKENS_CSS = """:root{color-scheme:light dark;
--bg:#fbf9f7;--surface:#ffffff;--panel:#f5f0ec;--ink:#211d1c;--muted:#6e6462;
--line:#e2dad4;--pill-line:#8f847f;--accent:#8a2d2b;--accent-soft:#f2e4e2;--on-accent:#ffffff;
--ok:#2f6b3a;--ok-bg:#eaf3ec;--warn:#8a4b08;--warn-bg:#fbf1e4;--bad:#a12622;--bad-bg:#fbeceb;
--focus:#8a2d2b;
--font:system-ui,-apple-system,"Segoe UI",sans-serif;--font-head:Georgia,"Times New Roman",serif;
--font-mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{
--bg:#191413;--surface:#221c1a;--panel:#2a2321;--ink:#ede7e4;--muted:#a89c98;
--line:#38302d;--pill-line:#857873;--accent:#d97d75;--accent-soft:#3a2523;--on-accent:#191413;
--ok:#7ccf8e;--ok-bg:#1d2a20;--warn:#e8b06a;--warn-bg:#2e2416;--bad:#f08a84;--bad-bg:#33201f;
--focus:#e8a09a}}
"""
