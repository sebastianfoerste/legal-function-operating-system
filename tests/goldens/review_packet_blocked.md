# LegalOps Review Packet: Enterprise customer DPA review

- Assessment ID: `loa_<hash>`
- Created: `<timestamp>`
- Matter type: `privacy`
- Jurisdiction: `EU and California`
- Urgency: `high`
- Review state: `needs_review`
- Export: `blocked`

## Summary

A prospective enterprise customer asks for DPA changes, regional data hosting, model training restrictions and a bespoke audit commitment before signature.

## Routing

- Owner role: Privacy Counsel
- Reviewers: Legal Ops, Privacy Counsel, AI Governance Lead, Commercial Counsel, General Counsel
- SLA: 24 hours
- Rationale: Routing is based on matter type, deterministic risk categories and urgency. Export remains blocked until human approval.

## Findings

- MEDIUM: privacy
  Summary: Personal or customer data categories are in scope.
  Evidence: customer account data, support tickets, workspace prompts
  Action: Confirm DPA roles, transfer basis, subprocessors and deletion mechanics.
- HIGH: customer_commitments
  Summary: The matter includes bespoke customer commitments.
  Evidence: EU hosting, no model training, annual audit evidence
  Action: Record each commitment in the customer obligations register before approval.
- MEDIUM: ai_governance
  Summary: AI processing or model-training restrictions require review.
  Evidence: A prospective enterprise customer asks for DPA changes, regional data hosting, model training restrictions and a bespoke audit commitment before signature.
  Action: Check training opt-out language and product configuration before signature.

## Controls

- source-boundary: pass
  Summary: Matter source boundary is explicit.
  Evidence: synthetic:dpa-review-example
  Owner: Legal Operations
- human-review-gate: pass
  Summary: Export is blocked until a human review decision is recorded.
  Evidence: review_state starts as needs_review
  Owner: General Counsel
- commitment-register: warning
  Summary: Customer commitments must be recorded before final signature.
  Evidence: EU hosting, no model training, annual audit evidence
  Owner: Commercial Counsel
- data-map: warning
  Summary: Data categories require privacy mapping and retention checks.
  Evidence: customer account data, support tickets, workspace prompts
  Owner: Privacy Counsel

## Source Verification

- pass: synthetic:dpa-review-example | category: synthetic | human review: False
  Reason: Synthetic source reference is permitted for local demo evaluation.

## Customer Commitment Register

- EU hosting | owner: Commercial Counsel | source: synthetic:dpa-review-example | review required: True
- no model training | owner: Commercial Counsel | source: synthetic:dpa-review-example | review required: True
- annual audit evidence | owner: Commercial Counsel | source: synthetic:dpa-review-example | review required: True

## Audit Trail

- <timestamp> | assessment_created | LegalOps Agent: Assessment created from typed matter intake.
- <timestamp> | review_packet_generated | LegalOps Agent: Review packet generated for human legal review.
