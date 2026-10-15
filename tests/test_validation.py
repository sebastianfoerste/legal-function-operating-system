"""Bad input is reported before any decision instead of silently changing the outcome."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from legal_function_os.cli import main as cli_main
from legal_function_os.rules import ROUTING, URGENCIES, VALUE_BANDS, decide
from legal_function_os.validation import (
    BOOLEAN_FIELDS,
    request_schema,
    suggest,
    validate_request,
    validate_requests,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json"
BASE = {"id": "REQ-1", "title": "Enterprise MSA (synthetic)", "type": "commercial_contract"}


def issues_for(**fields):
    return validate_request({**BASE, **fields}, 0)


def run_cli(argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    patch = mock.patch("sys.stdin", io.StringIO(stdin)) if stdin is not None else contextlib.nullcontext()
    with patch, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(argv)
    return code, out.getvalue(), err.getvalue()


class CapitalisedValueBand(unittest.TestCase):
    """'>1M' used to mean 'no value': LOW risk and Reviewer-only approval."""

    def test_validation_rejects_it_and_suggests_the_band(self):
        [issue] = issues_for(value_band=">1M")
        self.assertEqual((issue.severity, issue.field), ("error", "value_band"))
        self.assertIn("did you mean '>1m'", issue.message)

    def test_the_rules_no_longer_read_it_as_no_value(self):
        with self.assertRaisesRegex(ValueError, "unknown value_band '>1M'"):
            decide({**BASE, "value_band": ">1M"})
        self.assertEqual(decide({**BASE, "value_band": ">1m"}).risk, "HIGH")

    def test_cli_exits_2_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "requests.json"
            source.write_text(json.dumps([{**BASE, "value_band": ">1M"}]), encoding="utf-8")
            out_dir = Path(tmp) / "out"
            code, stdout, stderr = run_cli(["--input", str(source), "--out", str(out_dir)])
            self.assertEqual(code, 2)
            self.assertFalse(out_dir.exists())
        self.assertEqual(stdout, "")
        self.assertIn("error: request 1 (REQ-1): value_band: '>1M'", stderr)
        self.assertIn("1 error, 0 warnings in 1 request. Nothing was written.", stderr)


class FieldChecks(unittest.TestCase):
    def test_bundled_requests_are_clean(self):
        report = validate_requests(json.loads(SAMPLE.read_text(encoding="utf-8")))
        self.assertEqual(report.issues, ())
        self.assertTrue(report.ok)

    def test_unknown_urgency_is_an_error_and_no_longer_means_standard(self):
        [issue] = issues_for(urgency="urgent")
        self.assertEqual((issue.severity, issue.field), ("error", "urgency"))
        with self.assertRaisesRegex(ValueError, "unknown urgency"):
            decide({**BASE, "urgency": "urgent"})

    def test_urgency_is_matched_exactly(self):
        [issue] = issues_for(urgency="High")
        self.assertIn("did you mean 'high'", issue.message)

    def test_quoted_booleans_are_errors_with_the_intended_value(self):
        for field in BOOLEAN_FIELDS:
            with self.subTest(field=field):
                [issue] = issues_for(**{field: "no"})
                self.assertEqual((issue.severity, issue.field), ("error", field))
                self.assertIn("write false", issue.message)
        [issue] = issues_for(personal_data="Yes")
        self.assertIn("write true", issue.message)

    def test_required_fields_and_text_types(self):
        issues = validate_request({"type": "dpa", "title": " ", "counterparty": 7}, 2)
        self.assertEqual(
            [(issue.field, issue.message) for issue in issues],
            [
                ("id", "missing; every request needs one"),
                ("title", "missing; every request needs one"),
                ("counterparty", "expected a string, got a number"),
            ],
        )
        self.assertTrue(all(issue.index == 2 for issue in issues))

    def test_null_optional_fields_take_their_defaults(self):
        nulls = {
            "value_band": None,
            "urgency": None,
            "counterparty": None,
            **dict.fromkeys(BOOLEAN_FIELDS),
        }
        self.assertEqual(issues_for(**nulls), [])
        decision = decide({**BASE, **nulls})
        self.assertEqual((decision.risk, decision.priority), ("LOW", "P3_standard"))
        self.assertEqual(decision.approval_chain, ["Reviewer"])

    def test_misspelled_fields_are_errors_but_own_fields_pass(self):
        for key, meant in (
            ("valueBand", "value_band"),
            ("value-band", "value_band"),
            ("uncapped_liabilty", "uncapped_liability"),
            ("Personal Data", "personal_data"),
            ("sla_breach", "sla_breached"),
        ):
            with self.subTest(key=key):
                [issue] = issues_for(**{key: True})
                self.assertEqual((issue.severity, issue.field), ("error", key))
                self.assertIn(f"did you mean {meant!r}", issue.message)
        self.assertEqual(
            issues_for(x_value_band="kept", _internal=1, description="d", facts=["f"], deadline="2026-12-01"),
            [],
        )


class UnknownTypes(unittest.TestCase):
    def test_unknown_type_is_a_warning_and_needs_manual_triage(self):
        [issue] = issues_for(type="Fundraising")
        self.assertEqual((issue.severity, issue.field), ("warning", "type"))
        self.assertIn("did you mean 'fundraising'", issue.message)
        decision = decide({**BASE, "type": "regulatory"})
        self.assertEqual(decision.queue, "General")
        self.assertIn(
            "Request type 'regulatory' is not in the routing table: needs manual triage.",
            decision.rationale,
        )

    def test_missing_type_needs_manual_triage(self):
        request = {"id": "REQ-2", "title": "Untyped"}
        [issue] = validate_request(request, 0)
        self.assertEqual((issue.severity, issue.field), ("warning", "type"))
        self.assertIn("No request type given: needs manual triage.", decide(request).rationale)

    def test_known_types_carry_no_triage_note(self):
        for request in json.loads(SAMPLE.read_text(encoding="utf-8")):
            self.assertFalse(any("manual triage" in line for line in decide(request).rationale))

    def test_cli_warns_and_still_produces_the_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "requests.json"
            source.write_text(json.dumps([{**BASE, "type": "regulatory"}]), encoding="utf-8")
            code, stdout, stderr = run_cli(["--input", str(source)])
        self.assertEqual(code, 0)
        self.assertIn("| REQ-1 | Enterprise MSA (synthetic) | LOW | P3_standard | General |", stdout)
        self.assertIn("warning: request 1 (REQ-1): type: 'regulatory'", stderr)


class WholeInput(unittest.TestCase):
    def test_duplicate_ids_are_errors(self):
        report = validate_requests([BASE, {**BASE, "title": "Second"}])
        [issue] = report.errors
        self.assertEqual((issue.index, issue.field), (1, "id"))
        self.assertIn("same id as request 1", issue.message)

    def test_shape_errors(self):
        self.assertFalse(validate_requests({"id": "REQ-1"}).ok)
        report = validate_requests([BASE, "REQ-2"])
        self.assertEqual([issue.index for issue in report.errors], [1])
        empty = validate_requests([])
        self.assertTrue(empty.ok)
        self.assertEqual(len(empty.warnings), 1)

    def test_report_serialises(self):
        report = validate_requests([{**BASE, "value_band": ">1M"}])
        payload = report.to_dict()
        self.assertEqual(payload["schema"], "legal-function-os.validation-report.v1")
        self.assertFalse(payload["valid"])
        self.assertEqual(payload["issues"][0]["field"], "value_band")

    def test_cli_reads_standard_input(self):
        code, stdout, _ = run_cli(["--input", "-"], stdin=json.dumps([BASE]))
        self.assertEqual(code, 0)
        self.assertIn("| REQ-1 |", stdout)

    def test_cli_reports_unreadable_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.json"
            broken.write_text("[{", encoding="utf-8")
            code, _, stderr = run_cli(["--input", str(broken)])
            self.assertEqual(code, 2)
            self.assertIn("is not valid JSON", stderr)
            code, _, stderr = run_cli(["--input", str(Path(tmp) / "missing.json")])
            self.assertEqual(code, 2)
            self.assertIn("cannot read", stderr)


class Suggestions(unittest.TestCase):
    def test_suggest(self):
        self.assertEqual(suggest(">1M", VALUE_BANDS), ">1m")
        self.assertEqual(suggest("Commercial contract", list(ROUTING)), "commercial_contract")
        self.assertEqual(suggest("blocked", URGENCIES), "blocker")
        self.assertIsNone(suggest("zzzz", URGENCIES))


class PublishedContract(unittest.TestCase):
    def test_committed_schema_matches_the_code(self):
        committed = json.loads(
            (ROOT / "contracts" / "legal-request.v1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(committed, request_schema(), "run python scripts/build_contracts.py")

    def test_schema_enumerates_what_the_rules_accept(self):
        properties = request_schema()["properties"]
        self.assertEqual(properties["value_band"]["enum"], [*VALUE_BANDS, None])
        self.assertEqual(properties["urgency"]["enum"], [*URGENCIES, None])
        self.assertEqual(properties["type"]["examples"], list(ROUTING))
        for field in BOOLEAN_FIELDS:
            self.assertEqual(properties[field]["type"], ["boolean", "null"])
        sample_keys = {key for request in json.loads(SAMPLE.read_text(encoding="utf-8")) for key in request}
        self.assertEqual(sample_keys, set(properties))


if __name__ == "__main__":
    unittest.main()
