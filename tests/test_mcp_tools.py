import pytest

from src.legal_ops import build_sample_matter
from src.mcp_tools import legal_ops_mcp_manifest, run_tool


def test_mcp_manifest_exposes_controlled_tools():
    manifest = legal_ops_mcp_manifest()
    tool_names = {tool["name"] for tool in manifest["tools"]}
    assert tool_names == {
        "legal.matter.assess",
        "legal.review.decide",
        "legal.review.packet",
        "legal.review.packet.run",
        "legal.review.trust_cockpit",
        "legal.audit.verify",
        "legal.sources.list",
        "legal.sources.verify",
    }


def test_mcp_assess_tool_returns_blocked_assessment():
    result = run_tool("legal.matter.assess", build_sample_matter().model_dump(mode="json"))
    assert result["review_state"] == "needs_review"
    assert result["export_allowed"] is False


def test_mcp_rejects_unknown_tool():
    with pytest.raises(ValueError):
        run_tool("legal.unknown", {})


def test_mcp_review_packet_tool_returns_markdown():
    assessment = run_tool("legal.matter.assess", build_sample_matter().model_dump(mode="json"))
    result = run_tool("legal.review.packet", assessment)
    assert "LegalOps Review Packet" in result["markdown"]


def test_mcp_review_packet_runner_returns_policy_payload():
    result = run_tool(
        "legal.review.packet.run",
        build_sample_matter().model_dump(mode="json"),
    )

    assert result["schema"] == "legal-ops-agent.source-verified-review-packet-run.v1"
    assert result["status"] == "review_required"
    assert result["policy_envelope"]["external_actions_allowed"] is False
    assert "LegalOps Review Packet" in result["markdown_packet"]


def test_mcp_trust_cockpit_returns_reviewer_evidence_payload():
    result = run_tool(
        "legal.review.trust_cockpit",
        build_sample_matter().model_dump(mode="json"),
    )

    assert result["schema"] == "legal-ops-agent.trust-cockpit.v1"
    assert result["decision_summary"]["status"] == "review_required"
    assert result["decision_summary"]["export_allowed"] is False
    assert result["review_gate"]["external_actions_allowed"] is False
    assert result["source_summary"]["pass_count"] == 1
    assert "LegalOps Trust Cockpit" in result["markdown"]


def test_mcp_source_verify_tool_returns_structured_report():
    result = run_tool(
        "legal.sources.verify",
        {"source_refs": ["public:https://www.eba.europa.eu/", "confidential:board-note"]},
    )

    records = result["source_verifications"]
    assert records[0]["status"] == "pass"
    assert records[0]["public_authority"] == "eba.europa.eu"
    assert records[1]["status"] == "blocker"


def test_mcp_audit_verify_tool_returns_chain_report():
    assessment = run_tool("legal.matter.assess", build_sample_matter().model_dump(mode="json"))
    result = run_tool("legal.audit.verify", assessment)

    assert result["verified"] is True
    assert result["event_count"] == 1
    assert result["chain_root_hash"] == assessment["audit_events"][0]["event_hash"]
