#!/usr/bin/env python3
"""Fail on broken links in the built Pages site and the project's Markdown docs.

The check is offline. It resolves every link that points into this repository or
the published site against the local checkout:

- relative links in ``site/*.html`` must name a file in ``site/``;
- links to ``github.com/<owner>/<repo>/blob|tree/main/<path>`` must name a path
  in the working tree;
- links to the published Pages URL must name a file in ``site/``;
- relative links and ``#anchors`` in Markdown must name an existing file and a
  heading GitHub would generate an anchor for.

Links to other hosts are counted, not fetched.
"""

from __future__ import annotations

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
REPO_URL = "https://github.com/sebastianfoerste/legal-function-operating-system"
PAGES_URL = "https://sebastianfoerste.github.io/legal-function-operating-system"

# Markdown that belongs to the core project. The supervised agent keeps its own docs.
MARKDOWN_GLOBS = (
    "*.md",
    "docs/**/*.md",
    "contracts/*.md",
    "plugins/**/*.md",
)

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE = re.compile(r"`[^`]*`")
_MD_LINK = re.compile(r"!?\[(?:[^\]\[]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_MD_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_HTML_ANCHOR = re.compile(r"<a\s+(?:name|id)=\"([^\"]+)\"", re.IGNORECASE)


def github_slug(text: str) -> str:
    """Approximate GitHub's heading anchor: lower-case, drop punctuation, hyphenate spaces."""

    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # keep link text only
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def markdown_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        anchors.update(_HTML_ANCHOR.findall(line))
        match = _HEADING.match(line)
        if not match:
            continue
        slug = github_slug(match.group(2))
        seen = counts.get(slug, 0)
        anchors.add(slug if seen == 0 else f"{slug}-{seen}")
        counts[slug] = seen + 1
    return anchors


def markdown_links(path: Path) -> list[tuple[int, str]]:
    links: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        reference = _MD_REFERENCE.match(line)
        if reference:
            links.append((number, reference.group(1)))
            continue
        for target in _MD_LINK.findall(_INLINE_CODE.sub("", line)):
            links.append((number, target))
    return links


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if "id" in values:
            self.ids.add(values["id"])
        for name in ("href", "src"):
            if values.get(name):
                self.links.append(values[name])
        if tag == "meta" and values.get("property", values.get("name", "")) in {
            "og:image",
            "og:url",
            "twitter:image",
        }:
            if values.get("content"):
                self.links.append(values["content"])


def _repo_target(url: str, root: Path) -> tuple[Path, str] | None:
    """Map a link to this repository on github.com to a local path and kind."""

    if url.rstrip("/") == REPO_URL:
        return root, "tree"
    for kind in ("blob", "tree"):
        prefix = f"{REPO_URL}/{kind}/main/"
        if url.startswith(prefix):
            return root / unquote(url[len(prefix) :]), kind
    if url.startswith(REPO_URL + "/"):
        # Issues, actions, releases and similar GitHub pages are not files.
        return None
    return None


def _check_target(
    source: str, raw: str, base_dir: Path, root: Path, site: Path, *, markdown: bool
) -> str | None:
    parts = urlsplit(raw)
    if parts.scheme in {"mailto", "javascript", "data", "tel"}:
        return None
    url = raw.split("#", 1)[0].split("?", 1)[0]
    fragment = unquote(parts.fragment)

    if parts.scheme in {"http", "https"}:
        if url.startswith(REPO_URL):
            mapped = _repo_target(url, root)
            if mapped is None:
                return None
            path, kind = mapped
            if kind == "blob" and not path.is_file():
                return f"{source}: {raw} names a file that does not exist ({path.relative_to(root)})"
            if kind == "tree" and not path.exists():
                return f"{source}: {raw} names a path that does not exist ({path.relative_to(root)})"
            if fragment and path.suffix == ".md" and path.is_file():
                if fragment not in markdown_anchors(path):
                    return f"{source}: {raw} names a missing heading anchor #{fragment}"
            return None
        if url.startswith(PAGES_URL):
            relative = url[len(PAGES_URL) :].lstrip("/") or "index.html"
            if not (site / unquote(relative)).is_file():
                return f"{source}: {raw} is not a file in the built site ({relative})"
            return None
        return None  # external host: counted, not fetched

    if not url:
        return None  # same-page anchors are checked by the caller

    target = (base_dir / unquote(url)).resolve()
    if markdown:
        if not target.exists():
            return f"{source}: {raw} does not exist"
        if fragment and target.suffix == ".md" and target.is_file():
            if fragment not in markdown_anchors(target):
                return f"{source}: {raw} names a missing heading anchor #{fragment}"
        return None
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        return f"{source}: {raw} is not a file in the built site"
    return None


def check_site(site: Path = SITE, root: Path = ROOT) -> tuple[list[str], int]:
    """Return (problems, external link count) for every HTML page in ``site``."""

    if not (site / "index.html").is_file():
        return [f"{site} has no index.html; build the site first (make site)"], 0
    problems: list[str] = []
    external = 0
    for page in sorted(site.rglob("*.html")):
        collector = _LinkCollector()
        collector.feed(page.read_text(encoding="utf-8"))
        name = str(page.relative_to(site))
        for raw in collector.links:
            if raw.startswith("#"):
                if raw[1:] and raw[1:] not in collector.ids:
                    problems.append(f"site/{name}: {raw} is not an id on the page")
                continue
            problem = _check_target(f"site/{name}", raw, page.parent, root, site, markdown=False)
            if problem:
                problems.append(problem)
            elif urlsplit(raw).scheme in {"http", "https"} and not raw.startswith(
                (REPO_URL, PAGES_URL)
            ):
                external += 1
    return problems, external


def markdown_files(root: Path = ROOT) -> list[Path]:
    files: set[Path] = set()
    for pattern in MARKDOWN_GLOBS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def check_markdown(paths: list[Path], root: Path = ROOT, site: Path = SITE) -> list[str]:
    problems: list[str] = []
    for path in paths:
        relative = path.relative_to(root)
        for number, raw in markdown_links(path):
            if raw.startswith("#"):
                if raw[1:] not in markdown_anchors(path):
                    problems.append(f"{relative}:{number}: {raw} is not a heading in this file")
                continue
            if raw.startswith(PAGES_URL) and not (site / "index.html").is_file():
                continue  # the site is checked separately once it is built
            problem = _check_target(
                f"{relative}:{number}", raw, path.parent, root, site, markdown=True
            )
            if problem:
                problems.append(problem)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check site and Markdown links offline.")
    parser.add_argument("--site", type=Path, default=SITE, help="Built site directory.")
    parser.add_argument(
        "--skip-site", action="store_true", help="Check Markdown only (no built site needed)."
    )
    args = parser.parse_args(argv)

    problems: list[str] = []
    external = 0
    if not args.skip_site:
        site_problems, external = check_site(args.site)
        problems.extend(site_problems)
    docs = markdown_files()
    problems.extend(check_markdown(docs, site=args.site))

    if problems:
        print("\n".join(problems))
        print(f"{len(problems)} broken link(s)")
        return 1
    scope = "Markdown" if args.skip_site else "site and Markdown"
    print(
        f"{scope} link check passed ({len(docs)} Markdown files; "
        f"{external} external site links not fetched)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
