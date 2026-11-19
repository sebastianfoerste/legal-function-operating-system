import json
import re
from pathlib import Path

from src.mcp_tools import legal_ops_mcp_manifest

AGENT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = Path("README.md")
NUMBER_WORDS = {
    word: number
    for number, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve".split()
    )
}


def test_readme_uses_current_project_name():
    readme = README_PATH.read_text(encoding="utf-8")

    # The component was renamed when it was consolidated into the legal function
    # operating system; the standalone legal-ops-agent repository is archived.
    assert "# supervised-agent" in readme
    assert "LegalAgent" not in readme


def test_readme_local_markdown_links_exist():
    readme = README_PATH.read_text(encoding="utf-8")
    markdown_links = re.findall(r"\[[^\]]+\]\(([^)]+\.md)\)", readme)

    for link in markdown_links:
        assert Path(link).exists(), f"README link target does not exist: {link}"


def test_readme_counts_and_lists_every_mcp_style_tool():
    text = (AGENT_ROOT / "README.md").read_text(encoding="utf-8")
    names = [tool["name"] for tool in legal_ops_mcp_manifest()["tools"]]
    words = re.findall(r"\b(\w+) (?:local )?MCP-style tools\b", " ".join(text.split()))
    counts = [NUMBER_WORDS.get(word, word) for word in words if word.lower() != "local"]
    assert counts and set(counts) == {len(names)}, words
    for name in names:
        assert f"- `{name}`: " in text, name


def test_readme_says_what_mcp_json_starts():
    # mcp.json starts the HTTP canary, not an MCP stdio server; the README must not call
    # it an MCP server configuration.
    text = " ".join((AGENT_ROOT / "README.md").read_text(encoding="utf-8").split())
    [server] = json.loads((AGENT_ROOT / "mcp.json").read_text(encoding="utf-8"))[
        "mcpServers"
    ].values()
    command = " ".join([server["command"], *server["args"]])
    assert command == "python -m runtime_agent.app"
    assert f"`{command}`: an HTTP server on a loopback address, not an MCP stdio server" in text
    assert "MCP server configuration" not in text


def test_contributing_names_only_make_targets_that_exist():
    makefile = (AGENT_ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z][a-z-]*):", makefile, re.M))
    text = (AGENT_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    named = re.findall(r"^make ([a-z][a-z-]*)", text, re.M)
    assert named and set(named) <= targets, set(named) - targets
    assert "scenario-docs" in text
    # The worked example has a regenerator, and a test requires the committed copy to be
    # current (tests/test_evidence_record.py), so the guide names it.
    assert "python -m src.pilot.evidence.example" in text
    assert "nothing regenerates" not in " ".join(text.split())
