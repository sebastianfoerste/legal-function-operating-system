"""The research documents agree with the feature matrix and quote rules by their words.

``docs/research/2026-10-competitive-landscape.md`` states how many products the matrix
holds per ring, how many rows hold no capability data, and lists each product under
"Direct competitors" or "Adjacent products". The matrix,
``docs/research/feature-matrix.csv``, is the record; these tests recompute what the
landscape states from it, so a matrix change that the prose does not follow fails here.
"""

import csv
import re
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


class FollowUpsTest(unittest.TestCase):
    def test_the_plan_ends_with_the_follow_ups_and_leaves_built_items_to_their_specs(self) -> None:
        text = (RESEARCH / "adaptation-plan.md").read_text(encoding="utf-8")
        headings = re.findall(r"^## (.+)$", text, re.M)
        self.assertEqual(headings[-1], "Follow-ups after the owner decisions (2026-11-19)")
        follow_ups = text.split("\n## Follow-ups after the owner decisions (2026-11-19)\n", 1)[1]
        self.assertEqual(re.findall(r"^(\d+)\. ", follow_ups, re.M), ["1", "2", "3", "4", "5"])
        # F3, F9a and F10 record their own follow-ups in their specs and ADRs.
        for name in ("F3", "F9a", "F10", "ADR 0010", "ADR 0011", "ADR 0012"):
            self.assertNotIn(name, follow_ups)


if __name__ == "__main__":
    unittest.main()
