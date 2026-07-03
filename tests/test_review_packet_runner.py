from models import MatterIntake, ReviewDecision
from src.legal_ops import apply_review_decision, assess_matter, build_sample_matter
from src.review_packet_runner import (
    build_source_verified_review_packet_run,
    run_source_verified_review_packet,
)


def test_runner_returns_review_required_packet_for_sample_matter():
    result = run_source_verified_review_packet(build_sample_matter())

    assert result.schema_version == "legal-ops-agent.source-verified-review-packet-run.v1"
    assert result.status == "review_required"
    assert result.export_allowed is False
    assert result.policy_envelope.human_review_required is True
    assert result.policy_envelope.external_actions_allowed is False
    assert result.source_manifest.pass_count == 1
    assert "LegalOps Review Packet" in result.markdown_packet


def test_runner_redacts_sensitive_source_identifiers():
    matter = MatterIntake(
        title="Blocked source runner check",
        requester="Legal",
        business_unit="Enterprise Sales",
        matter_type="contract",
        jurisdiction="EU",
        summary="Reviewer checks that blocked source references stay out of runner payloads.",
        urgency="medium",
        source_refs=["client:acme-dpa"],
    )

    result = run_source_verified_review_packet(matter)
    payload = result.model_dump(mode="json")

    assert result.status == "blocked"
    assert result.source_manifest.entries[0].source_ref == "client:<redacted>"
    assert result.source_manifest.entries[0].redacted is True
    assert result.policy_envelope.source_boundary == "blocked_sensitive_source_reference"
    assert "acme-dpa" not in str(payload)
    assert "client:<redacted>" in result.markdown_packet


def test_runner_ready_after_human_approval_without_blockers():
    assessment = assess_matter(build_sample_matter())
    approved = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note="Approved after privacy, AI governance and customer commitment review.",
        ),
    )

    result = build_source_verified_review_packet_run(approved)

    assert result.status == "ready"
    assert result.export_allowed is True
    assert result.policy_envelope.human_review_required is False
    assert result.policy_envelope.delivery_mode == "local_review_only"
