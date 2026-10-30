"""Approval matrix: the rules' approval chain for every value band and risk level."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from legal_function_os.approval_matrix import (
    RISK_FIELDS,
    RISKS,
    build_approval_matrix,
    render_approval_html,
    render_approval_markdown,
)
from legal_function_os.cli import main as cli_main
from legal_function_os.policy import default_policy
from legal_function_os.rules import approval_chain, assess_risk, decide

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json"


def _requests() -> list[dict]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _cells(matrix: dict) -> dict:
    return {
        (row["value_band"], cell["risk"]): cell for row in matrix["rows"] for cell in row["cells"]
    }


def _run(argv: list[str]) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli_main(argv)
    return code, out.getvalue()


class ApprovalMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = default_policy()
        self.matrix = build_approval_matrix(_requests(), self.policy)

    def test_every_cell_is_the_rules_chain_and_starts_with_a_human(self) -> None:
        cells = _cells(self.matrix)
        self.assertEqual(len(cells), len(self.policy.value_bands) * len(RISKS))
        for (band, risk), cell in cells.items():
            if cell["reachable"]:
                self.assertEqual(
                    cell["approval_chain"],
                    approval_chain({"value_band": band}, risk, self.policy),
                )
                self.assertEqual(cell["approval_chain"][0], "Reviewer")
            else:
                self.assertEqual((cell["approval_chain"], cell["requests"]), ([], []))

    def test_only_unreachable_combinations_are_marked(self) -> None:
        unreachable = {
            key: cell["unreachable_reason"]
            for key, cell in _cells(self.matrix).items()
            if not cell["reachable"]
        }
        self.assertEqual(
            unreachable,
            {
                ("250k-1m", "LOW"): "Every request in this band is at least MEDIUM risk.",
                (">1m", "LOW"): "Every request in this band is HIGH risk.",
                (">1m", "MEDIUM"): "Every request in this band is HIGH risk.",
            },
        )

    def test_reachability_covers_every_field_assess_risk_reads(self) -> None:
        read: set[str] = set()

        class Recording(dict):
            def get(self, key, default=None):
                read.add(key)
                return super().get(key, default)

            def __getitem__(self, key):
                read.add(key)
                return super().__getitem__(key)

        for request in _requests():
            assess_risk(Recording(request), self.policy)
        self.assertLessEqual(read, set(RISK_FIELDS))

    def test_the_ladders_say_what_the_rules_do(self) -> None:
        policy = self.policy
        ladder = {step["adds"]: step["when"] for step in self.matrix["approval_ladder"]}
        self.assertEqual(ladder["Reviewer"], "Every request")
        bands = policy.value_bands
        for role, threshold in (
            ("Legal Ops Lead", policy.legal_ops_lead_from),
            ("General Counsel", policy.general_counsel_from),
            ("Board note", policy.board_note_from),
        ):
            self.assertTrue(ladder[role].startswith(f'Value band "{threshold}" or above'))
            below = bands[bands.index(threshold) - 1]
            self.assertIn(role, approval_chain({"value_band": threshold}, "LOW", policy))
            self.assertNotIn(role, approval_chain({"value_band": below}, "LOW", policy))
        self.assertIn("General Counsel", approval_chain({"value_band": "none"}, "HIGH", policy))

        plain = {"value_band": "none", "type": ""}
        high = [
            {**plain, "personal_data": True, "non_eea_transfer": True},
            {**plain, "value_band": policy.high_risk_from.value_band},
            {**plain, "uncapped_liability": True},
            {**plain, "type": "dispute", "value_band": policy.dispute_high_risk_from.value_band},
        ]
        medium = [
            {**plain, "value_band": policy.medium_risk_from.value_band},
            {**plain, "personal_data": True},
            *({**plain, "type": t} for t in policy.elevated_types),
        ]
        ladder_risk = {step["risk"]: step["any_of"] for step in self.matrix["risk_ladder"]}
        self.assertEqual(len(ladder_risk["HIGH"]), len(high))
        self.assertEqual(len(ladder_risk["MEDIUM"]), 3 if policy.elevated_types else 2)
        self.assertEqual(ladder_risk["LOW"], [])
        for request in high:
            self.assertEqual(assess_risk(request, policy)[0], "HIGH", request)
        for request in medium:
            self.assertEqual(assess_risk(request, policy)[0], "MEDIUM", request)
        self.assertEqual(assess_risk(plain, policy)[0], "LOW")

    def test_each_portfolio_request_sits_in_the_cell_its_decision_names(self) -> None:
        cells = _cells(self.matrix)
        placed = [rid for cell in cells.values() for rid in cell["requests"]]
        self.assertEqual(sorted(placed), sorted(r["id"] for r in _requests()))
        for request in _requests():
            decision = decide(request, self.policy)
            cell = cells[(request.get("value_band") or "none", decision.risk)]
            self.assertIn(decision.request_id, cell["requests"])
            self.assertEqual(cell["approval_chain"], decision.approval_chain)

    def test_a_request_without_a_value_band_counts_in_the_lowest_band(self) -> None:
        request = {**_requests()[2], "id": "REQ-NO-BAND"}
        del request["value_band"]
        matrix = build_approval_matrix([request], self.policy)
        [item] = matrix["requests"]
        self.assertEqual(item["value_band"], self.policy.value_bands[0])
        self.assertIn("REQ-NO-BAND", _cells(matrix)[(item["value_band"], item["risk"])]["requests"])

    def test_the_matrix_follows_the_policy(self) -> None:
        policy = replace(default_policy(), general_counsel_from="50k-250k", elevated_types=())
        matrix = build_approval_matrix([], policy)
        cell = _cells(matrix)[("50k-250k", "LOW")]
        self.assertEqual(cell["approval_chain"], ["Reviewer", "Legal Ops Lead", "General Counsel"])
        ladder = {step["adds"]: step["when"] for step in matrix["approval_ladder"]}
        self.assertTrue(ladder["General Counsel"].startswith('Value band "50k-250k"'))
        medium = next(step for step in matrix["risk_ladder"] if step["risk"] == "MEDIUM")
        self.assertEqual(len(medium["any_of"]), 2)
        self.assertEqual(matrix["requests"], [])
        self.assertIn("No request was given.", render_approval_markdown(matrix))

    def test_rendering_is_deterministic_escaped_and_self_contained(self) -> None:
        policy = replace(default_policy(), name='Policy <script>alert(1)</script> | "x"')
        requests = _requests()
        requests[0]["title"] = "MSA | <b>bold</b>"
        matrix = build_approval_matrix(requests, policy)
        page = render_approval_html(matrix)
        self.assertEqual(page, render_approval_html(build_approval_matrix(requests, policy)))
        self.assertNotIn("<script", page)
        self.assertNotIn("<b>bold</b>", page)
        for forbidden in ("http://", "https://", "<link"):
            self.assertNotIn(forbidden, page)
        markdown = render_approval_markdown(matrix)
        row = next(line for line in markdown.splitlines() if line.startswith("| REQ-1001 "))
        self.assertEqual(row.replace("\\|", "").count("|"), 6)
        self.assertIn("✓ 2 portfolio requests: REQ-1001, REQ-1005", render_approval_html(self.matrix))

    def test_the_cli_prints_and_writes_the_committed_matrix(self) -> None:
        code, stdout = _run(["approval-matrix", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout, (ROOT / "examples" / "approval-matrix.json").read_text(encoding="utf-8")
        )
        for argv in (["approval-matrix", "--out"], ["--quiet", "--approval-matrix-output"]):
            with tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(_run([*argv, tmp])[0], 0)
                self.assertEqual(
                    sorted(path.name for path in Path(tmp).glob("approval-matrix.*")),
                    ["approval-matrix.html", "approval-matrix.json", "approval-matrix.md"],
                )


if __name__ == "__main__":
    unittest.main()
