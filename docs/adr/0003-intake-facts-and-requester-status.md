# 0003. Required facts and requester status are derived views, not new state

- Status: Accepted
- Date: 2026-10-20

## Context

The pilot rehearsal (`supervised-agent/docs/pilot/RETROSPECTIVE.md`, step B02) refused
the specialist matter's first intake for one missing fact. Adding the fact created a
second version before any review. The retrospective proposed showing the five
required facts before submission. Requesters also saw the raw pilot state name
(`revision_requested`, `assignment`), which is internal vocabulary.

Peers handle this in different ways:

- docassemble treats fields as required by default and asks for any missing variable
  next (Observed in its source).
- claude-for-legal's Matter Intake will not write the matter while the conflicts check
  is not run (Observed).
- Plane and Linear give requesters a short status vocabulary (Observed and Claimed).

None of that requires another state machine.

## Decision

- `required_fact_checklist()` in `src/pilot/models.py` is the only blank test for
  required facts. The `intake_complete` gate, the matter view and the scenario list
  all use it, so the form and the gate cannot disagree.
- When a matter is opened from a synthetic scenario, the API accepts `facts`, limited
  to the five required-fact names with text values, and merges them into the
  scenario's intake before version 1 exists. Everything else still comes from the
  fixture. The `intake_complete` gate is unchanged and still refuses an incomplete
  intake.
- `src/pilot/requester_status.py` maps the nine pilot states to six requester stages.
  The mapping is a pure function of the state, the closed outcome and the number of
  open questions addressed to the requester. It adds no state, clock, permission or
  event, so `parent_bridge.CONTRACT_REVIEW_STATE` and the shared
  `legal-workflow-controls.v1` contract are unchanged.
- The requester payload never carries risk, queue, approval tier, playbook positions
  or internal comments. A test checks that the fallback wording shown to reviewers is
  absent from the requester view.

## Consequences

- A requester who uses the form submits a complete version 1; the rehearsal's B02
  path still works for scripts that skip the form.
- A future requester-facing surface, such as the core shared space, can reuse the
  stage list without importing the pilot.
- German labels for the stages are not added yet; the core shared space already
  writes German requester actions, and aligning the two is listed in the plan.
