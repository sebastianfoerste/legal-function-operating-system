"""Message drafts (F11): a synthetic message export becomes request drafts for legal.

Values are copied only from labelled lines; every decision field the message does not
state is left blank, so validate and triage refuse the draft until legal fills it. The
command reads a file and sends nothing. It is a CLI command, never an MCP tool.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

import legal_function_os.message_drafts as module
from legal_function_os import mcp_server
from legal_function_os.cli import main as cli_main
from legal_function_os.intake_page import ALWAYS_ASKED
from legal_function_os.message_drafts import (
    BUNDLED_SOURCE,
    MessageExportError,
    build_message_drafts,
    draft_request,
    labelled_values,
    load_message_export,
    read_messages,
    render_message_drafts_json,
    render_message_drafts_markdown,
    summary_line,
    write_message_drafts,
)
from legal_function_os.policy import default_policy, parse_policy
from legal_function_os.rules import decide
from legal_function_os.validation import (
    AUXILIARY_FIELDS,
    REQUEST_FIELDS,
    misspelled_field,
    validate_requests,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
BUNDLED = ROOT / "src" / "legal_function_os" / "data" / "sample_messages.jsonl"
DECISION_FIELDS = ("value_band", "personal_data", "non_eea_transfer", "uncapped_liability", "urgency")


def line(**fields: Any) -> str:
    message = {"message_id": "syn-msg-1", "sender": "syn-ana", "text": "Hello"}
    message.update(fields)
    return json.dumps({k: v for k, v in message.items() if v is not None})


def problems(text: str) -> list[str]:
    with unittest.TestCase().assertRaises(MessageExportError) as caught:
        read_messages(text, "export.jsonl")
    return caught.exception.problems


def drafts_of(*texts: str, subject: str | None = None) -> dict[str, Any]:
    lines = [line(message_id=f"syn-msg-{n}", text=text, subject=subject) for n, text in enumerate(texts, 1)]
    return build_message_drafts(read_messages("\n".join(lines), "export.jsonl"))


def one(text: str, subject: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    result = drafts_of(text, subject=subject)
    return result["drafts"][0], result["messages"][0]


def bundled() -> dict[str, Any]:
    text, source = load_message_export()
    return build_message_drafts(read_messages(text, source), source=source)


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli_main(argv)
        except SystemExit as exit_:
            code = int(exit_.code or 0)
    return code, out.getvalue(), err.getvalue()


class ReadExport(unittest.TestCase):
    def test_bundled_export_reads_six_messages(self) -> None:
        text, source = load_message_export()
        self.assertEqual(source, BUNDLED_SOURCE)
        messages = read_messages(text, source)
        self.assertEqual([m.line for m in messages], [1, 2, 3, 4, 5, 6])
        self.assertTrue(all(m.sender.startswith("syn-") for m in messages))
        self.assertTrue(all("@" not in m.channel and "://" not in m.text for m in messages))

    def test_blank_lines_are_skipped_and_problems_name_the_physical_line(self) -> None:
        text = "\n" + line() + "\r\n\n   \n" + line(message_id="syn-msg-2", sender="ana") + "\n"
        self.assertEqual(len(problems(text)), 1)
        self.assertTrue(problems(text)[0].startswith("line 5: sender: 'ana' is not a synthetic sender"))
        messages = read_messages("\n" + line() + "\r\n\n" + line(message_id="syn-msg-2"), "x")
        self.assertEqual([m.line for m in messages], [2, 4])

    def test_a_line_that_is_not_json_names_its_line(self) -> None:
        self.assertEqual(
            problems(line() + "\n{not json}"),
            ["line 2: not valid JSON: Expecting property name enclosed in double quotes (column 2)"],
        )

    def test_a_json_array_of_requests_is_pointed_at_validate(self) -> None:
        for text in ('[{"id": "REQ-1", "title": "T"}]', '  \n[\n  {"id": "REQ-1"}\n]\n'):
            with self.subTest(text=text):
                (problem,) = problems(text)
                self.assertIn("a JSON array, not JSON lines", problem)
                self.assertIn("a JSON array of requests goes to validate or triage, not here", problem)

    def test_a_line_that_is_not_an_object_is_refused(self) -> None:
        self.assertEqual(
            problems('"text"\n42\nnull'),
            [
                "line 1: expected a JSON object (one message per line), got a string",
                "line 2: expected a JSON object (one message per line), got a number",
                "line 3: expected a JSON object (one message per line), got null",
            ],
        )

    def test_required_keys_must_be_present_and_not_blank(self) -> None:
        self.assertEqual(
            problems(json.dumps({"sender": "syn-ana", "message_id": " ", "text": "　﻿", "subject": None})),
            [
                "line 1: message_id: missing; every message needs one",
                "line 1: text: missing; every message needs one",
            ],
        )
        self.assertEqual(problems(json.dumps({"message_id": "m", "text": "t"})), ["line 1: sender: missing; every message needs one"])

    def test_known_keys_must_be_strings(self) -> None:
        self.assertEqual(
            problems(line(message_id=7, channel=["c"], sent_at=True, subject={"a": 1})),
            [
                "line 1: message_id: expected a string, got a number",
                "line 1: channel: expected a string, got an array",
                "line 1: sent_at: expected a string, got a boolean",
                "line 1: subject: expected a string, got an object",
            ],
        )
        # null in an optional key means not given.
        (message,) = read_messages(line(channel=None, subject=None), "x")
        self.assertEqual((message.channel, message.subject), ("", ""))

    def test_unknown_key_gets_a_suggestion_and_x_keys_are_ignored(self) -> None:
        text = json.dumps(
            {"message_id": "m", "sender": "syn-a", "text": "t", "messageId": "m", "txt": "t", "colour": "red",
             "x_thread": {"any": "thing"}, "_note": 1}
        )
        self.assertEqual(
            problems(text),
            [
                "line 1: unknown key 'messageId' (did you mean 'message_id'?); prefix your own keys with x_",
                "line 1: unknown key 'txt' (did you mean 'text'?); prefix your own keys with x_",
                "line 1: unknown key 'colour'; prefix your own keys with x_",
            ],
        )
        (message,) = read_messages(line(x_thread="t-1", _seen=True), "x")
        self.assertEqual(message.message_id, "syn-msg-1")

    def test_repeated_message_id_names_the_earlier_line(self) -> None:
        text = "\n".join([line(), "", line(message_id=" syn-msg-1 ")])
        self.assertEqual(problems(text), ["line 3: message_id: 'syn-msg-1' repeats line 1"])

    def test_only_synthetic_senders_are_read(self) -> None:
        for sender in ("ana@corp.example", "Syn-ana", "syn_ana", "syn-", "syn-Ana", " syn-ana", "syn-ana\n", "syn-än"):
            with self.subTest(sender=sender):
                (problem,) = problems(line(sender=sender))
                self.assertEqual(
                    problem,
                    f"line 1: sender: {sender!r} is not a synthetic sender (syn- followed by lower-case "
                    "letters, digits or hyphens); this command reads synthetic exports only",
                )
        for sender in ("syn-ana", "syn-sales-ana-2", "syn-0"):
            with self.subTest(sender=sender):
                self.assertEqual(read_messages(line(sender=sender), "x")[0].sender, sender)

    def test_every_problem_is_reported_at_once(self) -> None:
        text = "\n".join(["nope", line(sender="ana"), "[1]", line(message_id="syn-msg-3", text=""),
                          line(message_id="syn-msg-2", oops=1)])
        found = problems(text)
        self.assertEqual([p.split(":")[0] for p in found], ["line 1", "line 2", "line 3", "line 4", "line 5"])

    def test_not_utf8_is_named_and_a_byte_order_mark_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.jsonl"
            bad.write_bytes(b'{"text": "caf\xe9"}\n')
            with self.assertRaises(MessageExportError) as caught:
                load_message_export(str(bad))
            self.assertEqual(caught.exception.source, str(bad))
            self.assertEqual(
                caught.exception.problems,
                ["cannot read the file: it is not UTF-8 text (byte 0xe9 at position 13); save it as UTF-8"],
            )
            good = Path(tmp) / "good.jsonl"
            good.write_bytes(b"\xef\xbb\xbf" + line().encode("utf-8") + b"\n")
            text, source = load_message_export(str(good))
            self.assertEqual(source, str(good))
            self.assertEqual(len(read_messages(text, source)), 1)
            with self.assertRaises(MessageExportError) as caught:
                load_message_export(str(Path(tmp) / "missing.jsonl"))
            self.assertEqual(caught.exception.problems, ["cannot read the file: No such file or directory"])

    def test_standard_input_is_not_read(self) -> None:
        with self.assertRaises(MessageExportError) as caught:
            load_message_export("-")
        self.assertEqual(caught.exception.source, "standard input")
        self.assertIn("save the export as a file", caught.exception.problems[0])

    def test_an_empty_export_is_a_note_not_an_error(self) -> None:
        result = build_message_drafts(read_messages("\n\n", "empty.jsonl"), source="empty.jsonl")
        self.assertEqual((result["drafts"], result["messages"]), ([], []))
        self.assertEqual(result["notes"], ["the export holds no messages"])
        self.assertEqual(summary_line(result), "0 drafts from 0 messages.")
        self.assertIn("No messages", render_message_drafts_markdown(result))

    def test_lone_surrogates_become_replacement_characters(self) -> None:
        text = '{"message_id": "syn-\\ud800", "sender": "syn-a", "channel": "c\\udfff", "subject": "S\\ud800", ' \
            '"text": "bad \\ud800 char\\nCounterparty: Acme \\udc00(synthetic)"}'
        result = build_message_drafts(read_messages(text, "x"))
        draft = result["drafts"][0]
        self.assertEqual(draft["x_message_id"], "syn-�")
        self.assertEqual(draft["title"], "S�")
        self.assertEqual(draft["counterparty"], "Acme �(synthetic)")
        self.assertIn("bad � char", draft["description"])
        render_message_drafts_json(result).encode("utf-8")
        render_message_drafts_markdown(result).encode("utf-8")


class Mapping(unittest.TestCase):
    def test_every_draft_holds_every_always_asked_field(self) -> None:
        for draft in bundled()["drafts"]:
            with self.subTest(draft=draft["id"]):
                for name in ALWAYS_ASKED:
                    self.assertIn(name, draft)

    def test_a_fully_labelled_message_gives_a_draft_validate_accepts(self) -> None:
        result = bundled()
        draft, entry = result["drafts"][0], result["messages"][0]
        self.assertEqual(
            draft,
            {
                "id": "REQ-DRAFT-1",
                "title": "NDA: Initech Design (synthetic)",
                "type": "commercial_contract",
                "counterparty": "Initech Design (synthetic)",
                "value_band": "<50k",
                "personal_data": False,
                "non_eea_transfer": False,
                "uncapped_liability": False,
                "urgency": "low",
                "requested_by": "sales",
                "description": draft["description"],
                "x_message_id": "syn-msg-0001",
            },
        )
        self.assertEqual((entry["blank"], entry["not_given"], entry["check"]), ([], ["deadline"], []))
        report = validate_requests([draft])
        self.assertEqual(report.issues, ())
        self.assertEqual(decide(draft).risk, "LOW")

    def test_each_blank_is_an_error_validate_names(self) -> None:
        result = bundled()
        report = validate_requests(result["drafts"])
        for index, entry in enumerate(result["messages"]):
            with self.subTest(draft=entry["draft_id"]):
                errors = {i.field for i in report.errors if i.index == index}
                warnings = {i.field for i in report.warnings if i.index == index}
                checked = {c["field"] for c in entry["check"]}
                self.assertEqual(errors - checked, set(entry["blank"]) - {"type"})
                self.assertEqual("type" in warnings, "type" in entry["blank"] or "type" in checked)

    def test_prose_is_never_read(self) -> None:
        result = bundled()
        draft, entry = result["drafts"][2], result["messages"][2]
        self.assertIn("uncapped liability", draft["description"])
        self.assertEqual(entry["copied"], [])
        self.assertEqual(entry["blank"], list(ALWAYS_ASKED))
        for name in ALWAYS_ASKED:
            self.assertEqual(draft[name], "")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drafts.json"
            path.write_text(json.dumps([draft]), encoding="utf-8")
            code, stdout, stderr = run_cli(["triage", "--input", str(path)])
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("Nothing was written", stderr)
        for name in ("title", *DECISION_FIELDS):
            self.assertIn(f"(REQ-DRAFT-3): {name}:", stderr)

    def test_labels_are_matched_like_csv_headers(self) -> None:
        for label in ("Value band", "value-band", "valueBand", "VALUE BAND", "value_band", " Value band ", "\tValue.band"):
            with self.subTest(label=label):
                values, notes = labelled_values(f"{label}: 50k-250k")
                self.assertEqual((values, notes), ({"value_band": "50k-250k"}, []))
        for label, name in (("Request type", "type"), ("Type", "type"), ("Requester", "requested_by"),
                            ("Requested by", "requested_by"), ("Counterparty", "counterparty"),
                            ("Deadline", "deadline"), ("Title", "title"), ("Urgency", "urgency")):
            with self.subTest(label=label):
                self.assertEqual(labelled_values(f"{label}:x"), ({name: "x"}, []))
        for label, name in (("Personal data", "personal_data"), ("Non-EEA transfer", "non_eea_transfer"),
                            ("nonEeaTransfer", "non_eea_transfer"), ("Uncapped liability", "uncapped_liability")):
            with self.subTest(label=label):
                self.assertEqual(labelled_values(f"{label}: x"), ({name: True}, []))

    def test_yes_no_answers_are_read_like_csv(self) -> None:
        for answer, value in (("ja", True), ("x", True), ("Yes", True), ("TRUE", True), ("nein", False),
                              ("0", False), ("No", False), ("maybe", "maybe")):
            with self.subTest(answer=answer):
                draft, entry = one(f"Personal data: {answer}")
                self.assertEqual(draft["personal_data"], value)
        draft, entry = one("Personal data: maybe")
        self.assertEqual(
            entry["check"],
            [{"severity": "error", "field": "personal_data", "message": "expected true or false, got 'maybe'"}],
        )

    def test_copied_values_are_not_corrected(self) -> None:
        draft, entry = one("Value band: >1M\nUrgency: soon\nType: Commercial contract")
        self.assertEqual((draft["value_band"], draft["urgency"], draft["type"]), (">1M", "soon", "Commercial contract"))
        messages = {c["field"]: c["message"] for c in entry["check"]}
        self.assertIn("did you mean '>1m'?", messages["value_band"])
        self.assertIn("'soon' is not an urgency", messages["urgency"])
        self.assertIn("did you mean 'commercial_contract'?", messages["type"])

    def test_misspelled_labels_are_noted_not_copied(self) -> None:
        draft, entry = one("Value bnad: 50k-250k\nUncapped liabilty: yes\nCounter party: Acme (synthetic)\nUrgent: yes")
        self.assertEqual((draft["value_band"], draft["uncapped_liability"], draft["urgency"]), ("", "", ""))
        self.assertNotIn("counterparty", draft)
        self.assertEqual(
            entry["notes"],
            [
                "'Value bnad' looks like 'value_band'; not copied",
                "'Uncapped liabilty' looks like 'uncapped_liability'; not copied",
                "'Counter party' looks like 'counterparty'; not copied",
            ],
        )

    def test_fields_legal_sets_are_never_copied(self) -> None:
        labels = ("Id", "Request ID", "SLA breached", "Awaiting business input", "Summary", "Dependencies", "Facts")
        draft, entry = one("\n".join(f"{label}: yes" for label in labels) + "\nId: again")
        for name in ("sla_breached", "awaiting_business_input", "summary", "dependencies", "facts"):
            self.assertNotIn(name, draft)
        self.assertEqual(draft["id"], "REQ-DRAFT-1")
        self.assertEqual(entry["notes"], [f"{label!r} is set by legal; not copied" for label in labels])

    def test_description_label_is_not_copied_on_its_own(self) -> None:
        draft, entry = one("Description: short\nMore text")
        self.assertEqual(draft["description"], "Description: short\nMore text")
        self.assertEqual(entry["notes"], [])

    def test_conflicting_repeats_leave_a_blank_and_identical_repeats_copy(self) -> None:
        draft, entry = one("Urgency: high\nUrgency: low\nUrgency: high\nType: dpa\nType: dpa\n"
                           "Personal data: yes\nPersonal data: ja\nCounterparty: A\nCounterparty: B\nValue band:")
        self.assertEqual((draft["urgency"], draft["type"], draft["personal_data"]), ("", "dpa", True))
        self.assertNotIn("counterparty", draft)
        self.assertEqual(draft["value_band"], "")
        self.assertIn("urgency", entry["blank"])
        self.assertIn("counterparty", entry["not_given"])
        self.assertEqual(
            entry["notes"],
            ["urgency is given 2 different ways; not copied", "counterparty is given 2 different ways; not copied"],
        )

    def test_quoted_reply_lines_are_not_copied(self) -> None:
        for text in ("> Value band: >1m", ">Value band: >1m", "- Value band: >1m", "1. Value band: >1m",
                     "Value band (EUR): >1m", "Value band = >1m"):
            with self.subTest(text=text):
                self.assertEqual(labelled_values(text), ({}, []))

    def test_title_is_the_subject_then_a_title_line_then_blank(self) -> None:
        draft, entry = one("Title: From the line", subject="  From   the\nsubject ")
        self.assertEqual((draft["title"], entry["title_from"]), ("From the subject", "subject"))
        self.assertEqual(entry["notes"], ["the subject and the Title line differ; the subject is used"])
        draft, entry = one("Title: From the line", subject=" ")
        self.assertEqual((draft["title"], entry["title_from"], entry["notes"]), ("From the line", "Title line", []))
        draft, entry = one("Title: Same", subject="Same")
        self.assertEqual(entry["notes"], [])
        draft, entry = one("No title here")
        self.assertEqual((draft["title"], entry["title_from"]), ("", None))
        self.assertIn("title", entry["blank"])

    def test_ids_follow_message_order_and_carry_the_message_id(self) -> None:
        result = bundled()
        self.assertEqual([d["id"] for d in result["drafts"]], [f"REQ-DRAFT-{n}" for n in range(1, 7)])
        self.assertEqual([d["x_message_id"] for d in result["drafts"]], [f"syn-msg-000{n}" for n in range(1, 7)])
        self.assertEqual([e["draft_id"] for e in result["messages"]], [d["id"] for d in result["drafts"]])

    def test_only_contract_fields_and_x_keys_are_written(self) -> None:
        for draft in bundled()["drafts"]:
            for key in draft:
                with self.subTest(draft=draft["id"], key=key):
                    self.assertTrue(key in REQUEST_FIELDS or key in AUXILIARY_FIELDS or key.startswith("x_"))
                    self.assertIsNone(misspelled_field(key))
                    self.assertNotIn(key, ("facts", "sla_breached", "awaiting_business_input", "summary", "dependencies"))

    def test_keys_are_in_contract_order(self) -> None:
        order = [*REQUEST_FIELDS, *AUXILIARY_FIELDS, "x_message_id"]
        for draft in bundled()["drafts"]:
            with self.subTest(draft=draft["id"]):
                self.assertEqual(list(draft), sorted(draft, key=order.index))

    def test_a_policy_changes_only_the_checks(self) -> None:
        text = json.dumps(default_policy().to_dict())
        for old, new in {"<50k": "small", "50k-250k": "medium", "250k-1m": "large", ">1m": "huge"}.items():
            text = text.replace(json.dumps(old), json.dumps(new))
        data = json.loads(text)
        data["name"] = "Custom bands (synthetic)"
        policy = parse_policy(data, "custom")
        text, source = load_message_export()
        default, custom = bundled(), build_message_drafts(read_messages(text, source), policy, source)
        self.assertEqual(default["drafts"], custom["drafts"])
        self.assertEqual(custom["policy"], "Custom bands (synthetic)")
        self.assertEqual(default["messages"][0]["check"], [])
        self.assertEqual([c["field"] for c in custom["messages"][0]["check"]], ["value_band"])

    def test_same_export_gives_the_same_bytes(self) -> None:
        first, second = bundled(), bundled()
        self.assertEqual(render_message_drafts_json(first), render_message_drafts_json(second))
        self.assertEqual(render_message_drafts_markdown(first), render_message_drafts_markdown(second))

    def test_draft_request_alone(self) -> None:
        (message,) = read_messages(line(text="Type: ip"), "x")
        draft, entry = draft_request(4, message)
        self.assertEqual((draft["id"], draft["type"], entry["copied"]), ("REQ-DRAFT-4", "ip", ["type"]))
        self.assertNotIn("check", entry)

    def test_summary_line_counts(self) -> None:
        self.assertEqual(
            summary_line(bundled()),
            "6 drafts from 6 messages; 5 have blanks for legal to fill before validate and triage.",
        )
        self.assertEqual(
            summary_line(drafts_of("Title: T")),
            "1 draft from 1 message; 1 has blanks for legal to fill before validate and triage.",
        )
        complete = "Type: ip\nValue band: none\nPersonal data: no\nNon-EEA transfer: no\nUncapped liability: no\nUrgency: low"
        self.assertEqual(summary_line(drafts_of(complete, subject="T")), "1 draft from 1 message; no draft has blanks.")


class Cli(unittest.TestCase):
    def test_out_writes_the_committed_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_cli(["message-drafts", "--out", tmp])
            self.assertEqual((code, stdout), (0, ""))
            for name in ("message-drafts.json", "message-drafts.md"):
                with self.subTest(name=name):
                    self.assertEqual((Path(tmp) / name).read_bytes(), (EXAMPLES / name).read_bytes())
                    self.assertIn(f"wrote {Path(tmp) / name}", stderr)
        self.assertTrue(stderr.rstrip().endswith(summary_line(bundled())))

    def test_json_on_stdout_is_the_drafts_array_and_validate_names_the_blanks(self) -> None:
        code, stdout, stderr = run_cli(["message-drafts", "--format", "json"])
        self.assertEqual(code, 0)
        drafts = json.loads(stdout)
        self.assertEqual(drafts, bundled()["drafts"])
        self.assertIn("note: REQ-DRAFT-4: 'Value bnad' looks like 'value_band'; not copied\n", stderr)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drafts.json"
            path.write_text(stdout, encoding="utf-8")
            code, report, _ = run_cli(["validate", "--input", str(path)])
        self.assertEqual(code, 2)
        for index, entry in enumerate(bundled()["messages"], 1):
            for name in entry["blank"]:
                with self.subTest(draft=entry["draft_id"], field=name):
                    self.assertIn(f"request {index} ({entry['draft_id']}): {name}: ", report)

    def test_markdown_on_stdout(self) -> None:
        code, stdout, _ = run_cli(["message-drafts"])
        self.assertEqual((code, stdout), (0, render_message_drafts_markdown(bundled())))

    def test_a_policy_and_an_input_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp) / "export.jsonl"
            export.write_text(line(text="Value band: small") + "\n", encoding="utf-8")
            policy = Path(tmp) / "policy.json"
            code, _, _ = run_cli(["init", "--defaults", "--out", str(policy)])
            self.assertEqual(code, 0)
            code, stdout, stderr = run_cli(["message-drafts", "--input", str(export), "--policy", str(policy)])
        self.assertEqual(code, 0)
        self.assertIn(f"Source: {export}.", stdout)
        self.assertIn("'small' is not a value band", stdout)
        self.assertIn("note: applying policy", stderr)

    def test_a_bad_export_exits_2_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp) / "export.jsonl"
            export.write_text(line(sender="ana@corp.example") + "\nnope\n", encoding="utf-8")
            out = Path(tmp) / "out"
            code, stdout, stderr = run_cli(["message-drafts", "--input", str(export), "--out", str(out)])
            self.assertEqual((code, stdout), (2, ""))
            self.assertFalse(out.exists())
        self.assertIn(f"error: {export}: line 1: sender: 'ana@corp.example' is not a synthetic sender", stderr)
        self.assertIn(f"error: {export}: line 2: not valid JSON", stderr)
        self.assertTrue(stderr.endswith("The message export cannot be read. Nothing was written.\n"))

    def test_an_empty_export_is_noted_and_gives_no_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export = Path(tmp) / "empty.jsonl"
            export.write_text("\n", encoding="utf-8")
            code, stdout, stderr = run_cli(["message-drafts", "--input", str(export), "--format", "json"])
        self.assertEqual((code, stdout), (0, "[]\n"))
        self.assertEqual(stderr, "note: the export holds no messages\n0 drafts from 0 messages.\n")

    def test_a_bad_policy_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.json"
            policy.write_text("{}", encoding="utf-8")
            code, stdout, _ = run_cli(["message-drafts", "--policy", str(policy)])
        self.assertEqual((code, stdout), (2, ""))

    def test_markdown_says_it_sends_and_decides_nothing(self) -> None:
        text = (EXAMPLES / "message-drafts.md").read_text(encoding="utf-8")
        for phrase in ("Nothing was sent and nothing was decided", "are not verified", "Not legal advice",
                       "Do not delete a blank field", "it says nothing about who sent"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        for word in ("authenticat", "sign-in", "signed in", "verified sender"):
            with self.subTest(word=word):
                self.assertNotIn(word, text.lower())

    def test_bundled_source_is_named_not_a_path(self) -> None:
        text = (EXAMPLES / "message-drafts.md").read_text(encoding="utf-8")
        self.assertIn(f"Source: {BUNDLED_SOURCE}.", text)
        self.assertNotIn(str(ROOT), text)
        self.assertNotIn(os.sep + "legal_function_os" + os.sep, text)

    def test_write_message_drafts_returns_the_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_message_drafts(bundled(), Path(tmp) / "new")
            self.assertEqual(sorted(p.name for p in paths.values()), ["message-drafts.json", "message-drafts.md"])
            self.assertTrue(all(p.is_file() for p in paths.values()))


class Boundary(unittest.TestCase):
    def test_not_an_mcp_tool(self) -> None:
        for tool in mcp_server.TOOLS:
            with self.subTest(tool=tool.__name__):
                self.assertNotIn("message", tool.__name__)
                self.assertNotIn("messages", inspect.signature(tool).parameters)
        source = Path(mcp_server.__file__).read_text(encoding="utf-8")
        self.assertNotIn("message_drafts", source)

    def test_imports_no_network_or_mail_module(self) -> None:
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        forbidden = {"email", "imaplib", "poplib", "smtplib", "socket", "ssl", "urllib", "http", "subprocess",
                     "mailbox", "asyncio", "ftplib", "requests", "httpx"}
        self.assertEqual(imported & forbidden, set())
        self.assertLessEqual(imported, {"__future__", "difflib", "json", "re", "dataclasses", "pathlib", "typing",
                                        "legal_function_os"})


if __name__ == "__main__":
    unittest.main()
