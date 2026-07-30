# Legal Function Outcome Control Tower

**Observed at: 2026-07-17T16:00:00+00:00**

## Executive outcome

- Requests: 8
- Completed: 6
- Open: 2
- Stalled: 2
- Response SLA attainment: 87.5%
- Resolution SLA attainment: 66.7%
- Binding queue: Commercial

## Queue calibration

| Queue | Requests | Open | Stalled | Planned points | Observed minutes | Minutes per point |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Commercial | 3 | 1 | 1 | 14 | 645 | 46.07 |
| Corporate / GC | 1 | 0 | 0 | 10 | 365 | 36.50 |
| Employment | 1 | 0 | 0 | 3 | 115 | 38.33 |
| Litigation | 1 | 0 | 0 | 13 | 340 | 26.15 |
| Privacy | 2 | 1 | 1 | 17 | 465 | 27.35 |

## Value proxies

All monetary figures are assumption-based management proxies over synthetic effort records. They are not realised savings or accounting conclusions.

- Estimated internal cost: EUR 5750.42
- Estimated labour-efficiency value: EUR 3673.33
- Estimated external-spend avoidance: EUR 5005.00

## Stalled action queue

- `REQ-1002` (Privacy, waiting_on_business, 35.00h): Confirm the next business input and owner.
- `REQ-1001` (Commercial, work_started, 26.00h): Review ownership, priority, and the next controlled step.

## Request outcomes

| Request | Queue | State | Gross h | Business wait h | Legal-controlled h | Response SLA | Resolution SLA |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| REQ-1001 | Commercial | work_started | 81.00 | 5.00 | 76.00 | met | open |
| REQ-1002 | Privacy | waiting_on_business | 45.00 | 35.00 | 10.00 | met | open |
| REQ-1003 | Commercial | completed | 3.00 | 0.00 | 3.00 | met | met |
| REQ-1004 | Privacy | completed | 22.00 | 0.00 | 22.00 | met | met |
| REQ-1005 | Corporate / GC | completed | 34.50 | 0.00 | 34.50 | met | breached |
| REQ-1006 | Commercial | completed | 5.00 | 0.00 | 5.00 | met | met |
| REQ-1007 | Litigation | completed | 36.00 | 0.00 | 36.00 | breached | breached |
| REQ-1008 | Employment | completed | 7.00 | 0.00 | 7.00 | met | met |

## Review gate

A human legal-operations owner must validate event completeness, calendar settings, effort records, value assumptions, and every staffing or external-counsel decision.
