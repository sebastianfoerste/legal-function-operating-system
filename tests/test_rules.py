"""Deterministic tests. Pure stdlib unittest so `make test` needs no dependencies."""

import json
import tempfile
import unittest
from pathlib import Path

from legal_function_os.rules import decide, assess_risk, approval_chain, external_counsel
from legal_function_os.board_pack import build_board_pack, render_markdown
from legal_function_os.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = json.loads((ROOT / "data" / "sample_requests.json").read_text(encoding="utf-8"))


def _req(rid):
    return next(r for r in REQUESTS if r["id"] == rid)


class Risk(unittest.TestCase):
    def test_non_eea_personal_data_is_high(self):
        risk, _ = assess_risk(_req("REQ-1002"))
        self.assertEqual(risk, "HIGH")

    def test_uncapped_liability_over_1m_is_high(self):
        risk, _ = assess_risk(_req("REQ-1001"))
        self.assertEqual(risk, "HIGH")

    def test_small_nda_is_low(self):
        risk, _ = assess_risk(_req("REQ-1003"))
        self.assertEqual(risk, "LOW")


class ApprovalMatrix(unittest.TestCase):
    def test_small_low_risk_needs_only_reviewer(self):
        self.assertEqual(approval_chain(_req("REQ-1003"), "LOW"), ["Reviewer"])

    def test_value_band_boundaries_flip_binding_approver(self):
        base = {"id": "REQ-BAND", "title": "Boundary fixture", "type": "commercial_contract"}
        self.assertEqual(approval_chain({**base, "value_band": "<50k"}, "LOW"), ["Reviewer"])
        self.assertEqual(
            approval_chain({**base, "value_band": "50k-250k"}, "LOW"),
            ["Reviewer", "Legal Ops Lead"],
        )
        self.assertEqual(
            approval_chain({**base, "value_band": "250k-1m"}, "MEDIUM"),
            ["Reviewer", "Legal Ops Lead", "General Counsel"],
        )
        self.assertEqual(
            approval_chain({**base, "value_band": ">1m"}, "HIGH"),
            ["Reviewer", "Legal Ops Lead", "General Counsel", "Board note"],
        )

    def test_high_risk_overrides_low_value_to_gc(self):
        req = {"id": "REQ-HIGH", "title": "High risk low value", "type": "dpa", "value_band": "<50k"}
        self.assertEqual(approval_chain(req, "HIGH"), ["Reviewer", "General Counsel"])

    def test_over_1m_requires_gc_and_board_note(self):
        chain = approval_chain(_req("REQ-1001"), "HIGH")
        self.assertIn("General Counsel", chain)
        self.assertIn("Board note", chain)

    def test_chain_always_starts_with_a_human_reviewer(self):
        for r in REQUESTS:
            risk, _ = assess_risk(r)
            self.assertEqual(approval_chain(r, risk)[0], "Reviewer")


class ExternalCounsel(unittest.TestCase):
    def test_large_dispute_goes_external(self):
        self.assertTrue(external_counsel(_req("REQ-1007"), "HIGH").startswith("External"))

    def test_small_dispute_stays_in_house(self):
        req = {"type": "dispute", "value_band": "50k-250k"}
        self.assertEqual(external_counsel(req, "MEDIUM"), "in-house")

    def test_fundraising_goes_external_corporate(self):
        self.assertIn("corporate", external_counsel(_req("REQ-1005"), "HIGH"))

    def test_cross_border_ai_governance_goes_to_specialist(self):
        self.assertEqual(
            external_counsel(_req("REQ-1004"), "HIGH"),
            "External: cross-border AI/privacy specialist",
        )

    def test_routine_nda_stays_in_house(self):
        self.assertEqual(external_counsel(_req("REQ-1003"), "LOW"), "in-house")


class Routing(unittest.TestCase):
    def test_dpa_routes_to_privacy(self):
        self.assertEqual(decide(_req("REQ-1002")).queue, "Privacy")

    def test_dispute_routes_to_litigation(self):
        self.assertEqual(decide(_req("REQ-1007")).queue, "Litigation")


class BoardPack(unittest.TestCase):
    def setUp(self):
        self.pack = build_board_pack(REQUESTS, period="Q2 2026 (synthetic)")

    def test_blocker_dispute_is_p1(self):
        dispute = next(d for d in self.pack.decisions if d.request_id == "REQ-1007")
        self.assertEqual(dispute.priority, "P1_blocker")
        self.assertIn("immediately", " ".join(dispute.escalations).lower())

    def test_board_attention_includes_over_1m_items(self):
        ids = {item["id"] for item in self.pack.board_attention}
        self.assertIn("REQ-1001", ids)  # >1m MSA
        self.assertIn("REQ-1005", ids)  # >1m financing

    def test_sla_breach_is_surfaced(self):
        ids = {item["id"] for item in self.pack.sla_breaches}
        self.assertIn("REQ-1006", ids)

    def test_zero_sla_breaches_clear_the_count(self):
        requests = [{k: v for k, v in r.items() if k != "sla_breached"} for r in REQUESTS]
        pack = build_board_pack(requests, period="Q2 2026 (synthetic)")
        self.assertEqual(pack.totals["sla_breaches"], 0)
        self.assertEqual(pack.sla_breaches, [])

    def test_multiple_sla_breaches_are_counted(self):
        requests = [dict(r) for r in REQUESTS]
        requests[0]["sla_breached"] = True
        requests[1]["sla_breached"] = True
        pack = build_board_pack(requests, period="Q2 2026 (synthetic)")
        self.assertEqual(pack.totals["sla_breaches"], 3)
        self.assertEqual({item["id"] for item in pack.sla_breaches}, {"REQ-1001", "REQ-1002", "REQ-1006"})

    def test_cli_fail_on_breach_gates_only_missed_slas(self):
        self.assertEqual(
            cli_main(["--input", str(ROOT / "data" / "sample_requests.json"), "--quiet"]),
            0,
        )
        self.assertEqual(
            cli_main(["--input", str(ROOT / "data" / "sample_requests.json"), "--quiet", "--fail-on-breach"]),
            1,
        )

    def test_cli_board_attention_without_sla_breach_does_not_fail(self):
        requests = [{k: v for k, v in r.items() if k != "sla_breached"} for r in REQUESTS]
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "no_sla_breach.json"
            tmp_path.write_text(json.dumps(requests), encoding="utf-8")
            self.assertEqual(cli_main(["--input", str(tmp_path), "--quiet", "--fail-on-breach"]), 0)

    def test_external_referrals_counted(self):
        self.assertGreaterEqual(self.pack.totals["external_referrals"], 2)

    def test_render_is_deterministic(self):
        again = build_board_pack(REQUESTS, period="Q2 2026 (synthetic)")
        self.assertEqual(render_markdown(self.pack), render_markdown(again))

    def test_totals_are_consistent(self):
        self.assertEqual(self.pack.totals["requests"], len(REQUESTS))
        self.assertEqual(self.pack.totals["high_risk"], self.pack.by_risk.get("HIGH", 0))


if __name__ == "__main__":
    unittest.main()
