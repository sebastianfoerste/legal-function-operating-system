"""The agent has no external model client and no outbound network client.

The decision path is deterministic and local. A model or network client would be a
separate, reviewed change with its own controls, never a setting.
"""

import ast
import json
import re
from pathlib import Path

from src.mcp_tools import run_tool

AGENT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCES = [
    AGENT_ROOT / "models.py",
    AGENT_ROOT / "master_orchestrator.py",
    *sorted((AGENT_ROOT / "src").rglob("*.py")),
    *sorted((AGENT_ROOT / "runtime_agent").rglob("*.py")),
    *sorted((AGENT_ROOT / "scripts").rglob("*.py")),
]
MODEL_SDKS = {"google-genai", "google-generativeai", "openai", "anthropic", "mistralai", "cohere"}
NETWORK_MODULES = {
    "google",
    "openai",
    "anthropic",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "websockets",
    "urllib.request",
    "http.client",
    "smtplib",
    "ftplib",
}


def _requirement_names(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name = re.split(r"[<>=!~\[; @]", line, maxsplit=1)[0]
            names.add(re.sub(r"[-_.]+", "-", name).lower())
    return names


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            # `from urllib import request` imports urllib.request, so count both names.
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_runtime_requirements_carry_no_model_sdk():
    for name in ("requirements.in", "requirements.txt"):
        found = _requirement_names(AGENT_ROOT / name) & MODEL_SDKS
        assert not found, f"{name} pins a model SDK: {sorted(found)}"


def test_requirement_names_are_compared_in_their_normalised_form(tmp_path):
    # pip treats "-", "_" and "." alike and ignores case (PEP 503), so every spelling counts.
    requirements = tmp_path / "requirements.in"
    requirements.write_text(
        "Google.GenAI>=1.63.0\ngoogle_generativeai\nOpenAI; python_version >= '3.10'\n"
        "pydantic==2.12.5  # a comment\n",
        encoding="utf-8",
    )
    assert _requirement_names(requirements) == {
        "google-genai",
        "google-generativeai",
        "openai",
        "pydantic",
    }


def test_no_runtime_module_imports_a_model_or_network_client():
    for path in RUNTIME_SOURCES:
        for module in _imported_modules(path):
            top = module.split(".")[0]
            assert (
                module not in NETWORK_MODULES and top not in NETWORK_MODULES
            ), f"{path.relative_to(AGENT_ROOT)} imports {module}"


def test_no_external_model_switch_is_offered():
    manifest = json.loads((AGENT_ROOT / "mcp.json").read_text(encoding="utf-8"))
    for server in manifest["mcpServers"].values():
        assert "LEGAL_AGENT_EXTERNAL_MODEL_ENABLED" not in server.get("env", {})
    for path in RUNTIME_SOURCES:
        assert "LEGAL_AGENT_EXTERNAL_MODEL_ENABLED" not in path.read_text(encoding="utf-8")


def test_the_source_boundary_says_nothing_is_processed_externally():
    # Not "disabled by default": there is no setting that could enable it.
    assert run_tool("legal.sources.list", {})["external_processing"] == "none"


def test_no_environment_file_is_offered():
    # The removed .env.example held the external model's settings; none is tracked or
    # excepted from the ignore rules, so no file invites a key.
    root = AGENT_ROOT.parent
    assert not (AGENT_ROOT / ".env.example").exists()
    assert not (root / ".env.example").exists()
    for path in (root / ".gitignore", AGENT_ROOT / ".gitignore"):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert not [line for line in lines if line.startswith("!") and ".env" in line], path
