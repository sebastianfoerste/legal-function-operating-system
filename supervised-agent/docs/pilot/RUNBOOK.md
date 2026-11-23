# Pilot runbook

How to run, check and recover the supervised pilot workflow on one machine. All commands run from `supervised-agent/` with the virtual environment active.

## 1. Set up

```bash
python3.13 -m venv .venv && source .venv/bin/activate
make install
pip install "black>=25.0" "mypy>=1.14" "pytest>=8.0" "ruff>=0.9"
```

The pilot imports the parent package for routing and reporting. It must run inside this repository, where `../src/legal_function_os` exists.

## 2. Rehearse before every trial session

```bash
python -m src.pilot.cli rehearse --db /tmp/pilot-rehearsal/pilot.sqlite3 --out /tmp/pilot-rehearsal/out
```

The command refuses to run into an existing store. It seeds the synthetic participants, runs the three scenario scripts and starts a new operating-system process at every restart marker. A last, separate process then checks the stored result and writes:

| File | Content |
| --- | --- |
| `rehearsal-report.md`, `.json` | Each check after the final restart, and every step with its expected and actual outcome |
| `pilot-metrics.md`, `.json` | The measurement report, including playbook override patterns |
| `parent-outcome-view.json` | The same events read by the parent outcome control tower |
| `shared-control-contract.json` | Each matter in the shared `legal-workflow-controls.v1` contract |
| `exports/` | Internal review exports and delivery packages |

Exit status 0 means every check passed. Do not start a session after a failed rehearsal. A dated run is committed under `examples/pilot/rehearsal-2026-10-06/`.

## 3. Run a session

```bash
python -m src.pilot.cli seed --db .pilot/pilot.sqlite3
python -m src.pilot.cli serve --db .pilot/pilot.sqlite3
```

Open `http://127.0.0.1:18085/pilot`. The store and the export folder live under `.pilot/`, which is ignored by Git. Set `PILOT_EXPORT_ROOT` to write exports elsewhere. The server listens only on a loopback address and refuses to start on any other; this is not authentication (see [IDENTITY_CONTROLS.md](IDENTITY_CONTROLS.md)).

Each participant selects their synthetic role, completes onboarding ([ONBOARDING.md](ONBOARDING.md)) and enters the minutes spent before each action, so that effort is recorded with the event. A requester opens a synthetic matter from one of the scenario fixtures. The facilitator scripts are in [scenarios/](scenarios/).

## 4. States, transitions and required evidence

| From | To | Command | Roles | Evidence required |
| --- | --- | --- | --- | --- |
| intake | triage | submit_intake | business_requester | intake_complete |
| triage | assignment | complete_triage | matter_owner | assessment_current, sources_usable, pilot_scope_met, decision_authority_agreed |
| triage | declined | decline | matter_owner | closure_reason_recorded |
| triage | duplicate | mark_duplicate | matter_owner | duplicate_original_visible, closure_reason_recorded |
| assignment | review | start_review | matter_owner | reviewers_available |
| review | revision_requested | request_revision | matter_owner, specialist_reviewer, final_approver | revision_reason_recorded |
| review | approved | approve | final_approver | assessment_current, sources_usable, changes_decided, no_open_blockers, specialist_signoffs_current, approver_authorised |
| revision_requested | revised | submit_revision | matter_owner | revision_addressed |
| revised | review | resume_review | matter_owner, specialist_reviewer, final_approver | assessment_current |
| approved | revision_requested | request_revision | matter_owner, specialist_reviewer, final_approver | revision_reason_recorded |
| approved | ready_for_delivery | prepare_delivery | matter_owner | export_gate_passes |
| ready_for_delivery | revision_requested | request_revision | matter_owner, specialist_reviewer, final_approver | revision_reason_recorded |
| ready_for_delivery | closed | accept_delivery | business_requester | delivery_manifest_current, acceptance_recorded |

`declined` and `duplicate` are final, like `closed`: no command is accepted afterwards. The three triage verbs, `complete_triage`, `decline` and `mark_duplicate`, and `snooze` below, are open to an onboarded matter owner who is not yet on the matter, and each claims it, so the owner can close a matter that cannot leave triage. A decline or a duplicate is also kept in the decision record, bound to the version it closed. The requester sees the reason as the owner wrote it, and the original's matter ID only when they asked for that matter too. The software never proposes a decline, a duplicate or a reason.

Five commands sit outside the table. `amend_matter` changes the document, a fact, the instructions, a routing input, the decision authority or the playbook. If the change is substantive after triage, the matter moves to `revised` from any later state. `withdraw` closes an open matter without delivery and needs a reason of at least 20 visible characters; after triage it is the only way to close a matter without delivery. It cancels every specialist sign-off and final approval on the matter and, in the same step, records a rejected review decision with the reason on the assessment the current version holds, so the version a withdrawal closes keeps no approved or exportable assessment. Earlier versions are history and are not rewritten (section 5): each keeps the assessment it had when a later version replaced it, which still reads approved if the version was approved then, and the approvals given on it are cancelled in the decision record. A package prepared before the withdrawal stays stored, and the room and the package route no longer open it (section 7). `snooze` pauses a matter in triage: the matter owner gives a reason of at least 20 visible characters and either a time (with a time zone, later than now and at most 30 days ahead) or a question of at least 10 visible characters for the requester. The matter stays in triage and a snooze is not a state. The requester sees the reason, and answers the question with `answer_snooze`, in at least 10 visible characters. For these minimums, and for the reasons `decline`, `mark_duplicate` and `withdraw` need, a run of whitespace counts as one character and invisible characters (format characters such as a zero-width space, and the other default-ignorable code points) are not counted; the text is kept as typed, with runs of whitespace collapsed. A clarification question to the requester follows the same rule. The owning matter owner may end a snooze early with `end_snooze`. A triage verb, the answer, `end_snooze` or a withdrawal ends it, and so does its time passing, which writes no event: every reader works it out from the events on the matter's clock. While a snooze runs, the clocks count the time as waiting on the requester. The decision is recorded in the parent repository as `docs/adr/0010-triage-verbs.md`.

| Evidence | Meaning |
| --- | --- |
| `intake_complete` | Every required fact, the instructions and a readable source document are present. |
| `assessment_current` | The assessment was made over the current matter version. |
| `sources_usable` | Every source reference passes the source boundary without a blocker or warning. |
| `pilot_scope_met` | The parent routing decision places the matter inside the pilot charter. |
| `decision_authority_agreed` | The recorded decision authority covers the approval tier the parent approval matrix requires. |
| `reviewers_available` | An onboarded, available matter owner, final approver and every required specialist are assigned, with duties separated. |
| `revision_reason_recorded` | The request names at least one open comment and gives a reason. |
| `revision_addressed` | Every comment named in the revision request has a response from the matter owner. |
| `changes_decided` | Every proposed change on the current version is accepted, rejected or amended. |
| `no_open_blockers` | No critical comment, clarification request or coverage gap is open. |
| `specialist_signoffs_current` | Every required specialist signed off on the current version. |
| `approver_authorised` | The approver holds the required tier, is neither the requester nor the matter owner, and decided none of the changes. |
| `export_gate_passes` | The single export-eligibility check passes for a delivery package. |
| `delivery_manifest_current` | A delivery manifest exists for the current version and reviewed state. |
| `acceptance_recorded` | The requester recorded an acceptance note. |
| `withdrawal_reason_recorded` | A reason for closing without delivery is recorded. |
| `closure_reason_recorded` | A reason of at least 20 visible characters is recorded. The requester sees it. |
| `duplicate_original_visible` | The original is another matter the matter owner can see, and is not itself a duplicate. |

A refused command changes nothing in the matter. It is written to the matter's event chain as `command_refused` with the actor and the reason.

## 5. Versions, approvals and reassessment

A matter version holds the intake, the document bytes, the playbook, the assessment, the parent routing decision, the findings and the proposed changes. Once it exists, most of it never changes: the intake, the document bytes, the playbook, the routing decision, the findings, the clause and wording of each proposed change (the customer's text and the proposal), and the content hash that sign-offs and approvals are bound to, which covers the intake, the playbook and the document. Two things are written to the current version afterwards. `approve`, `request_revision` and `withdraw` record a review decision on its assessment: the review state, the note, whether export is allowed and one event on the assessment's own audit chain. `decide_change` records the decision on a proposed change: the outcome, the reason, any amended wording, who decided and when, and who confirmed the source support; it also clears the mark that a decision was carried from an earlier version. Nothing is written to a version once a later version has replaced it.

- A substantive change creates the next version, reassesses it and invalidates every specialist sign-off and final approval given earlier. The policy that decides what is substantive is one function, `src/pilot/policy.py::is_substantive_change`.
- A change decision carries forward only where the clause, the original wording and the proposed wording are all unchanged. It is marked as carried from the earlier version.
- A comment is never deleted. If its anchor no longer exists it is marked orphaned and, if it was blocking, it keeps blocking until a person resolves it with evidence.
- A sign-off is bound to the version and its content hash. A final approval is also bound to the reviewed-state hash, which covers every change decision and every comment state. A later decision or comment therefore makes the approval stale without any separate step.
- Earlier versions stay readable. `restore_version` copies an earlier version forward as a new version; it never overwrites.

## 6. Conflicting edits

Every command carries the revision the caller loaded. If the stored revision differs, the command is refused with `stale_submission` and the current revision. The review room reloads the matter and says the input was not saved. Writes take the database lock from their first statement, so two processes cannot both pass the revision check.

## 7. Exports

There is one eligibility check, `src/export_gate.py::evaluate_export_eligibility`. It evaluates eleven conditions and reports each one.

| Export | Where | Requires |
| --- | --- | --- |
| Internal review export | `exports/<matter>/v<n>/internal-review/` | An assessment bound to the version, a clean source boundary, a matching document digest and an intact chain. Marked as a draft in every file. |
| Delivery package | `exports/<matter>/v<n>/delivery/` | Every condition: approved parent assessment, no blocker finding, all changes decided, no open blocker, every required reviewer decision bound to the version, intact chains, state `approved`. |
| Stateless reviewed DOCX (`render_annotated_docx`) | caller's path | The same gate without store checks. It never yields a delivery package. |

A delivery package contains `customer-package.md`, `customer-package.html`, `reviewed-document.docx`, `issue-list.json` and `manifest.json`. The manifest is also stored in the database. A folder without a matching stored manifest is not an approved package. Sending, filing and publication are not implemented.

A stored manifest alone does not open a package either. The review room and `GET /pilot/api/matters/{id}/package` offer the package only while its delivery stands: while the matter is `ready_for_delivery` and the evidence `delivery_manifest_current` passes, and after the requester accepted that delivery (`closed` with `delivered_locally_and_accepted`). A withdrawal, a revision request, an amendment or restore that makes a new version, a comment written, resolved or reopened after the package was prepared (any change to the state of a comment), and the assignment of another final approver in place of the one who approved each end it. An answer to a comment changes no comment's state and ends nothing. The room then shows a sentence in place of the link, for example "The package prepared earlier is no longer approved: the matter was withdrawn without delivery.", and the route refuses with the same sentence. The service decides this in one place and reports it in the matter view as `package`, so the room and the route cannot disagree. The requester's status goes by the same answer. A matter that stays `ready_for_delivery` after its delivery ended, because a comment was written, resolved or reopened after the package was prepared or because another final approver was assigned, is shown to its requester as "In review", not as "Ready for you". The explanation reads "The package prepared earlier is no longer approved, because the matter changed after it was prepared. Legal has to review the matter again before a package is ready for you.", the next step is "No action needed from you." unless a question to the requester is open, and the room offers no "Accept delivery" button. The state itself does not change, and from there a reviewer requests a revision, because `approve` and `prepare_delivery` are not open from that state. A reviewer's matter list still shows the pilot state, `ready for delivery`. The requester's matter list shows the label of their status instead, here "In review", so the list and the status say the same in every state. The requester's view (`GET /pilot/api/matters/{id}`) lists as `delivery` only the manifest of the package that may be opened now: one manifest while a delivery stands and after it was accepted, and none once the delivery has ended. A reviewer's view keeps every stored manifest under `manifests`. If the reviewed state the approval was given on comes back, the delivery stands again and the status reads "Ready for you" again. That happens when a comment is put back into the state it had when the package was prepared (a reopened comment is resolved again, or a resolved one is reopened) or when the earlier approver is assigned again. A comment written after the package was prepared cannot be taken back: resolving it does not restore the delivery. Ending a delivery deletes and rewrites nothing: the manifest stays in the store and the files stay in `exports/` for the audit trail. A new package opens after a new final approval and a new `prepare_delivery`. If that is for the same version, it writes its files into the same folder, in place of the earlier ones, and the earlier manifest stays in the store.

`customer-package.html` uses the shared colour tokens, with dark mode on screen and a stacked table layout on a phone. It always prints in the light palette: each numbered section starts a new page, table headers repeat, and the synthetic-data notice and the page number print at the foot of every page. The page footer was checked in Chromium only. The packages in the dated rehearsal of 2026-10-06 were written before this and keep the older look.

## 8. Supported DOCX subset

The tracked-change engine reads and edits body-level paragraphs whose runs contain text, tabs, simple line breaks and page-break markers. It replaces a span, deletes a paragraph or inserts a paragraph after an anchor.

- Each change is located by a hash of the paragraph text; the position is only a tie-breaker. The original text is verified before anything is written.
- It fails with a clear error when the target text has changed, when several identical paragraphs make the target ambiguous, when two changes overlap, or when the paragraph contains hyperlinks, fields, content controls, drawings or existing tracked changes.
- Tables, text boxes, headers, footers and footnotes are not read. Each unread body element becomes a coverage gap that blocks approval until a person records how it was reviewed.
- Only the bytes of an edited paragraph change. Every other byte of the document and every other part of the package is copied unchanged, and the source file is never written to.
- An inserted clause is not numbered.

Each change is a Word tracked change (`w:ins` or `w:del`, deleted text as `w:delText`) with its own author and date:

- In a delivery package the author is "Simulated local role: <display name> (<actor ID>)", the role that recorded the decision, and the date is when that decision was recorded, to the second (UTC). A decision carried forward to a new version keeps its role and time.
- In an internal review draft every author starts "DRAFT, not approved.". A change nobody has decided yet, including one waiting for clarification, reads "Playbook proposal, no reviewer decision yet" and is dated when the matter version was recorded.
- A change decided as "rejected" writes no tracked change. The customer's wording stays, and the reason is in the issue list and section 4 of the package.
- The dates are recorded times, not the export time, so exporting the same version again gives the same document.
- The stateless `render_annotated_docx` has no recorded reviewer. It labels every change "Legal reviewer (not authenticated)", dated from `SOURCE_DATE_EPOCH`.
- In Word, "Accept all" gives the reviewed wording and "Reject all" gives the customer draft. Accepting a tracked change in Word is a different step from "accepted" in the pilot, which means the reviewer took the playbook proposal.
- The names are simulated local roles, not authenticated identities. Selecting an actor is not authentication.
- Tables, Word comments and `w:trackRevisions` are not written. The rehearsal of 2026-10-06 in `examples/pilot/rehearsal-2026-10-06/` predates these labels: each of its documents carries one label and the export time on every change.

## 9. Recovery and troubleshooting

| Situation | Action |
| --- | --- |
| The server or the machine stops mid-session | Restart `serve`. Every saved action is in the store; an action in progress was either committed or not written at all. |
| "stale submission" | Reload, read the current state, decide again. |
| A matter will not leave triage | Read the evidence list on the transition. Correct the cause with `amend_matter`. If it cannot be corrected, the matter owner may decline it with a reason, or the requester may withdraw it. |
| Approval refused after a change | The matter is on a new version. Resume review, obtain the specialist sign-off again, then approve. |
| `prepare_delivery` refused | Open "Export eligibility" in the review room; each failing check names its cause. |
| The room shows "The package prepared earlier is no longer approved" where the link was | The delivery ended after the package was prepared (section 7). If the matter is still open, complete the review, obtain a new final approval and run `prepare_delivery` again. A matter that is still `ready_for_delivery` shows its requester "In review" until then, in the status and in their matter list; a reviewer starts with `request_revision`. A withdrawn matter stays closed. |
| Event chain fails verification | Stop condition. Preserve the store file, do not continue, inform the pilot lead. |
| The store must be inspected | It is one SQLite file. Open it read-only. Do not edit it: the gate detects altered documents, decisions and events and will refuse exports. |
| Back-up | Copy the store file and the export folder together while the server is stopped. |

## 10. Verification before a release of the pilot code

```bash
python -m pytest -q
make check
make -C .. check
python -m src.pilot.cli rehearse --db /tmp/pilot-rehearsal/pilot.sqlite3 --out /tmp/pilot-rehearsal/out
```

Then open one `reviewed-document.docx` in Microsoft Word with tracked changes shown, check that each change names its simulated local role and decision time, and open one `customer-package.html` in a browser and in its print preview.
