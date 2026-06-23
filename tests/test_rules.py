"""Deterministic tests. Pure stdlib unittest so `make test` needs no dependencies."""

import json
import unittest
from pathlib import Path

from legal_function_os.rules import decide, assess_risk, approval_chain, external_counsel
from legal_function_os.board_pack import build_board_pack, render_markdown

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

    def test_fundraising_goes_external_corporate(self):
        self.assertIn("corporate", external_counsel(_req("REQ-1005"), "HIGH"))

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
