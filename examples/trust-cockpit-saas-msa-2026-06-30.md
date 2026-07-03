# LegalOps Trust Cockpit: SaaS MSA deviation review

## Evidence Metadata
- Schema: legal-ops-agent.trust-cockpit.v1
- Assessment: loa_0b5d728ed132582a
- Generated: 2026-06-30T20:08:53Z
- Fixture: examples/matters/saas_msa_deviation.json
- Command: `python -m src.cli --input examples/matters/saas_msa_deviation.json --json-output demo_output/assessment.json --packet-output demo_output/review-packet.md --commitments-output demo_output/customer-commitments.json --sources-output demo_output/source-verification.json --review-runner-output demo_output/source-verified-review-runner.json --manifest-output demo_output/artifact-manifest.json --trust-cockpit-output examples/trust-cockpit-saas-msa-2026-06-30.md --trust-cockpit-json-output examples/trust-cockpit-saas-msa-2026-06-30.json`
- Python: 3.13.14
- Application version: 0.1.0
- Source runner schema: legal-ops-agent.source-verified-review-packet-run.v1

## Decision State
- Status: review_required
- Review state: needs_review
- Export allowed: false
- Human review required: true
- Highest severity: high
- Findings: 2
- Blockers: 0
- Owner role: Privacy Counsel
- Reviewers: Legal Ops, Privacy Counsel, Commercial Counsel, General Counsel
- SLA hours: 24

## Source Boundary
- Boundary: verified_demo_or_public_regulatory_sources
- Pass: 1
- Warning: 0
- Blocker: 0
- pass: synthetic:saas-msa-deviation-example (synthetic, review=False)

## Review Gate
- Delivery mode: local_review_only
- External actions allowed: false
- Blocked actions: external_delivery, publication, filing, outreach
- Legal advice status: draft_for_human_review

## Commitments
- Count: 3
- Review required: 3
- Owner roles: Commercial Counsel
- higher liability cap for security incidents | owner=Commercial Counsel | source=synthetic:saas-msa-deviation-example
- controlled annual audit right | owner=Commercial Counsel | source=synthetic:saas-msa-deviation-example
- non-binding roadmap review | owner=Commercial Counsel | source=synthetic:saas-msa-deviation-example

## Artifact Integrity
- Manifest schema: legal-ops-agent.artifact-manifest.v1
- Artifact count: 5
- Local integrity: sha256 02b1202669620c2772ab117bb49363d18facb61c47e6b0d4a7f3260cf1e2ba96
- assessment_json: 47e8f54e14232467fca868f1fccee69564c87ab9ff3faeef9251ff71d4595d54 (4376 bytes)
- customer_commitment_register_json: 20075426d24f82bef01118bbf7a143827cec5740093d17092e7bceb5752c06de (770 bytes)
- review_packet_markdown: 2d3c5668d67225c8e8792a5116a68074b43791d3712c7ff0142081298535f316 (2869 bytes)
- source_verification_json: 4e776746d98a80e06474dd3433f3e87154a069cf8ad9f124ecfdff8452df2971 (408 bytes)
- source_verified_review_packet_runner_json: ac24f074c96e7b6906deb11869bff414b7dc2fd337e408385d791cfab14c26f1 (5416 bytes)

## Audit Chain Integrity
- Verified: true
- Events: 1
- Chain root hash: 58029ad3ca9c32ddc0dba9a40f53843d1dad91b4a50d100519b6305c4179a3d5
- Reason: chain intact

## Next Actions
- Record a documented human review decision before export.
- Record customer commitments in the obligations register before signature.
- Confirm DPA roles, transfer basis, subprocessors and deletion mechanics.
- Record each commitment in the customer obligations register before approval.
