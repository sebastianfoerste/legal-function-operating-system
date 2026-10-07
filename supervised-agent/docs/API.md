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

### Matter documents

An intake may name the matter it belongs to and reference its documents in place.
All three fields are optional, and an intake without them serialises exactly as
before, so its assessment id is unchanged.

| Field | Meaning |
|---|---|
| `matter_id`, `round_id` | The matter and the point in its history this intake describes |
| `documents[].document_id`, `.kind`, `.title` | Identity of one document; `kind` is free, for example `contract` or `playbook` |
| `documents[].path` | Relative to a documents root given at run time. Absolute paths and `..` are refused |
| `documents[].sha256` | Hash of the exact version the intake refers to |
| `documents[].source_ref` | Source-boundary reference, checked like `source_refs` |
| `documents[].introduced_in` | Optional. The round in which the document entered the matter |

The assessment returns one `document_verifications` record per document, with status
`verified`, `mismatch`, `missing`, `refused` (the path leaves the root) or
`not_checked`. MCP tools take no documents root, so through them every document is
`not_checked`. A `mismatch`, `missing` or `refused` document is a blocker finding. An
assessment whose documents are not all `verified` cannot reach `export_allowed`, even
after approval. The command line checks hashes with `python -m src.cli --documents-root <dir>`.

Audit events may carry a `details` object. It enters the event hash only when present,
so chains written before it existed verify unchanged.

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

## Pilot review-room API

Served by `runtime_agent/app.py` under `/pilot` on `127.0.0.1`. Every data route needs the
`X-Pilot-Actor` header naming a registered synthetic actor. The header selects a simulated
local role. It is not authentication; see `docs/pilot/IDENTITY_CONTROLS.md`.

| Method and path | Purpose |
| --- | --- |
| `GET /pilot` | The review room page |
| `GET /pilot/api/actors` | Synthetic actors, onboarding tasks and scenario fixtures |
| `GET /pilot/api/matters` | Matters the actor is assigned to, plus the unclaimed triage queue for matter owners |
| `POST /pilot/api/matters` | Open a matter from `{"scenario_id"}` or from `{"intake", "document_name", "document_base64"}` |
| `GET /pilot/api/matters/{id}` | The matter as that role may see it |
| `GET /pilot/api/matters/{id}/history` | Versions, events and chain verification |
| `GET /pilot/api/matters/{id}/package` | The approved customer package, if a delivery manifest exists |
| `POST /pilot/api/matters/{id}/commands` | `{"command", "expected_revision", "args", "effort_minutes"}` |

Answers to a refused command:

| Status | `error` | Meaning |
| --- | --- | --- |
| 401 | `actor_required` | No actor header |
| 403 | `permission_denied` | Unknown actor, wrong role, or not assigned to the matter |
| 409 | `stale_submission` | The matter changed; `current_revision` is returned |
| 409 | `transition_blocked` | Evidence is missing; `evidence` lists each item |
| 409 | `export_blocked` | The export gate refused; `checks` lists each condition |
| 422 | `invalid_command` | Unknown command or invalid arguments |

Scripted fixture timestamps cannot be set through this API.

## `document.change-set.v2`

`document.change-set.v1` carried an `exportAllowed` flag that became true once every change
was decided. Version 2 removes it. The change set records `assessment_id`,
`allChangesDecided` and `coverageProblems`; whether an export is allowed is answered only by
`src/export_gate.py`. `render_annotated_docx` takes the parent assessment as a required
keyword argument.
