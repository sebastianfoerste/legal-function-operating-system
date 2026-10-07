from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from models import (
    ControlCheck,
    ControlStatus,
    CustomerCommitmentRecord,
    DocumentVerificationRecord,
    LegalOpsAssessment,
    MatterIntake,
    ReviewDecision,
    RiskFinding,
    RoutingDecision,
    SourceVerificationRecord,
)
from src.audit_chain import append_audit_event
from src.matter_documents import FAILED_STATUSES, verify_matter_documents
from src.source_verification import verify_source_refs

SYSTEM_ACTOR = "LegalOps Agent"


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_matter_json(matter: MatterIntake) -> str:
    """The intake as hashed for ids and digests."""

    fields = matter.model_dump(mode="json")
    # Intakes written before documents existed keep the ids and digests they always had.
    for optional in ("matter_id", "round_id", "documents"):
        if not fields[optional]:
            del fields[optional]
    return json.dumps(fields, sort_keys=True)


def stable_assessment_id(matter: MatterIntake) -> str:
    payload = canonical_matter_json(matter)
    return f"loa_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def all_source_refs(matter: MatterIntake) -> list[str]:
    """Every reference under the source boundary: the matter's own and its documents'."""

    return [*matter.source_refs, *(document.source_ref for document in matter.documents)]


def blocked_source_refs(matter: MatterIntake) -> list[str]:
    return [
        record.source_ref
        for record in verify_source_refs(all_source_refs(matter))
        if record.status == "blocker"
    ]


def unapproved_source_refs(matter: MatterIntake) -> list[str]:
    return [
        record.source_ref
        for record in verify_source_refs(all_source_refs(matter))
        if record.status == "warning" and record.category != "missing"
    ]


def build_sample_matter() -> MatterIntake:
    return MatterIntake(
        title="Enterprise customer DPA review",
        requester="Sales Ops",
        business_unit="Enterprise Sales",
        matter_type="privacy",
        jurisdiction="EU and California",
        summary=(
            "A prospective enterprise customer asks for DPA changes, regional data hosting, "
            "model training restrictions and a bespoke audit commitment before signature."
        ),
        urgency="high",
        data_categories=["customer account data", "support tickets", "workspace prompts"],
        customer_commitments=["EU hosting", "no model training", "annual audit evidence"],
        source_refs=["synthetic:dpa-review-example"],
    )


def generate_findings(
    matter: MatterIntake,
    document_verifications: list[DocumentVerificationRecord] | None = None,
) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    blocked_refs = blocked_source_refs(matter)
    failed_documents = [
        record for record in document_verifications or [] if record.status in FAILED_STATUSES
    ]

    if failed_documents:
        findings.append(
            RiskFinding(
                category="document_integrity",
                severity="blocker",
                summary="A matter document does not match the version the intake recorded.",
                evidence=", ".join(
                    f"{record.document_id}: {record.status}" for record in failed_documents
                ),
                recommended_action=(
                    "Restore the recorded document version or record the new hash at intake "
                    "before any review starts."
                ),
            )
        )

    if blocked_refs:
        findings.append(
            RiskFinding(
                category="source_boundary",
                severity="blocker",
                summary="Matter references blocked source material.",
                evidence=", ".join(blocked_refs),
                recommended_action=(
                    "Remove client, candidate, privileged or confidential source "
                    "references before processing."
                ),
            )
        )

    if matter.data_categories:
        findings.append(
            RiskFinding(
                category="privacy",
                severity="medium",
                summary="Personal or customer data categories are in scope.",
                evidence=", ".join(matter.data_categories),
                recommended_action="Confirm DPA roles, transfer basis, subprocessors and deletion mechanics.",
            )
        )

    if matter.customer_commitments:
        findings.append(
            RiskFinding(
                category="customer_commitments",
                severity="high" if matter.urgency == "high" else "medium",
                summary="The matter includes bespoke customer commitments.",
                evidence=", ".join(matter.customer_commitments),
                recommended_action="Record each commitment in the customer obligations register before approval.",
            )
        )

    if matter.matter_type == "ai_governance" or "model training" in matter.summary.lower():
        findings.append(
            RiskFinding(
                category="ai_governance",
                severity="medium",
                summary="AI processing or model-training restrictions require review.",
                evidence=matter.summary,
                recommended_action="Check training opt-out language and product configuration before signature.",
            )
        )

    if matter.matter_type == "product_launch":
        findings.append(
            RiskFinding(
                category="product_counsel",
                severity="medium",
                summary="Product launch requires privacy, AI and customer-contract review.",
                evidence=matter.title,
                recommended_action="Route launch through product counsel checklist and security review.",
            )
        )

    if matter.matter_type == "regulatory_monitoring":
        findings.append(
            RiskFinding(
                category="regulatory_monitoring",
                severity="medium",
                summary="Regulatory monitoring requires source verification and legal interpretation.",
                evidence=", ".join(matter.source_refs) if matter.source_refs else matter.title,
                recommended_action="Verify source boundaries and route any checklist update for legal review.",
            )
        )

    if not findings:
        findings.append(
            RiskFinding(
                category="workflow_control",
                severity="low",
                summary="No elevated deterministic flags were found.",
                evidence=matter.matter_type,
                recommended_action="Keep matter in standard review queue and document final decision.",
            )
        )

    return findings


def _document_integrity_control(
    document_verifications: list[DocumentVerificationRecord],
) -> ControlCheck:
    failed = [record for record in document_verifications if record.status in FAILED_STATUSES]
    unchecked = [record for record in document_verifications if record.status == "not_checked"]
    status: ControlStatus
    if failed:
        status = "blocker"
        summary = "A matter document failed hash verification."
        subjects = failed
    elif unchecked:
        status = "warning"
        summary = "Matter documents were not checked against their recorded hashes."
        subjects = unchecked
    else:
        status = "pass"
        summary = "Every matter document matches its recorded hash."
        subjects = document_verifications
    return ControlCheck(
        control_id="document-integrity",
        status=status,
        summary=summary,
        evidence=", ".join(f"{record.document_id}: {record.status}" for record in subjects),
        owner_role="Legal Operations",
    )


def generate_controls(
    matter: MatterIntake,
    findings: list[RiskFinding],
    source_verifications: list[SourceVerificationRecord],
    document_verifications: list[DocumentVerificationRecord] | None = None,
) -> list[ControlCheck]:
    blocked_refs = [
        record.source_ref for record in source_verifications if record.status == "blocker"
    ]
    warning_refs = [
        record.source_ref for record in source_verifications if record.status == "warning"
    ]

    if blocked_refs:
        source_boundary_status: ControlStatus = "blocker"
        source_boundary_summary = "Blocked source references prevent export."
        source_boundary_evidence = ", ".join(blocked_refs)
    elif all_source_refs(matter) and not warning_refs:
        source_boundary_status = "pass"
        source_boundary_summary = "Matter source boundary is explicit."
        source_boundary_evidence = ", ".join(all_source_refs(matter))
    elif warning_refs:
        source_boundary_status = "warning"
        source_boundary_summary = "Source references require approval before reviewer reliance."
        source_boundary_evidence = ", ".join(warning_refs)
    else:
        source_boundary_status = "warning"
        source_boundary_summary = "Matter source boundary is missing."
        source_boundary_evidence = "No source references supplied."

    controls = [
        ControlCheck(
            control_id="source-boundary",
            status=source_boundary_status,
            summary=source_boundary_summary,
            evidence=source_boundary_evidence,
            owner_role="Legal Operations",
        ),
        ControlCheck(
            control_id="human-review-gate",
            status="pass",
            summary="Export is blocked until a human review decision is recorded.",
            evidence="review_state starts as needs_review",
            owner_role="General Counsel",
        ),
    ]

    if document_verifications:
        controls.append(_document_integrity_control(document_verifications))

    if any(finding.severity == "blocker" for finding in findings):
        controls.append(
            ControlCheck(
                control_id="blocker-gate",
                status="blocker",
                summary="At least one blocker finding prevents export.",
                evidence="blocker finding present",
                owner_role="General Counsel",
            )
        )

    if matter.customer_commitments:
        controls.append(
            ControlCheck(
                control_id="commitment-register",
                status="warning",
                summary="Customer commitments must be recorded before final signature.",
                evidence=", ".join(matter.customer_commitments),
                owner_role="Commercial Counsel",
            )
        )

    if matter.data_categories:
        controls.append(
            ControlCheck(
                control_id="data-map",
                status="warning",
                summary="Data categories require privacy mapping and retention checks.",
                evidence=", ".join(matter.data_categories),
                owner_role="Privacy Counsel",
            )
        )

    return controls


def build_customer_commitment_register(matter: MatterIntake) -> list[CustomerCommitmentRecord]:
    source = matter.source_refs[0] if matter.source_refs else "matter-intake"
    return [
        CustomerCommitmentRecord(
            commitment=commitment,
            owner_role="Commercial Counsel",
            source=source,
            review_required=True,
        )
        for commitment in matter.customer_commitments
    ]


def route_matter(matter: MatterIntake, findings: list[RiskFinding]) -> RoutingDecision:
    reviewers = ["Legal Ops"]
    owner_role = "Legal Operations"

    categories = {finding.category for finding in findings}
    if "privacy" in categories:
        reviewers.append("Privacy Counsel")
        owner_role = "Privacy Counsel"
    if "ai_governance" in categories:
        reviewers.append("AI Governance Lead")
    if "customer_commitments" in categories:
        reviewers.append("Commercial Counsel")
    if "regulatory_monitoring" in categories:
        reviewers.append("Regulatory Counsel")
    if matter.urgency == "high":
        reviewers.append("General Counsel")

    unique_reviewers = list(dict.fromkeys(reviewers))
    sla_hours = 24 if matter.urgency == "high" else 72
    return RoutingDecision(
        owner_role=owner_role,
        reviewers=unique_reviewers,
        rationale=(
            "Routing is based on matter type, deterministic risk categories and urgency. "
            "Export remains blocked until human approval."
        ),
        sla_hours=sla_hours,
    )


def assess_matter(
    matter: MatterIntake,
    *,
    documents_root: Path | None = None,
    created_at: str | None = None,
) -> LegalOpsAssessment:
    source_verifications = verify_source_refs(all_source_refs(matter))
    document_verifications = verify_matter_documents(matter, documents_root)
    findings = generate_findings(matter, document_verifications)
    routing = route_matter(matter, findings)
    created_at = created_at or utc_now_iso()
    return LegalOpsAssessment(
        assessment_id=stable_assessment_id(matter),
        created_at_utc=created_at,
        matter=matter,
        findings=findings,
        controls=generate_controls(matter, findings, source_verifications, document_verifications),
        source_verifications=source_verifications,
        document_verifications=document_verifications,
        customer_commitments=build_customer_commitment_register(matter),
        routing=routing,
        review_state="needs_review",
        export_allowed=False,
        audit_events=append_audit_event(
            [],
            event_type="assessment_created",
            actor=SYSTEM_ACTOR,
            note="Assessment created from typed matter intake.",
            timestamp_utc=created_at,
            # Binds the reviewed document versions into the chain from its first link.
            details=(
                {
                    "documents": [
                        {
                            "document_id": record.document_id,
                            "sha256": record.expected_sha256,
                            "status": record.status,
                        }
                        for record in document_verifications
                    ]
                }
                if document_verifications
                else None
            ),
        ),
    )


def apply_review_decision(
    assessment: LegalOpsAssessment,
    decision: ReviewDecision,
    *,
    decided_at: str | None = None,
) -> LegalOpsAssessment:
    blocker_present = any(finding.severity == "blocker" for finding in assessment.findings)
    # Documents an intake pins by hash must have been checked, not merely listed.
    documents_verified = all(
        record.status == "verified" for record in assessment.document_verifications
    )
    export_allowed = decision.state == "approved" and not blocker_present and documents_verified
    audit_events = append_audit_event(
        assessment.audit_events,
        event_type="review_decision_applied",
        actor=decision.reviewer,
        note=decision.note,
        timestamp_utc=decided_at or utc_now_iso(),
        details={"state": decision.state},
    )
    payload = assessment.model_dump(mode="python")
    payload.update(
        {
            "review_state": decision.state,
            "review_note": f"{decision.reviewer}: {decision.note}",
            "export_allowed": export_allowed,
            "audit_events": audit_events,
        }
    )
    return LegalOpsAssessment.model_validate(payload)
