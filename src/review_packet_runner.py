from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from models import (
    ControlStatus,
    LegalOpsAssessment,
    MatterIntake,
    ReviewPacketRunStatus,
    ReviewPolicyEnvelope,
    RiskSeverity,
    RiskTriageSummary,
    SourceManifestEntry,
    SourceManifestSummary,
    SourceVerifiedReviewPacketRun,
)
from src.legal_ops import assess_matter, utc_now_iso
from src.review_packet import build_review_packet
from src.source_verification import BLOCKED_SOURCE_PREFIXES

RUNNER_SCHEMA: Literal["legal-ops-agent.source-verified-review-packet-run.v1"] = (
    "legal-ops-agent.source-verified-review-packet-run.v1"
)
SEVERITY_ORDER: dict[RiskSeverity, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "blocker": 3,
}


def _redacted_source_ref(source_ref: str) -> tuple[str, bool]:
    lower_ref = source_ref.lower()
    for prefix in BLOCKED_SOURCE_PREFIXES:
        if lower_ref.startswith(prefix):
            return f"{prefix}<redacted>", True
    return source_ref, False


def _source_redactions(assessment: LegalOpsAssessment) -> dict[str, str]:
    refs = [
        *assessment.matter.source_refs,
        *[record.source_ref for record in assessment.source_verifications],
        *[record.source for record in assessment.customer_commitments],
    ]
    redactions: dict[str, str] = {}
    for ref in refs:
        redacted, is_redacted = _redacted_source_ref(ref)
        if is_redacted:
            redactions[ref] = redacted
    return redactions


def _redact_payload(value: Any, redactions: dict[str, str]) -> Any:
    if isinstance(value, str):
        redacted_value = value
        for raw, redacted in redactions.items():
            redacted_value = redacted_value.replace(raw, redacted)
        return redacted_value
    if isinstance(value, list):
        return [_redact_payload(item, redactions) for item in value]
    if isinstance(value, dict):
        return {key: _redact_payload(item, redactions) for key, item in value.items()}
    return value


def _safe_assessment_for_packet(assessment: LegalOpsAssessment) -> LegalOpsAssessment:
    redactions = _source_redactions(assessment)
    if not redactions:
        return assessment
    payload = assessment.model_dump(mode="python")
    return LegalOpsAssessment.model_validate(_redact_payload(payload, redactions))


def _build_source_manifest(assessment: LegalOpsAssessment) -> SourceManifestSummary:
    entries: list[SourceManifestEntry] = []
    counts: dict[ControlStatus, int] = {"pass": 0, "warning": 0, "blocker": 0}
    for record in assessment.source_verifications:
        redacted_ref, is_redacted = _redacted_source_ref(record.source_ref)
        counts[record.status] += 1
        entries.append(
            SourceManifestEntry(
                source_ref=redacted_ref,
                category=record.category,
                status=record.status,
                reason=record.reason,
                public_authority=record.public_authority,
                requires_human_review=record.requires_human_review,
                redacted=is_redacted,
            )
        )
    return SourceManifestSummary(
        pass_count=counts["pass"],
        warning_count=counts["warning"],
        blocker_count=counts["blocker"],
        entries=entries,
    )


def _build_risk_triage(assessment: LegalOpsAssessment) -> RiskTriageSummary:
    severities = [finding.severity for finding in assessment.findings]
    highest_severity = max(severities, key=lambda item: SEVERITY_ORDER[item])
    return RiskTriageSummary(
        highest_severity=highest_severity,
        finding_count=len(assessment.findings),
        blocker_count=sum(1 for finding in assessment.findings if finding.severity == "blocker"),
        categories=sorted({finding.category for finding in assessment.findings}),
        control_status={control.control_id: control.status for control in assessment.controls},
        recommended_next_actions=[finding.recommended_action for finding in assessment.findings],
    )


def _build_policy_envelope(
    assessment: LegalOpsAssessment,
    source_manifest: SourceManifestSummary,
) -> ReviewPolicyEnvelope:
    human_review_required = (
        assessment.review_state != "approved" or source_manifest.blocker_count > 0
    )
    if source_manifest.blocker_count:
        source_boundary = "blocked_sensitive_source_reference"
    elif source_manifest.warning_count:
        source_boundary = "review_required_for_source_reliance"
    else:
        source_boundary = "verified_demo_or_public_regulatory_sources"
    return ReviewPolicyEnvelope(
        review_state=assessment.review_state,
        export_allowed=assessment.export_allowed,
        human_review_required=human_review_required,
        external_actions_allowed=False,
        source_boundary=source_boundary,
    )


def _status_for_run(
    assessment: LegalOpsAssessment,
    source_manifest: SourceManifestSummary,
) -> ReviewPacketRunStatus:
    if source_manifest.blocker_count or any(
        finding.severity == "blocker" for finding in assessment.findings
    ):
        return "blocked"
    if not assessment.export_allowed or assessment.review_state != "approved":
        return "review_required"
    return "ready"


def build_source_verified_review_packet_run(
    assessment: LegalOpsAssessment,
) -> SourceVerifiedReviewPacketRun:
    """Build a one-shot review packet run without external effects."""

    source_manifest = _build_source_manifest(assessment)
    safe_assessment = _safe_assessment_for_packet(assessment)
    return SourceVerifiedReviewPacketRun(
        schema=RUNNER_SCHEMA,
        assessment_id=assessment.assessment_id,
        generated_at_utc=utc_now_iso(),
        status=_status_for_run(assessment, source_manifest),
        matter_intake=safe_assessment.matter,
        risk_triage=_build_risk_triage(safe_assessment),
        source_manifest=source_manifest,
        policy_envelope=_build_policy_envelope(assessment, source_manifest),
        review_state=assessment.review_state,
        export_allowed=assessment.export_allowed,
        markdown_packet=build_review_packet(safe_assessment),
    )


def run_source_verified_review_packet(
    matter: MatterIntake,
) -> SourceVerifiedReviewPacketRun:
    return build_source_verified_review_packet_run(assess_matter(matter))


def write_source_verified_review_packet_run(
    assessment: LegalOpsAssessment,
    output_path: Path,
) -> Path:
    return write_source_verified_review_packet_run_payload(
        build_source_verified_review_packet_run(assessment),
        output_path,
    )


def write_source_verified_review_packet_run_payload(
    run: SourceVerifiedReviewPacketRun,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = run.model_dump(mode="json", by_alias=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path
