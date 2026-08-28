import pytest
from pydantic import ValidationError

from models import LegalOpsAssessment, MatterIntake, ReviewDecision, RiskFinding, RoutingDecision


def test_matter_intake_rejects_short_summary():
    with pytest.raises(ValidationError):
        MatterIntake(
            title="DPA review",
            requester="Sales",
            business_unit="Enterprise",
            matter_type="privacy",
            jurisdiction="EU",
            summary="Too short",
        )


def test_review_decision_requires_approval_note_detail():
    with pytest.raises(ValidationError):
        ReviewDecision(reviewer="GC", state="approved", note="Approved.")


def test_assessment_export_requires_approved_state():
    matter = MatterIntake(
        title="Enterprise customer DPA review",
        requester="Sales",
        business_unit="Enterprise",
        matter_type="privacy",
        jurisdiction="EU",
        summary="Customer asks for changes to data processing terms and audit controls.",
    )
    finding = RiskFinding(
        category="privacy",
        severity="medium",
        summary="Data processing terms require review.",
        evidence="DPA request",
        recommended_action="Review roles, subprocessors and transfer basis.",
    )
    routing = RoutingDecision(
        owner_role="Privacy Counsel",
        reviewers=["Privacy Counsel"],
        rationale="Privacy matter requires specialist review before export.",
        sla_hours=24,
    )

    with pytest.raises(ValidationError):
        LegalOpsAssessment(
            assessment_id="loa_test12345",
            created_at_utc="2026-06-02T12:00:00Z",
            matter=matter,
            findings=[finding],
            routing=routing,
            review_state="needs_review",
            export_allowed=True,
        )


def test_assessment_export_requires_review_note():
    matter = MatterIntake(
        title="Enterprise customer DPA review",
        requester="Sales",
        business_unit="Enterprise",
        matter_type="privacy",
        jurisdiction="EU",
        summary="Customer asks for changes to data processing terms and audit controls.",
    )
    finding = RiskFinding(
        category="privacy",
        severity="medium",
        summary="Data processing terms require review.",
        evidence="DPA request",
        recommended_action="Review roles, subprocessors and transfer basis.",
    )
    routing = RoutingDecision(
        owner_role="Privacy Counsel",
        reviewers=["Privacy Counsel"],
        rationale="Privacy matter requires specialist review before export.",
        sla_hours=24,
    )

    with pytest.raises(ValidationError):
        LegalOpsAssessment(
            assessment_id="loa_test12345",
            created_at_utc="2026-06-02T12:00:00Z",
            matter=matter,
            findings=[finding],
            routing=routing,
            review_state="approved",
            export_allowed=True,
        )


def test_assessment_export_requires_verified_audit_chain():
    matter = MatterIntake(
        title="Enterprise customer DPA review",
        requester="Sales",
        business_unit="Enterprise",
        matter_type="privacy",
        jurisdiction="EU",
        summary="Customer asks for changes to data processing terms and audit controls.",
    )
    finding = RiskFinding(
        category="privacy",
        severity="medium",
        summary="Data processing terms require review.",
        evidence="DPA request",
        recommended_action="Review roles, subprocessors and transfer basis.",
    )
    routing = RoutingDecision(
        owner_role="Privacy Counsel",
        reviewers=["Privacy Counsel"],
        rationale="Privacy matter requires specialist review before export.",
        sla_hours=24,
    )

    with pytest.raises(ValidationError):
        LegalOpsAssessment(
            assessment_id="loa_test12345",
            created_at_utc="2026-06-02T12:00:00Z",
            matter=matter,
            findings=[finding],
            routing=routing,
            review_state="approved",
            review_note="General Counsel: Approved after privacy review of the synthetic matter.",
            export_allowed=True,
            audit_events=[],
        )
