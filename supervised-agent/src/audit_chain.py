from __future__ import annotations

from typing import Any

from models import AuditEvent, AuditEventType, compute_audit_event_hash


def append_audit_event(
    events: list[AuditEvent],
    *,
    event_type: AuditEventType,
    actor: str,
    note: str,
    timestamp_utc: str,
    details: dict[str, Any] | None = None,
) -> list[AuditEvent]:
    """Return events plus one new chain-linked AuditEvent."""

    seq = len(events)
    prev_hash = events[-1].event_hash if events else None
    event_hash = compute_audit_event_hash(
        seq, prev_hash, event_type, actor, note, timestamp_utc, details
    )
    new_event = AuditEvent(
        event_type=event_type,
        actor=actor,
        note=note,
        timestamp_utc=timestamp_utc,
        seq=seq,
        prev_hash=prev_hash,
        event_hash=event_hash,
        details=details,
    )
    return [*events, new_event]
