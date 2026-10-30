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

from src.pilot.ledger import matter_ledger
from src.pilot.parent_bridge import CONTRACT_REVIEW_STATE, parent_module, parent_request
from src.pilot.service import StoredChange, VersionBody
from src.pilot.store import PilotStore
from src.pilot.timeline import payload_object

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
# A playbook rule that reviewers override this often is worth a lawyer's second look.
OVERRIDE_THRESHOLD = 5
OVERRIDE_WINDOW_DAYS = 365
_OVERRIDES = ("rejected", "amended")
_OVERRIDE_NOTE = (
    "Proposals only. Nothing here changes the playbook: a lawyer decides whether a rule "
    "is revised, clarified or kept, and records that as a new playbook version."
)


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
                {**dict(e), "payload": payload_object(e["payload"]) or {}}
                for e in connection.execute(
                    "SELECT * FROM events WHERE matter_id = ? ORDER BY seq", (row["matter_id"],)
                )
            ]
            version = connection.execute(
                "SELECT body FROM matter_versions WHERE matter_id = ? AND version = ?",
                (row["matter_id"], row["current_version"]),
            ).fetchone()
            changes = [
                StoredChange.model_validate_json(c["body"])
                for c in connection.execute(
                    "SELECT body FROM changes WHERE matter_id = ? AND version = ? ORDER BY position",
                    (row["matter_id"], row["current_version"]),
                )
            ]
            matters.append(
                {
                    "row": dict(row),
                    "events": events,
                    "body": VersionBody.model_validate_json(version["body"]),
                    "changes": changes,
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


# -- playbook override patterns ---------------------------------------------------


def _override_records(matters: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """One record per closed matter and change whose standing decision departs from the playbook.

    Only the final version counts, so a decision carried across versions is counted once.
    The time is that of the last ``change_decided`` event for the change and outcome, on
    the same clock as the rest of the report.
    """

    records = []
    for matter in matters:
        if matter["row"]["state"] != "closed":
            continue
        for change in matter["changes"]:
            if change.decision not in _OVERRIDES:
                continue
            times = [
                e[key]
                for e in matter["events"]
                if e["event_type"] == "change_decided"
                and e["payload"].get("change_id") == change.id
                and e["payload"].get("outcome") == change.decision
                and e[key]
            ]
            rule = matter["body"].playbook.rule(change.rule_id or "")
            records.append(
                {
                    "matter_id": matter["row"]["matter_id"],
                    "rule_id": change.rule_id or "(no rule)",
                    "topic": rule.topic if rule else "(no rule)",
                    "outcome": change.decision,
                    "reason": change.decision_reason or "",
                    "decided_by": change.decided_by,
                    "at": times[-1] if times else None,
                }
            )
    return records


def _override_suggestion(rejected: int, amended: int) -> str:
    if rejected and not amended:
        return (
            "Reviewers kept the counterparty's wording every time. Consider whether the "
            "standard position still fits these deals."
        )
    if amended and not rejected:
        return (
            "Reviewers rewrote the proposed wording every time. Consider whether the standard "
            "wording or the fallback needs revising."
        )
    return "Reviewers departed in both directions. Clarify the rule before revising it."


def override_patterns(
    records: list[dict[str, Any]],
    *,
    threshold: int = OVERRIDE_THRESHOLD,
    window_days: int = OVERRIDE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Count overrides per playbook rule in the window ending at the latest decision.

    Deterministic: the window ends at the latest dated record, not at the time the report
    is built. A rule with ``threshold`` or more overrides becomes a proposal for review.
    """

    dated = [r for r in records if r["at"]]
    as_of = max((r["at"] for r in dated), default=None)
    start = _parse(as_of) - timedelta(days=window_days) if as_of else None
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for record in dated:
        if start is not None and _parse(record["at"]) >= start:
            by_rule.setdefault(record["rule_id"], []).append(record)
    rules = []
    for rule_id, group in by_rule.items():
        group = sorted(group, key=lambda r: (r["at"], r["matter_id"]))
        rejected = sum(r["outcome"] == "rejected" for r in group)
        amended = len(group) - rejected
        flagged = len(group) >= threshold
        rules.append(
            {
                "rule_id": rule_id,
                "topic": group[0]["topic"],
                "overrides_in_window": len(group),
                "rejected": rejected,
                "amended": amended,
                "matters": sorted({r["matter_id"] for r in group}),
                "reasons": [
                    {"matter_id": r["matter_id"], "outcome": r["outcome"], "reason": r["reason"]}
                    for r in group
                ],
                "flagged": flagged,
                "suggestion": _override_suggestion(rejected, amended) if flagged else None,
            }
        )
    rules.sort(key=lambda r: (-r["overrides_in_window"], r["rule_id"]))
    return {
        "basis": "closed matters; the standing decision on each change in the final version",
        "threshold": threshold,
        "window_days": window_days,
        "as_of": as_of,
        "undated_overrides": len(records) - len(dated),
        "rules": rules,
        "proposals": [r["rule_id"] for r in rules if r["flagged"]],
        "note": _OVERRIDE_NOTE,
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
        "playbook_override_patterns": override_patterns(
            _override_records(matters, "fixture_at" if scripted else "occurred_at")
        ),
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
    lines += _render_overrides(metrics["playbook_override_patterns"])
    return "\n".join(lines)


def _render_overrides(patterns: dict[str, Any]) -> list[str]:
    lines = [
        "## Playbook override patterns",
        "",
        f"Basis: {patterns['basis']}. A rule overridden in {patterns['threshold']} or more "
        f"matters within {patterns['window_days']} days, up to {patterns['as_of'] or 'the latest decision'}, "
        "becomes a proposal for review.",
        "",
    ]
    if not patterns["rules"]:
        return [*lines, "No change departed from the playbook in a closed matter.", ""]
    lines += [
        "| Rule | Topic | Overrides | Counterparty wording kept | Amended | Matters | Proposal |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rule in patterns["rules"]:
        lines.append(
            f"| {rule['rule_id']} | {rule['topic']} | {rule['overrides_in_window']} | {rule['rejected']} "
            f"| {rule['amended']} | {', '.join(rule['matters'])} | {'yes' if rule['flagged'] else 'no'} |"
        )
    lines.append("")
    flagged = [r for r in patterns["rules"] if r["flagged"]]
    if not flagged:
        lines.append(f"No rule reached the threshold of {patterns['threshold']} overrides.")
    for rule in flagged:
        lines += [
            "",
            f"### Proposal: review `{rule['rule_id']}` ({rule['topic']})",
            "",
            rule["suggestion"],
            "",
            "Reasons recorded by the reviewers:",
            "",
        ]
        lines += [f"- {r['matter_id']} ({r['outcome']}): {r['reason']}" for r in rule["reasons"]]
    lines += ["", patterns["note"], ""]
    return lines


# -- parent reporting contract ---------------------------------------------------


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
        ledger_events.extend(matter_ledger(matter_id, events))
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
