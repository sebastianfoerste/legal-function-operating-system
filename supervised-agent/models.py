from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MatterType = Literal[
    "contract",
    "privacy",
    "ai_governance",
    "product_launch",
    "regulatory_monitoring",
]
Urgency = Literal["low", "medium", "high"]
RiskSeverity = Literal["low", "medium", "high", "blocker"]
ReviewState = Literal["needs_review", "approved", "rejected", "revision_requested", "escalated"]
ControlStatus = Literal["pass", "warning", "blocker"]
AuditEventType = Literal["assessment_created", "review_decision_applied", "review_packet_generated"]
SourceCategory = Literal[
    "synthetic", "public_regulatory", "public_unapproved", "blocked", "missing"
]
ReviewPacketRunStatus = Literal["blocked", "review_required", "ready"]


class MatterIntake(BaseModel):
    """Typed intake record for an incoming legal-operations matter."""

    title: str = Field(..., min_length=6)
    requester: str = Field(..., min_length=2)
    business_unit: str = Field(..., min_length=2)
    matter_type: MatterType
    jurisdiction: str = Field(..., min_length=2)
    summary: str = Field(..., min_length=30)
    urgency: Urgency = "medium"
    data_categories: list[str] = Field(default_factory=list)
    customer_commitments: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class RiskFinding(BaseModel):
    """Deterministic risk finding surfaced by the workflow."""

    category: str = Field(..., min_length=3)
    severity: RiskSeverity
    summary: str = Field(..., min_length=12)
    evidence: str = Field(..., min_length=6)
    recommended_action: str = Field(..., min_length=12)


class RoutingDecision(BaseModel):
    """Review routing decision for a legal matter."""

    owner_role: str = Field(..., min_length=3)
    reviewers: list[str] = Field(..., min_length=1)
    rationale: str = Field(..., min_length=20)
    sla_hours: int = Field(..., ge=1, le=168)


class ControlCheck(BaseModel):
    """Deterministic workflow control check."""

    control_id: str = Field(..., min_length=3)
    status: ControlStatus
    summary: str = Field(..., min_length=12)
    evidence: str = Field(..., min_length=6)
    owner_role: str = Field(..., min_length=3)


class CustomerCommitmentRecord(BaseModel):
    """Customer-facing commitment that must be tracked after review."""

    commitment: str = Field(..., min_length=3)
    owner_role: str = Field(..., min_length=3)
    source: str = Field(..., min_length=3)
    review_required: bool = True


class SourceVerificationRecord(BaseModel):
    """Deterministic source-boundary verification for an intake reference."""

    source_ref: str = Field(..., min_length=3)
    category: SourceCategory
    status: ControlStatus
    reason: str = Field(..., min_length=12)
    public_authority: str | None = None
    requires_human_review: bool = True


def compute_audit_event_hash(
    seq: int,
    prev_hash: str | None,
    event_type: str,
    actor: str,
    note: str,
    timestamp_utc: str,
) -> str:
    """Canonical SHA-256 digest for one position in the audit hash chain."""

    payload = json.dumps(
        {
            "seq": seq,
            "prev_hash": prev_hash,
            "event_type": event_type,
            "actor": actor,
            "note": note,
            "timestamp_utc": timestamp_utc,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditEvent(BaseModel):
    """Audit event for the supervised legal-ops workflow.

    Events form a hash chain: each event_hash commits to prev_hash plus the
    event's own content, so altering, reordering or dropping a past event is
    detectable by verify_audit_chain.
    """

    event_type: AuditEventType
    actor: str = Field(..., min_length=2)
    note: str = Field(..., min_length=12)
    timestamp_utc: str = Field(..., min_length=10)
    seq: int = Field(..., ge=0)
    prev_hash: str | None = None
    event_hash: str = Field(..., min_length=64, max_length=64)


class AuditChainVerification(BaseModel):
    """Result of walking an audit event hash chain."""

    verified: bool
    event_count: int = Field(..., ge=0)
    chain_root_hash: str | None = None
    broken_at_seq: int | None = None
    reason: str


def verify_audit_chain(events: list[AuditEvent]) -> AuditChainVerification:
    """Recompute and check every link in an audit event hash chain."""

    if not events:
        return AuditChainVerification(
            verified=False,
            event_count=0,
            chain_root_hash=None,
            broken_at_seq=None,
            reason="no audit events recorded",
        )

    expected_prev: str | None = None
    for index, event in enumerate(events):
        if event.seq != index:
            return AuditChainVerification(
                verified=False,
                event_count=len(events),
                chain_root_hash=None,
                broken_at_seq=event.seq,
                reason=f"sequence gap at seq {event.seq}",
            )
        if event.prev_hash != expected_prev:
            return AuditChainVerification(
                verified=False,
                event_count=len(events),
                chain_root_hash=None,
                broken_at_seq=event.seq,
                reason=f"prev_hash mismatch at seq {event.seq}",
            )
        recomputed = compute_audit_event_hash(
            event.seq,
            event.prev_hash,
            event.event_type,
            event.actor,
            event.note,
            event.timestamp_utc,
        )
        if recomputed != event.event_hash:
            return AuditChainVerification(
                verified=False,
                event_count=len(events),
                chain_root_hash=None,
                broken_at_seq=event.seq,
                reason=f"event_hash mismatch at seq {event.seq}",
            )
        expected_prev = event.event_hash

    return AuditChainVerification(
        verified=True,
        event_count=len(events),
        chain_root_hash=expected_prev,
        broken_at_seq=None,
        reason="chain intact",
    )


class ReviewDecision(BaseModel):
    """Human review decision. Notes are mandatory for auditability."""

    reviewer: str = Field(..., min_length=2)
    state: ReviewState
    note: str = Field(..., min_length=20)

    @model_validator(mode="after")
    def validate_review_note(self) -> "ReviewDecision":
        if self.state == "approved" and len(self.note.strip()) < 30:
            raise ValueError("approval notes must be at least 30 characters")
        return self


class LegalOpsAssessment(BaseModel):
    """Full assessment record produced by the legal-ops workflow."""

    assessment_id: str = Field(..., min_length=12)
    created_at_utc: str = Field(..., min_length=10)
    matter: MatterIntake
    findings: list[RiskFinding]
    controls: list[ControlCheck] = Field(default_factory=list)
    source_verifications: list[SourceVerificationRecord] = Field(default_factory=list)
    customer_commitments: list[CustomerCommitmentRecord] = Field(default_factory=list)
    routing: RoutingDecision
    review_state: ReviewState = "needs_review"
    export_allowed: bool = False
    review_note: str | None = None
    audit_events: list[AuditEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_export_gate(self) -> "LegalOpsAssessment":
        if self.export_allowed and self.review_state != "approved":
            raise ValueError("export requires approved review state")
        if self.export_allowed and any(finding.severity == "blocker" for finding in self.findings):
            raise ValueError("export is blocked while blocker findings remain")
        if self.export_allowed and not self.review_note:
            raise ValueError("export requires a documented review note")
        if self.export_allowed:
            chain_check = verify_audit_chain(self.audit_events)
            if not chain_check.verified:
                raise ValueError(
                    f"export is blocked while the audit chain is not verified: {chain_check.reason}"
                )
        return self


class SourceManifestEntry(BaseModel):
    """Safe source-verification entry for reviewer packet runs."""

    source_ref: str = Field(..., min_length=3)
    category: SourceCategory
    status: ControlStatus
    reason: str = Field(..., min_length=12)
    public_authority: str | None = None
    requires_human_review: bool = True
    redacted: bool = False


class SourceManifestSummary(BaseModel):
    """Source-boundary summary for a source-verified packet run."""

    pass_count: int = Field(..., ge=0)
    warning_count: int = Field(..., ge=0)
    blocker_count: int = Field(..., ge=0)
    entries: list[SourceManifestEntry]


class RiskTriageSummary(BaseModel):
    """Compact risk and control summary for reviewer routing."""

    highest_severity: RiskSeverity
    finding_count: int = Field(..., ge=0)
    blocker_count: int = Field(..., ge=0)
    categories: list[str]
    control_status: dict[str, ControlStatus]
    recommended_next_actions: list[str]


class ReviewPolicyEnvelope(BaseModel):
    """Local policy boundary attached to a packet runner result."""

    review_state: ReviewState
    export_allowed: bool
    human_review_required: bool
    external_actions_allowed: bool = False
    delivery_mode: Literal["local_review_only"] = "local_review_only"
    blocked_actions: list[str] = Field(
        default_factory=lambda: ["external_delivery", "publication", "filing", "outreach"]
    )
    source_boundary: str
    legal_advice_status: Literal["draft_for_human_review"] = "draft_for_human_review"


class SourceVerifiedReviewPacketRun(BaseModel):
    """One-shot runner output for a source-verified review packet."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["legal-ops-agent.source-verified-review-packet-run.v1"] = Field(
        alias="schema"
    )
    assessment_id: str = Field(..., min_length=12)
    generated_at_utc: str = Field(..., min_length=10)
    status: ReviewPacketRunStatus
    matter_intake: MatterIntake
    risk_triage: RiskTriageSummary
    source_manifest: SourceManifestSummary
    policy_envelope: ReviewPolicyEnvelope
    review_state: ReviewState
    export_allowed: bool
    markdown_packet: str


class TrustCockpitMetadata(BaseModel):
    """Reviewer-facing metadata for a trust cockpit snapshot."""

    generated_for: Literal["public_reviewer_proof"] = "public_reviewer_proof"
    fixture: str | None = None
    command: str | None = None
    python_version: str
    application_version: str
    source_verified_runner_schema: str


class TrustCockpitDecisionSummary(BaseModel):
    """Decision and routing summary for reviewer inspection."""

    status: ReviewPacketRunStatus
    review_state: ReviewState
    export_allowed: bool
    human_review_required: bool
    highest_severity: RiskSeverity
    finding_count: int = Field(..., ge=0)
    blocker_count: int = Field(..., ge=0)
    owner_role: str = Field(..., min_length=3)
    reviewers: list[str]
    sla_hours: int = Field(..., ge=1, le=168)


class TrustCockpitSourceSummary(BaseModel):
    """Source-boundary summary for the trust cockpit."""

    source_boundary: str = Field(..., min_length=3)
    pass_count: int = Field(..., ge=0)
    warning_count: int = Field(..., ge=0)
    blocker_count: int = Field(..., ge=0)
    entries: list[SourceManifestEntry]


class TrustCockpitReviewGateSummary(BaseModel):
    """Human review and external-action gate summary."""

    delivery_mode: Literal["local_review_only"] = "local_review_only"
    external_actions_allowed: bool = False
    blocked_actions: list[str]
    legal_advice_status: Literal["draft_for_human_review"] = "draft_for_human_review"


class TrustCockpitCommitmentSummary(BaseModel):
    """Customer commitment summary for post-review control."""

    count: int = Field(..., ge=0)
    review_required_count: int = Field(..., ge=0)
    owner_roles: list[str]
    commitments: list[CustomerCommitmentRecord]


class TrustCockpitArtifactDigest(BaseModel):
    """Local artifact digest surfaced inside the trust cockpit."""

    name: str = Field(..., min_length=3)
    sha256: str = Field(..., min_length=64, max_length=64)
    bytes: int = Field(..., ge=0)
    path: str | None = None


class TrustCockpitArtifactSummary(BaseModel):
    """Local artifact integrity summary for reviewer evidence."""

    manifest_schema: str | None = None
    artifact_count: int = Field(..., ge=0)
    local_integrity_algorithm: str | None = None
    local_integrity_value: str | None = None
    artifacts: list[TrustCockpitArtifactDigest] = Field(default_factory=list)


class LegalOpsTrustCockpit(BaseModel):
    """Source-verified reviewer cockpit for public-safe LegalOps proof."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["legal-ops-agent.trust-cockpit.v1"] = Field(alias="schema")
    assessment_id: str = Field(..., min_length=12)
    generated_at_utc: str = Field(..., min_length=10)
    matter_title: str = Field(..., min_length=6)
    metadata: TrustCockpitMetadata
    decision_summary: TrustCockpitDecisionSummary
    source_summary: TrustCockpitSourceSummary
    review_gate: TrustCockpitReviewGateSummary
    commitment_summary: TrustCockpitCommitmentSummary
    artifact_summary: TrustCockpitArtifactSummary
    audit_chain: AuditChainVerification
    next_actions: list[str]
    markdown: str
