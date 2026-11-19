"""Snoozes on a triage matter: a recorded pause with a typed reason, not a state.

A matter owner may snooze a matter in triage until a time, or until the requester
answers a question (ADR 0010). The snooze is one hash-chained event, and so is each way
a person ends it. Nothing acts when its time passes: no event is written and no timer
runs. Every reader (the review room, the requester view, the parent ledger and the
pilot metrics) works the pause out from the matter's events with this module, on the
matter's one clock, so they cannot disagree.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

SNOOZE_MAX_DAYS = 30
SNOOZE_EVENT = "matter_snoozed"
# Each of these, recorded while a snooze runs, ends it: the requester's answer, the
# owner ending it, a triage verb or a withdrawal.
ENDING_EVENTS = frozenset(
    {
        "snooze_answered",
        "snooze_ended",
        "triage_completed",
        "matter_declined",
        "matter_marked_duplicate",
        "matter_withdrawn",
    }
)
# How a snooze ended when its time ran out; no event records that.
TIME_PASSED = "time_passed"


def parse_time(value: Any) -> datetime | None:
    """An ISO 8601 time with a time zone, or None (no zone, not a time, or tampered)."""

    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def utc_text(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def matter_clock(events: Sequence[Mapping[str, Any]], now: str) -> tuple[str, str]:
    """The matter's one clock and its "now", as ``timing.matter_timing`` measures them.

    Scripted (``fixture_at``) when every event other than a refusal carries a scripted
    time; its "now" is the latest scripted step, refusals included. Otherwise the time
    the server recorded (``occurred_at``), whose "now" is the service clock's ``now``.
    """

    counted = [e for e in events if e["event_type"] != "command_refused"]
    if counted and all(e["fixture_at"] for e in counted):
        scripted = [(parse_time(e["fixture_at"]), e["fixture_at"]) for e in events]
        known = [(moment, text) for moment, text in scripted if moment is not None]
        if known:
            return "fixture_at", max(known)[1]
    return "occurred_at", now


def snooze_windows(
    events: Sequence[Mapping[str, Any]], clock: str, now: str | None = None
) -> list[dict[str, Any]]:
    """Every snooze on the matter in order, each with when and how it ended, if it has.

    ``events`` are the matter's events in seq order with parsed payloads; ``clock``
    names the field that times them. A snooze ends at the first ending event after it,
    or when its ``until`` passes, whichever comes first. Time passes only up to ``now``
    (when None, up to the latest event on this clock), so a snooze whose time has not
    come by then is still running.
    """

    starts = [i for i, e in enumerate(events) if e["event_type"] == SNOOZE_EVENT]
    if not starts:
        return []
    limit = parse_time(now)
    if limit is None:
        moments = [parse_time(e[clock]) for e in events]
        limit = max((m for m in moments if m is not None), default=None)
    windows: list[dict[str, Any]] = []
    for position, start in enumerate(starts):
        event = events[start]
        payload = event.get("payload") or {}
        since = parse_time(event[clock])
        until = parse_time(payload.get("until"))
        question = payload.get("question")
        window: dict[str, Any] = {
            "index": start,
            "since": event[clock],
            "until": utc_text(until) if until else None,
            "question": question if isinstance(question, str) and question else None,
            "reason": event["note"],
            "by": event["actor_id"],
            "answer": None,
            "end_index": None,
            "ended_at": None,
            "ended_by": None,
            "active": True,
        }
        # A later snooze can only start once this one is over; stop looking there.
        stop = starts[position + 1] if position + 1 < len(starts) else len(events)
        ending = next(
            (i for i in range(start + 1, stop) if events[i]["event_type"] in ENDING_EVENTS),
            None,
        )
        ending_at = parse_time(events[ending][clock]) if ending is not None else None
        # A pause cannot end before it began, whatever a mixed clock says.
        due = max(until, since) if until and since else until
        ran_out = (
            due is not None
            and limit is not None
            and due <= limit
            and (ending is None or (ending_at is not None and due <= ending_at))
        )
        if ran_out and due is not None:
            window.update(ended_at=utc_text(due), ended_by=TIME_PASSED, active=False)
        elif ending is not None:
            ended = events[ending]
            window.update(
                end_index=ending,
                ended_at=ended[clock],
                ended_by=ended["event_type"],
                active=False,
            )
            if ended["event_type"] == "snooze_answered":
                window["answer"] = ended["note"]
        if window["active"] and stop < len(events):
            # Only a store changed by hand holds a second snooze over a running one.
            window.update(end_index=stop, ended_at=events[stop][clock], ended_by=SNOOZE_EVENT)
            window["active"] = False
        windows.append(window)
    return windows


def latest_snooze(
    events: Sequence[Mapping[str, Any]], clock: str, now: str | None
) -> dict[str, Any] | None:
    """The matter's latest snooze, running or not, or None if it was never snoozed."""

    windows = snooze_windows(events, clock, now)
    return windows[-1] if windows else None


def active_snooze(
    events: Sequence[Mapping[str, Any]], clock: str, now: str | None
) -> dict[str, Any] | None:
    """The snooze running at ``now``, or None."""

    latest = latest_snooze(events, clock, now)
    return latest if latest and latest["active"] else None
