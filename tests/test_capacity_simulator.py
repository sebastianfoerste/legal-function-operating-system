import json
import unittest
from pathlib import Path

from legal_function_os.capacity_simulator import (
    build_capacity_simulation,
    render_capacity_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


class CapacitySimulationTests(unittest.TestCase):
    def setUp(self):
        self.requests = json.loads(
            (ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json").read_text(encoding="utf-8")
        )
        self.scenarios = json.loads(
            (ROOT / "src" / "legal_function_os" / "data" / "capacity_scenarios.json").read_text(encoding="utf-8")
        )

    def test_simulation_surfaces_and_reduces_constraints(self):
        simulation = build_capacity_simulation(self.requests, self.scenarios)

        current, protected = simulation["scenarios"]
        self.assertEqual(simulation["schema"], "legal-function-os.capacity-simulation.v1")
        self.assertEqual(current["status"], "CONSTRAINED")
        self.assertEqual(protected["status"], "WITHIN_ASSUMPTIONS")
        self.assertGreater(current["summary"]["backlog_points"], 0)
        self.assertEqual(protected["summary"]["backlog_points"], 0)
        self.assertGreater(current["summary"]["binding_constraints"], 0)
        self.assertEqual(protected["binding_constraints"], [])
        self.assertEqual(
            simulation["decision_brief"]["decision_status"],
            "HUMAN_REVIEW_REQUIRED",
        )
        self.assertEqual(
            simulation["decision_brief"]["scenarios_within_assumptions"],
            ["protected_focus_model"],
        )
        self.assertFalse(simulation["external_action_allowed"])

    def test_request_queue_is_deterministic_and_p1_first(self):
        first = build_capacity_simulation(self.requests, self.scenarios)
        second = build_capacity_simulation(self.requests, self.scenarios)

        self.assertEqual(first, second)
        self.assertEqual(
            first["scenarios"][0]["priority_review_queue"][0]["priority"],
            "P1_blocker",
        )

    def test_markdown_keeps_assumptions_and_review_gate_visible(self):
        markdown = render_capacity_markdown(
            build_capacity_simulation(self.requests, self.scenarios)
        )

        self.assertIn("illustrative management assumptions", markdown)
        self.assertIn("Binding constraints", markdown)
        self.assertIn("Minimum uplift", markdown)
        self.assertIn("Review gate", markdown)
        self.assertIn("No staffing change", markdown)

    def test_invalid_scenario_shape_fails_visibly(self):
        with self.assertRaisesRegex(ValueError, "JSON array of objects"):
            build_capacity_simulation(self.requests, {"scenario": "invalid"})


if __name__ == "__main__":
    unittest.main()
