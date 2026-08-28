from pathlib import Path

from models import MatterIntake, ReviewDecision
from src.legal_ops import apply_review_decision, assess_matter
from src.trust_cockpit import build_trust_cockpit

SAAS_MSA_FIXTURE = Path("examples/matters/saas_msa_deviation.json")


def test_trust_cockpit_summarizes_source_verified_saas_msa_fixture():
    matter = MatterIntake.model_validate_json(SAAS_MSA_FIXTURE.read_text(encoding="utf-8"))
    assessment = assess_matter(matter)

    cockpit = build_trust_cockpit(
        assessment,
        fixture="examples/matters/saas_msa_deviation.json",
        command="python -m src.cli --input examples/matters/saas_msa_deviation.json",
    )

    assert cockpit.schema_version == "legal-ops-agent.trust-cockpit.v1"
    assert cockpit.decision_summary.status == "review_required"
    assert cockpit.decision_summary.export_allowed is False
    assert cockpit.decision_summary.human_review_required is True
    assert cockpit.source_summary.pass_count == 1
    assert cockpit.source_summary.blocker_count == 0
    assert cockpit.review_gate.external_actions_allowed is False
    assert cockpit.commitment_summary.count == 3
    assert cockpit.commitment_summary.owner_roles == ["Commercial Counsel"]
    assert "LegalOps Trust Cockpit" in cockpit.markdown
    assert "Record a documented human review decision before export." in cockpit.next_actions
    assert cockpit.audit_chain.verified is True
    assert cockpit.audit_chain.event_count == 1
    assert "Audit Chain Integrity" in cockpit.markdown


def test_trust_cockpit_redacts_blocked_source_identifiers():
    matter = MatterIntake(
        title="Blocked source cockpit check",
        requester="Legal",
        business_unit="Enterprise Sales",
        matter_type="contract",
        jurisdiction="EU",
        summary="Reviewer checks that blocked source references stay out of cockpit payloads.",
        urgency="medium",
        customer_commitments=["special audit right"],
        source_refs=["client:acme-dpa"],
    )

    cockpit = build_trust_cockpit(assess_matter(matter))
    payload = cockpit.model_dump_json(by_alias=True)

    assert cockpit.decision_summary.status == "blocked"
    assert cockpit.source_summary.source_boundary == "blocked_sensitive_source_reference"
    assert cockpit.source_summary.entries[0].source_ref == "client:<redacted>"
    assert cockpit.commitment_summary.commitments[0].source == "client:<redacted>"
    assert "acme-dpa" not in payload
    assert "acme-dpa" not in cockpit.markdown
    assert "client:<redacted>" in cockpit.markdown


def test_trust_cockpit_ready_after_human_approval_without_blockers():
    matter = MatterIntake.model_validate_json(SAAS_MSA_FIXTURE.read_text(encoding="utf-8"))
    assessment = assess_matter(matter)
    approved = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note="Approved after commercial counsel review of the synthetic MSA deviation.",
        ),
    )

    cockpit = build_trust_cockpit(approved)

    assert cockpit.decision_summary.status == "ready"
    assert cockpit.decision_summary.export_allowed is True
    assert cockpit.decision_summary.human_review_required is False
    assert cockpit.review_gate.delivery_mode == "local_review_only"
    assert cockpit.audit_chain.verified is True
    assert cockpit.audit_chain.event_count == 2
