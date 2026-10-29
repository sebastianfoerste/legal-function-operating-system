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
    kpi_status_text,
    render_outcome_html,
    render_outcome_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


class OutcomeControlTowerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests = json.loads(
            (ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json").read_text(encoding="utf-8")
        )
        self.ledger = json.loads(
            (ROOT / "src" / "legal_function_os" / "data" / "service_events.json").read_text(encoding="utf-8")
        )
        self.config = json.loads(
            (ROOT / "src" / "legal_function_os" / "data" / "outcome_config.json").read_text(encoding="utf-8")
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

    def _tiles(self, tower: dict) -> dict:
        return {tile["kpi"]: tile for tile in tower["kpi_tiles"]}

    def test_kpi_tiles_show_target_delta_as_of_and_source(self) -> None:
        tower = build_outcome_control_tower(self.requests, self.ledger, self.config)
        tiles = self._tiles(tower)
        self.assertEqual(
            [tile["title"] for tile in tower["kpi_tiles"]],
            ["Completed requests", "Response SLA attainment", "Stalled requests", "Binding queue"],
        )
        expected = {
            "throughput_rate": ("6/8", "70.0%", "+5.0 pp", "on_target", "+5.0 pp against target 70.0%: on target"),
            "response_sla_attainment": ("87.5%", "90.0%", "-2.5 pp", "off_target", "-2.5 pp against target 90.0%: below target"),
            "stalled_requests": ("2", "0", "+2", "off_target", "+2 against target 0: above target"),
            "binding_queue": ("Commercial", None, None, "no_target", "No target set"),
        }
        for kpi, (display, target, delta, status, words) in expected.items():
            tile = tiles[kpi]
            self.assertEqual(
                (tile["display"], tile["target_display"], tile["delta_display"], tile["status"]),
                (display, target, delta, status),
                kpi,
            )
            self.assertEqual(kpi_status_text(tile), words)
            self.assertEqual(tile["as_of_utc"], "2026-07-17T16:00:00+00:00")
        self.assertIn("52 events over 8 requests", tiles["response_sla_attainment"]["source"])
        self.assertTrue(tiles["stalled_requests"]["source"].endswith("target from the outcome config"))
        self.assertNotIn("target from", tiles["binding_queue"]["source"])
        rendered = render_outcome_html(tower)
        self.assertIn("✗ -2.5 pp against target 90.0%: below target", rendered)
        self.assertIn("✓ +5.0 pp against target 70.0%: on target", rendered)
        self.assertIn(
            "| Stalled requests | 2 | +2 against target 0: above target | 2026-07-17T16:00:00+00:00 |",
            render_outcome_markdown(tower),
        )

    def test_as_of_comes_from_the_ledger_only(self) -> None:
        later = deepcopy(self.ledger)
        later["as_of_utc"] = "2026-07-20T09:00:00Z"
        tiles = self._tiles(build_outcome_control_tower(self.requests, later, self.config))
        self.assertEqual(
            {tile["as_of_utc"] for tile in tiles.values()}, {"2026-07-20T09:00:00+00:00"}
        )
        self.assertNotEqual(tiles["stalled_requests"]["display"], "")

    def test_a_target_met_exactly_is_on_target_in_either_direction(self) -> None:
        config = deepcopy(self.config)
        config["kpi_targets"] = {"response_sla_attainment": 0.875, "stalled_requests": 2}
        tiles = self._tiles(build_outcome_control_tower(self.requests, self.ledger, config))
        self.assertEqual(
            (tiles["response_sla_attainment"]["delta_display"], tiles["response_sla_attainment"]["status"]),
            ("+0.0 pp", "on_target"),
        )
        self.assertEqual(
            (tiles["stalled_requests"]["delta_display"], tiles["stalled_requests"]["status"]),
            ("+0", "on_target"),
        )
        self.assertEqual(tiles["throughput_rate"]["status"], "no_target")

    def test_kpi_targets_are_optional_and_checked(self) -> None:
        config = deepcopy(self.config)
        del config["kpi_targets"]
        tower = build_outcome_control_tower(self.requests, self.ledger, config)
        self.assertEqual({tile["status"] for tile in tower["kpi_tiles"]}, {"no_target"})
        self.assertEqual(tower["kpi_targets"], {})
        bad = [
            ([], "must be a JSON object"),
            ({"first_response_hours": 4}, "unknown KPI: first_response_hours"),
            ({"response_sla_attainment": 1.5}, "between 0 and 1"),
            ({"response_sla_attainment": -0.1}, "between 0 and 1"),
            ({"throughput_rate": "90%"}, "must be a number"),
            ({"throughput_rate": True}, "must be a number"),
            ({"throughput_rate": float("nan")}, "must be a number"),
            ({"stalled_requests": float("inf")}, "must be a number"),
            ({"stalled_requests": -1}, "whole number of at least 0"),
            ({"stalled_requests": 1.5}, "whole number of at least 0"),
        ]
        for targets, message in bad:
            config["kpi_targets"] = targets
            with self.assertRaisesRegex(ValueError, message, msg=repr(targets)):
                build_outcome_control_tower(self.requests, self.ledger, config)

    def test_an_unmeasured_attainment_renders_as_not_measured(self) -> None:
        request = deepcopy(self.requests[0])
        ledger = {
            "schema": self.ledger["schema"],
            "as_of_utc": "2026-07-06T12:00:00Z",
            "events": [
                {
                    "event_id": "E-1",
                    "request_id": request["id"],
                    "event_type": "submitted",
                    "occurred_at_utc": "2026-07-06T09:00:00Z",
                    "actor_role": "Business Requester",
                }
            ],
        }
        tower = build_outcome_control_tower([request], ledger, self.config)
        tile = self._tiles(tower)["response_sla_attainment"]
        self.assertEqual((tile["display"], tile["status"]), ("n/a", "unmeasured"))
        self.assertEqual(kpi_status_text(tile), "Target 90.0%; not measured yet")
        self.assertIn("Response SLA attainment: n/a", render_outcome_markdown(tower))
        self.assertIn("Target 90.0%; not measured yet", render_outcome_html(tower))

    def test_request_rows_carry_their_service_level_targets(self) -> None:
        tower = build_outcome_control_tower(self.requests, self.ledger, self.config)
        for row in tower["requests"]:
            self.assertGreater(row["response_target_business_hours"], 0)
            self.assertGreater(row["resolution_target_business_hours"], 0)
            if row["first_response_business_hours"] is not None:
                met = row["first_response_business_hours"] <= row["response_target_business_hours"]
                self.assertEqual(row["response_sla"], "met" if met else "breached", row["request_id"])

    def test_cli_requires_all_outcome_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = cli_main(
                [
                    "--input",
                    str(ROOT / "src" / "legal_function_os" / "data" / "sample_requests.json"),
                    "--events-input",
                    str(ROOT / "src" / "legal_function_os" / "data" / "service_events.json"),
                    "--out",
                    tmp,
                    "--quiet",
                ]
            )
        self.assertEqual(status, 2)


if __name__ == "__main__":
    unittest.main()
