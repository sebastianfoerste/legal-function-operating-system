import json
import unittest
from pathlib import Path

from legal_function_os.legora_workspace import (
    answer_portal,
    build_legora_workspace,
    validate_workflow_definition,
)


REQUESTS = json.loads(Path("data/sample_requests.json").read_text())


class LegoraWorkspaceTests(unittest.TestCase):
    def test_operational_list_is_deterministic_and_prioritises_blockers(self):
        first = build_legora_workspace(REQUESTS, "Q3 2026 synthetic")
        second = build_legora_workspace(REQUESTS, "Q3 2026 synthetic")
        self.assertEqual(first, second)
        rows = first["operational_list"]["rows"]
        if any(row["status"] == "blocked" for row in rows):
            self.assertEqual(rows[0]["status"], "blocked")

    def test_workflows_are_allowlisted_and_require_human_approval(self):
        definition = build_legora_workspace(REQUESTS, "Q3 2026")[
            "workflow_definitions"
        ][0]
        without_approval = {
            **definition,
            "steps": [
                step for step in definition["steps"] if step["type"] != "human_approval"
            ],
        }
        with self.assertRaisesRegex(ValueError, "human approval"):
            validate_workflow_definition(without_approval)

    def test_portal_answers_are_cited_or_abstain(self):
        portal = build_legora_workspace(REQUESTS, "Q3 2026")["knowledge_portal"]
        grounded = answer_portal(portal, "human approval workflow")
        self.assertEqual(grounded["status"], "grounded")
        self.assertTrue(grounded["citations"])
        self.assertEqual(
            answer_portal(portal, "quantum astrophysics")["status"],
            "insufficient_evidence",
        )
        self.assertFalse(portal["external_action_allowed"])


if __name__ == "__main__":
    unittest.main()
