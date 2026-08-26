from models import AuditEvent, AuditEventType, compute_audit_event_hash, verify_audit_chain
from src.audit_chain import append_audit_event


def _build_event(
    seq: int,
    prev_hash: str | None,
    event_type: AuditEventType,
    actor: str,
    note: str,
    timestamp_utc: str,
) -> AuditEvent:
    return AuditEvent(
        event_type=event_type,
        actor=actor,
        note=note,
        timestamp_utc=timestamp_utc,
        seq=seq,
        prev_hash=prev_hash,
        event_hash=compute_audit_event_hash(seq, prev_hash, event_type, actor, note, timestamp_utc),
    )


def test_verify_audit_chain_rejects_empty_chain():
    result = verify_audit_chain([])

    assert result.verified is False
    assert result.event_count == 0
    assert result.reason == "no audit events recorded"


def test_verify_audit_chain_accepts_valid_chain():
    first = _build_event(
        0,
        None,
        "assessment_created",
        "LegalOps Agent",
        "Assessment created from typed matter intake.",
        "2026-06-30T10:00:00Z",
    )
    second = _build_event(
        1,
        first.event_hash,
        "review_decision_applied",
        "General Counsel",
        "Approved after privacy review of the synthetic matter facts.",
        "2026-06-30T11:00:00Z",
    )

    result = verify_audit_chain([first, second])

    assert result.verified is True
    assert result.event_count == 2
    assert result.chain_root_hash == second.event_hash
    assert result.broken_at_seq is None


def test_verify_audit_chain_detects_tampered_note():
    first = _build_event(
        0,
        None,
        "assessment_created",
        "LegalOps Agent",
        "Assessment created from typed matter intake.",
        "2026-06-30T10:00:00Z",
    )
    tampered = first.model_copy(update={"note": "Assessment created from a different intake."})

    result = verify_audit_chain([tampered])

    assert result.verified is False
    assert result.broken_at_seq == 0
    assert "event_hash mismatch" in result.reason


def test_verify_audit_chain_detects_broken_prev_hash_link():
    first = _build_event(
        0,
        None,
        "assessment_created",
        "LegalOps Agent",
        "Assessment created from typed matter intake.",
        "2026-06-30T10:00:00Z",
    )
    second = _build_event(
        1,
        first.event_hash,
        "review_decision_applied",
        "General Counsel",
        "Approved after privacy review of the synthetic matter facts.",
        "2026-06-30T11:00:00Z",
    )
    broken_second = second.model_copy(update={"prev_hash": "0" * 64})

    result = verify_audit_chain([first, broken_second])

    assert result.verified is False
    assert result.broken_at_seq == 1
    assert "prev_hash mismatch" in result.reason


def test_append_audit_event_builds_linked_chain():
    events = append_audit_event(
        [],
        event_type="assessment_created",
        actor="LegalOps Agent",
        note="Assessment created from typed matter intake.",
        timestamp_utc="2026-06-30T10:00:00Z",
    )
    events = append_audit_event(
        events,
        event_type="review_decision_applied",
        actor="General Counsel",
        note="Approved after privacy review of the synthetic matter facts.",
        timestamp_utc="2026-06-30T11:00:00Z",
    )

    assert [event.seq for event in events] == [0, 1]
    assert events[0].prev_hash is None
    assert events[1].prev_hash == events[0].event_hash
    assert len(events[1].event_hash) == 64
    assert verify_audit_chain(events).verified is True
