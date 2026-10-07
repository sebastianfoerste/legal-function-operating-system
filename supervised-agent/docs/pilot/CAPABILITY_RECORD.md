# Capability record: executable, static and simulated

Recorded on 6 October 2026 for the supervised agent after the pilot workflow was added. It separates what the code does when called from what is only displayed and from what is a stand-in for a control that does not exist yet.

## Executable functionality

| Capability | Module | How it is exercised |
| --- | --- | --- |
| Typed intake, deterministic findings, controls and reviewer routing | `models.py`, `src/legal_ops.py` | existing tests |
| Source-boundary check on reference prefixes and regulatory domains | `src/source_verification.py` | existing tests |
| Hash-chained audit trail on an assessment | `src/audit_chain.py`, `models.py` | existing tests |
| Single export-eligibility check | `src/export_gate.py` | `tests/test_export_gate.py` |
| Playbook rules that locate a clause and propose a located change | `src/playbook.py` | `tests/test_docx_redline.py` |
| Tracked changes in a defined DOCX subset | `src/docx_redline.py` | `tests/test_docx_redline.py` |
| Persistent store for matters, versions, assignments, comments, findings, changes, decisions, events and deliverable manifests | `src/pilot/store.py` | `tests/test_pilot_workflow.py` |
| State machine with roles and evidence per transition | `src/pilot/state_machine.py`, `src/pilot/service.py` | `tests/test_pilot_workflow.py` |
| Role and assignment checks on every command, refusals logged | `src/pilot/service.py` | `tests/test_pilot_workflow.py`, `tests/test_pilot_api.py` |
| Stale-submission refusal and serialised writes | `src/pilot/service.py`, `src/pilot/store.py` | `test_concurrent_writers_only_one_wins` |
| Versioning, reassessment and invalidation of approvals | `src/pilot/service.py` | `tests/test_pilot_workflow.py` |
| Comments tied to a finding, source span, change or deliverable section, with resolution evidence | `src/pilot/service.py` | `tests/test_pilot_workflow.py` |
| Internal review export and approved delivery package | `src/pilot/deliverable.py` | `tests/test_pilot_workflow.py` |
| Measurement over the event log, on two separate clocks | `src/pilot/metrics.py` | `tests/test_pilot_rehearsal.py` |
| Review room API and page that save through the application layer | `src/pilot/api.py`, `src/pilot/review_room.py`, `runtime_agent/app.py` | `tests/test_pilot_api.py`, live inspection |
| End-to-end rehearsal across process restarts | `src/pilot/cli.py` | `tests/test_pilot_rehearsal.py` |

## Static presentation

| Item | What it is |
| --- | --- |
| `render_review_room` in `src/collaboration_workspace.py` | A read-only HTML snapshot. It used to carry Accept and Reject buttons and a comment box that changed the page and saved nothing. Those controls are removed and the page now says that nothing on it is saved. |
| Trust cockpit Markdown and JSON | A report rendered from one assessment. |
| Architecture and demo images under `docs/` | Illustrations. |
| `SharedReviewRoom` in `src/matter_workspace.py` | A description of intended permissions and audit events. Nothing in that module enforces it. The pilot service enforces the same three role names plus the final approver. |
| `WorkflowAgentLibrary` in `src/matter_workspace.py` | A description of three workflow steps, not a runner. |
| Customer package HTML | A rendered view of stored data. It has no controls. |

## Simulated controls

| Control | What is simulated | What would make it real |
| --- | --- | --- |
| Reviewer identity | The actor is selected by the caller. Roles and assignments are enforced; the person is not verified. | [IDENTITY_CONTROLS.md](IDENTITY_CONTROLS.md), items 1 to 6 |
| Reviewer name on a stateless assessment | A free-text string in `ReviewDecision.reviewer` | The store-backed path already replaces it for delivery packages |
| Source verification | The allowlist check reads the prefix only. The quote check compares text. Neither establishes that a source supports a legal proposition; a reviewer confirms that. | Stays a human judgement; retrieval of real sources would need its own controls |
| `external_action_allowed: false` flags | Constants. No code path sends, files or publishes, so there is nothing for the flag to stop. | Any delivery channel would need its own authorisation gate |
| Pilot participants, matters, documents, timestamps and effort in the scenarios | Synthetic and scripted | Named participants and real observations |
| Playbook positions | Illustrative synthetic positions | A playbook owned and approved by the legal team |

## Duplicated concepts found before building

The pilot adds no second matter model and no second approval model.

| Concept | Where it already existed | What the pilot does |
| --- | --- | --- |
| Matter | `MatterIntake` (agent), request dictionary (parent `rules.decide`) | `PilotIntake` wraps `MatterIntake` and adds the fields the parent rules read. `parent_bridge.parent_request` converts one into the other. |
| Approval | `LegalOpsAssessment.review_state` and `export_allowed`; `DocumentChangeSet.export_allowed`; parent `approval_chain`; parent shared-space approval note | The change-set flag is removed (schema `document.change-set.v2`). Approval of the pilot matter and of its parent assessment happen in one transaction. The required tier comes from the parent `approval_chain`. |
| Routing | agent `route_matter`; parent `rules.decide` | Queue, service levels and approval tier come from the parent. The agent's own routing stays on the assessment and is not used for assignment. |
| Lifecycle | agent `ReviewState`; parent outcome-tower lifecycle; shared contract `review_state` | One explicit pilot state machine, mapped onto the shared contract in `parent_bridge.CONTRACT_REVIEW_STATE` and onto the parent lifecycle in `metrics.to_parent_ledger`. |
| Audit chain | `AuditEvent` chain on the assessment; `TimelineEvent` chain on matter Lists | The matter event log uses the same hash function, `compute_audit_event_hash`, and the same verification result type. |
| Roles | `SharedReviewPermission` roles | Reused as the pilot role names, with the final approver added. |
| Proposed change | `DocumentChange`, `DocumentChangeSet` | One model, now in `src/playbook.py` and re-exported; the pilot stores a subclass with decision metadata. |

## The export inconsistency

Before this work, `decide_change` set `DocumentChangeSet.export_allowed` once every change was decided, and `render_annotated_docx` checked only that flag. A reviewed DOCX could therefore be written while the parent assessment was still `needs_review`. The reproduction is `test_decided_change_set_cannot_export_while_assessment_is_unapproved`. The flag is gone, the parent assessment is a required argument, and the stateless path calls the same gate as the pilot.

## Parent contracts reused

| Parent contract | Use in the pilot |
| --- | --- |
| `rules.decide`: risk, priority, queue, service levels, approval chain, external counsel | Triage, pilot scope, required approval tier |
| `legal-function-os.service-event-ledger.v1` and `outcome_control_tower.build_outcome_control_tower` | The rehearsal exports its scripted events in the ledger schema and runs the parent tower over them. Revision loops have no counterpart in the parent lifecycle and are folded into the working state. |
| `legal-workflow-controls.v1` | Each matter is exported in the shared contract and validated against the schema in `tests/test_pilot_rehearsal.py`. |
