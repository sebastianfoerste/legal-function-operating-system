"""Pilot measurement over the matter event log.

Two clocks are reported and never mixed. ``fixture_at`` is the scripted time a
scenario assigns to a step; it stands in for human elapsed time in a rehearsal.
``occurred_at`` and ``system_ms`` are operational: when the software actually ran
and how long it took. A rehearsal demonstrates that measurement works. It does not
produce pilot outcomes; those need observations from real participants.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.pilot.parent_bridge import CONTRACT_REVIEW_STATE, parent_module, parent_request
from src.pilot.service import VersionBody
from src.pilot.store import PilotStore

MEASUREMENT_PLAN_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "pilot" / "measurement-plan.json"
)
_STATE_AFTER = {
    "intake_submitted": "triage",
    "triage_completed": "assignment",
    "review_started": "review",
    "revision_requested": "revision_requested",
    "revision_submitted": "revised",
    "review_resumed": "review",
    "approved": "approved",
    "delivery_package_prepared": "ready_for_delivery",
    "delivery_accepted": "closed",
    "matter_withdrawn": "closed",
}
_WAITING_ON = {
    "business_requester": "requester_or_missing_facts",
    "matter_owner": "matter_owner_availability",
    "specialist_reviewer": "specialist_availability",
    "final_approver": "approver_availability",
}
_PARENT_ROLE = {
    "business_requester": "Business Requester",
    "matter_owner": "Legal Counsel",
    "specialist_reviewer": "Privacy Counsel",
    "final_approver": "General Counsel",
}


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _minutes(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    return round((_parse(end) - _parse(start)).total_seconds() / 60, 1)


def _load(store: PilotStore) -> list[dict[str, Any]]:
    matters: list[dict[str, Any]] = []
    with store.reading() as connection:
        for row in connection.execute("SELECT * FROM matters ORDER BY created_at, matter_id"):
            events = [
                {**dict(e), "payload": json.loads(e["payload"])}
                for e in connection.execute(
                    "SELECT * FROM events WHERE matter_id = ? ORDER BY seq", (row["matter_id"],)
                )
            ]
            version = connection.execute(
                "SELECT body FROM matter_versions WHERE matter_id = ? AND version = ?",
                (row["matter_id"], row["current_version"]),
            ).fetchone()
            matters.append(
                {
                    "row": dict(row),
                    "events": events,
                    "body": VersionBody.model_validate_json(version["body"]),
                    "chain": store.verify_chain(connection, row["matter_id"]),
                }
            )
    return matters


def _first(events: list[dict[str, Any]], event_type: str, key: str) -> str | None:
    return next((e[key] for e in events if e["event_type"] == event_type and e[key]), None)


def _matter_metrics(matter: dict[str, Any], key: str) -> dict[str, Any]:
    """Metrics for one matter on one clock (``fixture_at`` or ``occurred_at``)."""

    events = matter["events"]
    done = [e for e in events if e["event_type"] != "command_refused" and e[key]]
    created = next((e for e in events if e["event_type"] == "matter_created"), None)
    required = created["payload"].get("required_facts", 0) if created else 0
    missing = created["payload"].get("missing_facts", []) if created else []

    waiting: dict[str, float] = dict.fromkeys([*_WAITING_ON.values(), "requester_acceptance"], 0.0)
    reopened: set[str] = set()
    effort = {"intake": 0, "review": 0, "correction": 0}
    state = "intake"
    reviewed = False
    for index, event in enumerate(done):
        if index:
            gap = _minutes(done[index - 1][key], event[key]) or 0.0
            # The gap before an event is time spent waiting for whoever acted next.
            cause = (
                "requester_acceptance"
                if event["event_type"] == "delivery_accepted"
                else _WAITING_ON.get(event["role"], "matter_owner_availability")
            )
            waiting[cause] += gap
        minutes = event["effort_minutes"] or 0
        comment_id = event["payload"].get("comment_id", "")
        if event["event_type"] == "comment_reopened":
            reopened.add(comment_id)
        elif event["event_type"] == "comment_resolved":
            reopened.discard(comment_id)
        # Correction: work while a revision is open, amendments after review began,
        # and the matter owner's rework on an issue that was reopened.
        correcting = (
            state in {"revision_requested", "revised"}
            or (reviewed and event["event_type"] == "matter_amended")
            or (bool(reopened) and event["role"] == "matter_owner")
        )
        if correcting:
            effort["correction"] += minutes
        elif event["role"] == "business_requester":
            effort["intake"] += minutes
        else:
            effort["review"] += minutes
        if event["event_type"] == "matter_amended" and reviewed:
            state = "revised"
        state = _STATE_AFTER.get(event["event_type"], state)
        reviewed = reviewed or state == "review"

    clarification_wait = 0.0
    asked: dict[str, str] = {}
    for event in done:
        comment_id = event["payload"].get("comment_id")
        if event["event_type"] == "change_decided" and comment_id:
            asked[comment_id] = event[key]
        elif event["event_type"] == "comment_response_added" and comment_id in asked:
            clarification_wait += _minutes(asked.pop(comment_id), event[key]) or 0.0

    submitted = _first(done, "intake_submitted", key)
    return {
        "matter_id": matter["row"]["matter_id"],
        "state": matter["row"]["state"],
        "versions": matter["row"]["current_version"],
        "intake_completeness": {
            "required_facts": required,
            "present_at_first_submission": required - len(missing),
            "missing_at_first_submission": missing,
            "ratio": round((required - len(missing)) / required, 2) if required else None,
        },
        "assignment_minutes": _minutes(submitted, _first(done, "review_started", key)),
        "waiting_minutes_by_cause": {k: round(v, 1) for k, v in waiting.items()},
        "waiting_on_clarification_minutes": round(clarification_wait, 1),
        "effort_minutes": effort,
        "revision_count": sum(e["event_type"] == "revision_requested" for e in done),
        "substantive_amendments": sum(e["event_type"] == "matter_amended" for e in done),
        "reopened_issues": sum(e["event_type"] == "comment_reopened" for e in done),
        "refused_commands": sum(e["event_type"] == "command_refused" for e in events),
        "total_minutes_to_accepted_deliverable": _minutes(
            _first(done, "matter_created", key), _first(done, "delivery_accepted", key)
        ),
        "software_execution_ms": round(sum(e["system_ms"] or 0 for e in events), 1),
        "audit_chain_verified": matter["chain"].verified,
    }


def _plan() -> dict[str, Any]:
    return json.loads(MEASUREMENT_PLAN_PATH.read_text(encoding="utf-8"))


def build_pilot_metrics(store: PilotStore) -> dict[str, Any]:
    matters = _load(store)
    scripted = all(
        e["fixture_at"] for m in matters for e in m["events"] if e["event_type"] == "matter_created"
    )
    plan = _plan()
    return {
        "schema": "legal-ops-agent.pilot-metrics.v1",
        "data_basis": "synthetic_scripted_rehearsal" if scripted else "operational_observations",
        "interpretation": (
            "Scripted timestamps and declared effort demonstrate that the measures compute. "
            "They are not pilot outcomes and support no claim about time saved."
            if scripted
            else "Operational observations. Compare only against the baseline defined in the plan."
        ),
        "measurement_plan": plan,
        "baseline_comparison": (
            "not performed: no baseline has been collected"
            if plan["baseline"]["status"] != "collected"
            else "see baseline"
        ),
        "scripted_human_time": (
            [_matter_metrics(m, "fixture_at") for m in matters] if scripted else []
        ),
        "operational_time": [
            {
                key: value
                for key, value in _matter_metrics(m, "occurred_at").items()
                if key
                in {
                    "matter_id",
                    "software_execution_ms",
                    "refused_commands",
                    "audit_chain_verified",
                }
            }
            for m in matters
        ],
    }


def render_metrics_markdown(metrics: dict[str, Any]) -> str:
    plan = metrics["measurement_plan"]
    lines = [
        "# Pilot measurement report",
        "",
        f"- Data basis: `{metrics['data_basis']}`",
        f"- Interpretation: {metrics['interpretation']}",
        f"- Baseline: {plan['baseline']['status']} ({plan['baseline']['method']})",
        f"- Baseline window: {plan['baseline']['window']}",
        f"- Pilot window: {plan['pilot_window']}",
        f"- Baseline comparison: {metrics['baseline_comparison']}",
        "",
        "## Scripted human time per matter",
        "",
        "| Matter | State | Intake complete | Assignment (min) | Review effort | Correction effort | Revisions | Reopened | To accepted deliverable (min) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in metrics["scripted_human_time"]:
        intake = row["intake_completeness"]
        lines.append(
            f"| {row['matter_id']} | {row['state']} | {intake['present_at_first_submission']}/{intake['required_facts']} "
            f"| {row['assignment_minutes']} | {row['effort_minutes']['review']} | {row['effort_minutes']['correction']} "
            f"| {row['revision_count']} | {row['reopened_issues']} | {row['total_minutes_to_accepted_deliverable']} |"
        )
    lines += [
        "",
        "## Where the elapsed time went (scripted minutes)",
        "",
        "| Matter | Requester or missing facts | Matter owner | Specialist | Approver | Requester acceptance | Clarification open, ask to answer |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in metrics["scripted_human_time"]:
        waiting = row["waiting_minutes_by_cause"]
        lines.append(
            f"| {row['matter_id']} | {waiting['requester_or_missing_facts']} | {waiting['matter_owner_availability']} "
            f"| {waiting['specialist_availability']} | {waiting['approver_availability']} | {waiting['requester_acceptance']} | {row['waiting_on_clarification_minutes']} |"
        )
    lines += [
        "",
        "## Software execution (operational, measured)",
        "",
        "| Matter | Software execution (ms) | Refused commands | Event chain verified |",
        "| --- | --- | --- | --- |",
    ]
    for row in metrics["operational_time"]:
        lines.append(
            f"| {row['matter_id']} | {row['software_execution_ms']} | {row['refused_commands']} | {row['audit_chain_verified']} |"
        )
    lines += [
        "",
        "Software execution time is measured on the machine that ran the rehearsal. Human effort "
        "is declared per step in the scenario scripts. The two are reported separately because "
        "one does not predict the other.",
        "",
    ]
    return "\n".join(lines)


# -- parent reporting contract ---------------------------------------------------


def _matter_ledger(matter_id: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map one matter's scripted events onto the parent's request lifecycle."""

    entries: list[dict[str, Any]] = []
    approved_at = max(
        (i for i, e in enumerate(events) if e["event_type"] == "approved"), default=None
    )
    state: str | None = None
    waiting = False
    effort = 0

    def emit(kind: str, event: dict[str, Any], minutes: int) -> None:
        entry: dict[str, Any] = {
            "event_id": f"{matter_id}-{len(entries) + 1:02d}",
            "request_id": matter_id,
            "event_type": kind,
            "occurred_at_utc": event["fixture_at"],
            "actor_role": _PARENT_ROLE.get(event["role"], "Legal Counsel"),
            "note": f"Pilot event {event['event_type']} (synthetic).",
        }
        if minutes:
            entry["effort_minutes"] = minutes
        entries.append(entry)

    for index, event in enumerate(events):
        effort += event["effort_minutes"] or 0
        name, kinds = event["event_type"], []
        asks = name == "change_decided" and bool(event["payload"].get("comment_id"))
        if name == "matter_created" and state is None:
            kinds = ["submitted"]
        elif name == "triage_completed" and state == "submitted":
            kinds = ["acknowledged"]
        elif name == "review_started" and state == "acknowledged":
            kinds = ["assigned", "work_started"]
        elif asks and not waiting and state in {"work_started", "resumed"}:
            kinds, waiting = ["waiting_on_business"], True
        elif name == "comment_response_added" and waiting and event["role"] == "business_requester":
            kinds, waiting = ["resumed"], False
        elif index == approved_at and not waiting and state in {"work_started", "resumed"}:
            kinds = ["approval_requested", "approved"]
        elif name == "delivery_accepted" and state == "approved":
            kinds = ["completed"]
        for kind in kinds:
            # Effort recorded since the last mapped event travels with this one.
            emit(kind, event, effort)
            effort, state = 0, kind
    return entries


def to_parent_ledger(store: PilotStore) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Express scripted pilot events in the parent's service-event ledger schema.

    The parent lifecycle has no revision loop, so revision cycles are folded into
    the working state and the approval request is reported once, at final approval.
    """

    requests: list[dict[str, Any]] = []
    ledger_events: list[dict[str, Any]] = []
    for matter in _load(store):
        matter_id = matter["row"]["matter_id"]
        events = [
            e for e in matter["events"] if e["fixture_at"] and e["event_type"] != "command_refused"
        ]
        if not events:
            continue
        requests.append(parent_request(matter_id, matter["body"].intake))
        ledger_events.extend(_matter_ledger(matter_id, events))
    latest = max((e["occurred_at_utc"] for e in ledger_events), default=None)
    as_of = (
        (_parse(latest) + timedelta(hours=1)).isoformat().replace("+00:00", "Z") if latest else ""
    )
    ledger = {
        "schema": "legal-function-os.service-event-ledger.v1",
        "as_of_utc": as_of,
        "events": ledger_events,
    }
    return requests, ledger


def build_parent_outcome_view(store: PilotStore) -> dict[str, Any]:
    """Run the parent outcome control tower over the pilot's scripted events."""

    requests, ledger = to_parent_ledger(store)
    tower = parent_module("outcome_control_tower")
    config_path = parent_module("bundled").bundled_path("outcome_config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return tower.build_outcome_control_tower(requests, ledger, config)


def control_contract(view: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """One matter in the shared ``legal-workflow-controls.v1`` contract."""

    version, eligibility = view["version"], view["eligibility"]
    held = bool(version["scope_exclusions"]) or any(
        s["status"] == "blocker" for s in view["assessment"]["source_verifications"]
    )
    return {
        "schema": "legal-workflow-controls.v1",
        "review_state": "blocked" if held else CONTRACT_REVIEW_STATE[view["matter"]["state"]],
        "approval_gate": {
            "human_review_required": True,
            "export_allowed": bool(eligibility["eligible"]),
            "external_actions_allowed": False,
            "required_roles": [
                *[f"specialist_reviewer:{s}" for s in version["required_specialties"]],
                f"final_approver:{version['required_final_tier']}",
            ],
            "review_note": view["assessment"].get("review_note"),
        },
        "source_boundary": {
            "mode": "synthetic_only",
            "categories": sorted(
                {s["category"] for s in view["assessment"]["source_verifications"]}
            ),
            "human_verification_required": True,
        },
        "audit_events": [
            {
                "sequence": e["seq"],
                "event_type": e["event_type"],
                "actor": e["actor_id"],
                "timestamp_utc": e["occurred_at"],
                "note": e["note"],
                "previous_hash": e["prev_hash"],
                "event_hash": e["event_hash"],
            }
            for e in events
        ],
    }
