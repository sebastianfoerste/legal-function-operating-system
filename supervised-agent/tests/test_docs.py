import os
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


def test_readme_local_links_exist():
    # Every relative link, not only those to Markdown files: the README's file list links
    # sources, directories and examples, and a removed file must not stay listed.
    readme = (AGENT_ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)\s]+)\)", readme)
    local = [target for target in targets if not re.match(r"[a-z][a-z0-9+.-]*:|#", target)]

    assert len(local) > 40, local
    for link in local:
        target = AGENT_ROOT / link.split("#", 1)[0]
        assert target.exists(), f"README link target does not exist: {link}"


def test_readme_counts_and_lists_every_mcp_style_tool():
    text = (AGENT_ROOT / "README.md").read_text(encoding="utf-8")
    names = [tool["name"] for tool in legal_ops_mcp_manifest()["tools"]]
    words = re.findall(r"\b(\w+) (?:local )?MCP-style tools\b", " ".join(text.split()))
    counts = [NUMBER_WORDS.get(word, word) for word in words if word.lower() != "local"]
    assert counts and set(counts) == {len(names)}, words
    for name in names:
        assert f"- `{name}`: " in text, name


# Directories a tool fills on the machine it runs on: version control data, virtual
# environments, installed packages, tool caches and the local pilot store. Nothing in them
# is written for the agent or committed. Every other directory is searched, hidden or not:
# an MCP client reads its project configuration from one, such as .cursor or .vscode.
# The parent repository's test of the same thing, tests/test_research_docs.py, has this list.
MACHINE_LOCAL_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".pilot",
        ".playwright-mcp",
    }
)


def _files_named(root: Path, *names: str) -> list[str]:
    """Files with one of these names anywhere under ``root``, hidden directories included."""

    found: list[str] = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in MACHINE_LOCAL_DIRECTORIES]
        found += [
            Path(directory, name).relative_to(root).as_posix() for name in files if name in names
        ]
    return sorted(found)


def test_readme_says_how_the_tools_are_reached_and_that_no_mcp_client_can():
    # The tools are served over HTTP by the runtime: the README names the command and the
    # two endpoints (tests/test_runtime_agent.py requests them as the README gives them),
    # and calls nothing here an MCP server or an MCP client configuration.
    text = " ".join((AGENT_ROOT / "README.md").read_text(encoding="utf-8").split())
    assert (
        "`python -m runtime_agent.app`: an HTTP server on a loopback address, "
        "not an MCP stdio server"
    ) in text
    assert (AGENT_ROOT / "runtime_agent" / "app.py").is_file()
    assert "`GET /mcp/manifest`" in text and "`POST /tools/call`" in text
    assert (
        "The agent ships no MCP client configuration (no `mcp.json` or `.mcp.json`), "
        "because it has no MCP stdio server for a client to start."
    ) in text
    assert "MCP server configuration" not in text
    assert "](mcp.json)" not in text


def test_the_agent_ships_no_mcp_client_configuration():
    # An MCP client reads such a file and starts the stdio server it names. The agent has
    # none: the mcp.json it carried until 2026-11-20 started the HTTP runtime, which no MCP
    # client can use. A file that comes back fails here, wherever it is in the agent, a
    # hidden directory included. Only the machine-local directories above are not searched.
    assert _files_named(AGENT_ROOT, "mcp.json", ".mcp.json") == []


def test_the_search_for_a_client_configuration_reads_hidden_directories(tmp_path):
    names = (
        "mcp.json",
        ".mcp.json",
        ".cursor/mcp.json",
        ".vscode/mcp.json",
        "docs/.hidden/.mcp.json",
        "docs/mcp.json.txt",
        "docs/notes.md",
        *(f"{skipped}/mcp.json" for skipped in sorted(MACHINE_LOCAL_DIRECTORIES)),
        "src/__pycache__/.mcp.json",
    )
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    assert _files_named(tmp_path, "mcp.json", ".mcp.json") == [
        ".cursor/mcp.json",
        ".mcp.json",
        ".vscode/mcp.json",
        "docs/.hidden/.mcp.json",
        "mcp.json",
    ]


def test_features_lists_only_files_that_exist():
    text = (AGENT_ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    listed = re.findall(r"^\d+\. `([^`]+)`$", text, re.M)
    assert len(listed) > 15, listed
    for name in listed:
        assert (AGENT_ROOT / name).is_file(), f"FEATURES.md lists a missing file: {name}"
    # The tool surface names the module that serves the tools, as the README does.
    surface = text.split("## MCP-Style Tool Surface", 1)[1].split("\n## ", 1)[0]
    assert "`runtime_agent/app.py`" in surface
    assert "`GET /mcp/manifest`" in surface and "`POST /tools/call`" in surface


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
