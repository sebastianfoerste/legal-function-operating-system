# Identity: what is simulated and what must exist before practitioners rely on it

## What exists today

The pilot models permissions explicitly and enforces them on every command, whether it arrives from the review room, the HTTP API, a scenario script or a direct library call.

| Control | Enforced where |
| --- | --- |
| An action is attributed to a registered actor; an unknown name is refused | `PilotService._actor` |
| Each actor holds one role; each command names the roles that may run it | `state_machine.TRANSITIONS`, `PilotService._require_access` |
| A role grants nothing on its own; the actor must be assigned to that matter in that role | `PilotService._execute`, `_require_access` |
| A matter is invisible to actors who are not assigned to it, apart from the unclaimed triage queue for onboarded matter owners | `PilotService._can_read` |
| Specialist clauses are decided by that specialist, other clauses by the matter owner | `PilotService.decide_change` |
| The final approver holds the tier the parent approval matrix requires and is neither requester nor matter owner, and decided no change | `_ev_approver_authorised` |
| A critical comment is closed only by its author or the final approver | `PilotService.resolve_comment` |
| Refused commands are written to the matter's hash-chained event log | `PilotService._record_refusal` |

The three refusals of a final approval are tested in `tests/test_pilot_workflow.py`: an approver whose tier is below the one required, an approver who is also the requester or the matter owner, and an approver who decided a change. These rules compare actor IDs, not people, so one person who holds two IDs passes them (control 4 below). No HTTP route registers an actor or changes a role or an approval tier (`tests/test_pilot_api.py`). The library call that registers actors replaces an existing actor without writing an event (control 3 below).

## Local hardening (not authentication)

The local server also limits which requests it answers.

| Measure | Where | Test |
| --- | --- | --- |
| It listens only on a loopback address (`127.0.0.1` or `localhost`). Any other `HOST` stops it before it listens, and there is no switch to change that | `runtime_agent/app.py`, `build_server` | `tests/test_runtime_agent.py` |
| It answers only a `Host` header that names this server, against DNS rebinding | `RuntimeHandler._host_allowed` | `tests/test_runtime_agent.py` |
| It refuses a browser request whose `Origin` is not its own (403 `origin_not_allowed`) | `RuntimeHandler._origin_allowed` | `tests/test_runtime_agent.py` |
| It accepts only JSON POSTs, sends no `Access-Control-*` header and leaves a cross-origin preflight unanswered | `RuntimeHandler.do_POST` | `tests/test_runtime_agent.py` |
| No page may frame it, and no other origin may embed its responses | `SECURITY_HEADERS` | `tests/test_runtime_agent.py`, `tests/test_review_room_browser.py` |

These checks decide which requests the local server answers. They do not establish who sends them. Anyone who can use this machine can still act as any role. They satisfy none of the controls below.

## What is simulated

The actor is chosen by the caller. In the review room it is a drop-down; over HTTP it is the `X-Pilot-Actor` header; in a library call it is an argument. Nothing verifies that the person choosing "Synthetic Approver E" is that person. Anyone with access to the machine can act as any participant.

For that reason:

- every page of the review room, every API actor listing and every delivery manifest states that roles are simulated local roles;
- actor identifiers must start with `syn-`, so a real name cannot be registered by accident;
- the approval record in a delivery package names its approvers as simulated local roles;
- the "Also open" presence line in the review room names simulated local roles, says it is not authentication, and is held in server memory only: it is never stored, logged or exported, and requesters are not part of it. The local server leaves presence check-ins out of its request log, which would otherwise record which matter a room had open and when (`RuntimeHandler.log_message`, `tests/test_runtime_agent.py`);
- the charter treats approvals recorded in a trial as evidence of the workflow, with the named participants confirming their own decisions in the retrospective.

A reviewer name passed to the older stateless library (`apply_review_decision`, the `legal.review.decide` tool) is likewise a free-text string. That path can produce an internal reviewed document. It cannot produce a delivery package, because the export gate requires reviewer decisions recorded in the store.

## Controls required before multi-user practitioner operation

None of the following exists. Each is a precondition for use with real matters by several practitioners.

1. **Authentication against the organisation's identity provider.** Sign-in through OIDC or SAML with multi-factor authentication. The server derives the actor from the verified session. The `X-Pilot-Actor` header and the drop-down are removed.
2. **Server-side sessions.** Short-lived, bound to the device, revocable, with re-authentication before an approval.
3. **Role and assignment provisioning by an administrator.** Roles, specialties and approval tiers come from the directory or an administered register, with a second person approving any change to an approval tier. Self-registration of actors is removed.
4. **Person-level separation of duties.** The separation rules are applied to the verified person, so that two accounts held by one person do not satisfy them.
5. **Step-up confirmation for approvals.** A final approval and a specialist sign-off are confirmed with a fresh second factor, and the confirmation is stored with the decision.
6. **Access control on matters with ethical walls.** Per-matter access lists, conflict screens, and a logged reason for any access outside an assignment.
7. **Transport and network.** The server listens on TLS behind the organisation's access proxy. Today it listens on a loopback address without TLS and refuses to start on any other address.
8. **Tamper-resistant audit storage.** The event chain makes alteration detectable. It does not prevent deletion of the whole store. Events are replicated to an append-only store outside the application's control, with a trusted time source.
9. **Encryption and retention.** The SQLite file and the export folder hold documents in clear text. Encryption at rest, backup, retention and deletion rules are needed before any real document is stored.
10. **Administrative access.** Anyone who can write to the SQLite file can alter records. The gate detects altered documents, decisions and events, as the tests show, but direct database access must be restricted and monitored.
11. **Professional-secrecy review.** Before real matters are processed, the firm's own obligations on confidentiality and outsourcing have to be assessed for the deployment. That assessment is outside this repository.

Until items 1 to 6 exist, the system is suitable for a supervised trial with synthetic matters and for walkthroughs. It is not suitable for work product a practitioner relies on.

Owner decision 1 (2026-11-18): none of controls 1 to 11 is built; items 1 to 6 remain the precondition for practitioner use.
