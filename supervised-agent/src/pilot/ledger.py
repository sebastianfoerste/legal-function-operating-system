"""The pilot's events in the parent's service-event ledger, one matter at a time.

The parent lifecycle has no revision loop, so revision cycles are folded into the
working state and the approval request is reported once, at final approval. Used by
``metrics.to_parent_ledger`` for the rehearsal report and by the review room's timing.
"""

from __future__ import annotations

from typing import Any

from src.pilot.snooze import SNOOZE_EVENT, TIME_PASSED, parse_time, snooze_windows

_PARENT_ROLE = {
    "business_requester": "Business Requester",
    "matter_owner": "Legal Counsel",
    "specialist_reviewer": "Privacy Counsel",
    "final_approver": "General Counsel",
}
# The parent lets a request wait on the business only once work has started. A snooze on
# a request legal has not acknowledged is legal's first response, so it is reported as
# acknowledged, assigned and work started before the wait.
_TO_WORK = {
    "submitted": ["acknowledged", "assigned", "work_started"],
    "acknowledged": ["assigned", "work_started"],
    "work_started": [],
    "resumed": [],
}
_CLOSED_IN_TRIAGE = {"matter_declined", "matter_marked_duplicate"}


def matter_ledger(
    matter_id: str,
    events: list[dict[str, Any]],
    clock: str = "fixture_at",
    as_of: str | None = None,
) -> list[dict[str, Any]]:
    """Map one matter's events onto the parent's request lifecycle, on one clock.

    ``clock`` names the event field that times every entry: ``fixture_at`` for the
    scripted rehearsal time, ``occurred_at`` for the time the server recorded. ``as_of``
    is the time the ledger is read at: a snooze whose time runs out by then ends at its
    ``until`` with a ``resumed`` entry (none is ever later than ``as_of``). Without it,
    time is known to have passed only up to the latest event.
    """

    entries: list[dict[str, Any]] = []
    approved_at = max(
        (i for i, e in enumerate(events) if e["event_type"] == "approved"), default=None
    )
    state: str | None = None
    # The matter waits on the business while any clarification asked of the requester is
    # still open: an answer from the requester or a resolution closes it, a reopening
    # opens it again. A running snooze is a wait on the business too.
    clarifications: set[Any] = set()
    open_asks: set[Any] = set()
    windows = {w["index"]: w for w in snooze_windows(events, clock, as_of)}
    snooze: dict[str, Any] | None = None
    effort = 0

    def emit(kind: str, at: str, role: str, minutes: int, note: str) -> None:
        entry: dict[str, Any] = {
            "event_id": f"{matter_id}-{len(entries) + 1:02d}",
            "request_id": matter_id,
            "event_type": kind,
            "occurred_at_utc": at,
            "actor_role": _PARENT_ROLE.get(role, "Legal Counsel"),
            "note": note,
        }
        if minutes:
            entry["effort_minutes"] = minutes
        entries.append(entry)

    def run_out(before: Any) -> None:
        """End a snooze whose time ran out before ``before`` (None: by ``as_of``)."""

        nonlocal snooze, state
        if snooze is None or snooze["ended_by"] != TIME_PASSED:
            return
        due, then = parse_time(snooze["ended_at"]), parse_time(before)
        if before is not None and (due is None or then is None or then < due):
            return
        waited = snooze
        snooze = None
        if not open_asks and state == "waiting_on_business":
            emit(
                "resumed",
                waited["ended_at"],
                "matter_owner",
                0,
                "Snooze ran out at its time; no event records it (synthetic).",
            )
            state = "resumed"

    for index, event in enumerate(events):
        run_out(event[clock])
        effort += event["effort_minutes"] or 0
        name, kinds = event["event_type"], []
        comment_id = event["payload"].get("comment_id")
        was_waiting = bool(open_asks) or snooze is not None
        if name == "change_decided" and comment_id:
            clarifications.add(comment_id)
            open_asks.add(comment_id)
        elif name == "comment_reopened" and comment_id in clarifications:
            open_asks.add(comment_id)
        elif name == "comment_resolved" or (
            name == "comment_response_added" and event["role"] == "business_requester"
        ):
            open_asks.discard(comment_id)
        if name == SNOOZE_EVENT and index in windows:
            snooze = windows[index]
        elif snooze is not None and snooze["end_index"] == index:
            snooze = None
        waiting = bool(open_asks) or snooze is not None
        # Legal's clock starts when the request reaches legal, not when the draft opens.
        if name == "intake_submitted" and state is None:
            kinds = ["submitted"]
        elif name == "triage_completed" and state == "submitted":
            kinds = ["acknowledged"]
        elif name in _CLOSED_IN_TRIAGE and state == "submitted":
            # Declining, or naming the original, is legal's response; nothing is resolved.
            kinds = ["acknowledged"]
        elif name == "review_started" and state == "acknowledged":
            kinds = ["assigned", "work_started"]
        elif waiting and not was_waiting and state in {"work_started", "resumed"}:
            kinds = ["waiting_on_business"]
        elif waiting and not was_waiting and name == SNOOZE_EVENT and state in _TO_WORK:
            kinds = [*_TO_WORK[state], "waiting_on_business"]
        elif was_waiting and not waiting and state == "waiting_on_business":
            kinds = ["resumed"]
        elif index == approved_at and not open_asks and state in {"work_started", "resumed"}:
            kinds = ["approval_requested", "approved"]
        elif name == "delivery_accepted" and state == "approved":
            kinds = ["completed"]
        for kind in kinds:
            # Effort recorded since the last mapped event travels with this one.
            emit(kind, event[clock], event["role"], effort, f"Pilot event {name} (synthetic).")
            effort, state = 0, kind
    run_out(None)
    return entries
