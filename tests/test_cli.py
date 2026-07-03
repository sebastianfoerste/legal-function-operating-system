import json

from src.cli import build_parser, run


def test_cli_writes_json_and_review_packet(tmp_path):
    json_output = tmp_path / "assessment.json"
    packet_output = tmp_path / "packet.md"
    commitments_output = tmp_path / "commitments.json"
    sources_output = tmp_path / "sources.json"
    review_runner_output = tmp_path / "review-runner.json"
    manifest_output = tmp_path / "manifest.json"
    trust_cockpit_output = tmp_path / "trust-cockpit.md"
    trust_cockpit_json_output = tmp_path / "trust-cockpit.json"
    audit_chain_output = tmp_path / "audit-chain.json"
    parser = build_parser()
    args = parser.parse_args(
        [
            "--input",
            "examples/matters/enterprise_dpa.json",
            "--json-output",
            str(json_output),
            "--packet-output",
            str(packet_output),
            "--commitments-output",
            str(commitments_output),
            "--sources-output",
            str(sources_output),
            "--review-runner-output",
            str(review_runner_output),
            "--manifest-output",
            str(manifest_output),
            "--trust-cockpit-output",
            str(trust_cockpit_output),
            "--trust-cockpit-json-output",
            str(trust_cockpit_json_output),
            "--audit-chain-output",
            str(audit_chain_output),
        ]
    )

    payload = run(args)

    assert payload["export_allowed"] is False
    assert json.loads(json_output.read_text(encoding="utf-8"))["assessment_id"].startswith("loa_")
    assert "LegalOps Review Packet" in packet_output.read_text(encoding="utf-8")
    commitments = json.loads(commitments_output.read_text(encoding="utf-8"))
    assert commitments["assessment_id"] == payload["assessment_id"]
    assert len(commitments["commitments"]) == 3
    sources = json.loads(sources_output.read_text(encoding="utf-8"))
    assert sources["assessment_id"] == payload["assessment_id"]
    assert sources["source_verifications"][0]["status"] == "pass"
    review_runner = json.loads(review_runner_output.read_text(encoding="utf-8"))
    assert review_runner["schema"] == "legal-ops-agent.source-verified-review-packet-run.v1"
    assert review_runner["assessment_id"] == payload["assessment_id"]
    assert review_runner["policy_envelope"]["external_actions_allowed"] is False
    assert "LegalOps Review Packet" in review_runner["markdown_packet"]
    manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
    assert manifest["schema"] == "legal-ops-agent.artifact-manifest.v1"
    assert manifest["assessment_id"] == payload["assessment_id"]
    assert manifest["local_integrity_signature"]["algorithm"] == "sha256"
    assert len(manifest["local_integrity_signature"]["value"]) == 64
    assert {item["name"] for item in manifest["artifacts"]} == {
        "assessment_json",
        "review_packet_markdown",
        "customer_commitment_register_json",
        "source_verification_json",
        "source_verified_review_packet_runner_json",
    }
    trust_cockpit = json.loads(trust_cockpit_json_output.read_text(encoding="utf-8"))
    assert trust_cockpit["schema"] == "legal-ops-agent.trust-cockpit.v1"
    assert trust_cockpit["assessment_id"] == payload["assessment_id"]
    assert trust_cockpit["decision_summary"]["export_allowed"] is False
    assert trust_cockpit["review_gate"]["external_actions_allowed"] is False
    assert trust_cockpit["artifact_summary"]["artifact_count"] == 5
    assert "LegalOps Trust Cockpit" in trust_cockpit_output.read_text(encoding="utf-8")
    audit_chain = json.loads(audit_chain_output.read_text(encoding="utf-8"))
    assert audit_chain["verified"] is True
    assert audit_chain["event_count"] == 1
