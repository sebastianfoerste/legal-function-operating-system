# Pilot charter: supervised review of SaaS contract deviations

Status: ready for a supervised trial. Every participant, matter and document used so far is synthetic. No practitioner has taken part and nothing has been delivered outside the local machine.

## User and business problem

The user is the in-house commercial legal team of a SaaS supplier. Its customers return the supplier's standard master subscription agreement with their own changes. Each returned draft has to be compared with the supplier's playbook, the deviations decided, the exceptions approved at the right level and the result handed back to the requesting sales team.

Today that work has four recurring weaknesses, which the pilot tests one by one:

1. Requests arrive incomplete, and the missing fact is discovered after review has started.
2. A reviewer's decision on a clause is not tied to the version of the draft it was made on.
3. An approval given on one version is carried silently onto a later one.
4. The package returned to the business does not say who owns the follow-up obligations or by when.

The pilot answers one question: can a small team run this review through a recorded workflow in which an approval only ever covers the exact version that was reviewed, without the workflow costing more reviewer time than it saves? The second half of that question cannot be answered from synthetic data.

## Scope

One workflow: a customer's marked-up draft of the supplier's SaaS master subscription agreement, reviewed against `synthetic:saas-msa-deviation-playbook` version 1.

### Eligible matters

A matter is eligible when all of the following hold. The software checks each condition at triage; the first four come from the parent operating system's rules.

| Condition | Checked by |
| --- | --- |
| Request type is a commercial contract | intake model |
| Contract value is at most EUR 1m | `pilot_scope_met` |
| The parent rules keep the matter in-house | `pilot_scope_met` |
| No uncapped liability is requested, and no personal data leaves the EEA | `pilot_scope_met` |
| Every source reference passes the source boundary without blocker or warning | `sources_usable` |
| The draft is a DOCX file within the supported subset | `intake_complete`, coverage gaps |
| The five required facts and the requester's instructions are present | `intake_complete` |
| The recorded decision authority covers the approval tier the parent approval matrix requires | `decision_authority_agreed` |

### Exclusions

- Contract value above EUR 1m, or any matter the parent approval matrix sends to the board.
- A request for uncapped supplier liability.
- A transfer of personal data outside the EEA.
- Any matter the parent rules refer to external counsel.
- Disputes, employment, corporate and regulatory matters.
- Any client, candidate, privileged or confidential source material. Those source prefixes stop document processing.
- Drafts whose relevant clauses sit in tables, text boxes, headers, footnotes or content controls, unless a person records how that content was reviewed.

An excluded matter stays in triage. It can be withdrawn, or corrected by a new version that removes the cause.

## Roles and responsibilities

The role names are those of the existing shared review room. For the trial each role needs a named person; the synthetic stand-ins are listed in `src/pilot/onboarding.py`.

| Role | Person in the trial | Responsible for |
| --- | --- | --- |
| Sponsor | to be named, General Counsel level | Agreeing scope, decision authority and stop conditions; deciding at the end whether to continue |
| Business requester | to be named, Revenue Operations | Complete intake; answering clarifications; accepting the package |
| Matter owner | to be named, Commercial Counsel | Triage; assigning reviewers; deciding non-specialist changes; revisions; preparing exports |
| Specialist reviewer | to be named, Privacy Counsel | Deciding changes in the specialty; a sign-off bound to one version |
| Final approver | to be named, at the tier the parent matrix requires | Approval of one exact version and reviewed state; requesting revisions |
| Pilot lead | to be named, Legal Operations | Onboarding, the baseline, the weekly measurement report, the retrospective |

Separation of duties: the final approver is neither the requester nor the matter owner of the same matter and has decided none of its changes. A critical comment can be closed only by its author or by the final approver.

## Decision authority

The approval tier is the highest human tier in the parent approval chain for the matter (`Reviewer`, `Legal Ops Lead` or `General Counsel`). The sponsor agrees in advance which tier may accept exceptions for which deals, and the requester records that tier at intake. A matter whose recorded authority is lower than the required tier does not leave triage.

## Baseline and measurement

The baseline method, the baseline window, the pilot window and the definition of every measure are fixed in `examples/pilot/measurement-plan.json` before any result is read. In summary:

- Baseline: a retrospective sample of the last 15 closed deviation requests handled without the workflow, covering the eight weeks before the first pilot matter.
- Pilot window: six weeks or 20 closed matters, whichever comes first. The first week is reported separately.
- Measures: intake completeness, time to assignment, waiting time by cause, review effort, correction effort, revision count, reopened issues and total time to an accepted deliverable. Software execution time is reported separately from human effort.

No comparison is drawn until the baseline has been collected with that method. The figures in the rehearsal are scripted and are not pilot results.

## Acceptance criteria

The pilot is accepted as a basis for continued use if, at the end of the pilot window, all of the following are true.

1. No delivery package was written for a version other than the approved one. The rehearsal check for this runs against the real store.
2. Every closed matter has an intact event chain, and every approval in it is bound to the delivered version.
3. At least 15 eligible matters were closed through the workflow by the named participants.
4. Median elapsed time to an accepted deliverable is no worse than the baseline, and median reviewer effort is no more than 10% above it.
5. Reviewers rejected or amended fewer than one in three proposed changes for a reason that points to a wrong playbook rule or a wrong locator.
6. Each participant confirms in the retrospective that they would use the workflow for the next matter, or states what would have to change.

Criteria 1 and 2 are tested by software today. Criteria 3 to 6 need real participants. The thresholds in criteria 3 to 5 are proposals for the sponsor to confirm before the trial starts.

## Stop conditions

The pilot lead stops intake immediately, and the sponsor decides whether to resume, if any of the following occurs.

- A delivery package or reviewed document is produced that does not match the approved version, or the export gate passes when one of its conditions was not met.
- An event chain fails verification.
- Real client, candidate, privileged or confidential material is found in the store.
- A tracked change is applied at the wrong place in a document, or a reviewed document does not return to the source text when every tracked change is rejected.
- Two reviewers independently report that the workflow led them to approve something they had not read.
- The workflow is used for a matter outside this charter.

## What the pilot does not do

It gives no legal advice. It sends, files and publishes nothing. It does not authenticate anyone: the roles are simulated local selections, and the controls needed before practitioners rely on it are listed in [IDENTITY_CONTROLS.md](IDENTITY_CONTROLS.md).
