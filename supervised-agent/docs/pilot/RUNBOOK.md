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
| `pilot-metrics.md`, `.json` | The measurement report |
| `parent-outcome-view.json` | The same events read by the parent outcome control tower |
| `shared-control-contract.json` | Each matter in the shared `legal-workflow-controls.v1` contract |
| `exports/` | Internal review exports and delivery packages |

Exit status 0 means every check passed. Do not start a session after a failed rehearsal. A dated run is committed under `examples/pilot/rehearsal-2026-10-06/`.

## 3. Run a session

```bash
python -m src.pilot.cli seed --db .pilot/pilot.sqlite3
python -m src.pilot.cli serve --db .pilot/pilot.sqlite3
```

Open `http://127.0.0.1:18085/pilot`. The store and the export folder live under `.pilot/`, which is ignored by Git. Set `PILOT_EXPORT_ROOT` to write exports elsewhere. The server binds to `127.0.0.1` only; do not expose it.

Each participant selects their synthetic role, completes onboarding ([ONBOARDING.md](ONBOARDING.md)) and enters the minutes spent before each action, so that effort is recorded with the event. A requester opens a synthetic matter from one of the scenario fixtures. The facilitator scripts are in [scenarios/](scenarios/).

## 4. States, transitions and required evidence

| From | To | Command | Roles | Evidence required |
| --- | --- | --- | --- | --- |
| intake | triage | submit_intake | business_requester | intake_complete |
| triage | assignment | complete_triage | matter_owner | assessment_current, sources_usable, pilot_scope_met, decision_authority_agreed |
| assignment | review | start_review | matter_owner | reviewers_available |
| review | revision_requested | request_revision | matter_owner, specialist_reviewer, final_approver | revision_reason_recorded |
| review | approved | approve | final_approver | assessment_current, sources_usable, changes_decided, no_open_blockers, specialist_signoffs_current, approver_authorised |
| revision_requested | revised | submit_revision | matter_owner | revision_addressed |
| revised | review | resume_review | matter_owner, specialist_reviewer, final_approver | assessment_current |
| approved | revision_requested | request_revision | matter_owner, specialist_reviewer, final_approver | revision_reason_recorded |
| approved | ready_for_delivery | prepare_delivery | matter_owner | export_gate_passes |
| ready_for_delivery | revision_requested | request_revision | matter_owner, specialist_reviewer, final_approver | revision_reason_recorded |
| ready_for_delivery | closed | accept_delivery | business_requester | delivery_manifest_current, acceptance_recorded |

Two commands sit outside the table. `amend_matter` changes the document, a fact, the instructions, a routing input, the decision authority or the playbook. If the change is substantive after triage, the matter moves to `revised` from any later state. `withdraw` closes an open matter without delivery and needs a reason.

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
| `approver_authorised` | The approver holds the required tier and is neither the requester nor the matter owner. |
| `export_gate_passes` | The single export-eligibility check passes for a delivery package. |
| `delivery_manifest_current` | A delivery manifest exists for the current version and reviewed state. |
| `acceptance_recorded` | The requester recorded an acceptance note. |
| `withdrawal_reason_recorded` | A reason for closing without delivery is recorded. |

A refused command changes nothing in the matter. It is written to the matter's event chain as `command_refused` with the actor and the reason.

## 5. Versions, approvals and reassessment

A matter version is immutable. It holds the intake, the document bytes, the playbook, the assessment, the parent routing decision, the findings and the proposed changes.

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

## 8. Supported DOCX subset

The tracked-change engine reads and edits body-level paragraphs whose runs contain text, tabs, simple line breaks and page-break markers. It replaces a span, deletes a paragraph or inserts a paragraph after an anchor.

- Each change is located by a hash of the paragraph text; the position is only a tie-breaker. The original text is verified before anything is written.
- It fails with a clear error when the target text has changed, when several identical paragraphs make the target ambiguous, when two changes overlap, or when the paragraph contains hyperlinks, fields, content controls, drawings or existing tracked changes.
- Tables, text boxes, headers, footers and footnotes are not read. Each unread body element becomes a coverage gap that blocks approval until a person records how it was reviewed.
- Only the bytes of an edited paragraph change. Every other byte of the document and every other part of the package is copied unchanged, and the source file is never written to.
- An inserted clause is not numbered.

## 9. Recovery and troubleshooting

| Situation | Action |
| --- | --- |
| The server or the machine stops mid-session | Restart `serve`. Every saved action is in the store; an action in progress was either committed or not written at all. |
| "stale submission" | Reload, read the current state, decide again. |
| A matter will not leave triage | Read the evidence list on the transition. Correct the cause with `amend_matter`, or withdraw the matter. |
| Approval refused after a change | The matter is on a new version. Resume review, obtain the specialist sign-off again, then approve. |
| `prepare_delivery` refused | Open "Export eligibility" in the review room; each failing check names its cause. |
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

Then open one `reviewed-document.docx` in Microsoft Word with tracked changes shown, and one `customer-package.html` in a browser.
