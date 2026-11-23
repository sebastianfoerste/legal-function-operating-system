import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

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


# The agent ships what git tracks or would add. `git ls-files` with these options lists both,
# by their path under the directory it runs in, and leaves out what a .gitignore or the
# machine's own exclude file names, such as a developer's .vscode/mcp.json. NUL ends each path.
GIT_LISTING = ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z")
# A hook or a wrapper script can export these to point git at another repository, index or
# object store. The question is about the checkout this directory is in, so git is asked
# without them.
GIT_REPOSITORY_VARIABLES = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
    }
)
# Where git cannot say, every directory is walked, hidden or not, except the ones a tool
# fills on the machine it runs on: version control data, virtual environments, installed
# packages, tool caches and the local pilot store. The walk cannot tell which files in
# them are shipped, and on a developer's machine they hold many that are not. The parent
# repository's test of the same thing, tests/test_research_docs.py, has its own copy of
# these names and functions and a test that the copies are the same.
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
# Which search answered. Git and the walk do not find the same files: the walk also finds a
# file git ignores, and it does not find a file git tracks inside a machine-local directory.
# So the search says which of them answered, and a guard that finds a file passes that on.
GIT_ANSWERED = "git listed the files it tracks or would add here"
GIT_NOT_ASKED = (
    "git could not be asked here (it is not installed, this is no checkout, or it refused, "
    "as its ownership check does for a checkout that belongs to another user), so every "
    "directory outside the machine-local ones was walked; a file that git ignores is found "
    "that way too"
)
GIT_LISTED_NOTHING = (
    "git listed no file here, so every directory outside the machine-local ones was walked; "
    "a file that git ignores is found that way too"
)


def _git(root: Path, command: Sequence[str]) -> bytes | None:
    """What a git command prints when run in ``root``, or None if it cannot run or fails."""

    environment = {
        name: value for name, value in os.environ.items() if name not in GIT_REPOSITORY_VARIABLES
    }
    try:
        done = subprocess.run(command, cwd=root, env=environment, capture_output=True, check=False)
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def _walked(root: Path) -> list[str]:
    """Every file under ``root`` outside the machine-local directories, by its path."""

    found: list[str] = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in MACHINE_LOCAL_DIRECTORIES]
        found += [Path(directory, name).relative_to(root).as_posix() for name in files]
    return found


def _files_named(
    root: Path, *names: str, listing: Sequence[str] = GIT_LISTING
) -> tuple[list[str], str]:
    """The files with one of these names that ``root`` ships, and which search answered.

    The files are given by their path under ``root``. In a git checkout they are the files
    git tracks or would add under ``root``, whether ``root`` is the repository or a
    directory in it. Where git cannot say, they are the files the walk finds: without a
    checkout, without git, when the command fails, as it does when git's ownership check
    refuses a checkout that belongs to another user, and when it lists nothing at all, as
    it does for a copy of the tree inside a directory that another checkout ignores. The
    second value is GIT_ANSWERED, GIT_NOT_ASKED or GIT_LISTED_NOTHING.
    """

    listed = _git(root, listing)
    if listed:
        paths = [os.fsdecode(path) for path in listed.split(b"\0") if path]
        answered = GIT_ANSWERED
    else:
        paths = _walked(root)
        answered = GIT_NOT_ASKED if listed is None else GIT_LISTED_NOTHING
    return sorted(path for path in paths if path.rsplit("/", 1)[-1] in names), answered


def _require_no_client_configuration(root: Path, listing: Sequence[str] = GIT_LISTING) -> None:
    """Fail if the search finds an ``mcp.json`` or ``.mcp.json`` under ``root``.

    The message names the files and says which search answered. A walk that finds no such
    file passes: a copy of the tree without git is a legitimate place to run the suite.
    """

    found, answered = _files_named(root, "mcp.json", ".mcp.json", listing=listing)
    if found:
        raise AssertionError(f"found {', '.join(found)}: {answered}")


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
    # hidden directory included, if git tracks it or would add it. A file git ignores, such
    # as a developer's own .vscode/mcp.json, is not shipped and does not fail. Where git
    # cannot say, every directory is searched except the machine-local ones above. That
    # search also finds an ignored file and misses a tracked one inside a machine-local
    # directory, so a failure says which search answered. The walk alone fails nothing.
    _require_no_client_configuration(AGENT_ROOT)


# A program that stands in for git: this interpreter, started without the site module and
# without its environment variables, so nothing of the machine is printed or read.
PYTHON = (sys.executable, "-I", "-S", "-c")
FAILS_AFTER_A_LISTING = "import sys; sys.stdout.write('docs/notes.md\\0'); sys.exit(128)"
# What git does in a checkout that belongs to another user and is not listed in
# safe.directory: it lists nothing, says why on standard error and exits with 128.
REFUSES_THE_CHECKOUT = (
    "import sys; sys.stderr.write('fatal: detected dubious ownership in repository\\n'); "
    "sys.exit(128)"
)


def _write(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")


def test_in_a_checkout_the_search_asks_git_what_is_shipped(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    # The ignore rules of this checkout decide, not the configuration of the machine: not
    # the user's files, and not the system's (GIT_CONFIG_NOSYSTEM also keeps a file named
    # by GIT_CONFIG_SYSTEM from being read).
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # Nor configuration handed over in the environment. A count of 0 leaves every
    # GIT_CONFIG_KEY_<n> and GIT_CONFIG_VALUE_<n> pair unread, and GIT_CONFIG_PARAMETERS is
    # what `git -c` exports to the commands it starts. Some machines set such variables,
    # for example to rewrite URLs, and a core.excludesFile given that way would decide what
    # git lists here.
    monkeypatch.setenv("GIT_CONFIG_COUNT", "0")
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "")
    # The agent is a directory of the checkout here, as in the parent repository.
    checkout = tmp_path / "checkout"
    agent = checkout / "agent"
    _write(
        agent,
        "README.md",
        "docs/.mcp.json",
        "docs/mcp.json.txt",
        "runtime/mcp.json",
        ".idea/.mcp.json",
        ".vscode/mcp.json",
        ".cursor/mcp.json",
        "node_modules/package/mcp.json",
    )
    _write(checkout, "mcp.json", "plugin/.mcp.json")
    (agent / ".gitignore").write_text(".idea/\n.vscode/\n", encoding="utf-8")
    # Each command names its directory itself, so the set-up can only write under tmp_path.
    # The checkout starts without the machine's template, which could bring ignore rules.
    for directory, arguments in (
        (checkout, ("init", "--quiet", "--template=")),
        (checkout, ("add", "mcp.json", "plugin", "agent/README.md")),
        (agent, ("add", ".gitignore", "docs", "runtime")),
        # Tracked although its directory is ignored.
        (agent, ("add", "--force", ".idea/.mcp.json")),
    ):
        assert _git(directory, ("git", "-C", str(directory), *arguments)) is not None, arguments

    shipped = [
        ".cursor/mcp.json",  # untracked and not ignored: git would add it
        ".idea/.mcp.json",
        "docs/.mcp.json",
        "node_modules/package/mcp.json",  # git decides here, not the list of names
        "runtime/mcp.json",
    ]
    assert _files_named(agent, "mcp.json", ".mcp.json") == (shipped, GIT_ANSWERED)
    # The agent is the repository itself in a standalone export.
    assert _files_named(checkout, "mcp.json", ".mcp.json") == (
        sorted([*(f"agent/{path}" for path in shipped), "mcp.json", "plugin/.mcp.json"]),
        GIT_ANSWERED,
    )
    # Variables that point git somewhere else change nothing. With an object store that
    # does not exist, git would not find the checkout at all.
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere.git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "elsewhere.index"))
    monkeypatch.setenv("GIT_COMMON_DIR", str(tmp_path / "elsewhere.git"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(tmp_path / "elsewhere.git" / "objects"))
    assert _files_named(agent, "mcp.json", ".mcp.json") == (shipped, GIT_ANSWERED)
    # A directory in no checkout: git is not allowed to look above it, says so, and the walk
    # answers. Nothing is ignored there, and the machine-local directories are left out.
    plain = tmp_path / "plain"
    _write(plain, ".vscode/mcp.json", "node_modules/package/mcp.json")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    assert _git(plain, GIT_LISTING) is None
    assert _files_named(plain, "mcp.json", ".mcp.json") == ([".vscode/mcp.json"], GIT_NOT_ASKED)


def test_without_git_the_search_walks_all_but_the_machine_local_directories(tmp_path):
    tree = tmp_path / "tree"
    _write(
        tree,
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
    # Git is taken away by the command, so this does not need a machine without git: a
    # program that does not exist, one that fails with git's exit status after it listed a
    # file, one that refuses as git's ownership check does, and one that lists nothing. The
    # search says in each case that the walk answered, and why.
    walked = [
        ".cursor/mcp.json",
        ".mcp.json",
        ".vscode/mcp.json",
        "docs/.hidden/.mcp.json",
        "mcp.json",
    ]
    for case, listing, answered in (
        (
            "no such program",
            (str(tmp_path / "git-is-not-installed"), *GIT_LISTING[1:]),
            GIT_NOT_ASKED,
        ),
        ("fails after a listing", (*PYTHON, FAILS_AFTER_A_LISTING), GIT_NOT_ASKED),
        ("refuses the checkout", (*PYTHON, REFUSES_THE_CHECKOUT), GIT_NOT_ASKED),
        ("lists nothing", (*PYTHON, ""), GIT_LISTED_NOTHING),
    ):
        found = _files_named(tree, "mcp.json", ".mcp.json", listing=listing)
        assert found == (walked, answered), case
    # What a reader of a failing guard is told when the walk answered.
    for sentence in (GIT_NOT_ASKED, GIT_LISTED_NOTHING):
        assert "so every directory outside the machine-local ones was walked" in sentence
        assert "a file that git ignores is found that way too" in sentence
    assert GIT_NOT_ASKED.startswith("git could not be asked here (")
    assert "its ownership check" in GIT_NOT_ASKED and "walked" not in GIT_ANSWERED


def test_a_guard_that_finds_a_file_says_which_search_answered(tmp_path):
    # Git and the walk do not find the same files, so a failure names the search. Here git
    # refuses as its ownership check does, and the walk finds a file that the agent's own
    # .gitignore leaves out where git answers.
    refused = (*PYTHON, REFUSES_THE_CHECKOUT)
    tree = tmp_path / "tree"
    _write(tree, "README.md", ".vscode/mcp.json", "node_modules/package/mcp.json")
    with pytest.raises(AssertionError) as failure:
        _require_no_client_configuration(tree, refused)
    assert str(failure.value) == f"found .vscode/mcp.json: {GIT_NOT_ASKED}"
    # The walk alone fails nothing: a copy of the tree without git, or one git refuses to
    # answer for, passes while the walk finds no such file in it. The file under
    # node_modules is still there, and the walk does not look there.
    (tree / ".vscode" / "mcp.json").unlink()
    _require_no_client_configuration(tree, refused)
    _require_no_client_configuration(tree, (str(tmp_path / "git-is-not-installed"), "ls-files"))
    # Where git answers, the message says so. A command that lists two such files stands in.
    lists_two = "import sys; sys.stdout.write('docs/mcp.json\\0README.md\\0.mcp.json\\0')"
    with pytest.raises(AssertionError) as failure:
        _require_no_client_configuration(tree, (*PYTHON, lists_two))
    assert str(failure.value) == f"found .mcp.json, docs/mcp.json: {GIT_ANSWERED}"


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
