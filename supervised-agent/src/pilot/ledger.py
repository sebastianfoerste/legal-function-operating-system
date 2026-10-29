"""The pilot's events in the parent's service-event ledger, one matter at a time.

The parent lifecycle has no revision loop, so revision cycles are folded into the
working state and the approval request is reported once, at final approval. Used by
``metrics.to_parent_ledger`` for the rehearsal report and by the review room's timing.
"""

from __future__ import annotations

from typing import Any

_PARENT_ROLE = {
    "business_requester": "Business Requester",
    "matter_owner": "Legal Counsel",
    "specialist_reviewer": "Privacy Counsel",
    "final_approver": "General Counsel",
}


def matter_ledger(
    matter_id: str, events: list[dict[str, Any]], clock: str = "fixture_at"
) -> list[dict[str, Any]]:
    """Map one matter's events onto the parent's request lifecycle, on one clock.

    ``clock`` names the event field that times every entry: ``fixture_at`` for the
    scripted rehearsal time, ``occurred_at`` for the time the server recorded.
    """

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
            "occurred_at_utc": event[clock],
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
