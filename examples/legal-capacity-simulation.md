# Legal Function Capacity Simulation

Capacity points and slots are illustrative management assumptions over synthetic requests. They are planning inputs, not time estimates or legal advice.

## Current operating model

**Status: CONSTRAINED**

| Queue | Requests | Demand | Capacity | Backlog | Utilization |
| --- | ---: | ---: | ---: | ---: | ---: |
| Commercial | 3 | 14 | 8 | 6 | 175.0% |
| Corporate / GC | 1 | 10 | 6 | 4 | 166.7% |
| Employment | 1 | 3 | 4 | 0 | 75.0% |
| Legal Ops (AI) | 0 | 0 | 5 | 0 | 0.0% |
| Litigation | 1 | 13 | 5 | 8 | 260.0% |
| Privacy | 2 | 17 | 8 | 9 | 212.5% |

- GC approval demand/capacity: 5/3
- External-counsel coordination demand/capacity: 3/2

### Priority review queue

| ID | Priority | Risk | Queue | Work points |
| --- | --- | --- | --- | ---: |
| REQ-1007 | P1_blocker | HIGH | Litigation | 13 |
| REQ-1005 | P2_high | HIGH | Corporate / GC | 10 |
| REQ-1001 | P2_high | HIGH | Commercial | 9 |
| REQ-1004 | P2_high | HIGH | Privacy | 9 |
| REQ-1002 | P2_high | HIGH | Privacy | 8 |
| REQ-1006 | P3_standard | MEDIUM | Commercial | 4 |
| REQ-1008 | P3_standard | MEDIUM | Employment | 3 |
| REQ-1003 | P4_low | LOW | Commercial | 1 |

## Protected focus and specialist model

**Status: WITHIN_ASSUMPTIONS**

| Queue | Requests | Demand | Capacity | Backlog | Utilization |
| --- | ---: | ---: | ---: | ---: | ---: |
| Commercial | 3 | 14 | 14 | 0 | 100.0% |
| Corporate / GC | 1 | 10 | 12 | 0 | 83.3% |
| Employment | 1 | 3 | 6 | 0 | 50.0% |
| Legal Ops (AI) | 0 | 0 | 10 | 0 | 0.0% |
| Litigation | 1 | 13 | 14 | 0 | 92.9% |
| Privacy | 2 | 17 | 17 | 0 | 100.0% |

- GC approval demand/capacity: 5/6
- External-counsel coordination demand/capacity: 3/4

### Priority review queue

| ID | Priority | Risk | Queue | Work points |
| --- | --- | --- | --- | ---: |
| REQ-1007 | P1_blocker | HIGH | Litigation | 13 |
| REQ-1005 | P2_high | HIGH | Corporate / GC | 10 |
| REQ-1001 | P2_high | HIGH | Commercial | 9 |
| REQ-1004 | P2_high | HIGH | Privacy | 9 |
| REQ-1002 | P2_high | HIGH | Privacy | 8 |
| REQ-1006 | P3_standard | MEDIUM | Commercial | 4 |
| REQ-1008 | P3_standard | MEDIUM | Employment | 3 |
| REQ-1003 | P4_low | LOW | Commercial | 1 |

## Review gate

A human owner must validate effort assumptions, staffing availability, approval capacity, and any external-counsel instruction.

No staffing change, instruction, approval, or external communication is executed.
