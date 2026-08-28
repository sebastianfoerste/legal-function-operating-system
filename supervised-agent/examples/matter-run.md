# Matter Run Log: Supervised Legal-Ops Flow

This run log shows the end-to-end flow of a high-urgency matter from intake to human approval, demonstrating the deterministic triage and the review-gate control that blocks export until signed off.

---

## 1. Matter Intake Facts

Submitted by the business team:
- **Title:** Enterprise customer DPA review
- **Requester:** Sales Ops (Enterprise Sales)
- **Matter Type:** privacy
- **Urgency:** high
- **Summary:** A prospective enterprise customer asks for DPA changes, regional data hosting, model training restrictions and a bespoke audit commitment before signature.

---

## 2. Deterministic Triage & Risk Assessment (Export Blocked)

Upon intake, the workflow analyzes the matter facts and classifies the risk level:
- **Assessed Risk Level:** Privacy Counsel Routing Required
- **Initial Review State:** `needs_review`
- **Export Allowed:** `False` (Blocked)

### Risk Findings Identified:
- **[MEDIUM] privacy:** Personal or customer data categories are in scope.
  - *Evidence:* customer account data, support tickets, workspace prompts
  - *Recommended Action:* Confirm DPA roles, transfer basis, subprocessors and deletion mechanics.
- **[HIGH] customer_commitments:** The matter includes bespoke customer commitments.
  - *Evidence:* EU hosting, no model training, annual audit evidence
  - *Recommended Action:* Record each commitment in the customer obligations register before approval.
- **[MEDIUM] ai_governance:** AI processing or model-training restrictions require review.
  - *Evidence:* A prospective enterprise customer asks for DPA changes, regional data hosting, model training restrictions and a bespoke audit commitment before signature.
  - *Recommended Action:* Check training opt-out language and product configuration before signature.

### Control Checks Applied:
- **source-boundary:** PASS - Matter source boundary is explicit. (Owner: Legal Operations)
- **human-review-gate:** PASS - Export is blocked until a human review decision is recorded. (Owner: General Counsel)
- **commitment-register:** WARNING - Customer commitments must be recorded before final signature. (Owner: Commercial Counsel)
- **data-map:** WARNING - Data categories require privacy mapping and retention checks. (Owner: Privacy Counsel)

---

## 3. Human Decision (Approval Recorded)

The General Counsel reviews the packet and submits the following decision:
- **Reviewer:** General Counsel
- **Decision State:** `approved`
- **Review Note:** "General Counsel: Synthetic demo approval after privacy, customer commitment and AI-governance controls were routed for review."
- **Export Allowed:** `True` (Granted)

---

## 4. Generated Review Packet (Approved)

The final approved review packet:

# LegalOps Review Packet: Enterprise customer DPA review

- Assessment ID: `loa_c6ac9d9dddb6d43b`
- Created: `2026-06-24T22:35:03Z`
- Matter type: `privacy`
- Jurisdiction: `EU and California`
- Urgency: `high`
- Review state: `approved`
- Export: `allowed`

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

- 2026-06-24T22:35:03Z | assessment_created | LegalOps Agent: Assessment created from typed matter intake.
- 2026-06-24T22:35:03Z | review_decision_applied | General Counsel: Synthetic demo approval after privacy, customer commitment and AI-governance controls were routed for review.
- 2026-06-24T22:35:03Z | review_packet_generated | LegalOps Agent: Review packet generated for human legal review.

## Review Note

General Counsel: Synthetic demo approval after privacy, customer commitment and AI-governance controls were routed for review.
