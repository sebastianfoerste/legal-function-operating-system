from __future__ import annotations

import json
import platform
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from models import (
    AuditChainVerification,
    CustomerCommitmentRecord,
    LegalOpsAssessment,
    LegalOpsTrustCockpit,
    SourceVerifiedReviewPacketRun,
    TrustCockpitArtifactDigest,
    TrustCockpitArtifactSummary,
    TrustCockpitCommitmentSummary,
    TrustCockpitDecisionSummary,
    TrustCockpitMetadata,
    TrustCockpitReviewGateSummary,
    TrustCockpitSourceSummary,
    verify_audit_chain,
)
from src.legal_ops import utc_now_iso
from src.review_packet_runner import build_source_verified_review_packet_run
from src.source_verification import BLOCKED_SOURCE_PREFIXES

TRUST_COCKPIT_SCHEMA: Literal["legal-ops-agent.trust-cockpit.v1"] = (
    "legal-ops-agent.trust-cockpit.v1"
)
APPLICATION_VERSION = "0.1.0"


def _redacted_source_ref(source_ref: str) -> str:
    lower_ref = source_ref.lower()
    for prefix in BLOCKED_SOURCE_PREFIXES:
        if lower_ref.startswith(prefix):
            return f"{prefix}<redacted>"
    return source_ref


def _safe_commitments(assessment: LegalOpsAssessment) -> list[CustomerCommitmentRecord]:
    return [
        CustomerCommitmentRecord(
            commitment=record.commitment,
            owner_role=record.owner_role,
            source=_redacted_source_ref(record.source),
            review_required=record.review_required,
        )
        for record in assessment.customer_commitments
    ]


def _artifact_summary(
    artifact_manifest: Mapping[str, Any] | None,
) -> TrustCockpitArtifactSummary:
    if artifact_manifest is None:
        return TrustCockpitArtifactSummary(artifact_count=0)

    artifacts = [
        TrustCockpitArtifactDigest(
            name=str(item["name"]),
            sha256=str(item["sha256"]),
            bytes=int(item["bytes"]),
            path=str(item["path"]) if item.get("path") else None,
        )
        for item in artifact_manifest.get("artifacts", [])
        if isinstance(item, Mapping)
    ]
    local_signature = artifact_manifest.get("local_integrity_signature", {})
    if not isinstance(local_signature, Mapping):
        local_signature = {}
    return TrustCockpitArtifactSummary(
        manifest_schema=(
            str(artifact_manifest.get("schema")) if artifact_manifest.get("schema") else None
        ),
        artifact_count=len(artifacts),
        local_integrity_algorithm=(
            str(local_signature.get("algorithm")) if local_signature.get("algorithm") else None
        ),
        local_integrity_value=(
            str(local_signature.get("value")) if local_signature.get("value") else None
        ),
        artifacts=artifacts,
    )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item.strip()))


def _next_actions(
    assessment: LegalOpsAssessment,
    source_verified_run: SourceVerifiedReviewPacketRun,
) -> list[str]:
    actions: list[str] = []
    if source_verified_run.status == "blocked":
        actions.append("Remove blocked source references before reviewer reliance.")
    if source_verified_run.policy_envelope.human_review_required:
        actions.append("Record a documented human review decision before export.")
    if assessment.customer_commitments:
        actions.append("Record customer commitments in the obligations register before signature.")
    actions.extend(source_verified_run.risk_triage.recommended_next_actions)
    return _dedupe(actions)


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _render_artifacts(summary: TrustCockpitArtifactSummary) -> list[str]:
    if not summary.artifacts:
        return ["- Artifact manifest: unrecorded"]
    lines = [
        f"- Manifest schema: {summary.manifest_schema}",
        f"- Artifact count: {summary.artifact_count}",
        f"- Local integrity: {summary.local_integrity_algorithm} {summary.local_integrity_value}",
    ]
    for artifact in summary.artifacts:
        lines.append(f"- {artifact.name}: {artifact.sha256} ({artifact.bytes} bytes)")
    return lines


def _render_audit_chain(chain: AuditChainVerification) -> list[str]:
    return [
        f"- Verified: {_format_bool(chain.verified)}",
        f"- Events: {chain.event_count}",
        f"- Chain root hash: {chain.chain_root_hash or 'none'}",
        f"- Reason: {chain.reason}",
    ]


def render_trust_cockpit_markdown(cockpit: LegalOpsTrustCockpit) -> str:
    """Render a concise reviewer-facing trust cockpit."""

    source = cockpit.source_summary
    gate = cockpit.review_gate
    commitments = cockpit.commitment_summary
    decision = cockpit.decision_summary
    metadata = cockpit.metadata

    lines = [
        f"# LegalOps Trust Cockpit: {cockpit.matter_title}",
        "",
        "## Evidence Metadata",
        f"- Schema: {cockpit.schema_version}",
        f"- Assessment: {cockpit.assessment_id}",
        f"- Generated: {cockpit.generated_at_utc}",
        f"- Fixture: {metadata.fixture or 'unrecorded'}",
        f"- Command: `{metadata.command or 'unrecorded'}`",
        f"- Python: {metadata.python_version}",
        f"- Application version: {metadata.application_version}",
        f"- Source runner schema: {metadata.source_verified_runner_schema}",
        "",
        "## Decision State",
        f"- Status: {decision.status}",
        f"- Review state: {decision.review_state}",
        f"- Export allowed: {_format_bool(decision.export_allowed)}",
        f"- Human review required: {_format_bool(decision.human_review_required)}",
        f"- Highest severity: {decision.highest_severity}",
        f"- Findings: {decision.finding_count}",
        f"- Blockers: {decision.blocker_count}",
        f"- Owner role: {decision.owner_role}",
        f"- Reviewers: {', '.join(decision.reviewers)}",
        f"- SLA hours: {decision.sla_hours}",
        "",
        "## Source Boundary",
        f"- Boundary: {source.source_boundary}",
        f"- Pass: {source.pass_count}",
        f"- Warning: {source.warning_count}",
        f"- Blocker: {source.blocker_count}",
    ]
    for entry in source.entries:
        lines.append(
            f"- {entry.status}: {entry.source_ref} ({entry.category}, review={entry.requires_human_review})"
        )

    lines.extend(
        [
            "",
            "## Review Gate",
            f"- Delivery mode: {gate.delivery_mode}",
            f"- External actions allowed: {_format_bool(gate.external_actions_allowed)}",
            f"- Blocked actions: {', '.join(gate.blocked_actions)}",
            f"- Legal advice status: {gate.legal_advice_status}",
            "",
            "## Commitments",
            f"- Count: {commitments.count}",
            f"- Review required: {commitments.review_required_count}",
            f"- Owner roles: {', '.join(commitments.owner_roles) if commitments.owner_roles else 'none'}",
        ]
    )
    for commitment in commitments.commitments:
        lines.append(
            f"- {commitment.commitment} | owner={commitment.owner_role} | source={commitment.source}"
        )

    lines.extend(["", "## Artifact Integrity"])
    lines.extend(_render_artifacts(cockpit.artifact_summary))
    lines.extend(["", "## Audit Chain Integrity"])
    lines.extend(_render_audit_chain(cockpit.audit_chain))
    lines.extend(["", "## Next Actions"])
    lines.extend(f"- {action}" for action in cockpit.next_actions)
    return "\n".join(lines) + "\n"


def build_trust_cockpit(
    assessment: LegalOpsAssessment,
    *,
    source_verified_run: SourceVerifiedReviewPacketRun | None = None,
    artifact_manifest: Mapping[str, Any] | None = None,
    fixture: str | None = None,
    command: str | None = None,
) -> LegalOpsTrustCockpit:
    """Build a source-verified reviewer cockpit without external effects."""

    run = source_verified_run or build_source_verified_review_packet_run(assessment)
    commitments = _safe_commitments(assessment)
    artifact_summary = _artifact_summary(artifact_manifest)
    audit_chain = verify_audit_chain(assessment.audit_events)
    cockpit = LegalOpsTrustCockpit(
        schema=TRUST_COCKPIT_SCHEMA,
        assessment_id=assessment.assessment_id,
        generated_at_utc=utc_now_iso(),
        matter_title=run.matter_intake.title,
        metadata=TrustCockpitMetadata(
            fixture=fixture,
            command=command,
            python_version=platform.python_version(),
            application_version=APPLICATION_VERSION,
            source_verified_runner_schema=run.schema_version,
        ),
        decision_summary=TrustCockpitDecisionSummary(
            status=run.status,
            review_state=run.review_state,
            export_allowed=run.export_allowed,
            human_review_required=run.policy_envelope.human_review_required,
            highest_severity=run.risk_triage.highest_severity,
            finding_count=run.risk_triage.finding_count,
            blocker_count=run.risk_triage.blocker_count,
            owner_role=assessment.routing.owner_role,
            reviewers=assessment.routing.reviewers,
            sla_hours=assessment.routing.sla_hours,
        ),
        source_summary=TrustCockpitSourceSummary(
            source_boundary=run.policy_envelope.source_boundary,
            pass_count=run.source_manifest.pass_count,
            warning_count=run.source_manifest.warning_count,
            blocker_count=run.source_manifest.blocker_count,
            entries=run.source_manifest.entries,
        ),
        review_gate=TrustCockpitReviewGateSummary(
            delivery_mode=run.policy_envelope.delivery_mode,
            external_actions_allowed=run.policy_envelope.external_actions_allowed,
            blocked_actions=run.policy_envelope.blocked_actions,
            legal_advice_status=run.policy_envelope.legal_advice_status,
        ),
        commitment_summary=TrustCockpitCommitmentSummary(
            count=len(commitments),
            review_required_count=sum(1 for item in commitments if item.review_required),
            owner_roles=sorted({item.owner_role for item in commitments}),
            commitments=commitments,
        ),
        artifact_summary=artifact_summary,
        audit_chain=audit_chain,
        next_actions=_next_actions(assessment, run),
        markdown="pending",
    )
    payload = cockpit.model_dump(mode="python", by_alias=True)
    payload["markdown"] = render_trust_cockpit_markdown(cockpit)
    return LegalOpsTrustCockpit.model_validate(payload)


def write_trust_cockpit_json(cockpit: LegalOpsTrustCockpit, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = cockpit.model_dump(mode="json", by_alias=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def write_trust_cockpit_markdown(cockpit: LegalOpsTrustCockpit, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cockpit.markdown, encoding="utf-8")
    return output_path
