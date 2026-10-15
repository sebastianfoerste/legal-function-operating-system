"""The Pages site and the Markdown docs must not ship broken links."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


links = _script("check_site_links")
site_builder = _script("build_site")


class BuiltSiteTest(unittest.TestCase):
    def test_built_site_has_no_broken_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            site_builder.build(site)
            problems, _ = links.check_site(site)
        self.assertEqual(problems, [])

    def test_dpa_card_points_at_the_bundled_agreements(self) -> None:
        hrefs = {title: href for title, href, _blurb, _kind in site_builder.CARDS}
        target = hrefs["DPA clause review"].split("/blob/main/", 1)[1]
        self.assertTrue((ROOT / target).is_file(), target)

    def test_project_markdown_has_no_broken_links(self) -> None:
        self.assertEqual(links.check_markdown(links.markdown_files(), site=Path("/nonexistent")), [])


class CheckerTest(unittest.TestCase):
    def test_broken_repository_and_relative_links_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "ok.html").write_text("<p>ok</p>", encoding="utf-8")
            (site / "index.html").write_text(
                '<a href="ok.html">ok</a>'
                '<a href="missing.html">missing</a>'
                f'<a href="{links.REPO_URL}/blob/main/README.md">readme</a>'
                f'<a href="{links.REPO_URL}/blob/main/data/dpa_documents.json">old dpa link</a>'
                '<a href="#here">anchor</a>'
                '<a href="https://example.com/">external</a>',
                encoding="utf-8",
            )
            problems, external = links.check_site(site)
        self.assertEqual(external, 1)
        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(any("missing.html" in problem for problem in problems))
        self.assertTrue(any("data/dpa_documents.json" in problem for problem in problems))
        self.assertTrue(any("#here" in problem for problem in problems))

    def test_markdown_files_and_heading_anchors_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "guide.md").write_text(
                "# Guide\n\n## Art. 28 GDPR / DSGVO (AVV)\n\n## Repeat\n\n## Repeat\n",
                encoding="utf-8",
            )
            page = root / "index.md"
            page.write_text(
                "[good](guide.md#art-28-gdpr--dsgvo-avv)\n"
                "[second heading](guide.md#repeat-1)\n"
                "[bad anchor](guide.md#nope)\n"
                "[bad file](nope.md)\n"
                "```\n[inside a fence](ignored.md)\n```\n"
                "`[inline code](ignored.md)`\n",
                encoding="utf-8",
            )
            problems = links.check_markdown([page], root=root, site=root / "site")
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("#nope", problems[0])
        self.assertIn("nope.md", problems[1])

    def test_slug_matches_the_readme_anchor_into_modules(self) -> None:
        heading = "DPA clause review (AVV / Auftragsverarbeitungsvertrag, Art. 28 GDPR / DSGVO)"
        self.assertEqual(
            links.github_slug(heading),
            "dpa-clause-review-avv--auftragsverarbeitungsvertrag-art-28-gdpr--dsgvo",
        )


if __name__ == "__main__":
    unittest.main()
