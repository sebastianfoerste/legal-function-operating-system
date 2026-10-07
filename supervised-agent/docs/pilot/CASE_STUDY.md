# Case study: owning a contract-deviation review from intake to delivery

Synthetic data throughout. No practitioner has taken part. Not legal advice.

## The problem

A SaaS supplier's legal team receives its own master subscription agreement back from a customer with changes. The supervised agent in this repository could already assess such a request, check source references and gate an export behind a human approval. It could not carry the matter: nothing was stored, the review room saved nothing, and reviewer names were free text.

It also had a defect at the point that matters most. A change set became exportable as soon as every proposed change had a decision, and the function that wrote the reviewed DOCX looked only at that flag. A reviewed document could be produced while the assessment it belonged to was still waiting for review.

## What was built

One narrowly scoped pilot workflow for customer drafts of the SaaS agreement, covering onboarding, assignment, review, revision, escalation and a final package for the requesting team.

- **One gate.** Every reviewed document and every delivery package passes a single eligibility check over the matter version, the parent assessment, the document digest, the change decisions, open blockers, the required reviewer decisions and the audit chains. The older stateless path calls the same check and can no longer skip the assessment.
- **Approvals bound to what was reviewed.** A sign-off is tied to one matter version. A final approval is also tied to the reviewed state, which covers every change decision and comment. Changing the document, a fact, the instructions or the playbook creates a new version, reassesses it and invalidates earlier approvals.
- **A durable record.** A single SQLite file holds matters, versions, assignments, comments, findings, changes, decisions, events and deliverable manifests. Each command carries the revision the caller saw; a stale command is refused. Earlier versions stay readable.
- **Document-specific changes.** Playbook rules locate a clause by a hash of its text, verify the original wording and write tracked changes into that paragraph only. The engine refuses ambiguous and unsupported targets and reports content it did not read.
- **Explicit roles.** Each command names the roles that may run it and requires assignment to the matter. Refusals are written to the matter's hash-chained event log. Identity itself is simulated and labelled as such.
- **A usable package.** Executive summary, issue and deviation list, reviewed document, accepted exceptions, outstanding obligations with owners and deadlines, and the approval record. Internal review drafts are a separate, marked export.
- **Reuse of the parent system.** Queue, service levels and the approval tier come from the parent rules. Pilot events are exported in the parent's ledger schema and read by its outcome control tower. Control state is exported in the shared contract.

## What the rehearsal shows

The end-to-end rehearsal runs three scripted scenarios with synthetic participants and starts a new process at every restart marker. The committed run of 6 October 2026 is in `examples/pilot/rehearsal-2026-10-06/`.

| Claim | Support |
| --- | --- |
| The workflow survives restarts | 68 scripted steps across eight scenario processes; 27 checks made by a further process after the last restart, all passed (`rehearsal-report.md`) |
| A matter goes through a revision | Scenario 2: revision requested, addressed, an issue reopened and closed, three matter versions, final approval on version 3 |
| A stale approval is refused | Scenario 2, steps B38 and B40; `test_fact_change_invalidates_signoff_and_blocks_stale_approval` |
| The blocked matter stays blocked | Scenario 3 ends in triage with no export and no approval; `test_no_actor_and_no_command_moves_the_blocked_matter` tries 17 commands as each of six actors |
| Only the approved version is exported | Each delivery manifest matches a valid final approval on the same version and reviewed state; the specialist matter has a package for version 3 only |
| The gate holds when the screen sequence is bypassed | Direct API, service and library calls in `tests/test_pilot_api.py`, `tests/test_pilot_workflow.py` and `tests/test_export_gate.py`; records altered directly in the database are detected |
| The reviewed document is faithful to the source | Rejecting every tracked change reproduces the customer draft paragraph for paragraph; bytes outside edited paragraphs are unchanged (`tests/test_docx_redline.py`) |
| The original inconsistency is fixed | `test_decided_change_set_cannot_export_while_assessment_is_unapproved` |

The reviewed documents were read back by two independent DOCX readers, pandoc and Apple's text importer, and the review room and a rendered customer package were inspected in a browser against a running server.

## What it does not show

- **No outcome.** Times and effort in the rehearsal are scripted. They demonstrate that the measures compute and that delay is attributed separately to the requester, to each reviewer role and to the software. They support no statement about time saved. The baseline has not been collected.
- **No identity.** Roles and assignments are enforced, but the person is not verified. The controls required before practitioners rely on the system are listed in [IDENTITY_CONTROLS.md](IDENTITY_CONTROLS.md).
- **No legal validation.** The playbook positions are illustrative. Whether a source supports a proposed wording is confirmed by a reviewer; software checks only that a reference is permitted and that a quotation is where it is said to be.
- **A narrow document subset.** Body paragraphs with simple runs. Tables, fields and content controls are reported and left to a person.
- **No delivery.** The package is a local folder. Sending, filing and publication are not implemented.

## Status and remaining human validation

Ready for a supervised trial. Before any wider claim:

1. Name the sponsor, requester, matter owner, specialist and final approver, and have each complete onboarding.
2. Have the legal team review and approve the playbook rules and fallback positions.
3. Collect the baseline with the method in `examples/pilot/measurement-plan.json`.
4. Run the three scenarios with the named participants, then eligible matters within the charter, on synthetic or expressly approved material only.
5. Open reviewed documents in Microsoft Word and confirm the tracked changes read as intended.
6. Hold the retrospective in [RETROSPECTIVE.md](RETROSPECTIVE.md), Part B, and decide against the acceptance criteria in the charter.
7. Put the identity controls in place before any use with real matters.
