# End-to-end rehearsal report

- Result: **passed**
- Participants: synthetic actors only; no practitioner took part
- Status: ready for a supervised trial

## Checks after the final restart

| Check | Result | Detail |
| --- | --- | --- |
| every scripted step had its expected outcome | pass | 68 steps; failed: none |
| PM-ROUTINE-001: steps ran in more than one process | pass | 2 processes |
| PM-ROUTINE-001: final state | pass | closed (expected closed) |
| PM-ROUTINE-001: final version, earlier versions kept | pass | current v1, 1 stored |
| PM-ROUTINE-001: closing outcome | pass | delivered_locally_and_accepted |
| PM-ROUTINE-001: event chain intact | pass | 12 events, chain intact |
| PM-ROUTINE-001: delivery package count | pass | 1 (expected 1) |
| PM-ROUTINE-001: package is for the approved version and reviewed state | pass | package v1, current v1 |
| PM-ROUTINE-001: package files match the stored manifest | pass | PM-ROUTINE-001/v1/delivery |
| PM-ROUTINE-001: rejecting every tracked change restores the customer draft | pass | 5 tracked changes |
| PM-SPECIALIST-002: steps ran in more than one process | pass | 4 processes |
| PM-SPECIALIST-002: final state | pass | closed (expected closed) |
| PM-SPECIALIST-002: final version, earlier versions kept | pass | current v3, 3 stored |
| PM-SPECIALIST-002: closing outcome | pass | delivered_locally_and_accepted |
| PM-SPECIALIST-002: event chain intact | pass | 43 events, chain intact |
| PM-SPECIALIST-002: delivery package count | pass | 1 (expected 1) |
| PM-SPECIALIST-002: package is for the approved version and reviewed state | pass | package v3, current v3 |
| PM-SPECIALIST-002: package files match the stored manifest | pass | PM-SPECIALIST-002/v3/delivery |
| PM-SPECIALIST-002: rejecting every tracked change restores the customer draft | pass | 12 tracked changes |
| PM-BLOCKED-003: steps ran in more than one process | pass | 2 processes |
| PM-BLOCKED-003: final state | pass | triage (expected triage) |
| PM-BLOCKED-003: final version, earlier versions kept | pass | current v1, 1 stored |
| PM-BLOCKED-003: closing outcome | pass | None |
| PM-BLOCKED-003: event chain intact | pass | 8 events, chain intact |
| PM-BLOCKED-003: delivery package count | pass | 0 (expected 0) |
| PM-BLOCKED-003: blocked matter produced no export of any kind | pass | 0 manifests, 6 refused commands on record |
| PM-BLOCKED-003: no approval was ever recorded | pass | 0 approvals |

## Steps

| Step | Process | Actor | Command | Expected | Outcome | State after | Version |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A01 | 62301 | syn-requester-revops | create_matter | ok | ok | intake | 1 |
| A02 | 62301 | syn-requester-revops | submit_intake | ok | ok | triage | 1 |
| A03 | 62301 | syn-requester-revops | approve | transition_blocked | transition_blocked | triage | 1 |
| A04 | 62301 | syn-owner-legalops | complete_triage | ok | ok | assignment | 1 |
| A05 | 62301 | syn-owner-legalops | assign | ok | ok | assignment | 1 |
| A06 | 62301 | syn-owner-legalops | start_review | ok | ok | review | 1 |
| A07 | 62302 | syn-owner-legalops | prepare_delivery | transition_blocked | transition_blocked | review | 1 |
| A08 | 62302 | syn-owner-legalops | decide_change | ok | ok | review | 1 |
| A09 | 62302 | syn-owner-legalops | decide_change | ok | ok | review | 1 |
| A10 | 62302 | library caller | stateless_delivery_gate | export_blocked | export_blocked | review | 1 |
| A11 | 62302 | syn-approver-lead | approve | ok | ok | approved | 1 |
| A12 | 62302 | syn-owner-legalops | prepare_delivery | ok | ok | ready_for_delivery | 1 |
| A13 | 62302 | syn-requester-revops | accept_delivery | ok | ok | closed | 1 |
| B01 | 62303 | syn-requester-revops | create_matter | ok | ok | intake | 1 |
| B02 | 62303 | syn-requester-revops | submit_intake | transition_blocked | transition_blocked | intake | 1 |
| B03 | 62303 | syn-requester-revops | amend_matter | ok | ok | intake | 2 |
| B04 | 62303 | syn-requester-revops | submit_intake | ok | ok | triage | 2 |
| B05 | 62303 | syn-owner-legalops | complete_triage | ok | ok | assignment | 2 |
| B06 | 62303 | syn-owner-legalops | assign | ok | ok | assignment | 2 |
| B07 | 62303 | syn-owner-legalops | assign | ok | ok | assignment | 2 |
| B08 | 62303 | syn-owner-legalops | start_review | transition_blocked | transition_blocked | assignment | 2 |
| B09 | 62303 | syn-specialist-privacy | onboard | ok | ok | assignment | 2 |
| B10 | 62303 | syn-owner-legalops | start_review | ok | ok | review | 2 |
| B11 | 62304 | syn-owner-legalops | export_internal_review | ok | ok | review | 2 |
| B12 | 62304 | syn-owner-legalops | decide_change | ok | ok | review | 2 |
| B13 | 62304 | syn-owner-legalops | decide_change | ok | ok | review | 2 |
| B14 | 62304 | syn-owner-legalops | decide_change | ok | ok | review | 2 |
| B15 | 62304 | syn-owner-legalops | decide_change | ok | ok | review | 2 |
| B16 | 62304 | syn-owner-legalops | decide_change | ok | ok | review | 2 |
| B17 | 62304 | syn-owner-legalops | decide_change | ok | ok | review | 2 |
| B18 | 62304 | syn-owner-legalops | decide_change | permission_denied | permission_denied | review | 2 |
| B19 | 62304 | syn-specialist-privacy | decide_change | ok | ok | review | 2 |
| B20 | 62304 | syn-owner-legalops | resolve_comment | ok | ok | review | 2 |
| B21 | 62304 | syn-specialist-privacy | comment | ok | ok | review | 2 |
| B22 | 62304 | syn-specialist-privacy | specialist_signoff | ok | ok | review | 2 |
| B23 | 62304 | syn-approver-gc | approve | transition_blocked | transition_blocked | review | 2 |
| B24 | 62305 | syn-requester-revops | respond_comment | ok | ok | review | 2 |
| B25 | 62305 | syn-owner-legalops | resolve_comment | ok | ok | review | 2 |
| B26 | 62305 | syn-owner-legalops | decide_change | ok | ok | review | 2 |
| B27 | 62305 | syn-approver-gc | comment | ok | ok | review | 2 |
| B28 | 62305 | syn-approver-gc | request_revision | ok | ok | revision_requested | 2 |
| B29 | 62305 | syn-owner-legalops | resolve_comment | permission_denied | permission_denied | revision_requested | 2 |
| B30 | 62305 | syn-owner-legalops | respond_comment | ok | ok | revision_requested | 2 |
| B31 | 62305 | syn-owner-legalops | submit_revision | ok | ok | revised | 2 |
| B32 | 62305 | syn-approver-gc | resume_review | ok | ok | review | 2 |
| B33 | 62305 | syn-approver-gc | resolve_comment | ok | ok | review | 2 |
| B34 | 62305 | syn-approver-gc | reopen_comment | ok | ok | review | 2 |
| B35 | 62305 | syn-owner-legalops | respond_comment | ok | ok | review | 2 |
| B36 | 62305 | syn-approver-gc | resolve_comment | ok | ok | review | 2 |
| B37 | 62305 | syn-requester-revops | amend_matter | ok | ok | revised | 3 |
| B38 | 62305 | syn-approver-gc | approve | transition_blocked | transition_blocked | revised | 3 |
| B39 | 62305 | syn-owner-legalops | resume_review | ok | ok | review | 3 |
| B40 | 62305 | syn-approver-gc | approve | transition_blocked | transition_blocked | review | 3 |
| B41 | 62305 | syn-specialist-privacy | specialist_signoff | ok | ok | review | 3 |
| B42 | 62305 | syn-approver-gc | approve | ok | ok | approved | 3 |
| B43 | 62305 | library caller | stateless_delivery_gate | export_blocked | export_blocked | approved | 3 |
| B44 | 62305 | syn-owner-legalops | prepare_delivery | ok | ok | ready_for_delivery | 3 |
| B45 | 62306 | syn-requester-revops | accept_delivery | ok | ok | closed | 3 |
| C01 | 62307 | syn-requester-revops | create_matter | ok | ok | intake | 1 |
| C02 | 62307 | syn-requester-revops | submit_intake | ok | ok | triage | 1 |
| C03 | 62307 | syn-owner-legalops | complete_triage | transition_blocked | transition_blocked | triage | 1 |
| C04 | 62307 | syn-owner-legalops | assign | permission_denied | permission_denied | triage | 1 |
| C05 | 62307 | syn-approver-gc | approve | permission_denied | permission_denied | triage | 1 |
| C06 | 62307 | syn-owner-legalops | export_internal_review | permission_denied | permission_denied | triage | 1 |
| C07 | 62307 | library caller | stateless_delivery_gate | export_blocked | export_blocked | triage | 1 |
| C08 | 62307 | library caller | legacy_docx_render | export_blocked | export_blocked | triage | 1 |
| C09 | 62308 | syn-owner-second | complete_triage | transition_blocked | transition_blocked | triage | 1 |
| C10 | 62308 | syn-requester-revops | prepare_delivery | transition_blocked | transition_blocked | triage | 1 |
