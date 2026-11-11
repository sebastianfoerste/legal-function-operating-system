"""The subcommands print what the all-in-one flags write, and the old flags keep working."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from legal_function_os import __version__
from legal_function_os.board_pack import build_board_pack
from legal_function_os.cli import COMMANDS
from legal_function_os.cli import main as cli_main
from legal_function_os.rules import decide

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "legal_function_os" / "data"
EXAMPLES = ROOT / "examples"
SAMPLE = DATA / "sample_requests.json"
REQUESTS = json.loads(SAMPLE.read_text(encoding="utf-8"))


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli_main(argv)
        except SystemExit as exit_:  # argparse's --help, --version and usage errors
            code = exit_.code
    return code, out.getvalue(), err.getvalue()


def write_json(directory: str, name: str, payload) -> str:
    path = Path(directory) / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class HelpAndVersion(unittest.TestCase):
    def test_help_lists_every_command(self):
        code, stdout, _ = run_cli(["--help"])
        self.assertEqual(code, 0)
        for name in COMMANDS:
            self.assertIn(name, stdout)
        self.assertIn("original all-in-one flags", stdout)

    def test_version(self):
        code, stdout, _ = run_cli(["--version"])
        self.assertEqual((code, stdout.strip()), (0, f"legal-function-os {__version__}"))

    def test_python_dash_m_runs_the_cli(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        completed = subprocess.run(
            [sys.executable, "-m", "legal_function_os", "triage", "--id", "REQ-1003", "--format", "json"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual([d["request_id"] for d in payload["decisions"]], ["REQ-1003"])

    def test_unknown_option_is_a_usage_error(self):
        code, _, stderr = run_cli(["triage", "--nope"])
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments: --nope", stderr)


class Triage(unittest.TestCase):
    def test_json_matches_the_rules(self):
        code, stdout, stderr = run_cli(["triage", "--format", "json"])
        self.assertEqual((code, stderr), (0, ""))
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "legal-function-os.triage.v1")
        self.assertEqual(payload["request_count"], 8)
        self.assertEqual(payload["decisions"], [decide(r).to_dict() for r in REQUESTS])
        self.assertEqual(payload["warnings"], [])

    def test_markdown_puts_the_outcome_before_the_reasons(self):
        code, stdout, _ = run_cli(["triage", "--id", "REQ-1001"])
        self.assertEqual(code, 0)
        self.assertIn("# Legal request triage: 1 request", stdout)
        self.assertIn("## REQ-1001: Enterprise MSA: Globex (synthetic)", stdout)
        self.assertIn(
            "**Approval chain** Reviewer → Legal Ops Lead → General Counsel → Board note", stdout
        )
        self.assertLess(stdout.index("**Risk** HIGH"), stdout.index("- Value over EUR 1 million."))
        self.assertIn("not legal advice", stdout)
        self.assertNotIn("REQ-1002", stdout)

    def test_id_filter_keeps_input_order_and_rejects_unknown_ids(self):
        code, stdout, _ = run_cli(["triage", "--id", "REQ-1005", "--id", "REQ-1002", "--format", "json"])
        self.assertEqual(code, 0)
        ids = [d["request_id"] for d in json.loads(stdout)["decisions"]]
        self.assertEqual(ids, ["REQ-1002", "REQ-1005"])
        code, stdout, stderr = run_cli(["triage", "--id", "REQ-9999"])
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("no request with id REQ-9999", stderr)

    def test_warnings_are_reported_and_carried_in_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = write_json(tmp, "r.json", [{"id": "R-1", "title": "T", "type": "regulatory"}])
            code, stdout, stderr = run_cli(["triage", "--input", source, "--format", "json"])
        self.assertEqual(code, 0)
        self.assertIn("warning: request 1 (R-1): type", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["warnings"][0]["field"], "type")
        self.assertEqual(payload["decisions"][0]["queue"], "General")

    def test_invalid_input_stops_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = write_json(tmp, "r.json", [{"id": "R-1", "title": "T", "value_band": ">1M"}])
            code, stdout, stderr = run_cli(["triage", "--input", source])
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("did you mean '>1m'", stderr)

    def test_reads_csv(self):
        code, stdout, _ = run_cli(
            ["triage", "--input", str(EXAMPLES / "requests-template.csv"), "--format", "json"]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["request_count"], 8)


class BoardPack(unittest.TestCase):
    def test_out_writes_the_committed_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = run_cli(
                ["board-pack", "--period", "Q2 2026 (synthetic)", "--out", tmp]
            )
            self.assertEqual((code, stdout), (0, ""))
            for name in ("board-pack.md", "board-pack.json"):
                self.assertEqual(
                    (Path(tmp) / name).read_text(encoding="utf-8"),
                    (EXAMPLES / name).read_text(encoding="utf-8"),
                    name,
                )
                self.assertIn(f"wrote {Path(tmp) / name}", stderr)

    def test_prints_markdown_or_json(self):
        code, stdout, _ = run_cli(["board-pack"])
        self.assertEqual(code, 0)
        self.assertTrue(stdout.startswith("# Legal Function: Board Operations Pack"))
        code, stdout, _ = run_cli(["board-pack", "--format", "json", "--period", "Q3"])
        self.assertEqual(json.loads(stdout), build_board_pack(REQUESTS, period="Q3").to_dict())

    def test_fail_on_breach(self):
        self.assertEqual(run_cli(["board-pack", "--fail-on-breach"])[0], 1)
        with tempfile.TemporaryDirectory() as tmp:
            source = write_json(tmp, "r.json", [{"id": "R-1", "title": "T", "type": "ip"}])
            self.assertEqual(run_cli(["board-pack", "--input", source, "--fail-on-breach"])[0], 0)


class Validate(unittest.TestCase):
    def test_valid_input(self):
        code, stdout, _ = run_cli(["validate"])
        self.assertEqual(code, 0)
        self.assertIn("valid (0 errors, 0 warnings in 8 requests)", stdout)

    def test_invalid_input_exits_2_with_a_json_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = write_json(
                tmp,
                "r.json",
                [{"id": "R-1", "title": "T", "urgency": "urgent", "personal_data": "yes"}],
            )
            code, stdout, _ = run_cli(["validate", "--input", source, "--format", "json"])
        self.assertEqual(code, 2)
        report = json.loads(stdout)
        self.assertFalse(report["valid"])
        self.assertEqual(report["source"], source)
        self.assertEqual(
            [issue["field"] for issue in report["issues"]], ["type", "urgency", "personal_data"]
        )

    def test_markdown_names_the_csv_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "r.csv"
            source.write_text("id,title,value_band\nR-1,T,>1M\n", encoding="utf-8")
            code, stdout, _ = run_cli(["validate", "--input", str(source)])
        self.assertEqual(code, 2)
        self.assertIn("error: row 2 (R-1): value_band", stdout)
        self.assertIn("not valid (1 error, 1 warning in 1 request)", stdout)

    def test_unreadable_input(self):
        code, _, stderr = run_cli(["validate", "--input", "/nonexistent/requests.json"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", stderr)


class DpaReview(unittest.TestCase):
    def test_bundled_agreements(self):
        code, stdout, _ = run_cli(["dpa-review"])
        self.assertEqual(code, 0)
        self.assertIn("- **2** documents · **1** blocker (missing requirements)", stdout)
        self.assertIn(
            "| Nachweis- und Kontrollrechte | Art. 28 Abs. 3 lit. h DSGVO | MISSING | — |", stdout
        )
        code, stdout, _ = run_cli(["dpa-review", "--format", "json"])
        self.assertEqual(json.loads(stdout)["blocker_count"], 1)

    def test_out_writes_markdown_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _ = run_cli(["dpa-review", "--out", tmp])
            self.assertEqual((code, stdout), (0, ""))
            review = json.loads((Path(tmp) / "dpa-review.json").read_text(encoding="utf-8"))
            self.assertEqual(review["schema"], "legal-function-os.dpa-review.v1")
            self.assertTrue((Path(tmp) / "dpa-review.md").is_file())

    def test_unusable_agreements_are_rejected(self):
        documents = [
            {"id": "D-1", "clauses": {"audit_right": "Audits allowed.", "governing_law": "German law."}},
            {"id": "D-1", "clauses": {"deletion_return": 7}},
            {"title": "No id", "clauses": []},
            "D-4",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = write_json(tmp, "dpas.json", documents)
            code, stdout, stderr = run_cli(["dpa-review", "--input", source])
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("agreement 1 (D-1): clause 'audit_right' is not a playbook key (did you mean 'audit_rights'?)", stderr)
        self.assertNotIn("governing_law", stderr)
        self.assertIn("agreement 2 (D-1): id is used twice", stderr)
        self.assertIn("agreement 2 (D-1): clause 'deletion_return' must be text", stderr)
        self.assertIn("agreement 3: id is missing", stderr)
        self.assertIn("agreement 3: clauses must be an object", stderr)
        self.assertIn("agreement 4: expected an object, got str", stderr)
        self.assertIn("Nothing was written.", stderr)

    def test_legacy_flags_check_the_agreements_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = write_json(tmp, "dpas.json", {"id": "D-1"})
            out_dir = Path(tmp) / "out"
            code, _, stderr = run_cli(
                ["--quiet", "--out", str(out_dir), "--dpa-input", source, "--dpa-output", str(out_dir / "d.json")]
            )
            self.assertEqual(code, 2)
            self.assertFalse(out_dir.exists())
        self.assertIn("expected a JSON array of agreements", stderr)


class CapacityAndControlTower(unittest.TestCase):
    def test_capacity_json_is_the_committed_example(self):
        code, stdout, _ = run_cli(["capacity", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout, (EXAMPLES / "legal-capacity-simulation.json").read_text(encoding="utf-8")
        )

    def test_capacity_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = run_cli(["capacity", "--out", tmp])
            self.assertEqual(code, 0)
            self.assertEqual(
                (Path(tmp) / "legal-capacity-simulation.md").read_text(encoding="utf-8"),
                (EXAMPLES / "legal-capacity-simulation.md").read_text(encoding="utf-8"),
            )

    def test_own_requests_need_their_own_scenarios(self):
        code, stdout, stderr = run_cli(["capacity", "--input", str(SAMPLE)])
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("--scenarios is required with --input", stderr)
        code, _, stderr = run_cli(["control-tower", "--input", str(SAMPLE)])
        self.assertEqual(code, 2)
        self.assertIn("--events is required with --input", stderr)

    def test_bad_scenarios_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            scenarios = write_json(tmp, "s.json", [{"name": "only one"}])
            code, _, stderr = run_cli(
                ["capacity", "--input", str(SAMPLE), "--scenarios", scenarios]
            )
        self.assertEqual(code, 2)
        self.assertIn("invalid capacity simulation input", stderr)

    def test_control_tower_json_and_out(self):
        code, stdout, _ = run_cli(["control-tower", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout, (EXAMPLES / "legal-outcome-control-tower.json").read_text(encoding="utf-8")
        )
        code, stdout, _ = run_cli(["control-tower"])
        self.assertTrue(stdout.startswith("# "))
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = run_cli(["control-tower", "--out", tmp])
            self.assertEqual(code, 0)
            self.assertEqual(
                sorted(path.name for path in Path(tmp).iterdir()),
                [
                    "legal-outcome-control-tower.html",
                    "legal-outcome-control-tower.json",
                    "legal-outcome-control-tower.md",
                ],
            )

    def test_unreadable_side_files(self):
        code, _, stderr = run_cli(
            ["control-tower", "--input", str(SAMPLE), "--events", "/nonexistent.json", "--config", "/nonexistent.json"]
        )
        self.assertEqual(code, 2)
        self.assertIn("cannot read service event ledger /nonexistent.json", stderr)
        with tempfile.TemporaryDirectory() as tmp:
            latin = Path(tmp) / "events.json"
            latin.write_bytes('{"approvals": "Gepr\u00fcft"}'.encode("latin-1"))
            code, _, stderr = run_cli(["control-tower", "--input", str(SAMPLE), "--events", str(latin), "--config", str(latin)])
        self.assertEqual(code, 2)
        self.assertIn(
            f"cannot read service event ledger {latin}: it is not UTF-8 text (byte 0xfc at position 19); save it as UTF-8",
            stderr,
        )


class LegacyFlags(unittest.TestCase):
    def test_no_arguments_still_prints_the_board_pack(self):
        code, stdout, _ = run_cli([])
        self.assertEqual(code, 0)
        self.assertTrue(stdout.startswith("# Legal Function: Board Operations Pack"))

    def test_all_in_one_flags_still_write_every_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _ = run_cli(
                [
                    "--input", str(SAMPLE), "--out", tmp, "--period", "Q2 2026 (synthetic)",
                    "--capacity-scenarios", str(DATA / "capacity_scenarios.json"),
                    "--capacity-output", tmp,
                    "--events-input", str(DATA / "service_events.json"),
                    "--outcome-config", str(DATA / "outcome_config.json"),
                    "--outcome-output", tmp, "--quiet",
                ]
            )
            self.assertEqual((code, stdout), (0, ""))
            for name in ("board-pack.json", "legal-capacity-simulation.json", "legal-outcome-control-tower.json"):
                self.assertEqual(
                    (Path(tmp) / name).read_bytes(), (EXAMPLES / name).read_bytes(), name
                )

    def test_an_unreadable_approvals_file_stops_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, space = Path(tmp) / "out", Path(tmp) / "shared-space.json"
            broken = Path(tmp) / "approvals.json"
            broken.write_text("{", encoding="utf-8")
            listed, shaped = Path(tmp) / "listed.json", Path(tmp) / "shaped.json"
            listed.write_text('[{"request_id": "REQ-1001"}]', encoding="utf-8")
            shaped.write_text('{"REQ-1001": "yes"}', encoding="utf-8")
            shape = "expected an object that maps a request id to an approval object"
            for path, message in (
                (Path(tmp) / "missing.json", "cannot read approvals"),
                (broken, f"approvals {broken} is not valid JSON"),
                (listed, f"approvals {listed}: {shape}"),
                (shaped, f"approvals {shaped}: {shape}"),
            ):
                code, _, stderr = run_cli(
                    ["--quiet", "--out", str(out_dir), "--shared-space-output", str(space), "--approvals", str(path)]
                )
                self.assertEqual(code, 2, path)
                self.assertIn(message, stderr)
                self.assertFalse(out_dir.exists() or space.exists())
            # An empty entry still means no approval.
            approvals = Path(tmp) / "approvals-ok.json"
            approvals.write_text(
                json.dumps({"REQ-1001": {"approved_by": "Legal Ops", "note": "Checked against the policy today."}, "REQ-1002": None, "REQ-1003": ""}),
                encoding="utf-8",
            )
            code, _, stderr = run_cli(["--quiet", "--shared-space-output", str(space), "--approvals", str(approvals)])
            self.assertEqual(code, 0, stderr)
            entries = {e["request_id"]: e["shared"] for e in json.loads(space.read_text(encoding="utf-8"))["entries"]}
            self.assertEqual((entries["REQ-1001"], entries["REQ-1002"], entries["REQ-1003"]), (True, False, False))

    def test_legacy_side_files_that_are_not_utf8_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            latin = Path(tmp) / "latin.json"
            latin.write_bytes('{"name": "Pr\u00fcfung"}'.encode("latin-1"))
            not_utf8 = "it is not UTF-8 text (byte 0xfc at position 12); save it as UTF-8"
            code, _, stderr = run_cli(["--quiet", "--capacity-scenarios", str(latin), "--capacity-output", tmp])
            self.assertEqual(code, 2)
            self.assertIn(f"Invalid capacity simulation input: {latin}: {not_utf8}", stderr)
            events = str(DATA / "service_events.json")
            code, _, stderr = run_cli(
                ["--quiet", "--events-input", events, "--outcome-config", str(latin), "--outcome-output", tmp]
            )
            self.assertEqual(code, 2)
            self.assertIn(f"Invalid outcome control tower input: {latin}: {not_utf8}", stderr)
            # A byte order mark is accepted here too, as in every other JSON input.
            marked = Path(tmp) / "scenarios.json"
            marked.write_bytes(b"\xef\xbb\xbf" + (DATA / "capacity_scenarios.json").read_bytes())
            code, _, stderr = run_cli(["--quiet", "--capacity-scenarios", str(marked), "--capacity-output", tmp])
            self.assertEqual(code, 0, stderr)

    def test_approvals_are_read_only_for_the_shared_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "approvals.json"
            broken.write_text("{", encoding="utf-8")
            code, _, stderr = run_cli(["--quiet", "--approvals", str(broken)])
            self.assertEqual(code, 0, stderr)

    def test_dpa_input_error_points_at_the_subcommand(self):
        code, _, stderr = run_cli(["--quiet", "--dpa-input", str(DATA / "dpa_documents.json")])
        self.assertEqual(code, 2)
        self.assertIn("dpa-review --input PATH", stderr)


if __name__ == "__main__":
    unittest.main()
