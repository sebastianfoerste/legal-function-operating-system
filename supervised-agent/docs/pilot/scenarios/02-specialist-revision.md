# Scenario 2: specialist input and revision

> Synthetic identities and data. Generated from `examples/pilot/scenarios/02-specialist-revision.json`. Edit that file, then run `python -m src.pilot.cli scenario-docs`.

A higher-value draft with seven deviations needs a privacy specialist, a clarification from the requester, a revision cycle with a reopened issue and a re-approval after the matter changes.

- Matter: `PM-SPECIALIST-002`
- Customer draft: `examples/pilot/documents/synthetic-msa-specialist.docx`
- Parent routing inputs: value band `250k-1m`, personal data `True`, uncapped liability `False`
- Recorded decision authority: `General Counsel`

## Facilitator script

Scripted times are fixture timestamps used to demonstrate measurement. They are not observations.

| Step | Scripted time (UTC) | Who | Action | Expected result | What happens |
| --- | --- | --- | --- | --- | --- |
| B01 | 2026-09-08T08:30:00Z | Synthetic Requester A (Revenue Operations) | create matter | succeeds | The requester opens the matter but leaves the business owner blank: four of five required facts. |
| B02 | 2026-09-08T08:35:00Z | Synthetic Requester A (Revenue Operations) | submit intake | refused: evidence missing or not allowed in this state (intake_complete) | Submission is refused and names the missing fact. This first attempt is what the intake-completeness measure counts. |
| B03 | 2026-09-08T08:50:00Z | Synthetic Requester A (Revenue Operations) | amend matter | succeeds | A new fact is a substantive change, so the system keeps version 1 and creates version 2 with a fresh assessment. |
| B04 | 2026-09-08T08:55:00Z | Synthetic Requester A (Revenue Operations) | submit intake | succeeds | The intake is now complete. |
| B05 | 2026-09-08T10:00:00Z | Synthetic Matter Owner B (Commercial Counsel) | complete triage | succeeds | Parent routing: medium risk, priority P2, approval chain up to General Counsel. The subprocessor rule requires Privacy Counsel. |
| B06 | 2026-09-08T10:05:00Z | Synthetic Matter Owner B (Commercial Counsel) | assign | succeeds | The owner assigns the privacy specialist. |
| B07 | 2026-09-08T10:08:00Z | Synthetic Matter Owner B (Commercial Counsel) | assign | succeeds | The owner assigns the General Counsel as final approver. |
| B08 | 2026-09-08T10:10:00Z | Synthetic Matter Owner B (Commercial Counsel) | start review | refused: evidence missing or not allowed in this state (reviewers_available) | Readiness check: the specialist has not completed onboarding, so review cannot start. |
| B09 | 2026-09-08T10:50:00Z | Synthetic Specialist C (Privacy Counsel) | complete onboarding tasks | succeeds | The specialist completes the three onboarding tasks for the role. |
| B10 | 2026-09-08T11:00:00Z | Synthetic Matter Owner B (Commercial Counsel) | start review | succeeds | The readiness check passes and review opens. |
| restart |  | Facilitator | stop and restart the process |  | Stop the process. Review continues in a new process. |
| B11 | 2026-09-08T11:05:00Z | Synthetic Matter Owner B (Commercial Counsel) | export internal review | succeeds | An internal review draft is written for reading in Word. Every file is marked as a draft and it is stored apart from delivery packages. |
| B12 | 2026-09-08T11:30:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Audit right: standard position. |
| B13 | 2026-09-08T11:40:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Payment terms: the proposed change is rejected, which accepts the customer's wording as an exception. A reason is mandatory. |
| B14 | 2026-09-08T11:45:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Missing exclusion of indirect loss: the standard clause is inserted. |
| B15 | 2026-09-08T11:50:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Most-favoured-customer clause: deleted. |
| B16 | 2026-09-08T11:55:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Roadmap commitment: replaced by the informational statement. |
| B17 | 2026-09-08T12:00:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Liability cap: the owner needs a fact from the business and asks the requester. The clock for waiting on the business starts. |
| B18 | 2026-09-08T12:05:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | refused: role or assignment | Unauthorised decision: the owner tries to decide the privacy clause. Only Privacy Counsel may. |
| B19 | 2026-09-08T13:00:00Z | Synthetic Specialist C (Privacy Counsel) | decide change | succeeds | The privacy specialist accepts the standard subprocessor clause. |
| B20 | 2026-09-08T13:10:00Z | Synthetic Matter Owner B (Commercial Counsel) | resolve comment; at the same revision Synthetic Specialist C (Privacy Counsel) sends comment | succeeds; the second request is refused: stale submission | Conflicting edits: the owner and the specialist both act on the revision they loaded. The owner's write lands; the specialist's is refused as stale and nothing is overwritten. |
| B21 | 2026-09-08T13:15:00Z | Synthetic Specialist C (Privacy Counsel) | comment | succeeds | The specialist reloads and resubmits the comment. |
| B22 | 2026-09-08T13:30:00Z | Synthetic Specialist C (Privacy Counsel) | specialist signoff | succeeds | The specialist signs off. The sign-off is bound to version 2. |
| B23 | 2026-09-08T15:00:00Z | Synthetic Approver E (General Counsel) | approve | refused: evidence missing or not allowed in this state (changes_decided, no_open_blockers) | The approver tries to approve early. Refused: one change is undecided and a clarification is open. |
| restart |  | Facilitator | stop and restart the process |  | Stop the process overnight. The open clarification and every decision must still be there. |
| B24 | 2026-09-09T09:00:00Z | Synthetic Requester A (Revenue Operations) | respond comment | succeeds | The requester answers the clarification with a supporting note. Waiting on the business ends. |
| B25 | 2026-09-09T09:20:00Z | Synthetic Matter Owner B (Commercial Counsel) | resolve comment | succeeds | The owner, who asked, resolves the clarification. |
| B26 | 2026-09-09T09:30:00Z | Synthetic Matter Owner B (Commercial Counsel) | decide change | succeeds | Liability cap: amended to the fallback. Original, proposed and amended wording are all kept with the reason. |
| B27 | 2026-09-09T11:00:00Z | Synthetic Approver E (General Counsel) | comment | succeeds | The approver raises a critical comment on the accepted-exceptions section of the deliverable. |
| B28 | 2026-09-09T11:05:00Z | Synthetic Approver E (General Counsel) | request revision | succeeds | The approver requests a revision and names the comment it concerns. |
| B29 | 2026-09-09T11:10:00Z | Synthetic Matter Owner B (Commercial Counsel) | resolve comment | refused: role or assignment | Unauthorised decision: the owner tries to close a critical comment on their own work. Only its author or the final approver may. |
| B30 | 2026-09-09T11:40:00Z | Synthetic Matter Owner B (Commercial Counsel) | respond comment | succeeds | The owner responds with evidence. This is correction effort. |
| B31 | 2026-09-09T11:50:00Z | Synthetic Matter Owner B (Commercial Counsel) | submit revision | succeeds | The owner submits the revision. |
| B32 | 2026-09-09T12:00:00Z | Synthetic Approver E (General Counsel) | resume review | succeeds | The approver resumes review. |
| B33 | 2026-09-09T12:10:00Z | Synthetic Approver E (General Counsel) | resolve comment | succeeds | The approver resolves the comment. |
| B34 | 2026-09-09T12:15:00Z | Synthetic Approver E (General Counsel) | reopen comment | succeeds | Reopened issue: on reading the note the approver sees it covers sixty days only and reopens the comment. |
| B35 | 2026-09-09T12:40:00Z | Synthetic Matter Owner B (Commercial Counsel) | respond comment | succeeds | The owner supplies the corrected note. |
| B36 | 2026-09-09T13:00:00Z | Synthetic Approver E (General Counsel) | resolve comment | succeeds | The approver resolves the comment for good. |
| B37 | 2026-09-09T13:10:00Z | Synthetic Requester A (Revenue Operations) | amend matter | succeeds | The requester changes a fact. Version 3 is created and reassessed, the specialist's sign-off on version 2 is invalidated, unchanged change decisions carry forward, and the matter moves to revised. |
| B38 | 2026-09-09T13:15:00Z | Synthetic Approver E (General Counsel) | approve | refused: evidence missing or not allowed in this state | Stale approval: the approver tries to approve what they reviewed before the change. Approval is not reachable from revised. |
| B39 | 2026-09-09T13:20:00Z | Synthetic Matter Owner B (Commercial Counsel) | resume review | succeeds | The owner resumes review on version 3. |
| B40 | 2026-09-09T13:25:00Z | Synthetic Approver E (General Counsel) | approve | refused: evidence missing or not allowed in this state (specialist_signoffs_current) | Still refused: the privacy sign-off belongs to version 2. |
| B41 | 2026-09-09T14:00:00Z | Synthetic Specialist C (Privacy Counsel) | specialist signoff | succeeds | The specialist signs off on version 3. |
| B42 | 2026-09-09T14:30:00Z | Synthetic Approver E (General Counsel) | approve | succeeds | The approver approves version 3 and its reviewed state. |
| B43 | 2026-09-09T14:32:00Z | Caller outside the workflow | stateless delivery gate | refused by the export gate | Library bypass after approval: a stateless caller still gets no delivery package; only the store-backed path can supply the reviewer decisions. |
| B44 | 2026-09-09T14:40:00Z | Synthetic Matter Owner B (Commercial Counsel) | prepare delivery | succeeds | The gate passes for version 3 and the delivery package is written locally. |
| restart |  | Facilitator | stop and restart the process |  | Stop the process. The package and its manifest must verify after a restart. |
| B45 | 2026-09-10T09:00:00Z | Synthetic Requester A (Revenue Operations) | accept delivery | succeeds | The requester accepts the package. The matter closes. |

## Expected end state

- State: `closed`
- Matter version: 3
- Delivery packages written: 1
- Closing outcome: `delivered_locally_and_accepted`
