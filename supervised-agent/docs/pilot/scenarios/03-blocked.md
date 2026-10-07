# Scenario 3: matter that must remain blocked

> Synthetic identities and data. Generated from `examples/pilot/scenarios/03-blocked.json`. Edit that file, then run `python -m src.pilot.cli scenario-docs`.

A matter that cites a confidential source, asks for uncapped liability and has no agreed decision authority never leaves triage, whichever route is tried.

- Matter: `PM-BLOCKED-003`
- Customer draft: `examples/pilot/documents/synthetic-msa-blocked.docx`
- Parent routing inputs: value band `250k-1m`, personal data `True`, uncapped liability `True`
- Recorded decision authority: `none`

## Facilitator script

Scripted times are fixture timestamps used to demonstrate measurement. They are not observations.

| Step | Scripted time (UTC) | Who | Action | Expected result | What happens |
| --- | --- | --- | --- | --- | --- |
| C01 | 2026-09-08T10:00:00Z | Synthetic Requester A (Revenue Operations) | create matter | succeeds | The requester opens the matter. Because a blocked source prefix is present, the system withholds document processing: no change is proposed. |
| C02 | 2026-09-08T10:05:00Z | Synthetic Requester A (Revenue Operations) | submit intake | succeeds | The intake fields are complete, so the matter reaches the triage queue. |
| C03 | 2026-09-08T11:00:00Z | Synthetic Matter Owner B (Commercial Counsel) | complete triage | refused: evidence missing or not allowed in this state (sources_usable, pilot_scope_met, decision_authority_agreed) | Triage is refused for three independent reasons: a confidential source, a charter exclusion (uncapped liability) and no agreed decision authority. |
| C04 | 2026-09-08T11:05:00Z | Synthetic Matter Owner B (Commercial Counsel) | assign | refused: role or assignment | The owner tries to skip triage and assign an approver. The owner holds the role but is not assigned to this matter. |
| C05 | 2026-09-08T11:10:00Z | Synthetic Approver E (General Counsel) | approve | refused: role or assignment | A General Counsel approval attempt is refused: seniority grants nothing on a matter the approver is not assigned to, and approval is not reachable from triage in any case. |
| C06 | 2026-09-08T11:15:00Z | Synthetic Matter Owner B (Commercial Counsel) | export internal review | refused: role or assignment | Even an internal review export is refused for an unassigned actor. |
| C07 | 2026-09-08T11:20:00Z | Caller outside the workflow | stateless delivery gate | refused by the export gate | Library bypass: calling the export gate directly with an in-memory approval fails on the blocker finding and the missing store decisions. |
| C08 | 2026-09-08T11:25:00Z | Caller outside the workflow | legacy docx render | refused by the export gate | Library bypass: the stateless DOCX path refuses to process a document while a blocked source reference is present. |
| restart |  | Facilitator | stop and restart the process |  | Stop the process. The blocked state must survive a restart. |
| C09 | 2026-09-09T09:00:00Z | Synthetic Matter Owner F (Commercial Counsel) | complete triage | refused: evidence missing or not allowed in this state | After the restart a different matter owner tries triage. The same three holds apply. |
| C10 | 2026-09-09T09:05:00Z | Synthetic Requester A (Revenue Operations) | prepare delivery | refused: evidence missing or not allowed in this state | The requester asks for the package directly. Refused. |

## Expected end state

- State: `triage`
- Matter version: 1
- Delivery packages written: 0
- Closing outcome: `None`
