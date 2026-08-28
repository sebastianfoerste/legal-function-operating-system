"""Tests for the deterministic industrial robotics RaaS deal-desk pack."""

import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from legal_function_os.raas_cli import main as raas_cli_main
from legal_function_os.raas_deal_desk import (
    RAAS_INPUT_SCHEMA,
    SOURCE_MANIFEST,
    build_raas_deal_pack,
    render_raas_html,
    render_raas_markdown,
    render_raas_svg,
    source_digest,
    validate_raas_deal,
    write_raas_outputs,
)
from legal_function_os.raas_rules import _build_signing_gate

ROOT = Path(__file__).resolve().parents[1]
DEAL = json.loads((ROOT / "src" / "legal_function_os" / "data" / "raas_deal.json").read_text(encoding="utf-8"))


class RaaSDealDeskTests(unittest.TestCase):
    def setUp(self):
        self.pack = build_raas_deal_pack(DEAL)

    def test_current_draft_is_blocked(self):
        self.assertEqual(self.pack.signing_gate["status"], "blocked")
        self.assertFalse(self.pack.signing_gate["ready_for_human_approval"])
        self.assertFalse(self.pack.signing_gate["signature_action_allowed"])
        self.assertEqual(self.pack.signing_gate["answer"], "Do not sign the current draft.")
        self.assertFalse(self.pack.signing_gate["external_action_allowed"])
        self.assertEqual(len(self.pack.signing_gate["blocking_contract_items"]), 6)
        self.assertEqual(len(self.pack.signing_gate["blocking_finance_items"]), 1)
        self.assertEqual(len(self.pack.signing_gate["blocking_items"]), 7)

    def test_clear_deterministic_checks_still_require_human_approval(self):
        gate = _build_signing_gate((), (), ())
        self.assertEqual(gate["status"], "human_approval_required")
        self.assertTrue(gate["ready_for_human_approval"])
        self.assertFalse(gate["signature_action_allowed"])

    def test_playbook_catches_core_raas_nonstarters(self):
        blocked = {
            item.category
            for item in self.pack.clause_reviews
            if item.severity == "nonstarter"
        }
        self.assertTrue(
            {
                "liability",
                "acceptance",
                "IP ownership",
                "data and model improvement",
                "product and site safety",
                "commercial scope",
            }.issubset(blocked)
        )

    def test_every_clause_rule_is_evidence_backed_and_human_approved(self):
        self.assertTrue(self.pack.clause_reviews)
        for item in self.pack.clause_reviews:
            self.assertTrue(item.evidence_ref.startswith("synthetic-deal:"))
            self.assertTrue(item.required_approvals)

    def test_finance_handoff_blocks_subjective_acceptance(self):
        acceptance = next(
            item for item in self.pack.finance_handoff if item.issue_id == "FIN-002"
        )
        self.assertEqual(acceptance.status, "blocked")
        self.assertIn("IFRS 15", acceptance.framework)
        self.assertIn("ASC 606", acceptance.framework)
        self.assertTrue(
            any(item.issue_id == "FIN-005" and "lease" in item.topic.lower() for item in self.pack.finance_handoff)
        )

    def test_regulatory_matrix_uses_official_primary_sources(self):
        self.assertEqual(len(self.pack.regulatory_readiness), 7)
        source_ids = {item["id"] for item in SOURCE_MANIFEST}
        self.assertEqual(len(source_ids), len(SOURCE_MANIFEST))
        for item in self.pack.regulatory_readiness:
            self.assertIn(item.source_id, source_ids)
            self.assertTrue(item.source_url.startswith("https://eur-lex.europa.eu/"))
            self.assertTrue(item.evidence_required)
            self.assertIn(
                item.gate_effect,
                {
                    "signing_blocker",
                    "deployment_blocker",
                    "transition_follow_up",
                },
            )
        self.assertEqual(
            {item.gate_effect for item in self.pack.regulatory_readiness},
            {
                "signing_blocker",
                "deployment_blocker",
                "transition_follow_up",
            },
        )

    def test_source_manifest_distinguishes_regulations_and_directives(self):
        legal_effects = {item["legal_effect"] for item in SOURCE_MANIFEST}
        self.assertIn("directly_applicable_regulation", legal_effects)
        self.assertIn("directive_requires_national_implementation", legal_effects)
        product_liability = next(
            item for item in SOURCE_MANIFEST if item["id"] == "EU-PRODUCT-LIABILITY"
        )
        self.assertIn("transpose", product_liability["timing"])
        ai_act = next(item for item in SOURCE_MANIFEST if item["id"] == "EU-AI-ACT")
        self.assertIn("2 August 2026", ai_act["timing"])
        self.assertIn("2 August 2027", ai_act["timing"])

    def test_source_digest_is_stable_and_pack_bound(self):
        self.assertEqual(self.pack.source_digest, source_digest())
        self.assertEqual(
            self.pack.source_digest,
            build_raas_deal_pack(DEAL).source_digest,
        )

    def test_external_counsel_briefs_are_scoped_and_block_external_action(self):
        self.assertEqual(len(self.pack.external_counsel_briefs), 4)
        for brief in self.pack.external_counsel_briefs:
            self.assertFalse(brief.external_action_allowed)
            self.assertTrue(brief.budget_ceiling)
            self.assertTrue(brief.deliverable)
            self.assertTrue(brief.approval_required)

    def test_hundred_day_plan_has_three_operating_phases(self):
        self.assertEqual(len(self.pack.hundred_day_plan), 3)
        self.assertEqual(
            [phase.phase for phase in self.pack.hundred_day_plan],
            [
                "Days 1 to 30: establish control",
                "Days 31 to 60: build the operating model",
                "Days 61 to 100: scale and evidence",
            ],
        )

    def test_renderers_are_deterministic_and_show_reviewer_questions(self):
        second = build_raas_deal_pack(DEAL)
        self.assertEqual(render_raas_markdown(self.pack), render_raas_markdown(second))
        markdown = render_raas_markdown(self.pack)
        document = render_raas_html(self.pack)
        svg = render_raas_svg(self.pack)
        self.assertIn("What could delay deployment", markdown)
        self.assertIn("What could delay revenue", markdown)
        self.assertIn("Can we sign?", document)
        self.assertIn("RaaS Deal Decision Pack", svg)
        self.assertIn("+ 2 additional blockers in the decision pack", svg)
        self.assertIn("Offline local reviewer artifact", document)

    def test_outputs_include_machine_readable_sources_and_reviewer_room(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            outputs = write_raas_outputs(self.pack, Path(tmp_dir))
            self.assertEqual(set(outputs), {"json", "markdown", "html", "svg", "sources"})
            for output in outputs.values():
                self.assertTrue(output.exists())
            payload = json.loads(outputs["json"].read_text(encoding="utf-8"))
            sources = json.loads(outputs["sources"].read_text(encoding="utf-8"))
            self.assertEqual(payload["source_digest"], sources["source_digest"])
            self.assertFalse(payload["external_action_allowed"])

    def test_cli_writes_demo_and_can_gate_on_blockers(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertEqual(
                raas_cli_main(
                    [
                        "--input",
                        str(ROOT / "src" / "legal_function_os" / "data" / "raas_deal.json"),
                        "--out",
                        tmp_dir,
                        "--quiet",
                    ]
                ),
                0,
            )
            self.assertEqual(
                raas_cli_main(
                    [
                        "--input",
                        str(ROOT / "src" / "legal_function_os" / "data" / "raas_deal.json"),
                        "--quiet",
                        "--fail-on-blocker",
                    ]
                ),
                1,
            )
            self.assertTrue((Path(tmp_dir) / "raas-deal-room.html").exists())

    def test_invalid_deal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema must equal"):
            validate_raas_deal({"deal_id": "broken"})
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            validate_raas_deal({"schema": RAAS_INPUT_SCHEMA})
        with self.assertRaisesRegex(ValueError, "finance must be an object"):
            validate_raas_deal({**DEAL, "finance": []})
        with self.assertRaisesRegex(ValueError, "components must be"):
            validate_raas_deal(
                {
                    **DEAL,
                    "commercial_model": {
                        **DEAL["commercial_model"],
                        "components": [],
                    },
                }
            )
        with self.assertRaisesRegex(
            ValueError, "requested_terms.termination_for_convenience must be a boolean"
        ):
            validate_raas_deal(
                {
                    **DEAL,
                    "requested_terms": {
                        **DEAL["requested_terms"],
                        "termination_for_convenience": "yes",
                    },
                }
            )
        with self.assertRaisesRegex(
            ValueError, "commercial_model.annual_contract_value must be"
        ):
            validate_raas_deal(
                {
                    **DEAL,
                    "commercial_model": {
                        **DEAL["commercial_model"],
                        "annual_contract_value": True,
                    },
                }
            )

    def test_cli_malformed_input_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_input = Path(tmp_dir) / "bad.json"
            bad_input.write_text("{", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    raas_cli_main(["--input", str(bad_input), "--quiet"]),
                    2,
                )


if __name__ == "__main__":
    unittest.main()
