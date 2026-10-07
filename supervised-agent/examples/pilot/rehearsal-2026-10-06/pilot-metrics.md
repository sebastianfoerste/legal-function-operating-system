# Pilot measurement report

- Data basis: `synthetic_scripted_rehearsal`
- Interpretation: Scripted timestamps and declared effort demonstrate that the measures compute. They are not pilot outcomes and support no claim about time saved.
- Baseline: not_collected (Retrospective sample of the last 15 closed SaaS contract-deviation requests handled without the workflow, reconstructed from request and reply timestamps and the reviewers' time records. Where time records are missing, the reviewer estimates effort within one week of closing and the figure is marked as an estimate.)
- Baseline window: The eight weeks before the first pilot matter is opened.
- Pilot window: Six weeks from the first pilot matter, or 20 closed matters, whichever comes first. The first week is a settling week and is reported separately.
- Baseline comparison: not performed: no baseline has been collected

## Scripted human time per matter

| Matter | State | Intake complete | Assignment (min) | Review effort | Correction effort | Revisions | Reopened | To accepted deliverable (min) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PM-ROUTINE-001 | closed | 5/5 | 75.0 | 73 | 0 | 0 | 0 | 450.0 |
| PM-SPECIALIST-002 | closed | 4/5 | 125.0 | 210 | 45 | 1 | 1 | 2910.0 |
| PM-BLOCKED-003 | triage | 5/5 | None | 0 | 0 | 0 | 0 | None |

## Where the elapsed time went (scripted minutes)

| Matter | Requester or missing facts | Matter owner | Specialist | Approver | Requester acceptance | Clarification open, ask to answer |
| --- | --- | --- | --- | --- | --- | --- |
| PM-ROUTINE-001 | 5.0 | 135.0 | 0.0 | 230.0 | 80.0 | 0.0 |
| PM-SPECIALIST-002 | 1205.0 | 315.0 | 120.0 | 170.0 | 1100.0 | 1260.0 |
| PM-BLOCKED-003 | 5.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## Software execution (operational, measured)

| Matter | Software execution (ms) | Refused commands | Event chain verified |
| --- | --- | --- | --- |
| PM-ROUTINE-001 | 7.1 | 2 | True |
| PM-SPECIALIST-002 | 18.4 | 7 | True |
| PM-BLOCKED-003 | 2.7 | 6 | True |

Software execution time is measured on the machine that ran the rehearsal. Human effort is declared per step in the scenario scripts. The two are reported separately because one does not predict the other.
