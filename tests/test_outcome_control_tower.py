from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from legal_function_os.cli import main as cli_main
from legal_function_os.outcome_control_tower import (
    ServiceCalendar,
    build_outcome_control_tower,
    render_outcome_html,
    render_outcome_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


class OutcomeControlTowerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests = json.loads(
            (ROOT / "data" / "sample_requests.json").read_text(encoding="utf-8")
        )
        self.ledger = json.loads(
            (ROOT / "data" / "service_events.json").read_text(encoding="utf-8")
        )
        self.config = json.loads(
            (ROOT / "data" / "outcome_config.json").read_text(encoding="utf-8")
        )

    def test_seeded_tower_reconciles_and_surfaces_bottleneck(self) -> None:
        tower = build_outcome_control_tower(self.requests, self.ledger, self.config)

        self.assertEqual(tower["schema"], "legal-function-os.outcome-control-tower.v1")
        self.assertEqual(tower["executive_summary"]["requests"], 8)
        self.assertEqual(tower["executive_summary"]["binding_queue"], "Commercial")
        self.assertGreaterEqual(tower["executive_summary"]["stalled_requests"], 2)
        self.assertFalse(tower["external_action_allowed"])
        for row in tower["requests"]:
            self.assertAlmostEqual(
                row["gross_cycle_business_hours"],
                row["business_wait_hours"] + row["legal_controlled_hours"],
                places=2,
            )
        self.assertIn(
            "assumption-based management proxies",
            tower["value_proxy"]["assumption_notice"],
        )

    def test_business_calendar_handles_weekend_and_excluded_date(self) -> None:
        calendar = ServiceCalendar.from_dict(self.config["calendar"])
        start = datetime.fromisoformat("2026-07-09T15:00:00+00:00")
        end = datetime.fromisoformat("2026-07-13T09:00:00+00:00")

        self.assertEqual(calendar.business_minutes(start, end), 180)

    def test_unknown_request_and_invalid_transition_fail(self) -> None:
        unknown = deepcopy(self.ledger)
        unknown["events"][0]["request_id"] = "REQ-UNKNOWN"
        with self.assertRaisesRegex(ValueError, "unknown request"):
            build_outcome_control_tower(self.requests, unknown, self.config)

        invalid = deepcopy(self.ledger)
        invalid["events"][1]["event_type"] = "completed"
        with self.assertRaisesRegex(ValueError, "invalid transition"):
            build_outcome_control_tower(self.requests, invalid, self.config)

        unordered = deepcopy(self.ledger)
        unordered["events"][1], unordered["events"][2] = (
            unordered["events"][2],
            unordered["events"][1],
        )
        with self.assertRaisesRegex(ValueError, "chronological order"):
            build_outcome_control_tower(self.requests, unordered, self.config)

    def test_renderers_are_deterministic_and_escape_html(self) -> None:
        requests = deepcopy(self.requests)
        requests[0]["title"] = "Enterprise <script>alert(1)</script>"
        tower = build_outcome_control_tower(requests, self.ledger, self.config)

        self.assertEqual(
            render_outcome_markdown(tower),
            render_outcome_markdown(
                build_outcome_control_tower(requests, self.ledger, self.config)
            ),
        )
        rendered = render_outcome_html(tower)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)

    def test_cli_requires_all_outcome_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = cli_main(
                [
                    "--input",
                    str(ROOT / "data" / "sample_requests.json"),
                    "--events-input",
                    str(ROOT / "data" / "service_events.json"),
                    "--out",
                    tmp,
                    "--quiet",
                ]
            )
        self.assertEqual(status, 2)


if __name__ == "__main__":
    unittest.main()
