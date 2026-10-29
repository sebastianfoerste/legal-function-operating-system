"""The audit-chain timeline of a matter, for the review room.

Every event on the matter's hash chain, in chain order, in runs of the version it
concerns, each classified as a command, a refusal, a decision or an export. The chain
status is ``PilotStore.verify_chain``'s: the first event it rejects is marked, and the
events after it are marked as not verified. Built from stored rows only, so the same
store gives the same timeline. It is part of the review view, which requesters never
get (``PilotService.view_matter``).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

HASH_PREFIX = 12
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


def event_class(event_type: str) -> str:
    return EVENT_CLASSES.get(event_type, "command")


def read_payload(text: Any) -> dict[str, Any] | None:
    """The stored payload, or None when it is not a JSON object (the chain then fails)."""

    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _chain_state(seq: int, chain: Mapping[str, Any]) -> str:
    if chain["verified"]:
        return "verified"
    broken = chain.get("broken_at_seq")
    if broken is None or seq > broken:
        return "unverified"
    return "first_bad" if seq == broken else "verified"


def _group(
    version: int | None,
    known: Mapping[int, Mapping[str, Any]],
    set_aside: Mapping[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    meta = known.get(version, {}) if version is not None else {}
    return {
        "version": version,
        **{
            key: meta.get(key)
            for key in ("created_at", "document_name", "document_sha256", "content_hash")
        },
        "set_aside": set_aside.get(version, []) if version is not None else [],
        "events": [],
    }


def build_timeline(
    events: Iterable[Mapping[str, Any]],
    versions: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    chain: Mapping[str, Any],
) -> dict[str, Any]:
    """Group ``events`` (rows in seq order) into runs of one version, with the chain status.

    A refusal records no version; it belongs to the version in force when it happened,
    which an amendment moves to its ``new_version``.
    """

    known = {v["version"]: v for v in versions}
    set_aside: dict[int, list[dict[str, Any]]] = {}
    for d in decisions:
        if d["invalidated_at"]:
            set_aside.setdefault(d["version"], []).append(
                {
                    key: d[key]
                    for key in ("kind", "target_id", "outcome", "actor_id", "invalidated_reason")
                }
            )
    groups: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    in_force: int | None = None
    for row in events:
        payload = read_payload(row["payload"])
        version = _whole((payload or {}).get("version"))
        if version is None:
            version = in_force
        in_force = version
        if row["event_type"] == "matter_amended":
            in_force = _whole((payload or {}).get("new_version")) or version
        kind = event_class(row["event_type"])
        counts[kind] += 1
        if not groups or groups[-1]["version"] != version:
            first_run = all(g["version"] != version for g in groups)
            groups.append(_group(version, known, set_aside if first_run else {}))
        groups[-1]["events"].append(
            {
                "seq": row["seq"],
                "event_type": row["event_type"],
                "class": kind,
                "actor_id": row["actor_id"],
                "role": row["role"],
                "note": row["note"],
                "occurred_at": row["occurred_at"],
                "fixture_at": row["fixture_at"],
                "prev_hash": row["prev_hash"],
                "event_hash": row["event_hash"],
                "hash_prefix": str(row["event_hash"])[:HASH_PREFIX],
                "chain": _chain_state(row["seq"], chain),
                "payload": payload,
            }
        )
    # A version made by the latest amendment has no event of its own yet; it is still kept.
    grouped = {g["version"] for g in groups}
    groups.extend(_group(v, known, set_aside) for v in sorted(known) if v not in grouped)
    return {
        "chain": dict(chain),
        "legend": [
            {"class": key, "label": label, "meaning": meaning, "count": counts[key]}
            for key, label, meaning in LEGEND
        ],
        "groups": groups,
    }
