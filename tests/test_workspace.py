import json
import unittest
from pathlib import Path

from legal_function_os.workspace import build_legal_function_workspace

ROOT = Path(__file__).resolve().parents[1]
REQUESTS = json.loads((ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json").read_text(encoding="utf-8"))


class LegalFunctionWorkspace(unittest.TestCase):
    def setUp(self):
        self.workspace = build_legal_function_workspace(REQUESTS, period="Q3 2026 synthetic")

    def test_request_vault_preserves_provenance_and_blocks_external_action(self):
        vault = self.workspace["request_vault"]
        self.assertEqual(len(vault["records"]), len(REQUESTS))
        self.assertTrue(all(row["provenance_ref"].startswith("synthetic-request:") for row in vault["records"]))
        self.assertFalse(vault["external_action_allowed"])

    def test_guided_triage_workflows_cover_every_request(self):
        workflows = self.workspace["triage_workflows"]["workflows"]
        self.assertEqual(len(workflows), len(REQUESTS))
        self.assertTrue(all(len(workflow["steps"]) == 4 for workflow in workflows))
        self.assertTrue(all(workflow["external_action_allowed"] is False for workflow in workflows))

    def test_gc_command_center_prioritizes_blocked_workflows(self):
        command_center = self.workspace["command_center"]
        statuses = [row["status"] for row in command_center["rows"]]
        if "blocked" in statuses:
            self.assertEqual(statuses[0], "blocked")
        self.assertGreater(command_center["summary"]["blocked_workflows"], 0)
        self.assertFalse(command_center["external_action_allowed"])


if __name__ == "__main__":
    unittest.main()
