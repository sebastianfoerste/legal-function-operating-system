"""Reviewer sessions for a bounded pilot: who decided what, why, and how long it took.

A draft is prepared once per matter round. Each reviewer then works on a private
copy of it, so no reviewer sees another's decisions. Every step of a session is one
event in the assessment's hash-chained audit trail, and the timings are read from
those events rather than typed in afterwards.

The chain is the record. A session file is accepted only if replaying its events
onto the draft reproduces the file exactly, so nothing in it can be edited without
also rebuilding the chain.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models import (
    AuditEvent,
    AuditEventType,
    LegalOpsAssessment,
    MatterIntake,
    ReviewDecision,
    ReviewState,
    verify_audit_chain,
)
from src.audit_chain import append_audit_event
from src.legal_ops import SYSTEM_ACTOR, apply_review_decision, assess_matter, utc_now_iso
from src.pilot.evidence.harness_review import (
    HarnessMatterReview,
    recommendations_from_harness_review,
)
from src.pilot.evidence.recommendations import (
    DECIDED,
    RecommendationSet,
    decide_recommendation,
    recommendations_from_assessment,
)

DRAFT_SCHEMA: Final = "legal-ops-agent.pilot-review-draft.v1"
SESSION_SCHEMA: Final = "legal-ops-agent.pilot-review-session.v1"

EvidenceClass = Literal["practising_lawyer", "author_self_review", "synthetic_example"]
# Where the recommendations come from: this agent's rules, or a model review that
# contract-review-eval-harness captured and identifies by hash.
ReviewSource = Literal["agent_rules", "harness_review"]
# Reserved for worked examples, so a fabricated session cannot carry a pseudonym
# that a real reviewer could also hold.
SYNTHETIC_REVIEWER_ID = "R00"
_PSEUDONYM = re.compile(r"R[0-9]{2,}")


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def review_sha256(recommendation_set: RecommendationSet) -> str:
    """Identity of the exact recommendations put to a reviewer, decisions excluded."""

    return _digest(
        {
            "source_digest": recommendation_set.source_digest,
            "recommendations": [
                {
                    "id": item.id,
                    "locator": item.locator,
                    "original_text": item.original_text,
                    "proposed_text": item.proposed_text,
                    "rationale": item.rationale,
                    "source_refs": item.source_refs,
                }
                for item in recommendation_set.recommendations
            ],
        }
    )


def assessment_sha256(assessment: LegalOpsAssessment) -> str:
    """Identity of the assessment a draft was built on, its audit trail excluded."""

    return _digest(assessment.model_dump(mode="json", exclude={"audit_events"}))


class PilotReviewDraft(BaseModel):
    """The assessment and recommendations as first put to reviewers."""

    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.pilot-review-draft.v1"] = Field(
        DRAFT_SCHEMA, alias="schema"
    )
    assessment: LegalOpsAssessment
    recommendation_set: RecommendationSet
    review_source: ReviewSource = "agent_rules"
    review_sha256: str = Field(..., min_length=64, max_length=64)


class PilotReviewSession(BaseModel):
    """One reviewer's private copy of a draft, with that reviewer's decisions."""

    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.pilot-review-session.v1"] = Field(
        SESSION_SCHEMA, alias="schema"
    )
    session_id: str = Field(..., min_length=6)
    # A pseudonym such as R01. A public repository is a permanent, searchable record.
    reviewer_id: str
    reviewer_profile: str = ""
    evidence_class: EvidenceClass
    review_source: ReviewSource = "agent_rules"
    review_sha256: str = Field(..., min_length=64, max_length=64)
    assessment: LegalOpsAssessment
    recommendation_set: RecommendationSet
    material_omissions: list[str] = Field(default_factory=list)
    workflow_feedback: str = ""
    declared_review_minutes: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_reviewer(self) -> "PilotReviewSession":
        if not _PSEUDONYM.fullmatch(self.reviewer_id):
            raise ValueError(
                f"reviewer_id {self.reviewer_id!r} must be a pseudonym of the form R01"
            )
        is_synthetic = self.evidence_class == "synthetic_example"
        if is_synthetic and self.reviewer_id != SYNTHETIC_REVIEWER_ID:
            raise ValueError(f"a synthetic example uses the reviewer id {SYNTHETIC_REVIEWER_ID}")
        # Every all-zero id is held back, so R000 cannot pass for a person either.
        if not is_synthetic and set(self.reviewer_id[1:]) == {"0"}:
            raise ValueError(f"{self.reviewer_id} is reserved for synthetic examples")
        return self


class SessionTiming(BaseModel):
    """Timings of one session, read from its audit events."""

    started_at_utc: str
    reviewable_at_utc: str | None = None
    closed_at_utc: str | None = None
    draft_preparation_seconds: float = Field(..., ge=0)
    minutes_to_reviewable_draft: float | None = None
    elapsed_review_minutes: float | None = None
    declared_review_minutes: float | None = None
    review_minutes: float | None = None
    review_minutes_source: Literal["reviewer_declared", "audit_timestamps"] | None = None


def _parse(timestamp: str) -> datetime:
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp {timestamp!r} carries no UTC offset")
    return parsed


def _minutes_between(start: str, end: str) -> float:
    return round((_parse(end) - _parse(start)).total_seconds() / 60, 2)


def _first(events: list[AuditEvent], event_type: AuditEventType) -> AuditEvent | None:
    return next((event for event in events if event.event_type == event_type), None)


def _require_not_before_last(events: list[AuditEvent], timestamp: str) -> None:
    if _parse(timestamp) < _parse(events[-1].timestamp_utc):
        raise ValueError("an event cannot precede the last recorded event")


def prepare_review_draft(
    matter: MatterIntake,
    *,
    documents_root: Path | None = None,
    harness_review: HarnessMatterReview | None = None,
    intake_at: str | None = None,
    ready_at: str | None = None,
) -> PilotReviewDraft:
    """Assess a matter and fix the recommendations reviewers will be asked to rate.

    Without a harness review the recommendations are this agent's rule-based ones.
    With one, each finding of that review is a recommendation and the draft is bound
    to the hash by which the harness identifies the review.
    """

    assessment = assess_matter(matter, documents_root=documents_root, created_at=intake_at)
    unverified = [
        f"{record.document_id}: {record.status}"
        for record in assessment.document_verifications
        if record.status != "verified"
    ]
    if unverified:
        raise ValueError(
            f"a review draft needs every matter document verified: {', '.join(unverified)}"
        )
    blockers = [
        finding.category for finding in assessment.findings if finding.severity == "blocker"
    ]
    if blockers:
        raise ValueError(f"a review draft cannot be prepared while blockers remain: {blockers}")
    source: ReviewSource
    if harness_review is None:
        source = "agent_rules"
        recommendation_set = recommendations_from_assessment(assessment)
        digest = review_sha256(recommendation_set)
    else:
        source = "harness_review"
        recommendation_set = recommendations_from_harness_review(harness_review, matter)
        digest = harness_review.canonical_sha256()
    timestamp = ready_at or utc_now_iso()
    _require_not_before_last(assessment.audit_events, timestamp)
    events = append_audit_event(
        assessment.audit_events,
        event_type="review_draft_ready",
        actor=SYSTEM_ACTOR,
        note="Review draft prepared for reviewer sessions.",
        timestamp_utc=timestamp,
        details={
            "review_sha256": digest,
            "review_source": source,
            # The review hash may be the harness's. This one is always over the
            # recommendations as worded here, so a rewording is detectable either way.
            "recommendations_sha256": review_sha256(recommendation_set),
            "assessment_sha256": assessment_sha256(assessment),
            "finding_ids": [item.id for item in recommendation_set.recommendations],
        },
    )
    return PilotReviewDraft(
        schema=DRAFT_SCHEMA,
        assessment=assessment.model_copy(update={"audit_events": events}),
        recommendation_set=recommendation_set,
        review_source=source,
        review_sha256=digest,
    )


def draft_problems(draft: PilotReviewDraft) -> list[str]:
    """Every way a draft file disagrees with its own audit chain."""

    events = draft.assessment.audit_events
    chain = verify_audit_chain(events)
    if not chain.verified:
        return [f"draft audit chain not verified: {chain.reason}"]
    ready = events[-1]
    if ready.event_type != "review_draft_ready" or not ready.details:
        return ["the draft's audit chain does not end with the draft being fixed"]
    problems: list[str] = []
    recommendations = review_sha256(draft.recommendation_set)
    fixed = (ready.details.get("review_source"), ready.details.get("review_sha256"))
    if (
        recommendations != ready.details.get("recommendations_sha256")
        or (draft.review_source, draft.review_sha256) != fixed
        or (draft.review_source == "agent_rules" and draft.review_sha256 != recommendations)
    ):
        problems.append("the draft's recommendations are not the ones its audit chain fixed")
    if assessment_sha256(draft.assessment) != ready.details.get("assessment_sha256"):
        problems.append("the draft's assessment is not the one its audit chain fixed")
    if any(item.decision != "pending" for item in draft.recommendation_set.recommendations):
        problems.append("the draft already carries decisions")
    return problems


def is_closed(session: PilotReviewSession) -> bool:
    return _first(session.assessment.audit_events, "review_session_closed") is not None


def _append(
    session: PilotReviewSession,
    event_type: AuditEventType,
    note: str,
    at: str | None,
    details: dict[str, Any] | None = None,
    **updates: Any,
) -> PilotReviewSession:
    if is_closed(session):
        raise ValueError(f"session {session.session_id} is closed and accepts no further events")
    timestamp = at or utc_now_iso()
    events = session.assessment.audit_events
    _require_not_before_last(events, timestamp)
    events = append_audit_event(
        events,
        event_type=event_type,
        actor=session.reviewer_id,
        note=note,
        timestamp_utc=timestamp,
        details=details,
    )
    assessment = session.assessment.model_copy(update={"audit_events": events})
    updated = session.model_copy(update={"assessment": assessment, **updates})
    # Rebuilt through validation: a copy with updates would accept any value.
    return PilotReviewSession.model_validate(updated.model_dump(by_alias=True))


def start_review_session(
    draft: PilotReviewDraft,
    *,
    reviewer_id: str,
    evidence_class: EvidenceClass,
    reviewer_profile: str = "",
    at: str | None = None,
) -> PilotReviewSession:
    problems = draft_problems(draft)
    if problems:
        raise ValueError(f"the draft failed verification: {'; '.join(problems)}")
    session = PilotReviewSession(
        schema=SESSION_SCHEMA,
        session_id=f"{draft.review_sha256[:12]}-{reviewer_id}",
        reviewer_id=reviewer_id,
        reviewer_profile=reviewer_profile.strip(),
        evidence_class=evidence_class,
        review_source=draft.review_source,
        review_sha256=draft.review_sha256,
        assessment=draft.assessment,
        recommendation_set=draft.recommendation_set,
    )
    return _append(
        session,
        "review_session_started",
        "Reviewer session started on the prepared draft.",
        at,
        {
            "session_id": session.session_id,
            "evidence_class": evidence_class,
            "reviewer_profile": session.reviewer_profile,
            "review_sha256": draft.review_sha256,
        },
    )


def mark_draft_reviewable(
    session: PilotReviewSession, *, at: str | None = None
) -> PilotReviewSession:
    """Record the moment the reviewer holds a first draft fit to hand to a supervisor."""

    if _first(session.assessment.audit_events, "draft_marked_reviewable"):
        raise ValueError("the draft is already marked reviewable in this session")
    return _append(
        session, "draft_marked_reviewable", "Reviewer marked the draft as reviewable.", at
    )


def record_recommendation_decision(
    session: PilotReviewSession,
    *,
    recommendation_id: str,
    decision: str,
    usefulness: int,
    reason: str = "",
    corrected_text: str | None = None,
    at: str | None = None,
) -> PilotReviewSession:
    """Record one decision. A later decision on the same recommendation supersedes it."""

    timestamp = at or utc_now_iso()
    recommendation_set = decide_recommendation(
        session.recommendation_set,
        recommendation_id,
        decision,
        reviewer=session.reviewer_id,
        reason=reason,
        corrected_text=corrected_text,
        usefulness=usefulness,
        decided_at=timestamp,
    )
    return _append(
        session,
        "recommendation_decision_recorded",
        f"Recommendation {recommendation_id} {decision}.",
        timestamp,
        {
            "finding_id": recommendation_id,
            "decision": decision,
            "usefulness": usefulness,
            "reason": reason.strip(),
            "corrected_text": corrected_text,
        },
        recommendation_set=recommendation_set,
    )


def record_material_omission(
    session: PilotReviewSession, *, text: str, at: str | None = None
) -> PilotReviewSession:
    if not text.strip():
        raise ValueError("a material omission needs a description")
    return _append(
        session,
        "material_omission_recorded",
        "Reviewer recorded a material omission.",
        at,
        {"omission": text.strip()},
        material_omissions=[*session.material_omissions, text.strip()],
    )


def close_review_session(
    session: PilotReviewSession,
    *,
    state: ReviewState,
    note: str,
    declared_review_minutes: float | None = None,
    workflow_feedback: str = "",
    at: str | None = None,
) -> PilotReviewSession:
    """Apply the reviewer's decision on the matter and end the session."""

    if is_closed(session):
        raise ValueError(f"session {session.session_id} is already closed")
    pending = [
        item.id
        for item in session.recommendation_set.recommendations
        if item.decision not in DECIDED
    ]
    if pending:
        raise ValueError(f"every recommendation needs a decision before closing: {pending}")
    timestamp = at or utc_now_iso()
    events = session.assessment.audit_events
    _require_not_before_last(events, timestamp)
    started = _first(events, "review_session_started")
    elapsed = _minutes_between(started.timestamp_utc, timestamp)
    if elapsed <= 0:
        raise ValueError("a session cannot close at or before its start")
    declared = None if declared_review_minutes is None else float(declared_review_minutes)
    if declared is not None and not (math.isfinite(declared) and 0 < declared <= elapsed):
        raise ValueError(
            "declared review minutes must be positive and no more than the elapsed session time"
        )
    assessment = apply_review_decision(
        session.assessment,
        ReviewDecision(reviewer=session.reviewer_id, state=state, note=note),
        decided_at=timestamp,
    )
    return _append(
        session.model_copy(update={"assessment": assessment}),
        "review_session_closed",
        "Reviewer session closed after a decision on every recommendation.",
        timestamp,
        {
            "final_review_state": state,
            "declared_review_minutes": declared,
            "workflow_feedback": workflow_feedback.strip(),
        },
        declared_review_minutes=declared,
        workflow_feedback=workflow_feedback.strip(),
    )


def session_timing(session: PilotReviewSession) -> SessionTiming:
    events = session.assessment.audit_events
    started = _first(events, "review_session_started")
    reviewable = _first(events, "draft_marked_reviewable")
    closed = _first(events, "review_session_closed")
    ready = _first(events, "review_draft_ready")
    elapsed = _minutes_between(started.timestamp_utc, closed.timestamp_utc) if closed else None
    declared = session.declared_review_minutes
    review_minutes = declared if declared is not None else elapsed
    return SessionTiming(
        started_at_utc=started.timestamp_utc,
        reviewable_at_utc=reviewable.timestamp_utc if reviewable else None,
        closed_at_utc=closed.timestamp_utc if closed else None,
        draft_preparation_seconds=round(
            (_parse(ready.timestamp_utc) - _parse(events[0].timestamp_utc)).total_seconds(), 2
        ),
        minutes_to_reviewable_draft=(
            _minutes_between(started.timestamp_utc, reviewable.timestamp_utc)
            if reviewable
            else None
        ),
        elapsed_review_minutes=elapsed,
        declared_review_minutes=declared,
        review_minutes=review_minutes,
        review_minutes_source=(
            None
            if review_minutes is None
            else "reviewer_declared" if declared is not None else "audit_timestamps"
        ),
    )


def replay_session(draft: PilotReviewDraft, events: list[AuditEvent]) -> PilotReviewSession:
    """Rebuild a session from the draft and the session's own audit events alone."""

    if not events or events[0].event_type != "review_session_started":
        raise ValueError("the first event after the draft is not the start of a session")
    started = events[0].details or {}
    session = start_review_session(
        draft,
        reviewer_id=events[0].actor,
        evidence_class=started["evidence_class"],
        reviewer_profile=started["reviewer_profile"],
        at=events[0].timestamp_utc,
    )
    decision_note: str | None = None
    for event in events[1:]:
        details = event.details or {}
        at = event.timestamp_utc
        if event.event_type == "draft_marked_reviewable":
            session = mark_draft_reviewable(session, at=at)
        elif event.event_type == "recommendation_decision_recorded":
            session = record_recommendation_decision(
                session,
                recommendation_id=details["finding_id"],
                decision=details["decision"],
                usefulness=details["usefulness"],
                reason=details["reason"],
                corrected_text=details["corrected_text"],
                at=at,
            )
        elif event.event_type == "material_omission_recorded":
            session = record_material_omission(session, text=details["omission"], at=at)
        elif event.event_type == "review_decision_applied":
            # Applied together with the closing event that follows it.
            decision_note = event.note
        elif event.event_type == "review_session_closed" and decision_note is not None:
            session = close_review_session(
                session,
                state=details["final_review_state"],
                note=decision_note,
                declared_review_minutes=details["declared_review_minutes"],
                workflow_feedback=details["workflow_feedback"],
                at=at,
            )
        else:
            raise ValueError(f"unexpected {event.event_type} event at seq {event.seq}")
    return session


def _differences(recorded: dict[str, Any], replayed: dict[str, Any], prefix: str = "") -> list[str]:
    """Paths, two levels deep, at which a session file departs from its replay."""

    paths: list[str] = []
    for key in sorted(recorded.keys() | replayed.keys()):
        left, right = recorded.get(key), replayed.get(key)
        if left == right:
            continue
        if not prefix and isinstance(left, dict) and isinstance(right, dict):
            paths.extend(_differences(left, right, f"{key}."))
        else:
            paths.append(f"{prefix}{key}")
    return paths


def session_problems(session: PilotReviewSession, draft: PilotReviewDraft) -> list[str]:
    """Every way a session file disagrees with its draft or with its own audit chain."""

    problems = draft_problems(draft)
    if problems:
        return problems
    events = session.assessment.audit_events
    chain = verify_audit_chain(events)
    if not chain.verified:
        return [f"audit chain not verified: {chain.reason}"]
    fork = len(draft.assessment.audit_events)
    if [event.event_hash for event in events[:fork]] != [
        event.event_hash for event in draft.assessment.audit_events
    ]:
        return ["the session does not continue this draft"]
    try:
        replayed = replay_session(draft, events[fork:])
    except (ValueError, KeyError, TypeError) as error:
        return [f"the audit chain cannot be replayed as a session: {error}"]
    return [
        f"{path}: the file is not what the audit chain records"
        for path in _differences(session.model_dump(mode="json"), replayed.model_dump(mode="json"))
    ]
