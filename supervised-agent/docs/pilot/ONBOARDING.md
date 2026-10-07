# Onboarding

Each participant completes the tasks for their role before they can be counted as an available reviewer. The task identifiers below are the ones the software checks: `complete_onboarding` refuses until every task of the role is acknowledged, and a matter cannot enter review while an assigned participant has open tasks. The source of truth is `src/pilot/onboarding.py`.

Onboarding takes about 30 minutes per role when done with the synthetic scenarios in [scenarios/](scenarios/).

## Business requester

| Task | What to do |
| --- | --- |
| `req-1` | Read the pilot charter: eligible matters, exclusions and stop conditions. |
| `req-2` | Submit one practice intake with every required fact and the customer draft as DOCX. |
| `req-3` | Confirm with the sponsor which approval tier may accept exceptions for your deals. |
| `req-4` | Know that you answer clarification requests and accept the final package; you do not see internal review comments. |

The five required facts are `counterparty`, `annual_contract_value_eur`, `signature_target_date`, `requested_deviations` and `business_owner`. The signature target date drives every obligation deadline in the final package, so enter it as an ISO date.

## Matter owner

| Task | What to do |
| --- | --- |
| `own-1` | Read the pilot charter and the runbook, including the stop conditions. |
| `own-2` | Walk through triage: parent routing decision, pilot scope, source boundary, decision authority. |
| `own-3` | Practise accept, reject, amend and clarify on a synthetic change, including the source-support confirmation. |
| `own-4` | Practise a revision cycle and a stale-submission reload. |
| `own-5` | Prepare one internal review export and one delivery package and verify the package against the store. |

Rejecting a proposed change keeps the customer's wording. It is how an exception is accepted, so it always needs a reason.

## Specialist reviewer

| Task | What to do |
| --- | --- |
| `spec-1` | Read the playbook rules in your specialty and their fallback positions. |
| `spec-2` | Know that your sign-off is bound to one matter version and lapses when the matter changes. |
| `spec-3` | Practise deciding a specialist change and recording a sign-off note. |

## Final approver

| Task | What to do |
| --- | --- |
| `app-1` | Read the pilot charter and the export eligibility checks. |
| `app-2` | Know that approval is bound to the exact reviewed version and reviewed state. |
| `app-3` | Practise raising a critical comment, requesting a revision and approving. |
| `app-4` | Confirm you will not approve a matter you requested, own or decided changes on. |

## Readiness check

A matter moves from assignment to review only when the readiness check passes. The review room shows the four items with the reason for any failure.

| Item | Passes when |
| --- | --- |
| Complete intake | All five required facts and the instructions are present and the draft can be read as DOCX. |
| Usable sources | Every source reference passes the source boundary with no blocker and no warning. |
| Available reviewers | A matter owner, a final approver at the required tier and a specialist for every specialty the draft triggers are assigned, onboarded and marked available. |
| Agreed decision authority | The authority recorded at intake covers the approval tier the parent approval matrix requires. |

## What every participant should know

- The role selector is a simulation. It records which synthetic participant acted. It does not prove who was at the keyboard.
- Every action is saved with the revision of the matter you loaded. If someone else acted first, your action is refused, the page reloads and you decide again on the current state.
- Three checks appear beside every proposed change and they mean different things. The allowlist check says the reference uses a permitted source prefix. The quote check says the quoted wording is at the stated place in the stated version of the document or playbook. Whether the source supports the wording for this matter is your confirmation, and the software asks for it explicitly.
- Nothing leaves the machine. The delivery package is a local folder.
