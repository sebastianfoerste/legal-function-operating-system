import unittest

from legal_function_os.agent_run import build_agent_runs


def request(**overrides):
    base = {"id": "REQ-1", "title": "DPA für neuen Subprozessor", "type": "dpa", "description": "Neuer Auftragsverarbeiter für Ticketdaten.", "facts": ["Vendor: HelpDeskCo", "Datenkategorien: Kundendaten"], "value_band": "50k-250k"}
    base.update(overrides)
    return base


class AgentRunTests(unittest.TestCase):
    def test_every_request_gets_a_run_with_six_steps(self):
        result = build_agent_runs([request()], period="Q3 2026 synthetic")
        self.assertEqual(result["schema"], "legal-function-os.agent-runs.v1")
        self.assertEqual(len(result["runs"][0]["steps"]), 6)
        self.assertFalse(result["external_action_allowed"])

    def test_runs_never_complete_without_human_approval(self):
        run = build_agent_runs([request()])["runs"][0]
        approval = next(step for step in run["steps"] if step["key"] == "human_approval")
        self.assertEqual(approval["status"], "review_required")
        self.assertEqual(run["status"], "review_required")

    def test_p1_blocker_blocks_the_run(self):
        run = build_agent_runs([request(urgency="blocker", type="dispute")])["runs"][0]
        self.assertEqual(next(step for step in run["steps"] if step["key"] == "risk_triage")["status"], "blocked")
        self.assertEqual(run["status"], "blocked")

    def test_missing_intake_fields_block(self):
        run = build_agent_runs([request(title="")])["runs"][0]
        self.assertEqual(next(step for step in run["steps"] if step["key"] == "intake")["status"], "blocked")

    def test_factless_request_needs_evidence_review(self):
        run = build_agent_runs([request(facts=[])])["runs"][0]
        self.assertEqual(next(step for step in run["steps"] if step["key"] == "evidence")["status"], "review_required")

    def test_response_plan_is_derived_from_the_decision_only(self):
        actions = build_agent_runs([request()])["runs"][0]["response_plan"]["planned_actions"]
        self.assertTrue(any(action.startswith("Confirm queue:") for action in actions))
        self.assertTrue(any("approval" in action.lower() for action in actions))


if __name__ == "__main__":
    unittest.main()
