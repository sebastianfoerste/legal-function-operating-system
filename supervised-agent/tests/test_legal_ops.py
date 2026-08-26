from models import MatterIntake, ReviewDecision, verify_audit_chain
from src.legal_ops import apply_review_decision, assess_matter, build_sample_matter


def test_assess_matter_blocks_export_before_review():
    assessment = assess_matter(build_sample_matter())
    assert assessment.review_state == "needs_review"
    assert assessment.export_allowed is False
    assert assessment.assessment_id.startswith("loa_")
    assert assessment.controls
    assert assessment.customer_commitments
    assert assessment.audit_events[0].event_type == "assessment_created"
    assert {finding.category for finding in assessment.findings} >= {
        "privacy",
        "customer_commitments",
        "ai_governance",
    }


def test_apply_review_decision_allows_export_without_blockers():
    assessment = assess_matter(build_sample_matter())
    reviewed = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note="Approved after privacy, AI governance and customer commitment review.",
        ),
    )
    assert reviewed.review_state == "approved"
    assert reviewed.export_allowed is True
    assert reviewed.review_note is not None
    assert reviewed.audit_events[-1].event_type == "review_decision_applied"
    assert [event.seq for event in reviewed.audit_events] == [0, 1]
    chain_result = verify_audit_chain(reviewed.audit_events)
    assert chain_result.verified is True
    assert chain_result.event_count == 2


def test_route_matter_adds_gc_for_high_urgency():
    matter = MatterIntake(
        title="Product launch review",
        requester="Product",
        business_unit="Core Product",
        matter_type="product_launch",
        jurisdiction="EU",
        summary="Launch requires customer contract review, privacy review and AI governance review.",
        urgency="high",
    )
    assessment = assess_matter(matter)
    assert "General Counsel" in assessment.routing.reviewers
    assert assessment.routing.sla_hours == 24


def test_blocked_source_reference_prevents_export_after_approval():
    matter = MatterIntake(
        title="Privileged source boundary check",
        requester="Legal",
        business_unit="Enterprise Sales",
        matter_type="contract",
        jurisdiction="EU",
        summary="Reviewer checks that privileged or client source references are blocked.",
        urgency="medium",
        source_refs=["client:acme-dpa"],
    )

    assessment = assess_matter(matter)
    reviewed = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note="Approved only for source-boundary control testing with blocker still present.",
        ),
    )

    assert any(finding.category == "source_boundary" for finding in assessment.findings)
    assert any(control.status == "blocker" for control in assessment.controls)
    assert reviewed.export_allowed is False


def test_public_regulatory_source_is_verified_and_routed():
    matter = MatterIntake(
        title="Public regulatory monitoring review",
        requester="Legal Operations",
        business_unit="Product Legal",
        matter_type="regulatory_monitoring",
        jurisdiction="EU",
        summary="Legal operations reviews public regulatory monitoring before updating a checklist.",
        urgency="medium",
        source_refs=["public:https://www.esma.europa.eu/"],
    )

    assessment = assess_matter(matter)

    assert assessment.source_verifications[0].status == "pass"
    assert assessment.source_verifications[0].category == "public_regulatory"
    assert assessment.source_verifications[0].public_authority == "esma.europa.eu"
    assert any(finding.category == "regulatory_monitoring" for finding in assessment.findings)
    assert "Regulatory Counsel" in assessment.routing.reviewers


def test_unapproved_public_source_is_warning():
    matter = MatterIntake(
        title="Unapproved public source review",
        requester="Legal Operations",
        business_unit="Product Legal",
        matter_type="regulatory_monitoring",
        jurisdiction="EU",
        summary="Legal operations checks that non-allowlisted public sources require review.",
        urgency="medium",
        source_refs=["public:https://example.com/regulatory-note"],
    )

    assessment = assess_matter(matter)

    assert assessment.source_verifications[0].status == "warning"
    assert assessment.source_verifications[0].category == "public_unapproved"
    assert any(
        control.control_id == "source-boundary" and control.status == "warning"
        for control in assessment.controls
    )
