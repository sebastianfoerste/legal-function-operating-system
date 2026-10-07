"""The evidence a reviewer pilot leaves behind, and the claim it supports.

One record covers one draft and the closed reviewer sessions held on it. Its field
names follow the reviewer-session format of contract-review-eval-harness, so the two
repositories can be compared session by session.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from models import (
    AuditChainVerification,
    DocumentVerificationRecord,
    ReviewState,
    verify_audit_chain,
)
from src.harness_review import SESSION_SCHEMA as HARNESS_SESSION_SCHEMA
from src.legal_ops import utc_now_iso
from src.pilot_session import (
    PilotReviewDraft,
    PilotReviewSession,
    ReviewSource,
    SessionTiming,
    draft_problems,
    is_closed,
    session_problems,
    session_timing,
)

RECORD_SCHEMA: Final = "legal-ops-agent.pilot-record.v1"
PROTOCOL_PATH = "docs/PILOT_PROTOCOL.md"

# The fields of contract-review-eval.reviewer-session.v1, minus its schema id. Every
# session carries them. Only a session held on a harness review also gets the schema
# id, because only there does review_sha256 name an output the harness knows.
HARNESS_SESSION_FIELDS = (
    "matter_id",
    "round_id",
    "review_sha256",
    "reviewer_id",
    "reviewer_profile",
    "evidence_class",
    "minutes_to_reviewable_draft",
    "review_minutes",
    "decisions",
    "material_omissions",
    "workflow_feedback",
)

SYNTHETIC_LIMIT = (
    "Synthetic documents only. No client, matter or confidential material was reviewed."
)
SOURCE_LIMITS: dict[str, str] = {
    "agent_rules": (
        "One matter. The recommendations rated are this agent's rule-based workflow "
        "recommendations; the agent does not read contract text."
    ),
    "harness_review": (
        "One matter. The recommendations rated are one model review captured by "
        "contract-review-eval-harness and identified by the review hash above. This "
        "agent supplies the supervised workflow around it and does not read contract text."
    ),
}
ADOPTION_LIMIT = "Not an enterprise implementation. No adoption inside an organisation is recorded."


def claim_limits(review_source: str) -> list[str]:
    return [SYNTHETIC_LIMIT, SOURCE_LIMITS[review_source], ADOPTION_LIMIT]


class Recommendation(BaseModel):
    finding_id: str
    locator: str
    proposed_text: str
    rationale: str
    evidence: str = ""


class RecommendationOutcome(BaseModel):
    finding_id: str
    decision: Literal["accepted", "corrected", "rejected"]
    usefulness: int = Field(..., ge=1, le=4)
    reason: str = ""
    proposed_text: str
    corrected_text: str | None = None


class PilotSessionRecord(BaseModel):
    session_id: str
    assessment_id: str
    final_review_state: ReviewState
    export_allowed: bool
    timing: SessionTiming
    audit_chain: AuditChainVerification
    accepted: list[RecommendationOutcome]
    corrected: list[RecommendationOutcome]
    rejected: list[RecommendationOutcome]
    material_omissions: list[str]
    harness_fields: dict[str, Any]
    # Present only for a session on a harness review: a complete reviewer session in
    # the harness's own format, bound to the harness's hash of that review.
    harness_session: dict[str, Any] | None = None


class PilotSummary(BaseModel):
    """Aggregate over the sessions that count as pilot evidence."""

    measured: bool
    reason: str | None = None
    sessions: int = 0
    reviewers: int = 0
    sessions_excluded: int = 0
    findings_rated: int = 0
    accepted_rate: float | None = None
    corrected_rate: float | None = None
    rejected_rate: float | None = None
    mean_usefulness: float | None = None
    median_review_minutes: float | None = None
    # Review time is the reviewer's declared figure where one was given. These two
    # fields keep the measured figure and the number of declared ones in view.
    median_elapsed_review_minutes: float | None = None
    sessions_with_declared_review_time: int = 0
    median_minutes_to_reviewable_draft: float | None = None
    material_omissions: int = 0


class AcceptanceResult(BaseModel):
    criterion: str = Field(..., min_length=3)
    threshold: str = Field(..., min_length=1)
    observed: str = Field(..., min_length=1)
    met: bool


class PilotAcceptance(BaseModel):
    status: Literal["not_measured", "criteria_not_set", "met", "not_met"]
    results: list[AcceptanceResult] = Field(default_factory=list)


class PilotRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.pilot-record.v1"] = Field(RECORD_SCHEMA, alias="schema")
    generated_at_utc: str
    protocol: str = PROTOCOL_PATH
    matter_title: str
    matter_id: str | None
    round_id: str | None
    assessment_id: str
    review_source: ReviewSource
    review_sha256: str
    documents: list[DocumentVerificationRecord]
    recommendations: list[Recommendation]
    sessions: list[PilotSessionRecord]
    summary: PilotSummary
    acceptance: PilotAcceptance
    claim: str
    claim_limits: list[str]


def _outcomes(session: PilotReviewSession) -> list[RecommendationOutcome]:
    return [
        # Validated from a mapping: a closed session has no pending change, and a
        # missing usefulness score must fail here rather than reach the record.
        RecommendationOutcome.model_validate(
            {
                "finding_id": change.id,
                "decision": change.decision,
                "usefulness": change.usefulness,
                "reason": change.reason,
                "proposed_text": change.proposed_text,
                "corrected_text": change.corrected_text,
            }
        )
        for change in session.change_set.changes
    ]


def build_session_record(
    session: PilotReviewSession, draft: PilotReviewDraft
) -> PilotSessionRecord:
    if not is_closed(session):
        raise ValueError(f"session {session.session_id} is not closed")
    problems = session_problems(session, draft)
    if problems:
        raise ValueError(f"session {session.session_id} failed verification: {'; '.join(problems)}")
    timing = session_timing(session)
    outcomes = _outcomes(session)
    matter = session.assessment.matter
    harness_fields = {
        "matter_id": matter.matter_id,
        "round_id": matter.round_id,
        "review_sha256": session.review_sha256,
        "reviewer_id": session.reviewer_id,
        "reviewer_profile": session.reviewer_profile,
        "evidence_class": session.evidence_class,
        "minutes_to_reviewable_draft": timing.minutes_to_reviewable_draft,
        "review_minutes": timing.review_minutes,
        "decisions": [
            {
                "finding_id": item.finding_id,
                "decision": item.decision,
                "usefulness": item.usefulness,
                "reason": item.reason,
            }
            for item in outcomes
        ],
        "material_omissions": list(session.material_omissions),
        "workflow_feedback": session.workflow_feedback,
    }
    return PilotSessionRecord(
        session_id=session.session_id,
        assessment_id=session.assessment.assessment_id,
        final_review_state=session.assessment.review_state,
        export_allowed=session.assessment.export_allowed,
        timing=timing,
        audit_chain=verify_audit_chain(session.assessment.audit_events),
        accepted=[item for item in outcomes if item.decision == "accepted"],
        corrected=[item for item in outcomes if item.decision == "corrected"],
        rejected=[item for item in outcomes if item.decision == "rejected"],
        material_omissions=list(session.material_omissions),
        harness_fields=harness_fields,
        harness_session=(
            {"schema": HARNESS_SESSION_SCHEMA, **harness_fields}
            if session.review_source == "harness_review"
            else None
        ),
    )


def summarise_sessions(sessions: list[PilotSessionRecord]) -> PilotSummary:
    """Aggregate practising-lawyer sessions and count the ones that are excluded."""

    counted_sessions = [
        item for item in sessions if item.harness_fields["evidence_class"] == "practising_lawyer"
    ]
    counted = [item.harness_fields for item in counted_sessions]
    excluded = len(sessions) - len(counted)
    if not counted:
        return PilotSummary(
            measured=False,
            reason="no session by a practising lawyer other than the author is recorded",
            sessions_excluded=excluded,
        )
    decisions = [decision for fields in counted for decision in fields["decisions"]]
    total = len(decisions)
    drafts = [
        fields["minutes_to_reviewable_draft"]
        for fields in counted
        if fields["minutes_to_reviewable_draft"] is not None
    ]

    def rate(value: str) -> float:
        return round(sum(decision["decision"] == value for decision in decisions) / total, 4)

    return PilotSummary(
        measured=True,
        sessions=len(counted),
        reviewers=len({fields["reviewer_id"] for fields in counted}),
        sessions_excluded=excluded,
        findings_rated=total,
        accepted_rate=rate("accepted"),
        corrected_rate=rate("corrected"),
        rejected_rate=rate("rejected"),
        mean_usefulness=round(statistics.fmean(d["usefulness"] for d in decisions), 2),
        median_review_minutes=statistics.median(fields["review_minutes"] for fields in counted),
        # Every counted session is closed, so each has an elapsed time.
        median_elapsed_review_minutes=statistics.median(
            item.timing.elapsed_review_minutes or 0.0 for item in counted_sessions
        ),
        sessions_with_declared_review_time=sum(
            item.timing.review_minutes_source == "reviewer_declared" for item in counted_sessions
        ),
        median_minutes_to_reviewable_draft=statistics.median(drafts) if drafts else None,
        material_omissions=sum(len(fields["material_omissions"]) for fields in counted),
    )


def evaluate_acceptance(summary: PilotSummary) -> list[AcceptanceResult]:
    """Judge a measured summary against the criteria agreed with reviewers beforehand.

    Returning no results means no criteria are set, and the record says so.
    """

    # TODO(human): return one AcceptanceResult per criterion agreed with the reviewers.
    return []


def _acceptance(summary: PilotSummary) -> PilotAcceptance:
    if not summary.measured:
        return PilotAcceptance(status="not_measured")
    results = evaluate_acceptance(summary)
    if not results:
        return PilotAcceptance(status="criteria_not_set")
    status: Literal["met", "not_met"] = "met" if all(item.met for item in results) else "not_met"
    return PilotAcceptance(status=status, results=results)


def _claim(summary: PilotSummary) -> str:
    if not summary.measured:
        return (
            "No reviewer pilot is evidenced: no session by a practising lawyer other than "
            "the author is recorded."
        )
    return (
        f"A user pilot on synthetic documents: {summary.sessions} review session(s) by "
        f"{summary.reviewers} practising lawyer(s) on one matter round."
    )


def build_pilot_record(
    draft: PilotReviewDraft,
    sessions: list[PilotReviewSession],
    *,
    generated_at: str | None = None,
) -> PilotRecord:
    problems = draft_problems(draft)
    if problems:
        raise ValueError(f"the draft failed verification: {'; '.join(problems)}")
    reviewer_ids = [session.reviewer_id for session in sessions]
    repeated = sorted({item for item in reviewer_ids if reviewer_ids.count(item) > 1})
    if repeated:
        raise ValueError(f"more than one session for reviewers: {repeated}")
    records = [build_session_record(session, draft) for session in sessions]
    summary = summarise_sessions(records)
    matter = draft.assessment.matter
    return PilotRecord(
        schema=RECORD_SCHEMA,
        generated_at_utc=generated_at or utc_now_iso(),
        matter_title=matter.title,
        matter_id=matter.matter_id,
        round_id=matter.round_id,
        assessment_id=draft.assessment.assessment_id,
        review_source=draft.review_source,
        review_sha256=draft.review_sha256,
        documents=draft.assessment.document_verifications,
        recommendations=[
            Recommendation(
                finding_id=change.id,
                locator=change.locator,
                proposed_text=change.proposed_text,
                rationale=change.rationale,
                evidence=change.original_text,
            )
            for change in draft.change_set.changes
        ],
        sessions=records,
        summary=summary,
        acceptance=_acceptance(summary),
        claim=_claim(summary),
        claim_limits=claim_limits(draft.review_source),
    )


def _outcome_lines(title: str, outcomes: list[RecommendationOutcome]) -> list[str]:
    if not outcomes:
        return [f"**{title}:** none", ""]
    lines = [f"**{title}:**", ""]
    for item in outcomes:
        lines.append(f"- `{item.finding_id}` (usefulness {item.usefulness}): {item.proposed_text}")
        if item.corrected_text:
            lines.append(f"  - Corrected to: {item.corrected_text}")
        if item.reason:
            lines.append(f"  - Reason: {item.reason}")
    return [*lines, ""]


def _minutes(value: float | None) -> str:
    return "not recorded" if value is None else f"{value:g} min"


def render_pilot_record_markdown(record: PilotRecord) -> str:
    summary = record.summary
    lines = [
        f"# Pilot record: {record.matter_title}",
        "",
        f"- Schema: `{record.schema_id}`",
        f"- Generated: `{record.generated_at_utc}`",
        f"- Matter and round: `{record.matter_id}` / `{record.round_id}`",
        f"- Assessment: `{record.assessment_id}`",
        f"- Recommendations from: `{record.review_source}`",
        f"- Recommendations reviewed (sha256): `{record.review_sha256}`",
        f"- Protocol: `{record.protocol}`",
        *(
            ["", "> Contains a fabricated session (R00). It is an example of the format only."]
            if any(
                item.harness_fields["evidence_class"] == "synthetic_example"
                for item in record.sessions
            )
            else []
        ),
        "",
        "## Claim this record supports",
        "",
        record.claim,
        "",
        *[f"- {limit}" for limit in record.claim_limits],
        "",
        "## Summary",
        "",
    ]
    if summary.measured:
        lines += [
            f"- Sessions counted: {summary.sessions} by {summary.reviewers} reviewer(s)",
            f"- Sessions excluded (author or synthetic example): {summary.sessions_excluded}",
            f"- Recommendations rated: {summary.findings_rated}",
            f"- Accepted / corrected / rejected: {summary.accepted_rate:.0%} / "
            f"{summary.corrected_rate:.0%} / {summary.rejected_rate:.0%}",
            f"- Mean usefulness (1 to 4): {summary.mean_usefulness}",
            f"- Median review time: {_minutes(summary.median_review_minutes)} "
            f"(elapsed {_minutes(summary.median_elapsed_review_minutes)}; "
            f"{summary.sessions_with_declared_review_time} session(s) declared their own figure)",
            "- Median time to a reviewable draft: "
            f"{_minutes(summary.median_minutes_to_reviewable_draft)}",
            f"- Material omissions: {summary.material_omissions}",
        ]
    else:
        lines += [
            f"- Not measured: {summary.reason}.",
            f"- Sessions excluded (author or synthetic example): {summary.sessions_excluded}",
        ]
    lines += ["", f"- Acceptance criteria: `{record.acceptance.status}`"]
    lines += [
        f"  - {'met' if item.met else 'not met'}: {item.criterion} "
        f"(threshold {item.threshold}, observed {item.observed})"
        for item in record.acceptance.results
    ]
    lines += ["", "## Recommendations put to reviewers", ""]
    lines += [
        f"- `{item.finding_id}` ({item.locator}): {item.proposed_text} Basis: {item.rationale}"
        for item in record.recommendations
    ]
    if record.documents:
        lines += ["", "## Documents", ""]
        lines += [
            f"- {item.status}: `{item.document_id}` | {item.kind} | {item.path} | "
            f"sha256 `{item.expected_sha256}`"
            for item in record.documents
        ]
    for session in record.sessions:
        fields = session.harness_fields
        timing = session.timing
        lines += [
            "",
            f"## Session {fields['reviewer_id']} ({fields['evidence_class']})",
            "",
            f"- Final review state: `{session.final_review_state}`, "
            f"export allowed: `{str(session.export_allowed).lower()}`",
            f"- Time to a reviewable draft: {_minutes(timing.minutes_to_reviewable_draft)}",
            f"- Review time: {_minutes(timing.review_minutes)} "
            f"(source: {timing.review_minutes_source}; elapsed "
            f"{_minutes(timing.elapsed_review_minutes)})",
            f"- Audit chain: {session.audit_chain.reason}, {session.audit_chain.event_count} "
            f"events, root `{session.audit_chain.chain_root_hash}`",
            "",
            *_outcome_lines("Accepted", session.accepted),
            *_outcome_lines("Corrected", session.corrected),
            *_outcome_lines("Rejected", session.rejected),
            "**Material omissions:**" + (" none" if not session.material_omissions else ""),
            *[f"- {omission}" for omission in session.material_omissions],
        ]
        if fields["workflow_feedback"]:
            lines += ["", f"**Workflow feedback:** {fields['workflow_feedback']}"]
    return "\n".join(lines) + "\n"


def render_reviewed_recommendations(session: PilotReviewSession) -> str:
    """The revised draft: what survives one reviewer's decisions, in their wording."""

    if not (session.assessment.export_allowed and session.change_set.export_allowed):
        raise ValueError(
            "the revised draft is exported only from a closed session that approved the matter"
        )
    kept = [change for change in session.change_set.changes if change.reviewed_text() is not None]
    rejected = len(session.change_set.changes) - len(kept)
    lines = [
        f"# Reviewed recommendations: {session.assessment.matter.title}",
        "",
        f"- Reviewer: `{session.reviewer_id}` ({session.evidence_class})",
        f"- Assessment: `{session.assessment.assessment_id}`",
        "- Status: draft for human review. Synthetic documents only. Not legal advice.",
        f"- Rejected and left out: {rejected}",
        "",
    ]
    for change in kept:
        lines += [
            f"## {change.id} ({change.decision})",
            "",
            change.reviewed_text() or "",
            "",
            f"Basis: {change.rationale}",
            "",
        ]
    return "\n".join(lines)


def render_recommendations(draft: PilotReviewDraft) -> str:
    """The recommendations as a reviewer reads them before deciding each one."""

    origin = (
        "They are the output of a model, captured by contract-review-eval-harness. "
        "Nothing here says which model or setup produced them."
        if draft.review_source == "harness_review"
        else "They are this agent's rule-based workflow recommendations."
    )
    lines = [
        f"# Recommendations for review: {draft.assessment.matter.title}",
        "",
        f"- Matter and round: `{draft.assessment.matter.matter_id}` / "
        f"`{draft.assessment.matter.round_id}`",
        f"- Recommendations reviewed (sha256): `{draft.review_sha256}`",
        "- Status: draft for human review. Synthetic documents only. Not legal advice.",
        "",
        f"{origin} Decide each one as accepted, corrected or rejected.",
        "",
    ]
    for change in draft.change_set.changes:
        lines += [f"## {change.id}", "", change.proposed_text, "", f"Basis: {change.rationale}", ""]
        lines += [f"Scope: {change.locator}", ""]
        if change.original_text:
            lines += [*(f"> {quote}" for quote in change.original_text.splitlines()), ""]
    return "\n".join(lines)


def write_pilot_record(record: PilotRecord, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "pilot-record.json"
    markdown_path = output_dir / "pilot-record.md"
    json_path.write_text(record.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_pilot_record_markdown(record), encoding="utf-8")
    for session in record.sessions:
        if session.harness_session is not None:
            reviewer = session.harness_session["reviewer_id"]
            (output_dir / f"harness-session-{reviewer}.json").write_text(
                json.dumps(session.harness_session, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    return json_path, markdown_path
