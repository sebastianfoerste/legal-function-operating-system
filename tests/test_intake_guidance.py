"""Guidance from legal on the intake page (ADR 0012).

A team may give the page short texts per request type, each with a record of who
reviewed it for requesters. Nothing is bundled. The texts are static HTML at the top of
their type's section: they stay out of the page script and its data block, so the
checks, the review and the saved file are the same with and without them.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any

from legal_function_os.cli import main as cli_main
from legal_function_os.collaboration_workspace import build_knowledge_portal, build_workflow_library
from legal_function_os.intake_page import (
    GUIDANCE_SCHEMA,
    MAX_GUIDANCE_PASSAGE,
    MAX_GUIDANCE_PER_TYPE,
    IntakeGuidanceError,
    _review_date,
    add_guidance,
    guidance_digest,
    load_intake_guidance,
    render_intake_html,
    render_intake_markdown,
)
from tests.test_intake_page import EXAMPLE, custom_policy, form_for, parse, run_cli

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = json.loads((ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json").read_text(encoding="utf-8"))
SOURCE = "test guidance"
HEADING = "Guidance from legal for this kind of request"
LEAD = (
    "General information, not legal advice about your request. Reading it is optional: you can "
    "still answer the questions and save a request file for legal."
)


def sealed(item: dict[str, Any]) -> dict[str, Any]:
    """``item`` with a review record naming the digest of its text as it stands."""

    item = copy.deepcopy(item)
    if isinstance(item.get("approval"), dict):
        item["approval"]["text_sha256"] = guidance_digest(item)
    return item


def resource(**changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "dpa-template",
        "type": "dpa",
        "title": "Start from the DPA template",
        "passage": "Use the synthetic DPA template and mark every change you need.",
        "source_ref": "Synthetic contracts playbook, section 4",
        "prepared_by": "Alex Example",
        "approval": {"by": "Sam Example", "on": "2026-11-19"},
    }
    item.update(changes)
    return sealed(item)


def guidance(*resources: dict[str, Any], **top: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema": GUIDANCE_SCHEMA,
        "name": "Synthetic guidance for tests",
        "resources": list(resources) if resources else [resource()],
    }
    data.update(top)
    return data


def guided(data: Any = None, form: dict[str, Any] | None = None) -> dict[str, Any]:
    return add_guidance(form_for() if form is None else form, guidance() if data is None else data, SOURCE)


def problems(data: Any, form: dict[str, Any] | None = None) -> list[str]:
    try:
        guided(data, form)
    except IntakeGuidanceError as exc:
        return exc.problems
    return []


class GuidanceFileTests(unittest.TestCase):
    def test_reviewed_texts_are_kept_per_type_in_policy_order(self) -> None:
        vendor = resource(id="vendor-checklist", type="vendor_review", title="Supplier checklist", x_owner="ops")
        vendor["approval"]["x_ticket"] = "SYN-1"
        form = form_for()
        before = copy.deepcopy(form)
        result = guided(guidance(resource(), vendor, x_note="ignored"), form)
        # The form passed in is not changed.
        self.assertEqual(form, before)
        self.assertEqual({k: v for k, v in result.items() if k != "guidance"}, form)
        self.assertEqual(result["guidance"]["name"], "Synthetic guidance for tests")
        # Types follow the policy (vendor_review before dpa), and only the format's keys are kept.
        self.assertEqual(list(result["guidance"]["types"]), ["vendor_review", "dpa"])
        kept = result["guidance"]["types"]["vendor_review"][0]
        self.assertEqual(list(kept), ["id", "type", "title", "passage", "source_ref", "prepared_by", "approval"])
        self.assertEqual(list(kept["approval"]), ["by", "on", "text_sha256"])
        self.assertEqual(result["guidance"]["types"]["dpa"], [resource()])

    def test_the_digest_binds_what_a_requester_reads(self) -> None:
        item = resource()
        canonical = (
            '{"passage":"Use the synthetic DPA template and mark every change you need.",'
            '"source_ref":"Synthetic contracts playbook, section 4","title":"Start from the DPA template","type":"dpa"}'
        )
        self.assertEqual(guidance_digest(item), hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        # Text outside ASCII is digested as UTF-8, and a missing type as null.
        umlaut = {"title": "Über", "passage": "P", "source_ref": "S"}
        self.assertEqual(
            guidance_digest(umlaut),
            hashlib.sha256('{"passage":"P","source_ref":"S","title":"Über","type":null}'.encode()).hexdigest(),
        )
        # Every key a requester reads changes it; nothing else does.
        for key in ("type", "title", "passage", "source_ref"):
            self.assertNotEqual(guidance_digest({**item, key: item[key] + " "}), guidance_digest(item), key)
        for key, value in (("id", "other"), ("prepared_by", "Kim Example"), ("approval", {}), ("x_note", "n")):
            self.assertEqual(guidance_digest({**item, key: value}), guidance_digest(item), key)

    def test_a_text_changed_after_its_review_is_refused_with_its_digest(self) -> None:
        for key, value in (
            ("passage", "Use the synthetic DPA template and mark every change you need. "),
            ("title", "Start from the DPA template!"),
            ("source_ref", "Synthetic contracts playbook, section 5"),
            ("type", "vendor_review"),
        ):
            with self.subTest(key=key):
                changed = {**resource(), key: value}
                self.assertEqual(
                    problems(guidance(changed)),
                    [
                        "resources[0].approval.text_sha256: does not match the text (type, title, passage "
                        "and source_ref), so the review record is not for this text; the text now has the "
                        f"digest {guidance_digest(changed)}. Have this text reviewed and record that review"
                    ],
                )
        # A digest that is not one is named, with the digest the text has now.
        for value, shown in (
            (guidance_digest(resource()).upper(), repr(guidance_digest(resource()).upper())),
            ("abc", "'abc'"),
            (42, "a number"),
            (None, "null"),
        ):
            with self.subTest(value=value):
                item = resource()
                item["approval"]["text_sha256"] = value
                self.assertEqual(
                    problems(guidance(item)),
                    [
                        "resources[0].approval.text_sha256: expected a SHA-256 digest as 64 lower-case hex "
                        f"characters, got {shown}; the text now has the digest {guidance_digest(item)}"
                    ],
                )
        # A record with no digest yet is told the digest of the text as it stands, which
        # the reviewer records after reading that text.
        unsealed = resource()
        del unsealed["approval"]["text_sha256"]
        self.assertEqual(
            problems(guidance(unsealed)),
            [f"resources[0].approval.text_sha256: missing; the text now has the digest {guidance_digest(unsealed)}"],
        )
        # Text that has its own problem gives no digest to compare.
        broken = resource()
        broken["title"] = " "
        self.assertEqual(problems(guidance(broken)), ["resources[0].title: expected non-empty text, got text"])
        broken["approval"]["text_sha256"] = "abc"
        self.assertEqual(
            problems(guidance(broken))[1],
            "resources[0].approval.text_sha256: expected a SHA-256 digest as 64 lower-case hex characters, got 'abc'",
        )

    def test_the_person_who_prepared_a_text_cannot_record_its_review(self) -> None:
        for by in (
            "Alex Example",
            "alex example",
            "ALEX EXAMPLE",
            " Alex  Example ",
            "Alex Example",
            "Alex\tExample",
            "Alex​ Example",
            "﻿Alex Example",
            "Ａlex Example",  # a fullwidth A
        ):
            with self.subTest(by=by):
                item = resource()
                item["approval"]["by"] = by
                self.assertEqual(
                    problems(guidance(item)),
                    [
                        f"resources[0].approval.by: {by!r} is also who prepared the text (prepared_by); "
                        "another person records the review"
                    ],
                )
        item = resource()
        item["approval"]["by"] = "Alex Examples"
        self.assertEqual(problems(guidance(item)), [])

    def test_the_review_date_is_a_calendar_date(self) -> None:
        for value in ("2026-11-19", "2024-02-29", "0001-01-01", "9999-12-31", "2099-01-01", "1999-12-31"):
            self.assertTrue(_review_date(value), value)
        for value in (
            "2026-02-30", "2025-02-29", "2026-13-01", "2026-00-10", "0000-01-01", "26-11-19", "2026-1-19",
            "2026/11/19", "20261119", "2026-W47-4", "2026-323", "2026-11-19T00:00", " 2026-11-19",
            "2026-11-19 ", "2026-11-19\n", "２０２６-11-19", "٢026-11-19", "",
            20261119, None, True, ["2026-11-19"],
        ):
            self.assertFalse(_review_date(value), value)
        item = resource()
        item["approval"]["on"] = "2026-02-30"
        self.assertEqual(
            problems(guidance(item)),
            ["resources[0].approval.on: expected the date of the review as YYYY-MM-DD, got '2026-02-30'"],
        )
        item["approval"]["on"] = 20261119
        self.assertEqual(
            problems(guidance(item)),
            ["resources[0].approval.on: expected the date of the review as YYYY-MM-DD, got a number"],
        )

    def test_no_text_holds_a_link_or_an_unpaired_surrogate(self) -> None:
        link = "must not contain a link (http:// or https://); the page is self-contained"
        surrogate = "contains an unpaired surrogate; the page could not save it"
        for key in ("id", "type", "title", "passage", "source_ref", "prepared_by"):
            for value, message in (("See HTTPS://wiki.example", link), ("a\ud800b", surrogate)):
                with self.subTest(key=key, value=value):
                    found = problems(guidance(resource(**{key: value})))
                    self.assertEqual(found, [f"resources[0].{key}: {message}"])
        for value, message in (("See http://wiki.example", link), ("a\udc00b", surrogate)):
            item = resource()
            item["approval"]["by"] = value
            self.assertEqual(problems(guidance(item)), [f"resources[0].approval.by: {message}"])
            self.assertEqual(problems(guidance(name=value)), [f"name: {message}"])

    def test_passages_and_resources_per_type_are_limited(self) -> None:
        self.assertEqual(problems(guidance(resource(passage="p" * MAX_GUIDANCE_PASSAGE))), [])
        self.assertEqual(
            problems(guidance(resource(passage="p" * (MAX_GUIDANCE_PASSAGE + 1)))),
            [
                f"resources[0].passage: is {MAX_GUIDANCE_PASSAGE + 1} characters long; the page shows at most "
                f"{MAX_GUIDANCE_PASSAGE}. Shorten it, and name the longer text in source_ref"
            ],
        )
        three = [resource(id=f"dpa-{n}", title=f"DPA point {n}") for n in range(MAX_GUIDANCE_PER_TYPE)]
        others = [resource(id=f"ip-{n}", type="ip", title=f"IP point {n}") for n in range(MAX_GUIDANCE_PER_TYPE)]
        self.assertEqual(problems(guidance(*three, *others)), [])
        self.assertEqual(len(guided(guidance(*three, *others))["guidance"]["types"]["dpa"]), 3)
        fourth = resource(id="dpa-3", title="DPA point 3")
        self.assertEqual(
            problems(guidance(*three, *others, fourth, resource(id="dpa-4", title="DPA point 4"))),
            [
                f"resources[{n}].type: 'dpa' already has 3 resources; the page shows at most 3 for one request type"
                for n in (6, 7)
            ],
        )

    def test_ids_are_unique_and_titles_in_a_type_read_differently(self) -> None:
        self.assertEqual(
            problems(guidance(resource(), resource(type="ip", title="Brand checklist"))),
            ["resources[1].id: 'dpa-template' is used twice (also resources[0])"],
        )
        for twin in ("Start from the DPA template", "start from the dpa template", "Start  from the DPA​ template "):
            with self.subTest(twin=twin):
                self.assertEqual(
                    problems(guidance(resource(), resource(id="second", title=twin))),
                    [
                        f"resources[1].title: {twin!r} reads the same as the title of resources[0] for this "
                        "type; give each its own title"
                    ],
                )
        # The same title under another type is fine.
        self.assertEqual(problems(guidance(resource(), resource(id="second", type="ip"))), [])

    def test_keys_are_checked_and_extensions_skipped(self) -> None:
        item = resource(titel="Typo", x_owner="ops", _comment="kept out")
        item["approval"]["x_ticket"] = "SYN-1"
        item["approval"]["date"] = "2026-11-19"
        self.assertEqual(
            problems(guidance(item, extra=True, x_note="n")),
            [
                "extra: unknown key; prefix your own keys with x_",
                "resources[0].titel: unknown key (did you mean 'title'?); prefix your own keys with x_",
                "resources[0].approval.date: unknown key; prefix your own keys with x_",
            ],
        )

    def test_the_shape_is_checked(self) -> None:
        self.assertEqual(problems([]), ["expected an object, got a list"])
        self.assertEqual(
            problems({}),
            ["schema: missing", "name: missing", "resources: missing"],
        )
        self.assertEqual(
            problems(guidance(schema="legal-function-os.intake-questions.v1", name=" ", resources={})),
            [
                "schema: expected 'legal-function-os.intake-guidance.v1', got 'legal-function-os.intake-questions.v1'",
                "name: expected non-empty text, got text",
                "resources: expected a list of resources, got an object",
            ],
        )
        no_record = resource(id="a", title="A")
        del no_record["approval"], no_record["prepared_by"]
        bad_record = resource(id="b", title="B", approval="Sam Example, 2026-11-19")
        empty_record = {**resource(id="c", title="C"), "approval": {}}
        self.assertEqual(
            problems(guidance("dpa", no_record, bad_record, empty_record, resource(id=7, title=None))),
            [
                "resources[0]: expected an object, got text",
                "resources[1].prepared_by: missing",
                "resources[1].approval: missing",
                "resources[2].approval: expected an object, got text",
                "resources[3].approval.by: missing",
                "resources[3].approval.on: missing",
                f"resources[3].approval.text_sha256: missing; the text now has the digest {guidance_digest(empty_record)}",
                "resources[4].id: expected non-empty text, got a number",
                "resources[4].title: expected non-empty text, got null",
            ],
        )

    def test_a_knowledge_portal_document_is_refused(self) -> None:
        portal = build_knowledge_portal(REQUESTS, build_workflow_library())
        # The portal's own output is unchanged: approved is a flag set in code.
        self.assertEqual(portal["schema"], "portal.share.v1")
        self.assertEqual(
            {tuple(r) for r in portal["resources"]}, {("id", "title", "passage", "source_ref", "approved")}
        )
        flag = "a flag is not a review record; give prepared_by and approval (by, on, text_sha256) instead"
        found = problems(portal)
        for message in (
            "schema: expected 'legal-function-os.intake-guidance.v1', got 'portal.share.v1'",
            "local_only: unknown key; prefix your own keys with x_",
            f"approved: {flag}",
            "name: missing",
        ):
            self.assertIn(message, found)
        for index in range(len(portal["resources"])):
            for message in (f"approved: {flag}", "prepared_by: missing", "approval: missing"):
                self.assertIn(f"resources[{index}].{message}", found)
        # Its resources, given a type in a guidance file, are refused just the same.
        typed = [{**r, "type": "dpa"} for r in portal["resources"][:1]]
        self.assertEqual(
            problems(guidance(*typed)),
            [f"resources[0].approved: {flag}", "resources[0].prepared_by: missing", "resources[0].approval: missing"],
        )

    def test_a_resource_the_page_cannot_place_is_a_note(self) -> None:
        loose = resource(id="loose", title="No type")
        del loose["type"]
        loose = sealed(loose)
        typo = resource(id="typo", type="dpa ", title="Typo")
        form = guided(guidance(loose, typo, resource()))
        self.assertEqual(
            form["notes"],
            [
                "resources[0] ('loose') has no type, so the page does not show it",
                "resources[1] ('typo'): the policy has no request type 'dpa ' (did you mean 'dpa'?), so the page "
                "does not show it",
            ],
        )
        self.assertEqual(form["guidance"]["types"], {"dpa": [resource()]})
        # A type another policy has is shown only under that policy.
        ip = resource(id="ip", type="ip", title="Brands")
        self.assertEqual(guided(guidance(ip))["guidance"]["types"], {"ip": [ip]})
        custom = guided(guidance(ip), form_for(policy=custom_policy()))
        self.assertEqual(custom["guidance"]["types"], {})
        self.assertEqual(custom["notes"][-1], "resources[0] ('ip'): the policy has no request type 'ip', so the page does not show it")
        # A file with no resources says so; the page shows none.
        empty = guided(guidance(resources=[]))
        self.assertEqual(empty["guidance"]["types"], {})
        self.assertEqual(empty["notes"], ["the guidance file lists no resources, so the page shows none"])

    def test_every_problem_is_reported_at_once(self) -> None:
        stale = {**resource(), "passage": "Changed after the review."}
        found = problems(guidance(stale, resource(id="dpa-template", title="Second", passage="x" * 900), name=""))
        self.assertEqual(len(found), 4, found)
        self.assertEqual(found[0], "name: expected non-empty text, got text")
        self.assertTrue(found[1].startswith("resources[0].approval.text_sha256: does not match the text"))
        self.assertTrue(found[2].startswith("resources[1].passage: is 900 characters long"))
        self.assertEqual(found[3], "resources[1].id: 'dpa-template' is used twice (also resources[0])")

    def test_unreadable_files_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name, data, message in (
                ("missing.json", None, "cannot read the file: No such file or directory"),
                ("latin.json", "{\"name\": \"für\"}".encode("latin-1"), "cannot read the file: it is not UTF-8 text"),
                ("broken.json", b"{", "not valid JSON: "),
            ):
                path = Path(tmp) / name
                if data is not None:
                    path.write_bytes(data)
                with self.assertRaises(IntakeGuidanceError) as caught:
                    load_intake_guidance(str(path))
                self.assertEqual(caught.exception.source, str(path))
                self.assertTrue(caught.exception.problems[0].startswith(message), caught.exception.problems)
            path = Path(tmp) / "bom.json"
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps(guidance()).encode("utf-8"))
            self.assertEqual(load_intake_guidance(str(path)), (guidance(), str(path)))


def visible_text(page: str) -> str:
    return " ".join(" ".join(parse(page).text).split())


class GuidancePageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plain_form = form_for()
        self.plain = render_intake_html(self.plain_form)
        self.vendor = resource(id="vendor", type="vendor_review", title="Supplier checklist", passage="Line one.\nLine two.")
        self.form = guided(guidance(resource(), self.vendor))
        self.page = render_intake_html(self.form)

    def test_guidance_is_static_text_at_the_top_of_its_type(self) -> None:
        self.assertIn(
            '<h2 id="type-2-h">Data processing agreement (DPA): a few more questions</h2>'
            '<div class="guidance" role="note" aria-labelledby="type-2-guidance-h">'
            f'<h3 id="type-2-guidance-h">{HEADING}</h3><p>{LEAD}</p>'
            "<h4>Start from the DPA template</h4>"
            '<p class="passage">Use the synthetic DPA template and mark every change you need.</p>'
            '<p class="source">Source: Synthetic contracts playbook, section 4. Legal\'s guidance file records '
            "that Sam Example reviewed this text for requesters on 2026-11-19.</p></div>",
            self.page,
        )
        self.assertIn('<p class="passage">Line one.\nLine two.</p>', self.page)
        self.assertIn("Questions: Bundled synthetic intake questions. Guidance: Synthetic guidance for tests.</footer>", self.page)
        self.assertEqual(self.page.count('<div class="guidance"'), 2)
        # No link, control or focus stop inside the guidance.
        for block in re.findall(r'<div class="guidance".*?</div>', self.page, re.S):
            for tag in ("<a", "<button", "<input", "<textarea", "<select", "tabindex", "href"):
                self.assertNotIn(tag, block)
        parsed = parse(self.page)
        ids = [a["id"] for _, a in parsed.elements if a.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        for _, attrs in parsed.elements:
            for ref in (attrs.get("aria-labelledby") or "").split():
                self.assertIn(ref, ids)

    def test_guidance_stays_out_of_the_script_and_its_data(self) -> None:
        plain, page = parse(self.plain), parse(self.page)
        self.assertEqual(page.scripts, plain.scripts)
        self.assertEqual(page.style, plain.style)
        csp = [a for t, a in page.elements if t == "meta" and a.get("http-equiv")]
        self.assertEqual(csp, [a for t, a in plain.elements if t == "meta" and a.get("http-equiv")])
        # Without its guidance blocks and footer words, the page is the plain page exactly.
        stripped = re.sub(r'<div class="guidance".*?</div>', "", self.page, flags=re.S)
        self.assertEqual(stripped.replace(" Guidance: Synthetic guidance for tests.", ""), self.plain)
        self.assertNotIn("guidance", page.scripts[0][1])

    def test_without_guidance_the_page_shows_none(self) -> None:
        self.assertNotIn('<div class="guidance"', self.plain)
        self.assertNotIn("Guidance", visible_text(self.plain))
        self.assertEqual(self.plain, EXAMPLE.read_text(encoding="utf-8"))
        # A type with no guidance shows none: here only vendor_review has any.
        page = render_intake_html(guided(guidance(self.vendor)))
        self.assertEqual(page.count('<div class="guidance"'), 1)
        self.assertIn(
            '<h2 id="type-2-h">Data processing agreement (DPA): a few more questions</h2><div class="field"', page
        )
        self.assertIn('<h2 id="type-1-h">Checking a new supplier: a few more questions</h2><div class="guidance"', page)
        empty = render_intake_html(guided(guidance(resources=[])))
        self.assertNotIn('<div class="guidance"', empty)

    def test_team_text_is_escaped(self) -> None:
        hostile = resource(
            title="<b>Bold</b> & </div>", passage="</div><script>x</script>", source_ref="<i>S</i>",
            prepared_by="<i>P</i>", approval={"by": "<b>R</b>", "on": "2026-11-19"},
        )
        page = render_intake_html(guided(guidance(hostile, name="<i>Guide</i>")))
        parsed = parse(page)
        self.assertNotIn("b", [t for t, _ in parsed.elements])
        self.assertNotIn("i", [t for t, _ in parsed.elements])
        self.assertEqual(len(parsed.scripts), 2)
        text = visible_text(page)
        for raw in ("<b>Bold</b> & </div>", "</div><script>x</script>", "Source: <i>S</i>.", "that <b>R</b> reviewed", "Guidance: <i>Guide</i>."):
            self.assertIn(raw, text)

    def test_the_words_the_page_adds_never_claim_an_approval(self) -> None:
        text = visible_text(self.page)
        for sentence in (
            HEADING,
            LEAD,
            "Source: Synthetic contracts playbook, section 4. Legal's guidance file records that Sam Example "
            "reviewed this text for requesters on 2026-11-19.",
            "Guidance: Synthetic guidance for tests.",
        ):
            self.assertIn(sentence, text)
        # The words the guidance adds, once the team's own are taken out, are the page's.
        blocks = re.findall(r'<div class="guidance".*?</div>', self.page, re.S)
        own = " ".join(visible_text(block) for block in blocks) + " Guidance: "
        for item in (resource(), self.vendor):
            for value in (item["title"], " ".join(item["passage"].split()), item["source_ref"], item["approval"]["by"]):
                own = own.replace(value, "")
        self.assertIn("reviewed this text for requesters on", own)
        for word in ("approve", "approved", "approval", "approves", "approving", "authenticated", "signed",
                     "verified", "certified", "advice from legal", "send", "submit", "decide"):
            self.assertIsNone(re.search(rf"\b{word}\b", own, re.IGNORECASE), word)
        self.assertNotIn("approv", visible_text(self.plain).lower())

    def test_a_link_never_reaches_the_page(self) -> None:
        form = guided()
        form["guidance"]["types"]["dpa"][0]["passage"] = "See https://wiki.example"
        with self.assertRaises(ValueError):
            render_intake_html(form)
        with self.assertRaises(ValueError):
            render_intake_html({**guided(), "guidance": {"name": "http://x", "types": {}}})

    def test_the_question_sheet_lists_guidance_per_type(self) -> None:
        sheet = render_intake_markdown(self.form)
        self.assertIn(
            "Value bands and request types follow the policy: Default illustrative policy. "
            "Guidance: Synthetic guidance for tests.\n",
            sheet,
        )
        self.assertIn(
            "Also required for this type: Other party.\n\nGuidance shown above these questions:\n\n"
            "- **Start from the DPA template** (`dpa-template`): Use the synthetic DPA template and mark every "
            "change you need. Source: Synthetic contracts playbook, section 4. Prepared by Alex Example; "
            f"reviewed for requesters by Sam Example on 2026-11-19 (text_sha256 `{guidance_digest(resource())}`).\n\n"
            "1. **Who decides what the data is used for?**",
            sheet,
        )
        self.assertIn("- **Supplier checklist** (`vendor`): Line one. Line two. Source:", sheet)
        self.assertEqual(sheet.count("Guidance shown above these questions:"), 2)
        self.assertNotIn("Guidance", render_intake_markdown(self.plain_form))


class GuidanceCliTests(unittest.TestCase):
    def write(self, tmp: str, data: Any, name: str = "guidance.json") -> Path:
        path = Path(tmp) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_out_writes_the_page_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            loose = sealed({k: v for k, v in resource(id="loose").items() if k != "type"})
            path = self.write(tmp, guidance(resource(), loose))
            code, out, err = run_cli(["intake-page", "--guidance", str(path), "--out", tmp])
            self.assertEqual((code, out), (0, ""), err)
            self.assertIn("note: resources[1] ('loose') has no type, so the page does not show it\n", err)
            page = (Path(tmp) / "intake-page.html").read_text(encoding="utf-8")
            self.assertEqual(page, render_intake_html(add_guidance(form_for(), guidance(resource(), loose), str(path))))
            self.assertIn(HEADING, page)

    def test_prints_the_sheet_or_the_form_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, guidance())
            expected = add_guidance(form_for(), guidance(), str(path))
            code, out, _ = run_cli(["intake-page", "--guidance", str(path), "--format", "json"])
            self.assertEqual((code, json.loads(out)), (0, expected))
            code, out, _ = run_cli(["intake-page", "--guidance", str(path)])
            self.assertEqual((code, out), (0, render_intake_markdown(expected)))

    def test_bad_guidance_stops_before_anything_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item = resource()
            item["approval"]["by"] = "alex example"
            path = self.write(tmp, guidance(item, resource(id="x", title="T", passage="https://x")))
            out_dir = Path(tmp) / "out"
            code, out, err = run_cli(["intake-page", "--guidance", str(path), "--out", str(out_dir)])
            self.assertEqual((code, out), (2, ""))
            self.assertIn(f"error: {path}: resources[0].approval.by: 'alex example' is also who prepared", err)
            self.assertIn(f"error: {path}: resources[1].passage: must not contain a link", err)
            self.assertTrue(err.endswith("The intake guidance cannot be used. Nothing was written.\n"), err)
            self.assertFalse(out_dir.exists())
            code, out, err = run_cli(["intake-page", "--guidance", str(Path(tmp) / "nope.json"), "--out", str(out_dir)])
            self.assertEqual((code, out), (2, ""))
            self.assertIn("cannot read the file", err)
            self.assertFalse(out_dir.exists())

    def test_the_help_says_nothing_is_bundled(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            cli_main(["intake-page", "--help"])
        self.assertEqual(caught.exception.code, 0)
        help_text = " ".join(out.getvalue().split())
        self.assertIn("--guidance PATH", help_text)
        self.assertIn("Default: none; no guidance is bundled.", help_text)


if __name__ == "__main__":
    unittest.main()
