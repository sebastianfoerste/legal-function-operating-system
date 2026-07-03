# Case study — legal-ops-agent

> Agentic legal work should stay accountable: structured intake, visible assumptions, human approval. Synthetic data only; not legal advice.

## Problem
"Agentic" legal tools are tempting and dangerous in equal measure: an agent that drafts and *acts* can move fast and skip the parts that make legal work defensible — structured intake, surfaced assumptions, a review gate, an audit trail. The risk isn't a bad draft; it's an unreviewed action that leaves no record.

## Users
A legal ops lead or in-house lawyer who wants AI to accelerate routine matters (vendor reviews, NDAs) without surrendering control or auditability.

## Workflow
1. **Typed intake** — the matter is captured as structured fields, not free text.
2. **Deterministic risk triage** — rules assign a severity and route accordingly.
3. **Reviewer routing** — high-risk matters go to the right queue (e.g. Privacy), not a generic one.
4. **Approval gate** — export is **blocked** until a human resolves requested changes and signs off.
5. **Audit trail** — every step, change, and approval is logged with who and when.

## Controls
The agent cannot release output on its own. The approval gate is the spine: a requested change leaves the matter blocked until a human resolves it, and the override is recorded with a justification. Provenance and the audit trail are first-class, not afterthoughts. The audit trail is a SHA-256 hash chain — each event commits to the one before it, so tampering after the fact is detectable, and export is blocked if the chain does not verify.

## Evaluation
The bundled run (`examples/matter-run.md`) shows a HIGH-risk SaaS vendor matter routed to Privacy, **export blocked** pending an Art. 46 transfer mechanism, then approved by a reviewer with a logged justification — the full blocked-then-approved path.

## Limitations
It models the workflow and controls over synthetic matters; it is not integrated with a real DMS, identity provider, or e-signature, and the triage rules are illustrative defaults to be tuned per team.

## Next steps
Integrate real auth/roles for the approval tiers; connect intake to a ticketing system; add SLA tracking and escalation (see `legal-function-operating-system`); persist the audit trail to an append-only store.
