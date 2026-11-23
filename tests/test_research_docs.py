"""The research documents agree with the feature matrix and quote rules by their words.

``docs/research/2026-10-competitive-landscape.md`` states how many products the matrix
holds per ring, how many rows hold no capability data, and lists each product under
"Direct competitors" or "Adjacent products". The matrix,
``docs/research/feature-matrix.csv``, is the record; these tests recompute what the
landscape states from it, so a matrix change that the prose does not follow fails here.
"""

import ast
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research"
NUMBERS = {"three": 3, "twelve": 12}

# The name the landscape uses for each direct matrix row it lists, and the row's product.
DIRECT = {
    "Checkbox": "Checkbox",
    "LawVu": "LawVu",
    "Claude for Legal": "claude-for-legal",
    "Wordsmith": "Wordsmith",
    "Streamline AI": "Streamline AI",
    "Xakia": "Xakia",
    "Tonkean": "Tonkean (LegalWorks)",
    "Bryter": "Bryter",
    "Mitratech": "Mitratech (TAP, TeamConnect)",
    "ServiceNow Legal Service Delivery": "ServiceNow Legal Service Delivery",
    "Sandstone": "Sandstone",
    "DISCO Request": "DISCO Request",
    "Bigle": "Bigle Legal (legal requests module)",
    "Autologyx": "Autologyx",
    "Norton Rose Fulbright front door": (
        "Norton Rose Fulbright Intelligent Legal Front Door (NRF Transform)"
    ),
    "Wolters Kluwer": "Wolters Kluwer ELM (Passport, Legisway, LegalVIEW)",
    "otris": "otris (legal SUITE)",
    "DEPLAW": "DEPLAW (legaldata.tech)",
    "Onit": "Onit",
}
# The same for the adjacent products the landscape names in bold.
ADJACENT = {
    "Flank": "Flank",
    "Josef": "Josef",
    "Eudia": "Eudia",
    "GC AI": "GC AI",
    "Ironclad": "Ironclad",
    "LegalOn": "LegalOn",
    "SpotDraft": "SpotDraft",
    "docassemble": "docassemble",
    "Mike": "Mike",
    "Lavern": "Lavern",
}


def _matrix() -> list[dict[str, str]]:
    with (RESEARCH / "feature-matrix.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _landscape() -> str:
    return (RESEARCH / "2026-10-competitive-landscape.md").read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """The text under a heading, up to the next heading of any level."""

    match = re.search(rf"^#+ {re.escape(heading)}\n(.*?)(?=^#)", text, re.M | re.S)
    assert match, heading
    return match.group(1)


def _bold(text: str) -> list[str]:
    return [" ".join(span.split()) for span in re.findall(r"\*\*(.+?)\*\*", text, re.S)]


def _no_capability_data(row: dict[str, str]) -> bool:
    capabilities = [key for key in row if re.fullmatch(r"c\d\d_\w+", key)]
    return bool(capabilities) and all(row[key] == "unknown" for key in capabilities)


class LandscapeCountsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = _matrix()
        self.products = " ".join(_section(_landscape(), "Products").split())

    def test_the_ring_counts_are_the_matrix_counts(self) -> None:
        match = re.search(
            r"(\d+) products and projects are in the matrix: (\d+) direct, (\d+) adjacent "
            r"and (\d+) pattern donors\.",
            self.products,
        )
        assert match
        rings = [row["ring"] for row in self.rows]
        self.assertEqual(
            tuple(int(group) for group in match.groups()),
            (len(rings), rings.count("direct"), rings.count("adjacent"), rings.count("pattern")),
        )
        self.assertEqual(set(rings), {"direct", "adjacent", "pattern"})

    def test_the_rows_without_capability_data_are_counted_by_their_evidence(self) -> None:
        match = re.search(
            r"In (\d+) rows every capability cell is `unknown`: (\w+) carry evidence "
            r"`unknown`, and (\w+) hold Claimed product facts only\. So (\d+) rows hold "
            r"capability data\.",
            self.products,
        )
        assert match
        empty = [row for row in self.rows if _no_capability_data(row)]
        unknown = [row["product"] for row in empty if row["evidence"] == "unknown"]
        claimed = [row["product"] for row in empty if row["evidence"] == "Claimed"]
        self.assertEqual(len(unknown) + len(claimed), len(empty))
        self.assertEqual(
            (
                int(match.group(1)),
                NUMBERS[match.group(2)],
                NUMBERS[match.group(3)],
                int(match.group(4)),
            ),
            (len(empty), len(unknown), len(claimed), len(self.rows) - len(empty)),
        )
        # The paragraph names the three rows with evidence unknown, and why.
        self.assertEqual(
            sorted(unknown), ["Brightflag", "GitHub pull request reviews", "HighQ (Thomson Reuters)"]
        )
        self.assertIn("Brightflag and HighQ were not found in any search", self.products)
        self.assertIn("GitHub pull request reviews was not researched", self.products)


class LandscapeRingsTest(unittest.TestCase):
    def setUp(self) -> None:
        text = _landscape()
        self.ring = {row["product"]: row["ring"] for row in _matrix()}
        self.direct = _section(text, "Direct competitors")
        self.adjacent = _section(text, "Adjacent products")

    def test_each_direct_competitor_is_a_direct_row(self) -> None:
        spans = _bold(self.direct)
        for name, product in DIRECT.items():
            with self.subTest(name):
                self.assertEqual(self.ring[product], "direct")
                self.assertTrue(any(name in span for span in spans))

    def test_every_direct_row_is_listed_or_has_no_data(self) -> None:
        # Brightflag is direct, but no search found it; the Products paragraph says so.
        direct = {product for product, ring in self.ring.items() if ring == "direct"}
        self.assertEqual(direct - set(DIRECT.values()), {"Brightflag"})

    def test_each_adjacent_product_is_an_adjacent_row_and_not_listed_as_direct(self) -> None:
        spans = _bold(self.adjacent)
        for name, product in ADJACENT.items():
            with self.subTest(name):
                self.assertEqual(self.ring[product], "adjacent")
                self.assertTrue(any(name in span for span in spans))
                self.assertIsNone(re.search(rf"\b{re.escape(name)}\b", self.direct))


class ResearchRulesTest(unittest.TestCase):
    def test_rules_are_quoted_by_their_words_not_a_number(self) -> None:
        # The research once cited "Rule 4" and "rule 5", which no rule list in this
        # repository numbers that way. A rule is quoted in its own words instead.
        for path in sorted(RESEARCH.glob("*.md")):
            with self.subTest(path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"\b[Rr]ules? \d", text))


FOLLOW_UPS = "Follow-ups after the owner decisions (2026-11-19)"
OWNER_CHOICES = "Owner choices after the plan was finished (2026-11-20)"


def _closing_sections() -> tuple[str, str]:
    """The plan's last two sections: the follow-ups, then the owner's later choices."""

    text = (RESEARCH / "adaptation-plan.md").read_text(encoding="utf-8")
    follow_ups, choices = text.split(f"\n## {FOLLOW_UPS}\n", 1)[1].split(
        f"\n## {OWNER_CHOICES}\n", 1
    )
    return follow_ups, choices


class FollowUpsTest(unittest.TestCase):
    def test_the_plan_ends_with_the_follow_ups_and_then_the_owner_choices(self) -> None:
        text = (RESEARCH / "adaptation-plan.md").read_text(encoding="utf-8")
        headings = re.findall(r"^## (.+)$", text, re.M)
        self.assertEqual(headings[-2:], [FOLLOW_UPS, OWNER_CHOICES])

    def test_the_follow_ups_leave_built_items_to_their_specs(self) -> None:
        follow_ups, _ = _closing_sections()
        self.assertEqual(re.findall(r"^(\d+)\. ", follow_ups, re.M), ["1", "2", "3", "4", "5"])
        # F3, F9a and F10 record their own follow-ups in their specs and ADRs.
        for name in ("F3", "F9a", "F10", "ADR 0010", "ADR 0011", "ADR 0012"):
            self.assertNotIn(name, follow_ups)


# What each of the four items has to say, by its number: the outcome in bold first, then
# these words in the item's own text.
CHOICES = {
    "1": (
        "**Triage defaults: confirmed as built.**",
        "a snooze counts as legal's first response",
        "a snooze lasts at most 30 days",
        "a duplicate needs a reason",
        "](../adr/0010-triage-verbs.md)",
    ),
    "2": (
        "**A withdrawn matter is reported `rejected` in the shared contract.**",
        "`approved` only when the requester accepted the delivery of the approved package",
        "`rejected` when it was withdrawn, whatever state it had reached",
        # What a withdrawal does to the stored assessment, and of which version. An earlier
        # version keeps the assessment it had, so the sentence is not said of the matter
        # (supervised-agent/tests/test_pilot_contract_closings.py pins the behaviour).
        "A withdrawal also records a rejected review decision on the assessment stored in "
        "the current matter version",
        "so the version a withdrawal closes keeps no approved or exportable assessment",
        "Earlier versions are history and are not rewritten, as recorded on 2026-11-23",
        "The schema is unchanged and no value is added",
        "](../adr/0010-triage-verbs.md)",
    ),
    "3": (
        "**No German requester labels.**",
        "No German stage label is added in the pilot or in the core",
        "](../adr/0011-requester-vocabulary.md)",
    ),
    "4": (
        "**`supervised-agent/mcp.json`: removed.**",
        # What holds on any machine. Whether the client also read the server's first line
        # depends on output buffering, so the plan does not say it did.
        "that started the command got no answer to `initialize`",
        "the agent ships no MCP client configuration",
        # What the guard against a returning file looks at, and since when.
        "The guard is about what the agent ships (corrected on 2026-11-23:",
        "In a git checkout it asks git for the files it tracks or would add under the agent",
        "Where git cannot say (no checkout, no git, a command that fails or lists nothing), "
        "it walks every directory except the ones a tool fills on the machine",
    ),
}
# Decision 9 of ADR 0010, the shared contract, as amended on 2026-11-20: each sentence that
# carries a decision. The two sentences that only point to files are not pinned.
DECISION_9 = (
    "`declined` and `duplicate` map to `rejected`, which v1 already allows.",
    "`rejected` takes precedence over `blocked`: a declined matter that a charter exclusion "
    "held is no longer pending, so it is reported `rejected`.",
    "Amended on 2026-11-20. A `closed` matter is reported by how it closed, not by its state.",
    "Only a matter whose approved package the requester accepted "
    "(`delivered_locally_and_accepted`) is `approved`.",
    "A withdrawn matter (`withdrawn_without_delivery`) is `rejected`, whatever state it had "
    "reached, because a withdrawal cancels every sign-off and approval on it.",
    "It invalidates the specialist sign-offs and final approvals in the decision record.",
    # The assessment of the current version: an earlier version is not rewritten.
    "In the same step it records a rejected review decision on the assessment stored in the "
    "current matter version, with the actor and the reason they typed, so that assessment is "
    "no longer approved or exportable and the pilot's own export gate fails its check of it.",
    "It does this for every withdrawal, whatever the assessment said before.",
    "A delivery package prepared before the withdrawal stays in the store and in the export "
    "folder, but the review room and the package route no longer open it.",
    "A store in which a matter was withdrawn before this was built keeps the assessment as "
    "the approval left it. The contract takes neither its state nor its note from that "
    "assessment, so such a matter is reported `rejected` as well.",
    "A closed matter with no recorded outcome is `rejected` too, so nothing is reported "
    "approved unless its delivery was accepted.",
    "As for a decline, `rejected` takes precedence over `blocked`.",
    "The review note of a withdrawn matter is the withdrawal reason and the actor recorded "
    "for it, not the note of an approval that no longer stands.",
    "`export_allowed` was already false for every closed matter.",
    "In the pilot, `rejected` now means that a person closed the matter without delivery and "
    "no approval stands. It does not say that a reviewer rejected a draft.",
    "The schema is unchanged and no value is added.",
    "`parent_bridge.contract_review_state` decides this in one place.",
    # What the contract check can tell from the source text, and no more than that.
    "`scripts/check_shared_contracts.py` reads the module's source text and runs none of it. "
    "It fails if the state table has a `closed` entry, if a closing-outcome entry is missing "
    "or changed, or if the function does not begin with the closed branch that returns "
    '`CLOSED_OUTCOME_REVIEW_STATE.get(closed_outcome or "", "rejected")`.',
)
# The one paragraph in each record that starts with "Confirmed:", in full.
CONFIRMED = {
    "0010-triage-verbs.md": (
        "Confirmed: 2026-11-20, the owner confirmed the three revisable defaults. A snooze "
        "counts as legal's first response, a snooze lasts at most 30 days, and a duplicate "
        "needs a reason. Nothing in the code changed."
    ),
    "0011-requester-vocabulary.md": (
        "Confirmed: 2026-11-20, the owner confirmed that no German requester labels are added "
        "(Decision 3 and 4). Nothing in the code changed, and both owner questions above stay "
        "open."
    ),
}
# The agent ships what git tracks or would add. `git ls-files` with these options lists both,
# by their path under the directory it runs in, and leaves out what a .gitignore or the
# machine's own exclude file names, such as a developer's .vscode/mcp.json. NUL ends each path.
# The agent's own test of the same thing, supervised-agent/tests/test_docs.py, cannot import
# this module, because it also runs in a standalone export of the agent. So the definitions
# in SHARED_WITH_THE_AGENT are written out in both files, and a test below requires the two
# copies to be the same.
GIT_LISTING = ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z")
# A hook or a wrapper script can export these to point git at another repository or index.
# The question is about the checkout this directory is in, so git is asked without them.
GIT_REPOSITORY_VARIABLES = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
    }
)
# Where git cannot say, every directory is walked, hidden or not, except the ones a tool
# fills on the machine it runs on: version control data, virtual environments, installed
# packages, tool caches and the local pilot store. The walk cannot tell which files in
# them are shipped, and on a developer's machine they hold many that are not.
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


def _files_named(root: Path, *names: str, listing: Sequence[str] = GIT_LISTING) -> list[str]:
    """The files with one of these names that ``root`` ships, by their path under it.

    In a git checkout these are the files git tracks or would add under ``root``, whether
    ``root`` is the repository or a directory in it. Where git cannot say, they are the
    files the walk finds: without a checkout, without git, when the command fails, and when
    it lists nothing at all, as it does for a copy of the tree inside a directory that
    another checkout ignores.
    """

    listed = _git(root, listing)
    if listed:
        paths = [os.fsdecode(path) for path in listed.split(b"\0") if path]
    else:
        paths = _walked(root)
    return sorted(path for path in paths if path.rsplit("/", 1)[-1] in names)


SHARED_WITH_THE_AGENT = (
    "GIT_LISTING",
    "GIT_REPOSITORY_VARIABLES",
    "MACHINE_LOCAL_DIRECTORIES",
    "_git",
    "_walked",
    "_files_named",
)


def _definition(source: str, name: str) -> str:
    """One top-level assignment or function of a module, as it is written in ``source``.

    It runs from the line that starts with the name to the next line that starts a new
    top-level statement or comment. Read as text, so nothing of the module is imported.
    """

    match = re.search(
        rf"^(?:def {re.escape(name)}\(|{re.escape(name)} = ).*?(?=^[^\s)\]}}])",
        source,
        re.M | re.S,
    )
    if match is None:
        raise AssertionError(f"no top-level definition of {name}")
    return match.group(0).rstrip() + "\n"


# A program that stands in for git: this interpreter, started without the site module and
# without its environment variables, so nothing of the machine is printed or read.
PYTHON = (sys.executable, "-I", "-S", "-c")
FAILS_AFTER_A_LISTING = "import sys; sys.stdout.write('docs/notes.md\\0'); sys.exit(128)"


def _write(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _numbered_items(text: str) -> dict[str, str]:
    """Each numbered item that starts a line in ``text``, flattened, by its number."""

    parts = re.split(r"^(\d+)\. ", text, flags=re.M)
    return {number: _flat(item) for number, item in zip(parts[1::2], parts[2::2], strict=True)}


class OwnerChoicesTest(unittest.TestCase):
    """What the owner chose on 2026-11-20 is in the plan and in the records it confirms."""

    def test_the_plan_lists_the_four_choices(self) -> None:
        _, choices = _closing_sections()
        self.assertEqual(re.findall(r"^(\d+)\. ", choices, re.M), ["1", "2", "3", "4"])
        items = _numbered_items(choices)
        for number, (outcome, *words) in CHOICES.items():
            with self.subTest(number):
                self.assertTrue(items[number].startswith(outcome), items[number][:80])
                for phrase in words:
                    self.assertIn(phrase, items[number])
        # Said of the whole matter, this is false where an earlier version was approved.
        self.assertNotIn("the pilot keeps no approved or exportable assessment", items["2"])

    def test_each_confirmed_record_carries_its_confirmation(self) -> None:
        adr = ROOT / "docs" / "adr"
        for name, confirmation in CONFIRMED.items():
            with self.subTest(name):
                text = (adr / name).read_text(encoding="utf-8")
                confirmed = [
                    _flat(paragraph)
                    for paragraph in text.split("\n\n")
                    if paragraph.startswith("Confirmed:")
                ]
                self.assertEqual(confirmed, [confirmation])
                self.assertIn("- Status: Accepted\n", text)

    def test_the_triage_record_carries_its_amendment(self) -> None:
        # Choice 2 changed ADR 0010: its header says so, and Decision 9 holds the new rule.
        text = (ROOT / "docs" / "adr" / "0010-triage-verbs.md").read_text(encoding="utf-8")
        header = text.split("\n## Context\n", 1)[0]
        amended = [
            _flat(entry)
            for entry in re.split(r"^- ", header, flags=re.M)
            if entry.startswith("Amended:")
        ]
        self.assertEqual(
            amended,
            [
                "Amended: 2026-11-20: a withdrawn matter is reported `rejected` in the shared "
                "contract, not `approved` (owner choice of 2026-11-20); see Decision 9 and "
                "Consequences."
            ],
        )
        shared_contract = _numbered_items(_section(text, "Decision"))["9"]
        self.assertTrue(shared_contract.startswith("**Shared contract.**"))
        for words in DECISION_9:
            with self.subTest(words):
                self.assertIn(words, shared_contract)
        # The check reads text. It cannot tell how a closed matter is mapped when the code
        # runs, and the record claimed that once.
        self.assertNotIn("mapped by its state alone", shared_contract)

    def test_the_vocabulary_record_says_when_a_held_matter_stops_being_blocked(self) -> None:
        # ADR 0011, which choice 3 confirms, describes the contract value of a matter that
        # a charter exclusion or a blocked source holds. A decline, a duplicate and, since
        # choice 2, a withdrawal end it: `rejected` takes precedence over `blocked` (ADR
        # 0010, Decision 9), and the matter leaves triage.
        text = (ROOT / "docs" / "adr" / "0011-requester-vocabulary.md").read_text(encoding="utf-8")
        [blocked] = [
            _flat(entry)
            for entry in re.split(r"^- ", _section(text, "Context"), flags=re.M)
            if entry.startswith("**`blocked` means different things.**")
        ]
        for words in (
            "the pilot reports `blocked` for a matter that a charter exclusion or a blocked "
            "source holds, until the matter is declined, closed as a duplicate or withdrawn; "
            "it is then reported `rejected` ([ADR 0010](0010-triage-verbs.md), Decision 9).",
            "`complete_triage` refuses a held matter, so a matter held when it reaches triage "
            "stays there while it is held, or is closed in one of these three ways.",
        ):
            with self.subTest(words):
                self.assertIn(words, blocked)
        # The record said such a matter "stays there", as if nothing could close it.
        self.assertNotIn("reaches triage stays there.", blocked)
        ending = (
            "stays `blocked` in the contract until a new version removes the exclusion or "
            "the matter is withdrawn. Since 2026-11-20 a withdrawn matter is reported "
            "`rejected` ([ADR 0010](0010-triage-verbs.md), amended that day)."
        )
        self.assertTrue(blocked.endswith(ending), blocked[-len(ending) :])

    def test_the_removed_agent_configuration_stays_removed(self) -> None:
        # The plan says the file is removed; the agent's own tests say why it stays out.
        # No file of either name that git tracks or would add is anywhere in the agent, a
        # hidden directory included. A file git ignores, such as a developer's own
        # .vscode/mcp.json, is not shipped. Where git cannot say, every directory is
        # searched except the machine-local ones.
        self.assertEqual(_files_named(ROOT / "supervised-agent", "mcp.json", ".mcp.json"), [])

    def test_both_suites_search_for_a_client_configuration_in_the_same_way(self) -> None:
        mine = Path(__file__).read_text(encoding="utf-8")
        agents = (ROOT / "supervised-agent" / "tests" / "test_docs.py").read_text(encoding="utf-8")
        for name in SHARED_WITH_THE_AGENT:
            with self.subTest(name):
                self.assertEqual(_definition(agents, name), _definition(mine, name))
        # What was compared is the list itself: the agent's text gives the names used here.
        written = _definition(agents, "MACHINE_LOCAL_DIRECTORIES")
        names = ast.literal_eval(written[written.index("{") : written.rindex("}") + 1])
        self.assertEqual(names, set(MACHINE_LOCAL_DIRECTORIES))
        self.assertIn(".git", names)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_in_a_checkout_the_search_asks_git_what_is_shipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            home = base / "home"
            home.mkdir()
            # The ignore rules of this checkout decide, not the configuration of the machine.
            isolated = {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / "config"),
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            }
            # Variables that point git somewhere else must change nothing.
            elsewhere = {
                "GIT_DIR": str(base / "elsewhere.git"),
                "GIT_WORK_TREE": str(base),
                "GIT_INDEX_FILE": str(base / "elsewhere.index"),
                "GIT_COMMON_DIR": str(base / "elsewhere.git"),
            }
            # The agent is a directory of the checkout here, as in this repository.
            checkout = base / "checkout"
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
            shipped = [
                ".cursor/mcp.json",  # untracked and not ignored: git would add it
                ".idea/.mcp.json",
                "docs/.mcp.json",
                "node_modules/package/mcp.json",  # git decides here, not the list of names
                "runtime/mcp.json",
            ]
            with mock.patch.dict(os.environ, isolated):
                # Each command names its directory itself, so the set-up can only write
                # under the temporary directory. The checkout starts without the machine's
                # template, which could bring ignore rules.
                for directory, arguments in (
                    (checkout, ("init", "--quiet", "--template=")),
                    (checkout, ("add", "mcp.json", "plugin", "agent/README.md")),
                    (agent, ("add", ".gitignore", "docs", "runtime")),
                    # Tracked although its directory is ignored.
                    (agent, ("add", "--force", ".idea/.mcp.json")),
                ):
                    command = ("git", "-C", str(directory), *arguments)
                    self.assertIsNotNone(_git(directory, command), arguments)
                self.assertEqual(_files_named(agent, "mcp.json", ".mcp.json"), shipped)
                # The agent is the repository itself in a standalone export.
                self.assertEqual(
                    _files_named(checkout, "mcp.json", ".mcp.json"),
                    sorted([*(f"agent/{path}" for path in shipped), "mcp.json", "plugin/.mcp.json"]),
                )
                with mock.patch.dict(os.environ, elsewhere):
                    self.assertEqual(_files_named(agent, "mcp.json", ".mcp.json"), shipped)
                # A directory in no checkout: git is not allowed to look above it, says
                # so, and the walk answers. Nothing is ignored there, and the machine-local
                # directories are left out.
                plain = base / "plain"
                _write(plain, ".vscode/mcp.json", "node_modules/package/mcp.json")
                with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(base)}):
                    self.assertIsNone(_git(plain, GIT_LISTING))
                    self.assertEqual(
                        _files_named(plain, "mcp.json", ".mcp.json"), [".vscode/mcp.json"]
                    )

    def test_without_git_the_search_walks_all_but_the_machine_local_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            tree = base / "tree"
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
            # Git is taken away by the command, so this does not need a machine without
            # git: a program that does not exist, one that fails with git's exit status
            # after it listed a file, and one that lists nothing.
            for case, listing in (
                ("no such program", (str(base / "git-is-not-installed"), *GIT_LISTING[1:])),
                ("fails after a listing", (*PYTHON, FAILS_AFTER_A_LISTING)),
                ("lists nothing", (*PYTHON, "")),
            ):
                with self.subTest(case):
                    self.assertEqual(
                        _files_named(tree, "mcp.json", ".mcp.json", listing=listing),
                        [
                            ".cursor/mcp.json",
                            ".mcp.json",
                            ".vscode/mcp.json",
                            "docs/.hidden/.mcp.json",
                            "mcp.json",
                        ],
                    )


if __name__ == "__main__":
    unittest.main()
