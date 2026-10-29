"""How long a matter has taken, measured by the parent's outcome control tower.

The matter's events go through the mapping behind ``metrics.to_parent_ledger``
(``ledger.matter_ledger``), and the parent tower measures them on its service calendar,
so business time, waiting time and the service levels are the parent's. Each matter is
measured on one clock and the two are never mixed: the scripted rehearsal time when
every event carries one, otherwise the time the server recorded. No clock is added: an
open matter is measured up to the service clock's ``now``, which tests inject.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.pilot.ledger import matter_ledger
from src.pilot.models import PilotIntake
from src.pilot.parent_bridge import parent_module, parent_request


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _utc(value: str) -> str:
    return _parse(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def matter_timing(
    matter_id: str,
    intake: PilotIntake,
    events: list[dict[str, Any]],
    *,
    closed: bool,
    withdrawn: bool,
    now: str,
) -> dict[str, Any]:
    """Elapsed and business time for one matter, or why it cannot be measured.

    ``events`` are the matter's event rows in seq order, with parsed payloads.
    """

    counted = [e for e in events if e["event_type"] != "command_refused"]
    scripted = bool(counted) and all(e["fixture_at"] for e in counted)
    clock = "fixture_at" if scripted else "occurred_at"
    base: dict[str, Any] = {"clock": "scripted" if scripted else "recorded"}
    if not counted:
        return {**base, "available": False, "reason": "no event recorded"}
    tower = parent_module("outcome_control_tower")
    try:
        # A closed matter is measured to its closing event. The scripted clock has no
        # "now", so an open rehearsal matter is measured to its latest scripted step,
        # refusals included.
        if closed:
            as_of = _utc(counted[-1][clock])
        elif scripted:
            as_of = _utc(max((e[clock] for e in events if e[clock]), key=_parse))
        else:
            as_of = _utc(now)
        config = json.loads(
            parent_module("bundled").bundled_path("outcome_config.json").read_text("utf-8")
        )
        result = tower.build_outcome_control_tower(
            [parent_request(matter_id, intake)],
            {
                "schema": tower.LEDGER_SCHEMA,
                "as_of_utc": as_of,
                "events": matter_ledger(matter_id, counted, clock),
            },
            config,
        )
        [row] = result["requests"]
        completed = row["state"] == "completed"
        measured_to = _utc(row["last_event_at_utc"]) if completed else as_of
        elapsed = (_parse(measured_to) - _parse(row["submitted_at_utc"])).total_seconds()
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        # A stored event the parent cannot read (or a tampered one) leaves timing out;
        # it never stops the review room.
        return {**base, "available": False, "reason": str(error)}
    return {
        **base,
        "available": True,
        "as_of": as_of,
        "measured_to": measured_to,
        "open": not closed,
        "elapsed_hours": round(elapsed / 3600, 2),
        "business_hours": row["gross_cycle_business_hours"],
        "legal_controlled_hours": row["legal_controlled_hours"],
        "business_wait_hours": row["business_wait_hours"],
        "first_response_business_hours": row["first_response_business_hours"],
        "response_target_business_hours": row["response_target_business_hours"],
        "response_sla": row["response_sla"],
        "resolution_target_business_hours": row["resolution_target_business_hours"],
        "resolution_sla": (
            "not_applicable" if withdrawn and not completed else row["resolution_sla"]
        ),
        "calendar": result["calendar"],
    }
