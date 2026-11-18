"""Install instructions name only git or a clone while the package is not on PyPI.

The package is not published (owner decision 9 in docs/research/adaptation-plan.md).
An instruction to install ``legal-function-os`` by name finds nothing on PyPI today,
and would install someone else's code if another party registered the name. The
owner's release pull request deletes this file together with the README's
"not on PyPI" wording.
"""

from __future__ import annotations

import re
import unittest
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "legal-function-os"
INSTALL = re.compile(r"\b(?:pip|pipx|uv\s+pip|uv\s+tool)\s+install\b|\buvx\b")


def user_facing_files() -> list[Path]:
    """Files that tell people how to install or run the package.

    The ADRs, the research notes and the changelog are records and are not scanned.
    """

    files = [ROOT / name for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md")]
    files += sorted((ROOT / "docs").glob("*.md"))
    files += sorted(path for path in (ROOT / "plugins").rglob("*") if path.is_file())
    files += sorted((ROOT / ".claude-plugin").glob("*.json"))
    files += sorted((ROOT / "src" / "legal_function_os").rglob("*.py"))
    files.append(ROOT / "scripts" / "build_site.py")
    return files


def logical_lines(text: str) -> Iterator[tuple[int, str]]:
    """Each line with its number; a line ending in a backslash continues on the next."""

    pending, start = "", 0
    for number, line in enumerate(text.splitlines(), start=1):
        if not pending:
            start = number
        if line.rstrip().endswith("\\"):
            pending += line.rstrip().rstrip("\\") + " "
            continue
        yield start, pending + line
        pending = ""
    if pending:
        yield start, pending


class InstallInstructionTests(unittest.TestCase):
    def test_no_install_by_name_while_not_on_pypi(self):
        offenders, from_git = [], 0
        for path in user_facing_files():
            for number, line in logical_lines(path.read_text(encoding="utf-8")):
                if not (INSTALL.search(line) and PACKAGE in line):
                    continue
                if "git+" in line:
                    from_git += 1
                else:
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "the package is not on PyPI: install it from git or a clone")
        # The scan must see the git commands the README and the docs do give.
        self.assertGreaterEqual(from_git, 3)

    def test_readme_says_not_on_pypi(self):
        self.assertIn("not on PyPI", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
