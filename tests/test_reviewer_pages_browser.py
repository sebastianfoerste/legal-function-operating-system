"""The reviewer pages on the shared tokens, in a real browser.

Opens the published control tower and RaaS deal room, and a freshly rendered knowledge
portal, from files at phone width in light and dark mode. Each page must fit the
phone without sideways scroll, follow the colour scheme, load nothing from the
network, let the keyboard reach every scrolling table, and print in the light palette
even when the reader uses dark mode. Chromium makes a scroller with no focusable content
focusable by itself, so the test also checks that the focus came from ``tabindex="0"``.

Runs a short Node Playwright script. It is skipped when Node, its Playwright package
or a Chromium build is not installed, so ``make test`` does not need a browser. With
``REQUIRE_BROWSER_TESTS=1`` (set in the CI agent job, which installs Playwright) that
skip becomes a failure. axe is not used here: it is not a repository dependency.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from legal_function_os.collaboration_workspace import build_collaboration_workspace, render_portal
from legal_function_os.design_tokens import TOKENS_CSS

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = {
    "control tower": ROOT / "examples" / "legal-outcome-control-tower.html",
    "deal room": ROOT / "examples" / "raas-deal-room.html",
}
UNAVAILABLE = 3
REQUIRE_BROWSER_TESTS = "REQUIRE_BROWSER_TESTS"

SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const out = {};
  for (const file of process.argv.slice(2)) {
    const result = { requests: [], errors: [] };
    for (const scheme of ["light", "dark"]) {
      for (const width of [320, 390]) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
        const page = await context.newPage();
        page.on("request", (r) => { if (!r.url().startsWith("file://")) result.requests.push(r.url()); });
        page.on("pageerror", (e) => result.errors.push(e.message));
        await page.goto("file://" + file);
        const key = scheme + "-" + width;
        result["sideways-" + key] = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        result["bg-" + key] = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
        if (width === 390) {
          // Tab through the page and note which scrolling tables take focus, and how
          // the focus ring looks on them. Chromium can focus a scroller by itself (and
          // reports tabIndex -1 for it), so note which ones lack tabindex="0".
          const regions = await page.locator(".table-scroll").count();
          const reached = new Set();
          const implicit = new Set();
          const rings = [];
          for (let i = 0; i < 80 && reached.size < regions; i += 1) {
            await page.keyboard.press("Tab");
            const hit = await page.evaluate(() => {
              const all = [...document.querySelectorAll(".table-scroll")];
              const index = all.indexOf(document.activeElement);
              if (index < 0) return null;
              const style = getComputedStyle(document.activeElement);
              return { index, explicit: document.activeElement.getAttribute("tabindex") === "0", ring: style.outlineStyle + " " + style.outlineWidth, scrolls: document.activeElement.scrollWidth > document.activeElement.clientWidth };
            });
            if (hit) {
              reached.add(hit.index); rings.push(hit.ring); result["scrolls-" + hit.index] = hit.scrolls;
              if (!hit.explicit) implicit.add(hit.index);
            }
          }
          result["regions-" + scheme] = regions;
          result["reached-" + scheme] = reached.size;
          result["implicit-" + scheme] = implicit.size;
          result["rings-" + scheme] = [...new Set(rings)];
        }
        if (scheme === "dark" && width === 390) {
          await page.emulateMedia({ media: "print", colorScheme: "dark" });
          result.printInk = await page.evaluate(() => getComputedStyle(document.body).color);
          result.printBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
        }
        await context.close();
      }
    }
    out[file] = result;
  }
  await browser.close();
  console.log(JSON.stringify(out));
})();
"""


def _light(token: str) -> str:
    """A light-theme token as the rgb() string a browser reports."""

    value = re.search(rf"{token}:#([0-9a-f]{{6}})", TOKENS_CSS.split("@media", 1)[0])
    assert value is not None, token
    red, green, blue = (int(value.group(1)[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({red}, {green}, {blue})"


def run_pages(paths: list[Path]) -> dict | None:
    """The browser run's results per page, or None when no browser is available."""

    if shutil.which("node") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "reviewer-pages.cjs"
        script.write_text(SCRIPT, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script), *map(str, paths)],
            capture_output=True, text=True, timeout=300, env=os.environ.copy(),
        )
    if result.returncode == UNAVAILABLE:
        return None
    if result.returncode != 0:
        raise AssertionError(f"browser script failed: {result.stderr}")
    return json.loads(result.stdout.split("\n")[0])


class ReviewerPagesBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        requests = json.loads(
            (ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json").read_text(encoding="utf-8")
        )
        portal = build_collaboration_workspace(requests, "Q2 2026 (synthetic)")["knowledge_portal"]
        cls.pages = {
            **PUBLISHED,
            "knowledge portal": render_portal(portal, Path(cls.tmp.name) / "knowledge-portal.html"),
        }
        try:
            out = run_pages(list(cls.pages.values()))
        except BaseException:
            cls.tmp.cleanup()
            raise
        if out is None:
            cls.tmp.cleanup()
            if os.environ.get(REQUIRE_BROWSER_TESTS) == "1":
                raise AssertionError("REQUIRE_BROWSER_TESTS=1 but Node, Playwright or Chromium is missing")
            raise unittest.SkipTest("Node, Playwright or Chromium is not installed")
        cls.out = {name: out[str(path)] for name, path in cls.pages.items()}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_pages_fit_a_phone_and_load_nothing(self) -> None:
        for name, result in self.out.items():
            with self.subTest(page=name):
                for key in ("light-320", "light-390", "dark-320", "dark-390"):
                    self.assertEqual(result["sideways-" + key], 0, key)
                self.assertEqual(result["requests"], [])
                self.assertEqual(result["errors"], [])

    def test_pages_follow_the_colour_scheme(self) -> None:
        for name, result in self.out.items():
            with self.subTest(page=name):
                self.assertEqual(result["bg-light-390"], _light("--bg"))
                self.assertNotEqual(result["bg-dark-390"], result["bg-light-390"])

    def test_the_keyboard_reaches_every_scrolling_table(self) -> None:
        for name in PUBLISHED:
            result = self.out[name]
            with self.subTest(page=name):
                for scheme in ("light", "dark"):
                    self.assertGreater(result["regions-" + scheme], 0)
                    self.assertEqual(result["reached-" + scheme], result["regions-" + scheme])
                    # Reached through tabindex="0", not only because Chromium focuses a
                    # scroller with nothing focusable inside by itself.
                    self.assertEqual(result["implicit-" + scheme], 0, "focused without tabindex=0")
                    self.assertEqual(result["rings-" + scheme], ["solid 3px"])
                # At 390px the wide tables do scroll, inside their focusable region.
                self.assertTrue(result["scrolls-0"])

    def test_pages_print_in_the_light_palette_in_dark_mode(self) -> None:
        for name, result in self.out.items():
            with self.subTest(page=name):
                self.assertEqual(result["printInk"], _light("--ink"))
                self.assertEqual(result["printBg"], _light("--bg"))


if __name__ == "__main__":
    unittest.main()
