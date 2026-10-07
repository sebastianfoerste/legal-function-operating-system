# Scenario 1: routine matter

> Synthetic identities and data. Generated from `examples/pilot/scenarios/01-routine.json`. Edit that file, then run `python -m src.pilot.cli scenario-docs`.

A low-value customer draft with two ordinary deviations moves from intake to an accepted delivery package without specialist input or revision.

- Matter: `PM-ROUTINE-001`
- Customer draft: `examples/pilot/documents/synthetic-msa-routine.docx`
- Parent routing inputs: value band `<50k`, personal data `False`, uncapped liability `False`
- Recorded decision authority: `Legal Ops Lead`

## Facilitator script

Scripted times are fixture timestamps used to demonstrate measurement. They are not observations.

| Step | Scripted time (UTC) | Who | Action | Expected result | What happens |
| --- | --- | --- | --- | --- | --- |
| A01 | 2026-09-07T08:00:00Z | Synthetic Requester A (Revenue Operations) | create matter | succeeds | The requester opens the matter with the customer draft and all five required facts. |
| A02 | 2026-09-07T08:05:00Z | Synthetic Requester A (Revenue Operations) | submit intake | succeeds | Intake is complete, so submission succeeds. The system has already assessed the matter, asked the parent rules for routing and proposed two document changes. |
| A03 | 2026-09-07T08:06:00Z | Synthetic Requester A (Revenue Operations) | approve | refused: evidence missing or not allowed in this state | Unauthorised decision: the requester tries to approve. Approval is not a transition out of triage, and the refusal is written to the matter's event chain. |
| A04 | 2026-09-07T09:10:00Z | Synthetic Matter Owner B (Commercial Counsel) | complete triage | succeeds | The matter owner confirms triage: parent routing says Commercial queue, low risk, approval tier Reviewer. The recorded decision authority covers it. |
| A05 | 2026-09-07T09:15:00Z | Synthetic Matter Owner B (Commercial Counsel) | assign | succeeds | No playbook rule in this draft needs a specialist, so only a final approver is assigned. |
| A06 | 2026-09-07T09:20:00Z | Synthetic Matter Owner B (Commercial Counsel) | start review | succeeds | The readiness check passes: complete intake, usable sources, onboarded reviewers, agreed decision authority. |
| restart |  | Facilitator | stop and restart the process |  | Stop the process here. Every step below runs in a new process against the same store. |
| A07 | 2026-09-07T09:25:00Z | Synthetic Matter Owner B (Commercial Counsel) | prepare delivery | refused: evidence missing or not allowed in this state | Export bypass: the matter owner asks for a delivery package before any approval. The state machine refuses. |
| A08 | 2026-09-07T10:00:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Payment terms revert to thirty days. The owner confirms having checked the playbook rule; software does not establish that. |
| A09 | 2026-09-07T10:10:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | The audit right reverts to one audit per year on notice. |
| A10 | 2026-09-07T10:12:00Z | Caller outside the workflow | stateless delivery gate | refused by the export gate | Library bypass: a caller fabricates an approved assessment in memory and calls the export gate directly. Without recorded reviewer decisions from the store it gets no delivery package. |
| A11 | 2026-09-07T14:00:00Z | Synthetic Approver D (Legal Ops Lead) | approve | succeeds | The final approver approves this exact version and reviewed state. The parent assessment is approved in the same transaction. |
| A12 | 2026-09-07T14:10:00Z | Synthetic Matter Owner B (Commercial Counsel) | prepare delivery | succeeds | The export gate passes and the local delivery package is written. Nothing is sent. |
| A13 | 2026-09-07T15:30:00Z | Synthetic Requester A (Revenue Operations) | accept delivery | succeeds | The requester accepts the package. The matter closes. |

## Expected end state

- State: `closed`
- Matter version: 1
- Delivery packages written: 1
- Closing outcome: `delivered_locally_and_accepted`
