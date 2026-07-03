# Features: LegalOps Agent

## Matter Assessment

Turns a typed `MatterIntake` into deterministic findings, control checks, reviewer routing, source verification records and audit events.

Implementation:

1. `models.py`
2. `src/legal_ops.py`
3. `tests/test_legal_ops.py`

## Source Verification

Classifies source references without external fetching. Synthetic references pass for demo use, public regulatory domains are allowlisted for review, and sensitive prefixes become blockers.

Implementation:

1. `src/source_verification.py`
2. `docs/tool-risk-registry.md`
3. `tests/test_source_verification.py`

## MCP-Style Tool Surface

Exposes controlled local tools for assessment, review decisions, review packets, trust cockpit evidence, source listing and source verification.

Implementation:

1. `src/mcp_tools.py`
2. `mcp.json`
3. `tests/test_mcp_tools.py`

## LegalOps Trust Cockpit

Turns the source-verified runner into a reviewer-facing evidence board covering decision state, source boundary, review gate, disabled external actions, customer commitments, local artifact digests and next actions.

Implementation:

1. `models.py`
2. `src/trust_cockpit.py`
3. `src/cli.py`
4. `tests/test_trust_cockpit.py`

## Audit Integrity Chain

Hash-chains every audit event: each event commits to the hash of the one before it,
so altering, reordering or dropping a past event is detectable. Export is blocked if
the chain does not verify, in addition to the existing review-state, blocker-finding
and review-note conditions. Surfaced in the Trust Cockpit, a standalone CLI output and
a dedicated MCP tool.

The hash-chain technique itself is not novel — other open-source tools log AI agent
actions the same way. What this feature adds is pairing that chain with the legal-matter
workflow itself: it can only block export on *this* repo's typed intake, risk triage and
reviewer routing, not a generic action log. See
[`docs/competitive-research-2026-06-30.md`](competitive-research-2026-06-30.md#round-2-audit-integrity-chain).

Implementation:

1. `models.py`
2. `src/audit_chain.py`
3. `tests/test_audit_chain.py`

## Review Packets And Artifact Manifests

Renders Markdown review packets and local integrity manifests for generated artifacts. The manifest records SHA-256 digests for traceability and is not an eIDAS signature.

Implementation:

1. `src/review_packet.py`
2. `src/artifact_manifest.py`
3. `tests/test_review_packet.py`
4. `tests/test_cli.py`

## Runtime Canary

Provides local health and tool-call endpoints for development and proof checks.

Implementation:

1. `runtime_agent/app.py`
2. `tests/test_runtime_agent.py`
