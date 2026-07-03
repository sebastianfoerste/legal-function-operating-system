from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from models import AuditEvent, LegalOpsAssessment
from src.audit_chain import append_audit_event

PACKET_ACTOR = "LegalOps Agent"


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _lines_for_findings(assessment: LegalOpsAssessment) -> list[str]:
    lines: list[str] = []
    for finding in assessment.findings:
        lines.extend(
            [
                f"- {finding.severity.upper()}: {finding.category}",
                f"  Summary: {finding.summary}",
                f"  Evidence: {finding.evidence}",
                f"  Action: {finding.recommended_action}",
            ]
        )
    return lines


def _lines_for_controls(assessment: LegalOpsAssessment) -> list[str]:
    lines: list[str] = []
    for control in assessment.controls:
        lines.extend(
            [
                f"- {control.control_id}: {control.status}",
                f"  Summary: {control.summary}",
                f"  Evidence: {control.evidence}",
                f"  Owner: {control.owner_role}",
            ]
        )
    return lines


def _lines_for_commitments(assessment: LegalOpsAssessment) -> list[str]:
    if not assessment.customer_commitments:
        return ["- No customer commitments recorded from intake."]
    return [
        (
            f"- {item.commitment} | owner: {item.owner_role} | "
            f"source: {item.source} | review required: {item.review_required}"
        )
        for item in assessment.customer_commitments
    ]


def _lines_for_sources(assessment: LegalOpsAssessment) -> list[str]:
    if not assessment.source_verifications:
        return ["- No source verification records available."]
    lines: list[str] = []
    for item in assessment.source_verifications:
        authority = f" | authority: {item.public_authority}" if item.public_authority else ""
        lines.append(
            (
                f"- {item.status}: {item.source_ref} | category: {item.category}"
                f"{authority} | human review: {item.requires_human_review}"
            )
        )
        lines.append(f"  Reason: {item.reason}")
    return lines


def _audit_events_for_packet(assessment: LegalOpsAssessment) -> list[AuditEvent]:
    return append_audit_event(
        assessment.audit_events,
        event_type="review_packet_generated",
        actor=PACKET_ACTOR,
        note="Review packet generated for human legal review.",
        timestamp_utc=_utc_now_iso(),
    )


def _lines_for_audit(events: list[AuditEvent]) -> list[str]:
    return [
        f"- {event.timestamp_utc} | {event.event_type} | {event.actor}: {event.note}"
        for event in events
    ]


def build_review_packet(assessment: LegalOpsAssessment) -> str:
    """Render a reviewer-ready markdown packet from an assessment."""

    export_status = "allowed" if assessment.export_allowed else "blocked"
    lines = [
        f"# LegalOps Review Packet: {assessment.matter.title}",
        "",
        f"- Assessment ID: `{assessment.assessment_id}`",
        f"- Created: `{assessment.created_at_utc}`",
        f"- Matter type: `{assessment.matter.matter_type}`",
        f"- Jurisdiction: `{assessment.matter.jurisdiction}`",
        f"- Urgency: `{assessment.matter.urgency}`",
        f"- Review state: `{assessment.review_state}`",
        f"- Export: `{export_status}`",
        "",
        "## Summary",
        "",
        assessment.matter.summary,
        "",
        "## Routing",
        "",
        f"- Owner role: {assessment.routing.owner_role}",
        f"- Reviewers: {', '.join(assessment.routing.reviewers)}",
        f"- SLA: {assessment.routing.sla_hours} hours",
        f"- Rationale: {assessment.routing.rationale}",
        "",
        "## Findings",
        "",
        *_lines_for_findings(assessment),
        "",
        "## Controls",
        "",
        *_lines_for_controls(assessment),
        "",
        "## Source Verification",
        "",
        *_lines_for_sources(assessment),
        "",
        "## Customer Commitment Register",
        "",
        *_lines_for_commitments(assessment),
        "",
        "## Audit Trail",
        "",
        *_lines_for_audit(_audit_events_for_packet(assessment)),
    ]

    if assessment.review_note:
        lines.extend(["", "## Review Note", "", assessment.review_note])

    return "\n".join(lines) + "\n"


def write_review_packet(assessment: LegalOpsAssessment, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_review_packet(assessment), encoding="utf-8")
    return output_path
