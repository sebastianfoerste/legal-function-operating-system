"""The rule settings live in a policy file; the default policy changes nothing."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from legal_function_os.board_pack import build_board_pack, render_markdown
from legal_function_os.cli import main as cli_main
from legal_function_os.policy import (
    PolicyError,
    default_policy,
    load_policy,
    parse_policy,
    policy_schema,
    render_policy_json,
)
from legal_function_os.policy_init import InterviewError, run_interview
from legal_function_os.rules import ROUTING, SLA, VALUE_BANDS, decide
from legal_function_os.validation import validate_requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "legal_function_os" / "data"
DEFAULT_FILE = DATA / "default_policy.json"
EXAMPLES = ROOT / "examples"
REQUESTS = json.loads((DATA / "sample_requests.json").read_text(encoding="utf-8"))
RAW = json.loads(DEFAULT_FILE.read_text(encoding="utf-8"))
PERIOD = "Q2 2026 (synthetic)"


def custom_raw() -> dict:
    """A policy with renamed bands, other queues and other service levels."""

    raw = copy.deepcopy(RAW)
    raw["name"] = "Acme Legal (synthetic)"
    raw["value_bands"] = ["none", "<100k", "100k-500k", "500k-2m", ">2m"]
    raw["routing"]["by_type"]["dpa"] = "Data Protection"
    raw["routing"]["by_type"]["regulatory"] = "Regulatory"
    raw["routing"]["unknown_type"] = "Front door"
    raw["routing"]["non_eea_transfer"] = "Data Protection"
    raw["sla"]["P2_high"] = {"response_hours": 6, "resolution_days": 2}
    raw["approval"] = {
        "legal_ops_lead_from": "100k-500k",
        "general_counsel_from": "500k-2m",
        "board_note_from": ">2m",
    }
    raw["risk"]["high_from"] = {"value_band": ">2m", "reason": "Contract value above EUR 2m."}
    raw["risk"]["medium_from"] = {"value_band": "500k-2m", "reason": "Contract value from EUR 500k."}
    raw["risk"]["dispute_high_from"] = {"value_band": "100k-500k", "reason": "Dispute from EUR 100k."}
    raw["external_counsel"]["dispute_from"] = "500k-2m"
    raw["escalation"] = {
        "board_awareness_from": {"value_band": ">2m", "message": "Value above EUR 2m: tell the board."},
        "dispute_board_attention_from": "500k-2m",
    }
    return raw


def run_cli(argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    patch = mock.patch("sys.stdin", io.StringIO(stdin)) if stdin is not None else contextlib.nullcontext()
    with patch, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(argv)
    return code, out.getvalue(), err.getvalue()


def problems(raw) -> list[str]:
    try:
        parse_policy(raw, "test.json")
    except PolicyError as exc:
        return exc.problems
    raise AssertionError("expected PolicyError")


class DefaultPolicyChangesNothing(unittest.TestCase):
    def test_default_policy_reproduces_the_committed_board_pack(self):
        policy = load_policy(str(DEFAULT_FILE))
        pack = build_board_pack(REQUESTS, period=PERIOD, policy=policy)
        committed = json.loads((EXAMPLES / "board-pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack.to_dict(), committed)
        self.assertEqual(render_markdown(pack), (EXAMPLES / "board-pack.md").read_text(encoding="utf-8"))

    def test_cli_with_the_default_policy_file_writes_the_committed_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, stderr = run_cli(
                ["board-pack", "--policy", str(DEFAULT_FILE), "--period", PERIOD, "--out", tmp]
            )
            self.assertEqual(code, 0)
            self.assertIn("note: applying policy 'Default illustrative policy'", stderr)
            for name in ("board-pack.md", "board-pack.json"):
                self.assertEqual((Path(tmp) / name).read_bytes(), (EXAMPLES / name).read_bytes())

    def test_old_constants_still_name_the_default_values(self):
        self.assertEqual(VALUE_BANDS, RAW["value_bands"])
        self.assertEqual(ROUTING, RAW["routing"]["by_type"])
        self.assertEqual(SLA, RAW["sla"])

    def test_policy_round_trips(self):
        self.assertEqual(default_policy().to_dict(), RAW)
        self.assertEqual(parse_policy(json.loads(render_policy_json(default_policy()))), default_policy())

    def test_committed_schema_matches_the_code(self):
        committed = ROOT / "contracts" / "legal-function-policy.v1.schema.json"
        self.assertEqual(
            json.loads(committed.read_text(encoding="utf-8")),
            policy_schema(),
            "run `make contracts` and commit the result",
        )


class CustomPolicyIsApplied(unittest.TestCase):
    def setUp(self):
        self.policy = parse_policy(custom_raw(), "custom")

    def decide(self, **fields):
        return decide({"id": "R-1", "title": "T", "type": "commercial_contract", **fields}, self.policy)

    def test_value_thresholds_follow_the_policy(self):
        decision = self.decide(value_band="500k-2m")
        self.assertEqual(decision.risk, "MEDIUM")
        self.assertIn("Contract value from EUR 500k.", decision.rationale)
        self.assertEqual(decision.approval_chain, ["Reviewer", "Legal Ops Lead", "General Counsel"])
        top = self.decide(value_band=">2m", urgency="high")
        self.assertEqual(top.risk, "HIGH")
        self.assertEqual(top.approval_chain[-1], "Board note")
        self.assertIn("Value above EUR 2m: tell the board.", top.escalations)
        self.assertTrue(top.board_attention)
        self.assertEqual((top.sla_response_hours, top.sla_resolution_days), (6, 2))

    def test_disputes_follow_their_own_thresholds(self):
        dispute = self.decide(type="dispute", value_band="100k-500k")
        self.assertEqual(dispute.risk, "HIGH")
        self.assertIn("Dispute from EUR 100k.", dispute.rationale)
        self.assertEqual(dispute.external_counsel, "in-house")
        self.assertFalse(dispute.board_attention)
        larger = self.decide(type="dispute", value_band="500k-2m")
        self.assertEqual(larger.external_counsel, "External: litigation counsel")
        self.assertTrue(larger.board_attention)

    def test_queues_follow_the_policy(self):
        self.assertEqual(self.decide(type="dpa").queue, "Data Protection")
        self.assertEqual(self.decide(type="regulatory").queue, "Regulatory")
        self.assertEqual(self.decide(non_eea_transfer=True).queue, "Data Protection")
        unknown = self.decide(type="tax")
        self.assertEqual(unknown.queue, "Front door")
        self.assertIn("Request type 'tax' is not in the routing table: needs manual triage.", unknown.rationale)

    def test_validation_checks_the_policy_bands(self):
        report = validate_requests([{"id": "R-1", "title": "T", "value_band": ">1m"}], self.policy)
        [error] = report.errors
        self.assertIn("'>1m' is not a value band (did you mean '>2m'?)", error.message)
        self.assertTrue(validate_requests([{"id": "R-1", "title": "T", "value_band": ">2m"}], self.policy).ok)
        warning = validate_requests([{"id": "R-1", "title": "T", "type": "regulatory"}], self.policy)
        self.assertEqual(warning.issues, ())

    def test_the_default_policy_still_rejects_the_custom_bands(self):
        with self.assertRaisesRegex(ValueError, "unknown value_band '>2m'"):
            decide({"id": "R-1", "title": "T", "value_band": ">2m"})


class PolicyChecks(unittest.TestCase):
    def test_every_problem_is_reported_with_its_place(self):
        raw = copy.deepcopy(RAW)
        raw["schema"] = "legal-function-os.policy.v0"
        raw["approval"]["general_counsel_from"] = "250k-1M"
        raw["risk"]["hgh_from"] = raw["risk"].pop("high_from")
        raw["sla"]["P2_high"]["response_hours"] = 0
        raw["sla"]["P3_standard"]["resolution_days"] = True
        del raw["routing"]["unknown_type"]
        found = problems(raw)
        self.assertIn("schema: expected 'legal-function-os.policy.v1', got 'legal-function-os.policy.v0'", found)
        self.assertIn(
            "approval.general_counsel_from: '250k-1M' is not one of the value bands (did you mean "
            "'250k-1m'?); use one of none, <50k, 50k-250k, 250k-1m, >1m",
            found,
        )
        self.assertIn("risk.hgh_from: unknown key (did you mean 'high_from'?); prefix your own keys with x_", found)
        self.assertIn("risk.high_from: missing", found)
        self.assertIn("sla.P2_high.response_hours: expected a whole number above 0, got 0", found)
        self.assertIn("sla.P3_standard.resolution_days: expected a whole number above 0, got True", found)
        self.assertIn("routing.unknown_type: missing", found)

    def test_approval_tiers_must_rise_in_order(self):
        raw = copy.deepcopy(RAW)
        raw["approval"]["general_counsel_from"] = ">1m"
        raw["approval"]["board_note_from"] = "50k-250k"
        found = problems(raw)
        self.assertEqual(
            found,
            [
                "approval.general_counsel_from: '>1m' is above approval.board_note_from "
                "('50k-250k'); a lower tier cannot start at a higher value"
            ],
        )
        raw = copy.deepcopy(RAW)
        raw["risk"]["medium_from"]["value_band"] = ">1m"
        raw["risk"]["high_from"]["value_band"] = "<50k"
        self.assertTrue(any(p.startswith("risk.medium_from: '>1m' is above") for p in problems(raw)))

    def test_shape_problems(self):
        self.assertEqual(problems([]), ["expected an object, got an array"])
        raw = copy.deepcopy(RAW)
        raw["value_bands"] = ["only"]
        raw["routing"]["by_type"] = {}
        raw["sla"]["P5_later"] = {"response_hours": 1, "resolution_days": 1}
        del raw["sla"]["P4_low"]
        raw["risk"]["elevated_types"] = "corporate"
        found = problems(raw)
        self.assertIn("value_bands: expected at least two non-empty band names, lowest first", found)
        self.assertIn("routing.by_type: expected an object of request type to queue name", found)
        self.assertIn("sla.P5_later: unknown priority; use P1_blocker, P2_high, P3_standard, P4_low", found)
        self.assertIn("sla.P4_low: missing", found)
        self.assertIn("risk.elevated_types: expected an array of request types", found)
        raw = copy.deepcopy(RAW)
        raw["value_bands"] = ["a", "a"]
        self.assertIn("value_bands: each band name may appear only once", problems(raw))

    def test_own_keys_and_a_schema_reference_are_allowed(self):
        raw = copy.deepcopy(RAW)
        raw["$schema"] = "../contracts/legal-function-policy.v1.schema.json"
        raw["x_owner"] = "Legal Ops"
        raw["approval"]["_why"] = "Board asked for EUR 1m."
        del raw["description"]
        self.assertEqual(parse_policy(raw).name, RAW["name"])

    def test_unreadable_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "policy.json"
            broken.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(PolicyError, "not valid JSON"):
                load_policy(str(broken))
            with self.assertRaisesRegex(PolicyError, "cannot read the file"):
                load_policy(str(Path(tmp) / "missing.json"))


class CliPolicyFlag(unittest.TestCase):
    def write(self, tmp: str, name: str, payload) -> str:
        path = Path(tmp) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_every_request_command_applies_the_policy(self):
        request = {"id": "R-1", "title": "T", "type": "dpa", "value_band": ">2m"}
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.write(tmp, "policy.json", custom_raw())
            source = self.write(tmp, "requests.json", [request])
            code, stdout, _ = run_cli(["triage", "--policy", policy, "--input", source, "--format", "json"])
            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["policy"], "Acme Legal (synthetic)")
            self.assertEqual(payload["decisions"][0]["queue"], "Data Protection")
            self.assertEqual(payload["decisions"][0]["approval_chain"][-1], "Board note")
            code, stdout, _ = run_cli(["triage", "--policy", policy, "--input", source])
            self.assertIn("_Policy: Acme Legal (synthetic)_", stdout)
            code, stdout, _ = run_cli(["board-pack", "--policy", policy, "--input", source, "--format", "json"])
            self.assertEqual(json.loads(stdout)["totals"]["board_attention_items"], 1)
            code, stdout, _ = run_cli(["validate", "--policy", policy, "--input", source, "--format", "json"])
            self.assertEqual((code, json.loads(stdout)["policy"]), (0, "Acme Legal (synthetic)"))
            out = Path(tmp) / "legacy"
            code, _, _ = run_cli(["--policy", policy, "--input", source, "--out", str(out), "--quiet"])
            self.assertEqual(code, 0)
            pack = json.loads((out / "board-pack.json").read_text(encoding="utf-8"))
            self.assertEqual(pack["decisions"][0]["queue"], "Data Protection")

    def test_the_bundled_requests_do_not_fit_a_policy_with_other_bands(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.write(tmp, "policy.json", custom_raw())
            code, stdout, stderr = run_cli(["board-pack", "--policy", policy])
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("'>1m' is not a value band (did you mean '>2m'?)", stderr)

    def test_a_broken_policy_stops_the_run_before_anything_is_written(self):
        raw = copy.deepcopy(RAW)
        raw["approval"]["board_note_from"] = "1m+"
        with tempfile.TemporaryDirectory() as tmp:
            policy = self.write(tmp, "policy.json", raw)
            out = Path(tmp) / "out"
            for argv in (
                ["board-pack", "--policy", policy, "--out", str(out)],
                ["--policy", policy, "--out", str(out)],
            ):
                code, stdout, stderr = run_cli(argv)
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn(f"error: {policy}: approval.board_note_from: '1m+' is not one of the value bands", stderr)
                self.assertIn("The policy cannot be applied. Nothing was written.", stderr)
            self.assertFalse(out.exists())


class InitInterview(unittest.TestCase):
    def test_enter_throughout_keeps_the_default_values(self):
        policy = run_interview(lambda _prompt: "", lambda _line: None)
        written, bundled = policy.to_dict(), default_policy().to_dict()
        self.assertEqual(written.pop("name"), "Our legal team")
        written.pop("description")
        bundled.pop("name")
        bundled.pop("description")
        self.assertEqual(written, bundled)

    def test_answers_build_the_policy_and_bad_answers_are_asked_again(self):
        answers = iter(
            [
                "Acme Legal",
                "none, <100k, 100k-500k, 500k-2m, >2m",
                "1m",  # not a band: asked again
                "100k-500k",
                "<100k",  # below the Legal Ops Lead tier: asked again
                "500k-2m",
                ">2m",
                "",  # no default once the bands changed: asked again
                "500k-2m",
                "dpa=Data Protection, regulatory=Regulatory, ip=",
                "Front door",
                "",
                "two, one",  # not numbers: asked again
                "2, 1",
                "",
                "",
                "",
            ]
        )
        said: list[str] = []
        policy = run_interview(lambda _prompt: next(answers), said.append)
        self.assertEqual(policy.name, "Acme Legal")
        self.assertEqual(policy.value_bands, ("none", "<100k", "100k-500k", "500k-2m", ">2m"))
        self.assertEqual(
            (policy.legal_ops_lead_from, policy.general_counsel_from, policy.board_note_from),
            ("100k-500k", "500k-2m", ">2m"),
        )
        self.assertEqual(policy.dispute_counsel_from, "500k-2m")
        self.assertEqual(policy.routing["dpa"], "Data Protection")
        self.assertEqual(policy.routing["regulatory"], "Regulatory")
        self.assertNotIn("ip", policy.routing)
        self.assertEqual(policy.unknown_type_queue, "Front door")
        self.assertEqual(policy.sla["P1_blocker"].response_hours, 2)
        self.assertEqual(policy.high_risk_from.text, "Contract value in band >2m or above.")
        self.assertTrue(any("Choose one of: none, <100k" in line for line in said))
        self.assertTrue(any("cannot start below the one before it" in line for line in said))
        self.assertTrue(any("An answer is required." in line for line in said))
        self.assertTrue(any("two whole numbers" in line for line in said))
        self.assertEqual(parse_policy(policy.to_dict()), policy)
        self.assertEqual(next(answers, "done"), "done")

    def test_repeated_bad_answers_end_the_interview(self):
        answers = iter(["Team", "one-band", "still-one", "one-more"])
        with self.assertRaisesRegex(InterviewError, "Value bands"):
            run_interview(lambda _prompt: next(answers), lambda _line: None)

    def test_cli_writes_a_policy_the_other_commands_accept(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "team" / "policy.json"
            code, stdout, stderr = run_cli(["init", "--out", str(target)], stdin="Team Legal\n" + "\n" * 12)
            self.assertEqual(code, 0, stderr)
            self.assertIn("1. Whose policy is this", stdout)
            self.assertIn(f"wrote {target}", stderr)
            self.assertEqual(load_policy(str(target)).name, "Team Legal")
            code, _, stderr = run_cli(["init", "--out", str(target), "--defaults"])
            self.assertEqual(code, 2)
            self.assertIn("already exists; pass --force", stderr)
            code, _, _ = run_cli(["init", "--out", str(target), "--defaults", "--force"])
            self.assertEqual(code, 0)
            code, stdout, _ = run_cli(["board-pack", "--policy", str(target), "--format", "json", "--period", PERIOD])
            self.assertEqual(code, 0)
            committed = json.loads((EXAMPLES / "board-pack.json").read_text(encoding="utf-8"))
            self.assertEqual(json.loads(stdout), committed)

    def test_cli_stops_when_the_answers_run_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "policy.json"
            code, _, stderr = run_cli(["init", "--out", str(target)], stdin="Team\n")
            self.assertEqual(code, 2)
            self.assertIn("init --defaults", stderr)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
