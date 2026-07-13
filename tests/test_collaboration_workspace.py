import json
import unittest
from pathlib import Path

from legal_function_os.collaboration_workspace import (
    activate_workflow,
    answer_portal,
    build_collaboration_workspace,
    compare_workflow_versions,
    render_portal,
    validate_workflow_definition,
)


REQUESTS = json.loads(Path("data/sample_requests.json").read_text())


class CollaborationWorkspaceTests(unittest.TestCase):
    def test_operational_list_is_deterministic_and_prioritises_blockers(self):
        first = build_collaboration_workspace(REQUESTS, "Q3 2026 synthetic")
        second = build_collaboration_workspace(REQUESTS, "Q3 2026 synthetic")
        self.assertEqual(first, second)
        rows = first["operational_list"]["rows"]
        if any(row["status"] == "blocked" for row in rows):
            self.assertEqual(rows[0]["status"], "blocked")
        self.assertTrue(all(row["facts"] for row in rows))

    def test_workflows_are_allowlisted_and_require_human_approval(self):
        definition = build_collaboration_workspace(REQUESTS, "Q3 2026")[
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

    def test_workflow_comparison_and_activation_require_review(self):
        active = build_collaboration_workspace(REQUESTS, "Q3 2026")["workflow_definitions"][0]
        draft = {**active, "version": 2, "status": "draft", "steps": [*active["steps"], {"id": "evidence-2", "type": "collect_evidence"}]}
        comparison = compare_workflow_versions(active, draft)
        self.assertEqual(comparison["to_version"], 2)
        self.assertEqual(len(comparison["added_steps"]), 1)
        with self.assertRaisesRegex(ValueError, "named reviewer"):
            activate_workflow(draft, reviewer="", approved=True)
        with self.assertRaisesRegex(ValueError, "named reviewer"):
            activate_workflow(draft, reviewer=None, approved=True)
        self.assertEqual(activate_workflow(draft, reviewer="General Counsel", approved=True)["status"], "active")

    def test_missing_request_values_use_stable_fallbacks(self):
        workspace = build_collaboration_workspace(
            [
                {
                    **REQUESTS[0],
                    "id": None,
                    "description": None,
                    "facts": None,
                    "dependencies": None,
                }
            ],
            "Q3 2026",
        )
        resource = workspace["knowledge_portal"]["resources"][0]
        self.assertEqual(resource["id"], "resource:1")
        self.assertEqual(
            resource["passage"],
            "Synthetic legal request precedent for local review.",
        )

    def test_zero_request_id_is_preserved(self):
        workspace = build_collaboration_workspace(
            [{**REQUESTS[0], "id": 0}],
            "Q3 2026",
        )
        resource = workspace["knowledge_portal"]["resources"][0]
        self.assertEqual(resource["id"], "resource:0")
        self.assertEqual(resource["source_ref"], "synthetic-request:0")

    def test_portal_answers_are_cited_or_abstain(self):
        portal = build_collaboration_workspace(REQUESTS, "Q3 2026")["knowledge_portal"]
        grounded = answer_portal(portal, "human approval workflow")
        self.assertEqual(grounded["status"], "grounded")
        self.assertTrue(grounded["citations"])
        self.assertEqual(
            answer_portal(portal, "quantum astrophysics")["status"],
            "insufficient_evidence",
        )
        self.assertFalse(portal["external_action_allowed"])

    def test_rendered_portal_has_local_search_and_abstention_message(self):
        portal = build_collaboration_workspace(REQUESTS, "Q3 2026")["knowledge_portal"]
        output = render_portal(portal, Path(self.id().replace(".", "-") + ".html"))
        try:
            content = output.read_text(encoding="utf-8")
            self.assertIn("Search approved passages", content)
            self.assertIn("Insufficient evidence in approved resources", content)
            self.assertNotIn("https://", content)
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
