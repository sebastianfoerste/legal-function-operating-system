"""Install instructions name only git or a clone while the package is not on PyPI.

The package is not published (owner decision 9 in docs/research/adaptation-plan.md).
An instruction to install ``legal-function-os`` by name finds nothing on PyPI today,
and would install someone else's code if another party registered the name. The
owner's release pull request deletes this file together with the README's
"not on PyPI" wording.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# PyPI treats runs of "-", "_" and "." alike and ignores case (PEP 503), so
# "legal_function_os" and "Legal-Function-OS" name the same project.
PACKAGE = re.compile(r"legal[-_.]+function[-_.]+os", re.IGNORECASE)
INSTALL = re.compile(
    r"\b(?:pip3?|pipx|pipenv|poetry|pdm|conda)\b[^\n]*\b(?:install|add)\b"
    r"|\buv\s+(?:pip\s+install|tool\s+install|add)\b"
    r"|\bpipx\s+run\b|\buvx\b"
)
# Commands that install by name, each of which the scan must catch.
BY_NAME = (
    "pip install legal-function-os",
    "pip3 install legal-function-os",
    "python -m pip install legal_function_os",
    "pipx install Legal-Function-OS",
    "pipx run --spec legal-function-os legal-function-os-mcp",
    "uv add legal-function-os",
    "uv pip install legal.function.os",
    "uv tool install legal-function-os",
    "uvx --from legal-function-os[mcp] legal-function-os-mcp",
    "pipenv install legal-function-os",
    "poetry add legal-function-os",
    "pdm add legal-function-os",
)


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


def json_commands(data: Any) -> Iterator[str]:
    """Each command a JSON config declares, such as an MCP server's, joined with its args.

    In a config file the command and its arguments sit on separate lines, so the line
    scan alone would never see ``uvx`` next to the package it installs.
    """

    if isinstance(data, dict):
        if isinstance(data.get("command"), str):
            args = data.get("args", [])
            yield " ".join([data["command"], *(str(arg) for arg in (args if isinstance(args, list) else [args]))])
        for value in data.values():
            yield from json_commands(value)
    elif isinstance(data, list):
        for value in data:
            yield from json_commands(value)


def install_source(line: str) -> str | None:
    """"git" for a line that installs the package from git, "name" for one by name."""

    if not (INSTALL.search(line) and PACKAGE.search(line)):
        return None
    return "git" if "git+" in line else "name"


def scan(paths: list[Path], root: Path = ROOT) -> tuple[list[str], int]:
    """The install-by-name lines in ``paths``, and how many lines install from git."""

    offenders, from_git = [], 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        found = [(f"{number}", line) for number, line in logical_lines(text)]
        if path.suffix == ".json":
            found += [("command", command) for command in json_commands(json.loads(text))]
        for where, line in found:
            source = install_source(line)
            if source == "git":
                from_git += 1
            elif source == "name":
                offenders.append(f"{path.relative_to(root)}:{where}: {line.strip()}")
    return offenders, from_git


class InstallInstructionTests(unittest.TestCase):
    def test_no_install_by_name_while_not_on_pypi(self):
        offenders, from_git = scan(user_facing_files())
        self.assertEqual(offenders, [], "the package is not on PyPI: install it from git or a clone")
        # The scan must see the git commands the README, the docs and the plugin do give.
        self.assertGreaterEqual(from_git, 4)

    def test_readme_says_not_on_pypi(self):
        self.assertIn("not on PyPI", (ROOT / "README.md").read_text(encoding="utf-8"))


class TripwireTests(unittest.TestCase):
    """The scan fires on each way of installing by name, in a doc and in a plugin config."""

    def test_each_install_by_name_is_caught(self):
        for line in BY_NAME:
            with self.subTest(line=line):
                self.assertEqual(install_source(line), "name")
        git = "pip install 'legal-function-os @ git+https://github.com/sebastianfoerste/legal-function-operating-system'"
        self.assertEqual(install_source(git), "git")
        self.assertIsNone(install_source("pip install -e ."))

    def test_the_plugin_config_is_read_as_json(self):
        path = ROOT / "plugins" / "legal-function-os" / ".mcp.json"
        self.assertIn(path, user_facing_files())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([install_source(command) for command in json_commands(data)], ["git"])
        for server in data["mcpServers"].values():
            server["args"] = ["--python", "3.13", "--from", "legal-function-os[mcp]", "legal-function-os-mcp"]
        self.assertEqual([install_source(command) for command in json_commands(data)], ["name"])

    def test_the_scan_reports_each_offending_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text("```bash\n" + "\n".join(BY_NAME) + "\n```\n", encoding="utf-8")
            config = root / ".mcp.json"
            server = {"command": "uvx", "args": ["--from", "legal-function-os[mcp]", "legal-function-os-mcp"]}
            config.write_text(json.dumps({"mcpServers": {"legal-function-os": server}}, indent=2), encoding="utf-8")
            offenders, from_git = scan([readme, config], root)
        self.assertEqual(len(offenders), len(BY_NAME) + 1)
        self.assertEqual(offenders[-1], ".mcp.json:command: uvx --from legal-function-os[mcp] legal-function-os-mcp")
        self.assertEqual(from_git, 0)


if __name__ == "__main__":
    unittest.main()
