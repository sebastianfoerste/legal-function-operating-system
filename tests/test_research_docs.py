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


# How a changelog entry points to another place of the changelog by its position. The six
# parts of the pattern, in its order:
#   1 "at the top of this section", "the bottom of the subsection", "the top of this list".
#   2 "the entry above", "the entries just below", "the entry further down". What follows
#     can be what the entry is above or below, as in "its entry below 320 px of width" or
#     "the entry above the break": that is a place on a page and no pointer.
#   3 "the above entry", "the previous entry", "the next entry but one".
#   4 "the first entry of this section", "the last entry under Fixed".
#   5 "below this entry", "above that one", "recorded below in this section".
#   6 "above" or "below" where it ends a phrase, as in "(see the entry on drafts above)" or
#     "the fix for drafts below,". A mark, a dash between spaces or the end of the line
#     ends a phrase. "Above" or "below" followed by what it is above or below ("the status
#     above that line") is no pointer, and neither is "or above" for a value.
BY_POSITION = re.compile(
    r"\b(?:top|bottom) of (?:this \w+|the (?:section|subsection|release|changelog))\b"
    r"|\bentr(?:y|ies) (?:(?:directly |just |right )?(?:above|below)|further (?:up|down))\b"
    r"(?! (?:(?:the|an?)\b|\d))"
    r"|\b(?:above|below|previous|next|preceding|following) entr(?:y|ies)\b"
    r"|\b(?:first|last) entr(?:y|ies) (?:(?:of|in) this \w+|under (?-i:[A-Z]))"
    r"|\b(?:above|below) (?:(?:this|that) (?:entry|one)|in this \w+)\b"
    r"|(?<!\bor )\b(?:above|below)(?=\s*(?:[,.;:)(!?\u2013\u2014]|-\s|$))",
    re.I,
)
# An entry is named by its opening words in straight double quotes, after "entry" or
# "entries" and, if the sentence wants one, "named", "called" or "titled". Several names can
# follow each other with a comma, "and" or "or". The first test below looks up each name.
NAMED = re.compile(
    r'\bentr(?:y|ies),? (?:(?:named|called|titled) )?("[^"]+"(?:,? (?:(?:and|or) )?"[^"]+")*)',
    re.I,
)
# A name in other quotes, or written as code, is not looked up, so it is not accepted.
IN_OTHER_QUOTES = re.compile(
    r"\bentr(?:y|ies),? (?:(?:named|called|titled) )?['‘’“”`]", re.I
)


def _named_entries(text: str) -> list[str]:
    """The opening words by which the text names changelog entries."""

    return [name for names in NAMED.findall(text) for name in re.findall(r'"([^"]+)"', names)]


def _own_words(line: str) -> str:
    """A line of the changelog without what it quotes: code and text in double quotes."""

    return re.sub(r'"[^"]*"', '""', re.sub(r"`[^`]*`", "``", line))


def _unnamed_pointers(line: str) -> list[str]:
    """Where the line's own words point by position, or name an entry in other quotes."""

    words = _own_words(line)
    return [
        found.group(0)
        for pattern in (BY_POSITION, IN_OTHER_QUOTES)
        for found in pattern.finditer(words)
    ]


class ChangelogPointersTest(unittest.TestCase):
    def test_a_changelog_entry_that_names_another_names_one_that_exists(self) -> None:
        # New entries go on top of each subsection, so "the entry at the top of this
        # section", "above" and "below" come to mean another entry, or none. An entry is
        # named by its opening words instead: `the entry "..."`. Every such name has to be
        # the opening of exactly one entry of the same release, so a reworded entry fails
        # here until the sentences that name it follow. The names of a list are looked up
        # one by one, also after "entries" and after "named", "called" or "titled". The next
        # test refuses the pointers this one cannot look up.
        for text, names in (
            ('(see the entry "Pilot: one")', ["Pilot: one"]),
            ('The matter list has its own entry, "Pilot: one". Tests:', ["Pilot: one"]),
            ('(the entries "Pilot: one" and "Pilot: two")', ["Pilot: one", "Pilot: two"]),
            (
                '(the Entries, "Pilot: one", "Pilot: two", or "Pilot: three")',
                ["Pilot: one", "Pilot: two", "Pilot: three"],
            ),
            ('(the entry named "Pilot: one")', ["Pilot: one"]),
            ('(the entry called "Pilot: one")', ["Pilot: one"]),
            ('(the entries titled "Pilot: one" or "Pilot: two")', ["Pilot: one", "Pilot: two"]),
            # What an entry said is quoted, and names no entry.
            ('The entry on drafts said "(the entry at the top of this section)".', []),
            ('It is shown as "In review", in the entry and in the status "Approved".', []),
        ):
            with self.subTest(text):
                self.assertEqual(_named_entries(text), names)
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        named = 0
        for release in re.split(r"^## ", text, flags=re.M)[1:]:
            entries = re.findall(r"^- (.+)$", release, re.M)
            for name in _named_entries(release):
                named += 1
                with self.subTest(name):
                    self.assertEqual(sum(entry.startswith(name) for entry in entries), 1)
        self.assertTrue(named, "no entry is named anywhere in the changelog")

    def test_no_changelog_entry_points_to_another_by_its_position(self) -> None:
        # The test above looks up a name written as `entry "..."`. A pointer by position
        # and a name in other quotes passed it unseen, and the first is the defect the rule
        # was made for. Both are refused here, in every line of the changelog. What a line
        # quotes, in double quotes or as code, is not its own wording: the entry that
        # records the correction quotes the old pointers. The check reads words and does
        # not understand a sentence, so it errs both ways. A pointer worded in yet another
        # way is not found, for example "the entry above the one on drafts", which reads
        # like a place on a page, or "two entries further on". And a sentence that points
        # to no entry is refused where it ends a phrase with "above" or "below" or speaks
        # of "the top of this changelog": it has to be reworded. Every alternative of the
        # patterns, each word and each mark, is held by an example below, so that none can
        # be taken out unseen.
        for pointer, found in (
            # 1
            ("names it (the entry at the top of this section).", "top of this section"),
            ("(the entry at the top of this list)", "top of this list"),
            ("(the entry at the bottom of the section)", "bottom of the section"),
            ("(the entry at the top of the subsection)", "top of the subsection"),
            ("The fix at the top of the release says why.", "top of the release"),
            ("(the entry at the top of the changelog)", "top of the changelog"),
            # 2
            ("The entry above says why.", "entry above"),
            ("The entries below say why.", "entries below"),
            ("(the entry directly below this)", "entry directly below"),
            ("The entry just above says why.", "entry just above"),
            ("The entry right below says why.", "entry right below"),
            ("(the entry further down in the list)", "entry further down"),
            ("The entry further up says why.", "entry further up"),
            ("The entry above then said the opposite.", "entry above"),
            ("The entry below answers it.", "entry below"),
            # 3
            ("(see the above entry for the reason)", "above entry"),
            ("The below entries say why.", "below entries"),
            ("(the previous entry has the reason)", "previous entry"),
            ("(the next entry but one)", "next entry"),
            ("The preceding entry says why.", "preceding entry"),
            ("The following entries say why.", "following entries"),
            # 4
            ("(the first entry of this section)", "first entry of this section"),
            ("(the last entries in this release)", "last entries in this release"),
            ("(the last entry under Fixed)", "last entry under F"),
            # 5
            ("This is undone by the change recorded below this entry.", "below this entry"),
            ("The correction above that one says why.", "above that one"),
            ("(the fix for drafts recorded below in this section)", "below in this section"),
            # 6
            ("Since the fix for unsubmitted drafts below, the ledger left out a matter.", "below"),
            ("The reason is given above.", "above"),
            ("It is the fix for drafts below; the ledger follows it.", "below"),
            ("The corrections are recorded below: the word filter and four more.", "below"),
            ("keeps the assessment it had (see the entry on the pilot's records above).", "above"),
            ("which lists the five corrections below (the word filter and four more)", "below"),
            ("How could the fix for drafts above! It names the matter.", "above"),
            ("Is it the fix for drafts below? It names the matter.", "below"),
            ("(the entry on drafts above \u2013 it names the matter)", "above"),
            ("(the entry on drafts above \u2014 it names the matter)", "above"),
            ("(the entry on drafts above - it names the matter)", "above"),
            ("The reason is with the fix for drafts below", "below"),
            ("(see above and below)", "below"),
            ("Below, the fix for drafts says why.", "Below"),
            # A name that the test above does not look up.
            ("(see the entry 'Pilot: a matter legal never received')", "entry '"),
            ("(see the entry ‘Pilot: a matter legal never received’)", "entry ‘"),
            ("(see the entries ’Pilot: a matter legal never received’)", "entries ’"),
            ("(see the entry, “Pilot: a matter legal never received”)", "entry, “"),
            ("(see the entry ”Pilot: a matter legal never received”)", "entry ”"),
            ("(the entry `Pilot: no such entry anywhere`)", "entry `"),
            ("Entry 'Pilot: no such entry anywhere' says why.", "Entry '"),
            ("(the entry named 'Pilot: no such entry anywhere')", "entry named '"),
            ("(the entry called 'Pilot: no such entry anywhere')", "entry called '"),
            ("(the entry titled `Pilot: no such entry anywhere`)", "entry titled `"),
        ):
            with self.subTest(pointer):
                self.assertEqual(_unnamed_pointers(pointer), [found])
        for ordinary in (
            '(see the entry "Pilot: a matter legal received is no longer left out")',
            '(the entries named "Pilot: one" and "Pilot: two")',
            'The entry on drafts said "(the entry at the top of this section)".',
            'That pointer and two others, which said "below" and "above", now name the entry.',
            "The test refuses `the entry above` and `(see the entry 'Pilot: no such entry')`.",
            "Entries were then added above the one it meant, so it pointed to another entry.",
            "a question can depend only on an answer given above it, which is checked",
            'The status above that line still read "Ready for you".',
            "the room showed the sentence and, right below it, the button",
            '`init` writes "Value in band or above." for the high risk sentences.',
            "A dispute value of EUR 250,000 or above.",
            "The audit entry's time and the `closed` entry, if one is missing",
            # A place on a page: what the entry is above or below follows.
            "The pill may wrap inside its entry below 320 px of width.",
            "A list entry below the selected one keeps its place.",
            "The timeline shows the entry above the break in grey.",
            "Each audit entry above the first unreadable one is still verified.",
            "A list entry just above a closed one keeps its place.",
            "The room scrolls to the entry below an open form.",
            # Not the changelog's own parts, and no heading of it.
            "The newest matter stands at the top of the list.",
            "The last entry under review keeps its place in the list.",
            "The first entry of the list is opened when the page loads.",
            "the wording above-mentioned in the runbook",
        ):
            with self.subTest(ordinary):
                self.assertEqual(_unnamed_pointers(ordinary), [])
        lines = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            with self.subTest(line=number):
                self.assertEqual(
                    _unnamed_pointers(line),
                    [],
                    'name the entry by its opening words instead: the entry "..."; a sentence '
                    "that points to no entry and speaks of a place on a page has to be reworded",
                )


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
        # What the guard against a returning file looks at, and since when: an ignored file
        # does not fail it and a tracked one does, where it was the other way round.
        "The guard is about what the agent ships (corrected on 2026-11-23: it had failed on a "
        "developer's own ignored file and passed for a file under `node_modules`, which git "
        "would add).",
        "In a git checkout it asks git for the files it tracks or would add under the agent, "
        "so a file git ignores, such as a developer's own `.vscode/mcp.json`, does not fail it "
        "and a tracked file does, wherever it is.",
        # When the walk answers instead, the refusal of git's ownership check included, and
        # that the guard then says so and does not fail for that alone.
        "Where git cannot say (no checkout, no git, a command that fails, as it does when "
        "git's ownership check refuses a checkout that belongs to another user, or a command "
        "that lists nothing), it walks every directory except the ones a tool fills on the "
        "machine",
        "The walk does not find the same files: it also finds a file git ignores, and it "
        "misses a tracked file inside one of those directories.",
        "So the search reports which of the two answered, and a guard that finds a file says "
        "so in its failure message (recorded on 2026-11-23).",
        "A walk that finds no such file passes, because a copy of the agent without git is a "
        "legitimate place to run the suite.",
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
# The note of 2026-11-23 in ADR 0011, on a matter that stays ready for delivery after its
# delivery ended: each sentence that says what the requester is shown, why, how the earlier
# status comes back and what the matter list and the view carry. The agent's suite pins the
# behaviour (test_pilot_intake_ux.py and test_pilot_package_standing.py); these pin the
# record of it, in the order of the note.
ENDED_DELIVERY_NOTE = (
    "Note (2026-11-23): one state now shows another of the six stages in one case.",
    "A matter can stay `ready_for_delivery` after its delivery ended.",
    "A comment written, resolved or reopened after the package was prepared does that, in "
    "other words any change to the state of a comment, and so does another final approver "
    "assigned in place of the one who approved.",
    # The stage, the explanation and the next step.
    'Such a matter is now shown as `in_review` (In review), with the explanation "The '
    "package prepared earlier is no longer approved, because the matter changed after it was "
    'prepared. Legal has to review the matter again before a package is ready for you." and '
    'the next step "No action needed from you.".',
    "An open question to the requester still replaces that next step, as it does in every "
    "stage but `closed`.",
    "A `ready_for_delivery` matter whose delivery stands is `ready`, as before, and every "
    "other state shows the stage Decision 5 lists, except `approved` in the one case the note "
    "of 2026-11-24 below adds.",
    # Why that stage: what the state machine leaves open.
    "The state machine has two transitions from `ready_for_delivery`.",
    "`accept_delivery` is the requester's, and its evidence `delivery_manifest_current` fails.",
    "The other is `request_revision`, for the matter owner, a specialist reviewer or the "
    "final approver, and it leads to `revision_requested`, which is `in_review` already.",
    "`approve` and `prepare_delivery` are not open from `ready_for_delivery`.",
    "`approved` would say that the review is approved and a package is being prepared, and "
    "neither is true.",
    "no stage is added, renamed or moved, and no pilot state is added either.",
    # The status follows the delivery, and the ways back.
    "`requester_status` receives it as `delivery_stands` and does not work it out again.",
    "If legal restores the reviewed state the approval was given on, the delivery stands "
    "again and the stage is `ready` again.",
    "A comment has two ways back, and each puts it into the state it had when the package "
    "was prepared: a comment that was reopened is resolved again, or a comment that was "
    "resolved is reopened.",
    "The approver has one: the earlier approver is assigned again.",
    "A new comment cannot be taken back, so after one a package is offered only after a "
    "revision request or a new version, a review and a new approval.",
    # What the matter list shows a requester, and every other role.
    "For a requester, each entry of `GET /pilot/api/matters` now also carries "
    "`requester_status_label`, the label of the status in their view of that matter, and the "
    "room shows it in the entry's pill.",
    "One function in the service (`PilotService._requester_status`) puts the facts together "
    "for the view and for the list, so the two cannot differ.",
    'This holds in every state: a withdrawn matter reads "Closed: withdrawn without delivery" '
    "in the requester's list, where it read `closed`.",
    "The key `state` stays in the entry, every other role's list is unchanged, and their "
    "page shows the pilot state as before.",
    # What the requester's view lists as delivered.
    "It now lists only the manifest of the package that may be opened now, which is the one "
    "`PilotService._standing_package` returns, and nothing otherwise.",
    "A reviewer's view keeps every stored manifest under `manifests`.",
    "**Unchanged.** The stored state, the state machine, the export gate and "
    "`legal-workflow-controls.v1`. No manifest is deleted or rewritten.",
)
# The note of 2026-11-24 in the same record, on an approved matter from whose approval no
# package can be prepared: what the requester is shown, the four ways it happens, why the
# explanation names no cause, who can move the matter in each way, where the answer comes
# from and the limit that is recorded and not closed. In the order of the note.
NO_PACKAGE_NOTE = (
    "Note (2026-11-24): a second state now shows another of the six stages in one case.",
    "A matter can be `approved` while `prepare_delivery` would be refused, so that no package "
    "can be prepared from the approval as the matter stands.",
    # The stage, the explanation and the next step.
    'Such a matter is now shown as `in_review` (In review), with the explanation "The review '
    "was approved, but a package for the customer cannot be prepared from that approval as "
    "the matter stands now. Legal has to work on the matter again before a package is ready "
    'for you." and the next step "No action needed from you.".',
    "An open question to the requester still replaces that next step.",
    "An `approved` matter from whose approval a package can be prepared is `approved`, as "
    "before.",
    "`ready_for_delivery` and `approved` are the two states with such a case, and every other "
    "state shows the stage Decision 5 lists.",
    # The four ways.
    "A comment was written, resolved or reopened after the approval, in other words any "
    "change to the state of a comment.",
    "Another final approver was assigned in place of the one who approved.",
    "A pilot scope hold applied when the matter was approved: an amendment after triage can "
    "bring a matter under a charter exclusion, and `approve` does not ask `pilot_scope_met`.",
    "A listed matter document is unchecked: the pilot gives the assessment no folder to check "
    "it in, so the approval does not allow export.",
    "In the first two the approval no longer counts.",
    "In the last two it never allowed a package, and nothing changed after it.",
    # No cause is named.
    '"The approval no longer counts because the matter changed after it was given" would be '
    "true in the first two ways and false in the last two.",
    "The sentence that is shown is true in every case in which `prepare_delivery` is refused.",
    "no reviewer, no check name, no hold reason and no comment text is shown.",
    # Who can move the matter, in each way.
    "In each of the four ways a package can be prepared only after someone in legal acts, "
    "and people in legal can run every command that leads to one, so the matter does not "
    "wait for its requester.",
    "A comment that was resolved or reopened after the approval can be put back into the "
    "state it had at the approval: a reviewer reopens it, or it is resolved again.",
    "In place of another approver, the matter owner can assign the earlier approver again.",
    "The stage is then `approved` again.",
    "A comment written after the approval cannot be taken back, and a new approver cannot "
    "approve from `approved`, because `approve` is not open from that state.",
    "A reviewer then requests a revision that names an open comment, the matter owner answers "
    "it and submits the revision, a reviewer resumes the review, the final approver approves "
    "and the matter owner prepares the package.",
    "Under a scope hold, or with an unchecked listed document, a review and a new approval "
    "change nothing.",
    "`amend_matter` has to make a version without the excluded input or without the listed "
    "document, and the matter owner may run it as well as the requester.",
    "`resume_review`, `approve` and `prepare_delivery` follow.",
    "The only other way out is to withdraw the matter.",
    "A question to the requester that is reopened after the approval is one such comment.",
    "The requester is then asked to answer it, as in every stage but `closed`, and its author "
    "can resolve it again on the answer it already has.",
    # Where the answer comes from.
    "The service asks the evidence that `prepare_delivery` itself needs, `export_gate_passes`, "
    "as the state machine lists it.",
    "It asks once, in `PilotService._requester_status`, the function the requester's view and "
    "matter list share.",
    "`requester_status` receives the answer as `package_can_be_prepared` and does not work it "
    "out again.",
    "It reads that answer only for `approved`, as it reads `delivery_stands` only for "
    "`ready_for_delivery`.",
    "As soon as a package can be prepared again, the stage is `approved` again.",
    # The limit, and what did not change.
    "A matter can be approved while a pilot scope hold applies or a listed matter document is "
    "unchecked, and can then get no package until it is amended or withdrawn.",
    "Whether `approve` should refuse such a matter is a change to the state machine that the "
    "owner decides separately.",
    "This note changes only what the requester is told.",
    "**Unchanged.** The stored state, the state machine, the export gate, "
    "`legal-workflow-controls.v1` and every schema.",
    "A reviewer's view and matter list are unchanged, and their list shows the pilot state, "
    "`approved`.",
)
# F3 of the plan: the two states that show "In review" in one case each, where the spec says
# it and where its acceptance says it.
F3_EXCEPTION = (
    "There are two exceptions.",
    "Since 2026-11-23 a matter that stays ready for delivery after its delivery ended is shown "
    'as "In review", with its own explanation and nothing to accept ([ADR '
    "0011](../adr/0011-requester-vocabulary.md), note of that day).",
    "Since 2026-11-24 an approved matter from whose approval no package can be prepared is "
    'shown as "In review" as well, with its own explanation, and is not told that a package '
    "is being prepared (the same record, note of that day).",
    "Every pilot state maps to exactly one stage, except that `ready_for_delivery` shows "
    '"In review" while its delivery has ended and `approved` shows "In review" while no '
    "package can be prepared from the approval.",
    "`tests/test_requester_vocabulary.py` pins the six stage ids, the stage of every pilot "
    "state, the two exceptions and the core's words (ADR 0011).",
)
# The agent ships what git tracks or would add. `git ls-files` with these options lists both,
# by their path under the directory it runs in, and leaves out what a .gitignore or the
# machine's own exclude file names, such as a developer's .vscode/mcp.json. NUL ends each path.
# The agent's own test of the same thing, supervised-agent/tests/test_docs.py, cannot import
# this module, because it also runs in a standalone export of the agent. So the definitions
# in SHARED_WITH_THE_AGENT are written out in both files, and a test below requires the two
# copies to be the same.
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
# Which search answered. Git and the walk do not find the same files: the walk also finds a
# file git ignores, and it does not find a file git tracks inside a machine-local directory.
# So the search says which of them answered, and a guard that finds a file passes that on.
GIT_ANSWERED = "git listed the files it tracks or would add here"
GIT_NOT_ASKED = (
    "git could not be asked here (it is not installed, this is no checkout, or its command "
    "failed, as it does when its ownership check refuses a checkout that belongs to another "
    "user), so every directory outside the machine-local ones was walked; a file that git "
    "ignores is found that way too"
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


SHARED_WITH_THE_AGENT = (
    "GIT_LISTING",
    "GIT_REPOSITORY_VARIABLES",
    "MACHINE_LOCAL_DIRECTORIES",
    "GIT_ANSWERED",
    "GIT_NOT_ASKED",
    "GIT_LISTED_NOTHING",
    "_git",
    "_walked",
    "_files_named",
    "_require_no_client_configuration",
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


def _function(source: str, name: str) -> str:
    """One function or method of a module as Python writes it back out.

    Its decorators, its signature and its statements, without comments and without the
    layout of the file. The module is parsed, not imported.
    """

    [found] = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    return ast.unparse(found)


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
        # searched except the machine-local ones. That search also finds an ignored file
        # and misses a tracked one inside a machine-local directory, so a failure says
        # which search answered. The walk alone fails nothing.
        _require_no_client_configuration(ROOT / "supervised-agent")

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
        # Each suite's guard is the shared helper, asked about the agent, and nothing else.
        # A guard that compares the files of the search itself still fails when a file
        # comes back, but is silent again about which search answered.
        for source, guard in (
            (
                agents,
                "def test_the_agent_ships_no_mcp_client_configuration():\n"
                "    _require_no_client_configuration(AGENT_ROOT)\n",
            ),
            (
                mine,
                "def test_the_removed_agent_configuration_stays_removed(self) -> None:\n"
                '    _require_no_client_configuration(ROOT / "supervised-agent")\n',
            ),
        ):
            name = guard[len("def ") : guard.index("(")]
            with self.subTest(name):
                self.assertEqual(_function(source, name), ast.unparse(ast.parse(guard)))
        self.assertEqual(
            _definition(agents, "AGENT_ROOT"), "AGENT_ROOT = Path(__file__).resolve().parents[1]\n"
        )

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_in_a_checkout_the_search_asks_git_what_is_shipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            home = base / "home"
            home.mkdir()
            # The ignore rules of this checkout decide, not the configuration of the machine:
            # not the user's files, and not the system's (GIT_CONFIG_NOSYSTEM also keeps a
            # file named by GIT_CONFIG_SYSTEM from being read). Nor configuration handed
            # over in the environment. A count of 0 leaves every GIT_CONFIG_KEY_<n> and
            # GIT_CONFIG_VALUE_<n> pair unread, and GIT_CONFIG_PARAMETERS is what `git -c`
            # exports to the commands it starts. Some machines set such variables, for
            # example to rewrite URLs, and a core.excludesFile given that way would decide
            # what git lists here.
            isolated = {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / "config"),
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_COUNT": "0",
                "GIT_CONFIG_PARAMETERS": "",
            }
            # Variables that point git somewhere else must change nothing. With an object
            # store that does not exist, git would not find the checkout at all.
            elsewhere = {
                "GIT_DIR": str(base / "elsewhere.git"),
                "GIT_WORK_TREE": str(base),
                "GIT_INDEX_FILE": str(base / "elsewhere.index"),
                "GIT_COMMON_DIR": str(base / "elsewhere.git"),
                "GIT_OBJECT_DIRECTORY": str(base / "elsewhere.git" / "objects"),
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
                self.assertEqual(
                    _files_named(agent, "mcp.json", ".mcp.json"), (shipped, GIT_ANSWERED)
                )
                # The agent is the repository itself in a standalone export.
                self.assertEqual(
                    _files_named(checkout, "mcp.json", ".mcp.json"),
                    (
                        sorted(
                            [*(f"agent/{path}" for path in shipped), "mcp.json", "plugin/.mcp.json"]
                        ),
                        GIT_ANSWERED,
                    ),
                )
                with mock.patch.dict(os.environ, elsewhere):
                    self.assertEqual(
                        _files_named(agent, "mcp.json", ".mcp.json"), (shipped, GIT_ANSWERED)
                    )
                # A directory in no checkout: git is not allowed to look above it, says
                # so, and the walk answers. Nothing is ignored there, and the machine-local
                # directories are left out.
                plain = base / "plain"
                _write(plain, ".vscode/mcp.json", "node_modules/package/mcp.json")
                with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(base)}):
                    self.assertIsNone(_git(plain, GIT_LISTING))
                    self.assertEqual(
                        _files_named(plain, "mcp.json", ".mcp.json"),
                        ([".vscode/mcp.json"], GIT_NOT_ASKED),
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
            # after it listed a file, one that refuses as git's ownership check does, and
            # one that lists nothing. The search says in each case that the walk answered,
            # and why.
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
                    (str(base / "git-is-not-installed"), *GIT_LISTING[1:]),
                    GIT_NOT_ASKED,
                ),
                ("fails after a listing", (*PYTHON, FAILS_AFTER_A_LISTING), GIT_NOT_ASKED),
                ("refuses the checkout", (*PYTHON, REFUSES_THE_CHECKOUT), GIT_NOT_ASKED),
                ("lists nothing", (*PYTHON, ""), GIT_LISTED_NOTHING),
            ):
                with self.subTest(case):
                    self.assertEqual(
                        _files_named(tree, "mcp.json", ".mcp.json", listing=listing),
                        (walked, answered),
                    )
        # What a reader of a failing guard is told when the walk answered.
        for sentence in (GIT_NOT_ASKED, GIT_LISTED_NOTHING):
            with self.subTest(sentence):
                self.assertIn(
                    "so every directory outside the machine-local ones was walked", sentence
                )
                self.assertIn("a file that git ignores is found that way too", sentence)
        self.assertTrue(GIT_NOT_ASKED.startswith("git could not be asked here ("))
        self.assertIn("its ownership check", GIT_NOT_ASKED)
        self.assertNotIn("walked", GIT_ANSWERED)

    def test_a_guard_that_finds_a_file_says_which_search_answered(self) -> None:
        # Git and the walk do not find the same files, so a failure names the search. Here
        # git refuses as its ownership check does, and the walk finds a file that the
        # agent's own .gitignore leaves out where git answers.
        refused = (*PYTHON, REFUSES_THE_CHECKOUT)
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary) / "tree"
            _write(tree, "README.md", ".vscode/mcp.json", "node_modules/package/mcp.json")
            with self.assertRaises(AssertionError) as failure:
                _require_no_client_configuration(tree, refused)
            self.assertEqual(str(failure.exception), f"found .vscode/mcp.json: {GIT_NOT_ASKED}")
            # The walk alone fails nothing: a copy of the tree without git, or one git
            # refuses to answer for, passes while the walk finds no such file in it. The
            # file under node_modules is still there, and the walk does not look there.
            (tree / ".vscode" / "mcp.json").unlink()
            _require_no_client_configuration(tree, refused)
            _require_no_client_configuration(
                tree, (str(Path(temporary) / "git-is-not-installed"), "ls-files")
            )
            # Where git answers, the message says so. A command that lists two such files
            # stands in for it.
            lists_two = "import sys; sys.stdout.write('docs/mcp.json\\0README.md\\0.mcp.json\\0')"
            with self.assertRaises(AssertionError) as failure:
                _require_no_client_configuration(tree, (*PYTHON, lists_two))
            self.assertEqual(
                str(failure.exception), f"found .mcp.json, docs/mcp.json: {GIT_ANSWERED}"
            )


def _dated_notes() -> tuple[str, str, str]:
    """ADR 0011 up to its two dated notes, and each note, flattened.

    The notes stand after the decision and its confirmation and before the alternatives,
    the older one first. Each runs to the next note or heading and includes its list.
    """

    text = (ROOT / "docs" / "adr" / "0011-requester-vocabulary.md").read_text(encoding="utf-8")
    for day in ("2026-11-23", "2026-11-24"):
        assert len(re.findall(rf"^Note \({day}\):", text, re.M)) == 1, day
    before, after = text.split("\nNote (2026-11-23):", 1)
    assert "\nConfirmed: 2026-11-20," in before
    first, after = after.split("\nNote (2026-11-24):", 1)
    second, rest = after.split("\n## ", 1)
    assert rest.startswith("Alternatives rejected\n"), rest[:40]
    assert "\n## " not in first and "\nNote (" not in first + second
    return (
        _flat(before),
        _flat("Note (2026-11-23):" + first),
        _flat("Note (2026-11-24):" + second),
    )


class EndedDeliveryRecordsTest(unittest.TestCase):
    """What the records say a requester is shown where a state alone would mislead them.

    Once a delivery has ended (2026-11-23), and while an approval gives no package
    (2026-11-24).
    """

    def assert_in_order(self, note: str, sentences: tuple[str, ...]) -> None:
        place = 0
        for sentence in sentences:
            with self.subTest(sentence):
                self.assertIn(sentence, note)
                # In the order of the record, so no sentence is counted for another place.
                self.assertGreaterEqual(note.find(sentence, place), place)
                place = note.find(sentence, place) + len(sentence)
        self.assertTrue(note.startswith(sentences[0]))

    def test_the_vocabulary_record_says_what_the_requester_is_shown(self) -> None:
        before, note, _ = _dated_notes()
        self.assert_in_order(note, ENDED_DELIVERY_NOTE)
        # The note changes what one state shows. It adds no stage: Decision 1 stands.
        self.assertIn("Every pilot state maps to one of the six", before)
        # What it said before the note of 2026-11-24 named a second state.
        self.assertNotIn("every other state shows the stage Decision 5 lists.", note)

    def test_the_vocabulary_record_says_what_an_approval_without_a_package_shows(self) -> None:
        before, earlier, note = _dated_notes()
        self.assert_in_order(note, NO_PACKAGE_NOTE)
        # No stage is added for it either, and the earlier note keeps its own subject.
        self.assertIn("Every pilot state maps to one of the six", before)
        self.assertNotIn("package_can_be_prepared", earlier)
        # The wording that was decided against, because two of the four ways make it false,
        # is quoted once, to say so, and is not what the requester is shown.
        self.assertEqual(note.count("The approval no longer counts because the matter changed"), 1)

    def test_the_plan_names_the_two_exceptions(self) -> None:
        plan = (RESEARCH / "adaptation-plan.md").read_text(encoding="utf-8")
        spec = _flat(_section(plan, "F3. Requester status (built)"))
        place = 0
        for sentence in F3_EXCEPTION:
            with self.subTest(sentence):
                self.assertIn(sentence, spec)
                self.assertGreaterEqual(spec.find(sentence, place), place)
                place = spec.find(sentence, place) + len(sentence)
        # Without the exceptions the acceptance line is no longer true, and one alone is
        # no longer all of them.
        self.assertNotIn("Every pilot state maps to exactly one stage.", spec)
        self.assertNotIn("there is one exception", spec)
        self.assertNotIn('"In review" while its delivery has ended.', spec)


if __name__ == "__main__":
    unittest.main()
