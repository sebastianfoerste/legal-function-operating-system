# API Reference: LegalOps Agent MCP Tools

The repository exposes a local MCP-style surface through `src/mcp_tools.py` and
the runtime canary. Tool calls are designed for synthetic or approved local
matter data only.

## Global safety limits

- No client, candidate, privileged, confidential or personal data.
- No external delivery or publication.
- No legal advice or filing-ready output.
- Export remains blocked until a documented human decision is applied.
- `client:`, `candidate:`, `privileged:` and `confidential:` source prefixes
  are blocker findings.
- Public references are classified locally; the tool does not fetch external
  source text.

## `legal.matter.assess`

Purpose: validate a `MatterIntake`, generate deterministic findings, source
checks, reviewer routing, controls and audit events.

Input schema: `MatterIntake.model_json_schema()`.

Output schema: `LegalOpsAssessment.model_json_schema()`.

Example call:

```json
{
  "name": "legal.matter.assess",
  "arguments": {
    "title": "SaaS MSA deviation review",
    "requester": "Revenue Operations",
    "business_unit": "Enterprise Sales",
    "matter_type": "contract",
    "jurisdiction": "EU and United States",
    "summary": "Synthetic MSA deviation with higher liability cap and audit rights.",
    "urgency": "high",
    "source_refs": ["synthetic:saas-msa-deviation-example"]
  }
}
```

## `legal.review.decide`

Purpose: apply a human review decision to an assessment.

Input schema: object with `assessment` (`LegalOpsAssessment`) and `decision`
(`ReviewDecision`).

Output schema: `LegalOpsAssessment.model_json_schema()`.

Safety limit: an approval note is mandatory. Export is still blocked if blocker
findings remain.

Example call:

```json
{
  "name": "legal.review.decide",
  "arguments": {
    "assessment": "<LegalOpsAssessment JSON>",
    "decision": {
      "reviewer": "General Counsel",
      "state": "approved",
      "note": "Approved after review of the synthetic matter facts and controls."
    }
  }
}
```

## `legal.review.packet`

Purpose: render a markdown review packet from an assessment.

Input schema: `LegalOpsAssessment.model_json_schema()`.

Output schema:

```json
{
  "type": "object",
  "properties": {
    "markdown": { "type": "string" }
  },
  "required": ["markdown"]
}
```

Safety limit: packets are reviewer drafts. They are not legal advice and do not
override the export gate.

## `legal.review.packet.run`

Purpose: assess a `MatterIntake` and return one source-verified runner payload
with risk triage, safe source manifest, policy envelope, review state and
Markdown packet.

Input schema: `MatterIntake.model_json_schema()`.

Output schema: `SourceVerifiedReviewPacketRun.model_json_schema()`.

Safety limits:

1. The runner has no external effects.
2. External delivery, publication, filing and outreach remain blocked.
3. Blocked sensitive source identifiers are redacted inside the runner payload.
4. The Markdown packet remains a draft for human review.

## `legal.review.trust_cockpit`

Purpose: assess a `MatterIntake` and return a reviewer-facing trust cockpit
with decision state, source boundary, review gate, customer commitments, local
artifact evidence fields and next actions.

Input schema: `MatterIntake.model_json_schema()`.

Output schema: `LegalOpsTrustCockpit.model_json_schema()`.

Safety limits:

1. The cockpit has no external effects.
2. External delivery, publication, filing and outreach remain blocked.
3. Blocked sensitive source identifiers are redacted inside source and commitment fields.
4. The output is a reviewer evidence surface for local evaluation.

Example call:

```json
{
  "name": "legal.review.trust_cockpit",
  "arguments": {
    "title": "SaaS MSA deviation review",
    "requester": "Revenue Operations",
    "business_unit": "Enterprise Sales",
    "matter_type": "contract",
    "jurisdiction": "EU and United States",
    "summary": "Synthetic MSA deviation with higher liability cap and audit rights.",
    "urgency": "high",
    "source_refs": ["synthetic:saas-msa-deviation-example"]
  }
}
```

## `legal.audit.verify`

Purpose: verify the tamper-evident hash chain on an assessment's audit trail.

Input schema: `LegalOpsAssessment.model_json_schema()`.

Output schema: `AuditChainVerification.model_json_schema()`.

Safety limits:

1. The tool only recomputes hashes over the supplied assessment; it has no external effects.
2. A broken or empty chain reports `verified: false` with a `reason` and `broken_at_seq`.
3. The same check runs inside the export gate: an assessment cannot carry `export_allowed: true` over an unverified chain.

Example call:

```json
{
  "name": "legal.audit.verify",
  "arguments": "<LegalOpsAssessment JSON>"
}
```

## `legal.sources.verify`

Purpose: classify source references without fetching external content.

Input schema:

```json
{
  "type": "object",
  "properties": {
    "source_refs": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "required": ["source_refs"]
}
```

Output schema: object containing `source_verifications` and
`public_regulatory_domains`.

Example call:

```json
{
  "name": "legal.sources.verify",
  "arguments": {
    "source_refs": [
      "synthetic:dpa-review-example",
      "public:https://www.esma.europa.eu/",
      "privileged:board-advice"
    ]
  }
}
```

## `legal.sources.list`

Purpose: show the public demo boundary.

Input schema: empty object.

Output schema:

```json
{
  "type": "object",
  "properties": {
    "allowed_sources": { "type": "array", "items": { "type": "string" } },
    "blocked_sources": { "type": "array", "items": { "type": "string" } },
    "external_processing": { "type": "string" }
  },
  "required": ["allowed_sources", "blocked_sources", "external_processing"]
}
```
