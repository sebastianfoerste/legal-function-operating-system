# Worked example: supervised legal-ops flow

This example uses synthetic facts and shows the intended workflow mechanics.

## 1. Intake

A business team submits a legal request through a typed form.

```json
{
  "matter_type": "contract_review",
  "business_owner": "sales",
  "urgency": "high",
  "issue_summary": "Customer asks for changes to standard data-use and review language.",
  "requires_customer_response": true
}
```

## 2. Triage

The workflow classifies the request before any final output is created.

```json
{
  "risk_level": "high",
  "reviewer_route": "legal_reviewer",
  "approval_required": true,
  "external_output_allowed": false
}
```

## 3. Review packet

The agent prepares a reviewer packet, not a final legal answer.

```markdown
## Review required

The request changes standard customer-facing language. A legal reviewer should confirm the approved position before any response is sent externally.
```

## 4. Human decision

The reviewer records a decision and a review note.

```json
{
  "decision": "approved_with_changes",
  "review_note": "Reviewer approved a revised response after checking the standard fallback position and escalation rules."
}
```

## 5. Output gate

Only after the human decision may the workflow produce an approved internal instruction or customer-facing response.

## Intended signal

The repository demonstrates controlled legal operations: typed intake, deterministic triage, reviewer routing, documented human approval and blocked external output until review.
