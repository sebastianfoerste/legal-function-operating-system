"""The audit-chain timeline of a matter, for the review room.

Every event on the matter's hash chain, in chain order, in runs of the version it
concerns, each classified as a command, a refusal, a decision or an export. The chain
status comes from ``PilotStore.check_events`` on the same rows: events before the
first failing row are verified, the failing row is the first bad event, and every
later event is not verified. Built from stored rows only, so the same store gives the
same timeline, and a tampered row is shown, never raised. It is part of the review
view, which requesters never get (``PilotService.view_matter``).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from src.pilot.store import ChainBreak

HASH_PREFIX = 12
PAYLOAD_TEXT_LIMIT = 2000
LEGEND = (
    ("command", "Command", "An accepted command that changed the matter."),
    (
        "refusal",
        "Refusal",
        "A command the server refused. The matter did not change; the refusal stays on the chain.",
    ),
    (
        "decision",
        "Decision",
        "A decision bound to this version: a change decision, sign-off, revision request, "
        "approval or acceptance. Each is also kept in the decision record.",
    ),
    ("export", "Export", "Files written to the local export folder. Nothing was sent."),
)
# Every event type the service writes, so a new one has to be classified on purpose.
EVENT_CLASSES = {
    "matter_created": "command",
    "matter_amended": "command",
    "non_substantive_edit": "command",
    "intake_submitted": "command",
    "triage_completed": "command",
    "reviewer_assigned": "command",
    "review_started": "command",
    "comment_added": "command",
    "comment_response_added": "command",
    "comment_resolved": "command",
    "comment_reopened": "command",
    "revision_submitted": "command",
    "review_resumed": "command",
    "matter_withdrawn": "command",
    "command_refused": "refusal",
    "change_decided": "decision",
    "specialist_signed_off": "decision",
    "revision_requested": "decision",
    "approved": "decision",
    "delivery_accepted": "decision",
    "internal_review_exported": "export",
    "delivery_package_prepared": "export",
}


def event_class(event_type: Any) -> str:
    """The class of an event type; an unknown (or tampered) type shows as a command."""

    return EVENT_CLASSES.get(event_type, "command")


def load_payload(text: Any) -> tuple[Any, bool]:
    """A stored payload parsed as JSON, and whether it parsed at all."""

    try:
        return json.loads(text), True
    except (TypeError, ValueError, RecursionError):
        return None, False


def payload_object(text: Any) -> dict[str, Any] | None:
    """A stored payload when it is a JSON object, as the service always writes it."""

    value, parsed = load_payload(text)
    return value if parsed and isinstance(value, dict) else None


def stored_text(value: Any) -> str | None:
    """A stored value as text; a tampered column can hold bytes or a number."""

    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _whole(value: Any) -> int | None:
    return value if type(value) is int else None


def _states(count: int, verified: bool, brk: ChainBreak | None) -> list[str]:
    """Each row's chain state, by its place in seq order (a stored seq may be tampered)."""

    if verified:
        return ["verified"] * count
    if brk is None:
        return ["unverified"] * count
    # A prev_hash mismatch means this row or the one before it was changed: the one
    # before may have been rewritten and rehashed, so it is not vouched for either.
    suspect = brk.index - 1 if brk.kind == "prev_hash_mismatch" and brk.index else None
    states = []
    for index in range(count):
        if index == suspect:
            states.append("suspect")
        elif index < brk.index:
            states.append("verified")
        else:
            states.append("first_bad" if index == brk.index else "unverified")
    return states


def _position(seq: Any) -> str:
    whole = _whole(seq)
    return str(whole) if whole is not None else repr(stored_text(seq))


def _explain(rows: Sequence[Mapping[str, Any]], brk: ChainBreak | None, ok: int) -> str:
    if not rows:
        return "No event is recorded."
    if brk is None:
        return "No event is verified."
    if ok == 0:
        parts = ["No event is verified."]
    else:
        parts = [f"Positions 0 to {ok - 1} are verified." if ok > 1 else "Position 0 is verified."]
    seq = _whole(brk.seq)
    if brk.kind == "sequence_gap":
        if seq is not None and seq > brk.index:
            parts.append(
                f"Position {brk.index} is missing."
                if seq == brk.index + 1
                else f"Positions {brk.index} to {seq - 1} are missing."
            )
        else:
            parts.append(f"The event stored at position {_position(brk.seq)} is out of sequence.")
    elif brk.kind == "prev_hash_mismatch" and brk.index:
        parts.append(
            f"Position {brk.index} does not link to position {brk.index - 1}, "
            "so one of the two was changed after it was recorded."
        )
    first = _position(rows[ok]["seq"])
    parts.append(f"The event at position {first} and every later event are not verified.")
    return " ".join(parts)


def _group(version: int | None, known: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    meta = known.get(version, {}) if version is not None else {}
    return {
        "version": version,
        **{
            key: meta.get(key)
            for key in ("created_at", "document_name", "document_sha256", "content_hash")
        },
        "set_aside": [],
        "events": [],
    }


def build_timeline(
    rows: Sequence[Mapping[str, Any]],
    versions: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    verification: Mapping[str, Any],
    brk: ChainBreak | None,
) -> dict[str, Any]:
    """Group event ``rows`` (in seq order) into runs of one version, with the chain status.

    ``verification`` and ``brk`` are ``PilotStore.check_events(rows)``, so the status
    covers exactly the rows shown. A refusal records no version; it belongs to the
    version in force when it happened, which an amendment moves to its ``new_version``.
    """

    known = {v["version"]: v for v in versions}
    states = _states(len(rows), bool(verification["verified"]), brk)
    ok = states.count("verified")
    groups: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    in_force: int | None = None
    for index, row in enumerate(rows):
        value, parsed = load_payload(row["payload"])
        payload = value if parsed and isinstance(value, dict) else None
        version = _whole((payload or {}).get("version"))
        if version is None:
            version = in_force
        in_force = version
        if row["event_type"] == "matter_amended":
            in_force = _whole((payload or {}).get("new_version")) or version
        kind = event_class(row["event_type"])
        counts[kind] += 1
        if not groups or groups[-1]["version"] != version:
            groups.append(_group(version, known))
        event_hash = stored_text(row["event_hash"]) or ""
        groups[-1]["events"].append(
            {
                "index": index,
                "seq": row["seq"] if _whole(row["seq"]) is not None else stored_text(row["seq"]),
                "event_type": stored_text(row["event_type"]),
                "class": kind,
                "actor_id": stored_text(row["actor_id"]),
                "role": stored_text(row["role"]),
                "note": stored_text(row["note"]),
                "occurred_at": stored_text(row["occurred_at"]),
                "fixture_at": stored_text(row["fixture_at"]),
                "prev_hash": stored_text(row["prev_hash"]),
                "event_hash": event_hash,
                "hash_prefix": event_hash[:HASH_PREFIX],
                "chain": states[index],
                "payload": payload,
                "payload_readable": parsed,
                "payload_text": (
                    None
                    if payload is not None
                    else (stored_text(row["payload"]) or "")[:PAYLOAD_TEXT_LIMIT]
                ),
            }
        )
    # A version made by the latest amendment has no event of its own yet; it is still kept.
    grouped = {g["version"] for g in groups}
    groups.extend(_group(v, known) for v in sorted(known) if v not in grouped)
    # Decisions set aside later are listed once per version, on its longest run (a version
    # has more than one run only when a stored version number was changed).
    longest: dict[int, dict[str, Any]] = {}
    for g in groups:
        v = g["version"]
        if v is not None and (v not in longest or len(g["events"]) > len(longest[v]["events"])):
            longest[v] = g
    for d in decisions:
        if d["invalidated_at"] and d["version"] in longest:
            longest[d["version"]]["set_aside"].append(
                {
                    key: d[key]
                    for key in ("kind", "target_id", "outcome", "actor_id", "invalidated_reason")
                }
            )
    return {
        "chain": {
            **verification,
            "verified_events": ok,
            "first_unverified_index": None if ok == len(rows) else ok,
            "explanation": _explain(rows, brk, ok),
        },
        "legend": [
            {"class": key, "label": label, "meaning": meaning, "count": counts[key]}
            for key, label, meaning in LEGEND
        ],
        "groups": groups,
    }
