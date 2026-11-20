"""The research documents agree with the feature matrix and quote rules by their words.

``docs/research/2026-10-competitive-landscape.md`` states how many products the matrix
holds per ring, how many rows hold no capability data, and lists each product under
"Direct competitors" or "Adjacent products". The matrix,
``docs/research/feature-matrix.csv``, is the record; these tests recompute what the
landscape states from it, so a matrix change that the prose does not follow fails here.
"""

import csv
import os
import re
import tempfile
import unittest
from pathlib import Path

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
        # What a withdrawal does to the stored assessment.
        "A withdrawal also records a rejected review decision on the assessment stored in "
        "the matter version",
        "so the pilot keeps no approved or exportable assessment for a withdrawn matter",
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
    ),
}
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
# Directories a tool fills on the machine it runs on: version control data, virtual
# environments, installed packages, tool caches and the local pilot store. Nothing in them
# is written for the agent or committed. Every other directory is searched, hidden or not.
# The agent's own test of the same thing, supervised-agent/tests/test_docs.py, has this list.
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


def _flat(text: str) -> str:
    return " ".join(text.split())


def _numbered_items(text: str) -> dict[str, str]:
    """Each numbered item that starts a line in ``text``, flattened, by its number."""

    parts = re.split(r"^(\d+)\. ", text, flags=re.M)
    return {number: _flat(item) for number, item in zip(parts[1::2], parts[2::2], strict=True)}


def _files_named(root: Path, *names: str) -> list[str]:
    """Files with one of these names anywhere under ``root``, hidden directories included."""

    found: list[str] = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in MACHINE_LOCAL_DIRECTORIES]
        found += [
            Path(directory, name).relative_to(root).as_posix() for name in files if name in names
        ]
    return sorted(found)


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
        for words in (
            "Amended on 2026-11-20. A `closed` matter is reported by how it closed, not by "
            "its state.",
            "Only a matter whose approved package the requester accepted "
            "(`delivered_locally_and_accepted`) is `approved`.",
            "A withdrawn matter (`withdrawn_without_delivery`) is `rejected`, whatever state "
            "it had reached",
            "In the same step it records a rejected review decision on the assessment "
            "stored in the matter version, with the actor and the reason they typed, so that "
            "assessment is no longer approved or exportable",
            "It does this for every withdrawal, whatever the assessment said before.",
            "The schema is unchanged and no value is added.",
        ):
            with self.subTest(words):
                self.assertIn(words, shared_contract)

    def test_the_vocabulary_record_says_when_a_held_matter_stops_being_blocked(self) -> None:
        # ADR 0011, which choice 3 confirms, describes the contract value of a matter a
        # charter exclusion holds after triage. Since choice 2 a withdrawal ends it too.
        text = (ROOT / "docs" / "adr" / "0011-requester-vocabulary.md").read_text(encoding="utf-8")
        [blocked] = [
            _flat(entry)
            for entry in re.split(r"^- ", _section(text, "Context"), flags=re.M)
            if entry.startswith("**`blocked` means different things.**")
        ]
        ending = (
            "stays `blocked` in the contract until a new version removes the exclusion or "
            "the matter is withdrawn. Since 2026-11-20 a withdrawn matter is reported "
            "`rejected` ([ADR 0010](0010-triage-verbs.md), amended that day)."
        )
        self.assertTrue(blocked.endswith(ending), blocked[-len(ending) :])

    def test_the_removed_agent_configuration_stays_removed(self) -> None:
        # The plan says the file is removed; the agent's own tests say why it stays out.
        # No file of either name is anywhere in the agent, a hidden directory included.
        self.assertEqual(_files_named(ROOT / "supervised-agent", "mcp.json", ".mcp.json"), [])

    def test_the_search_for_a_client_configuration_reads_hidden_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in (
                "mcp.json",
                ".mcp.json",
                ".cursor/mcp.json",
                ".vscode/mcp.json",
                "docs/.hidden/.mcp.json",
                "docs/mcp.json.txt",
                "docs/notes.md",
                *(f"{skipped}/mcp.json" for skipped in sorted(MACHINE_LOCAL_DIRECTORIES)),
                "src/__pycache__/.mcp.json",
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                _files_named(root, "mcp.json", ".mcp.json"),
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
