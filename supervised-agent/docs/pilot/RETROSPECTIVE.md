# Pilot retrospective

## Part A: rehearsal retrospective, 6 October 2026

This part reviews the scripted rehearsal committed under `examples/pilot/rehearsal-2026-10-06/`. Its participants are synthetic and its timings are scripted, so it shows where the workflow produces friction by design. It says nothing about how real reviewers will experience it.

Each row links one observed friction to the change made in response, or to a change proposed for the trial.

| Observed in the rehearsal | Evidence | Change |
| --- | --- | --- |
| The specialist scenario's first intake was refused for one missing fact, and adding the fact created a second matter version before any review. | Step B02 refused on `intake_complete`; `pilot-metrics.md`, intake 4 of 5 | Kept. The refusal names the missing fact. Proposed for the trial: show the five required facts on the intake form before submission so that the first attempt is complete. |
| Review could not start because the specialist had not onboarded. | Step B08 refused on `reviewers_available` | Kept as a readiness check. Proposed: onboard every named reviewer before the first matter is opened, and track open onboarding tasks in the weekly report. |
| A playbook rule matched a section heading as well as its clause, so no change was proposed for the roadmap clause in the first run. | First smoke run reported an ambiguous target for `roadmap-commitment` | Made: the rule's clause pattern was narrowed, and an ambiguous match is reported as a coverage gap that blocks approval. |
| The order-summary table in the customer draft was not read by the engine. | Coverage-gap comment on the specialist matter, resolved at step B20 with a manual review note | Made: unread body content is listed as a blocking item with its own evidence requirement. Proposed: decide with the trial team whether tables need engine support or stay a manual check. |
| Two reviewers acted on the same revision. | Step B20: the owner's write landed, the specialist's was refused as stale | Kept. Proposed: measure how often this happens with real reviewers; if it is frequent, show who else has the matter open. |
| The requester's clarification stayed open overnight. | 1,260 scripted minutes from question to answer | No change to the software. Proposed: agree a response time for clarifications in the charter and notify the requester outside the tool. |
| The approver resolved a critical comment and reopened it five minutes later because the evidence covered sixty days, not ninety. | Steps B33 to B36; one reopened issue | Made: a reopened issue counts as correction effort. Proposed: show the evidence reference text beside the resolve control so that the approver reads it before resolving. |
| A changed signature date invalidated the privacy sign-off although the change had no privacy relevance. | Steps B37 to B41; ten scripted minutes of repeated specialist work | Kept for the trial, because a narrower rule is a legal judgement. The policy is isolated in `is_substantive_change` for the legal team to set. |
| The approver tried to approve twice before the matter was ready. | Steps B23, B38 and B40 refused | Made: the review room lists the missing evidence beside each transition. |
| The matter owner saw the approver's authority check evaluated against their own account. | Live inspection of the review room | Made: evidence that depends on who the caller is appears only for that role. |
| The changes table overflowed the page. | Live inspection of the review room | Made: table layout fixed; confirmed by a second inspection. |
| An inserted clause carries no number. | Reviewed document of the specialist matter | Open. Documented as a limit of the supported DOCX subset. |
| Decisions in the review room use browser prompt dialogs. | Live inspection | Open. Adequate for a trial with a facilitator; inline forms are the first interface change to make if the trial continues. |

Delay attribution in the scripted data:

- System: software execution took between 2 and 25 milliseconds per matter in the committed run. No scripted delay is attributable to the system.
- Missing facts and the requester: the incomplete intake and the overnight clarification account for the largest share of the specialist scenario's elapsed time.
- Reviewer availability: the remaining gaps are the scripted waits for the owner, the specialist and the approver.

These proportions are properties of the script. They demonstrate that the report separates the three causes.

## Part B: template for the trial retrospective

Hold it within one week of the end of the pilot window. The pilot lead brings the measurement report and the baseline.

1. **Facts first.** Matters opened, closed, withdrawn, blocked. Any stop condition triggered.
2. **Baseline comparison.** For each measure in `measurement-plan.json`: baseline, pilot, difference, sample sizes. State where a figure is an estimate.
3. **Delay attribution.** Minutes waiting on the requester or missing facts, on each reviewer role, on acceptance. Software execution time. Refused commands by cause.
4. **Each participant, in turn.** What cost you time that the workflow should have saved? What did you approve or sign off without reading in full, and why? Which refusal was wrong?
5. **Playbook quality.** Proposed changes accepted, amended, rejected; rejections caused by a wrong rule or a wrong locator.
6. **Friction to change.** One table in the form used in Part A: observation, evidence, change, owner, date.
7. **Decision.** Continue, change and continue, or stop, against the acceptance criteria in the charter.
