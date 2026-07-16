# Case study: legal-function-operating-system

For the industrial robotics and Robotics-as-a-Service flagship, read
[`RAAS_CASE_STUDY.md`](RAAS_CASE_STUDY.md).

> Running a legal function at scale is an operations problem: consistent triage, enforced approvals, deliberate escalation, and a true board view. Synthetic data only; not legal advice.

## Problem
The operating challenge for a first legal hire or General Counsel is consistency.
Requests arrive from every team, approvals are improvised, external counsel is used
reactively, and the board has no reliable picture of legal load and risk. The
function runs out of an inbox until it breaks.

## Users
A first legal hire, General Counsel, or legal operations lead building the function,
plus the leadership team and board who need a recurring view of legal risk and load.

## Workflow
Each legal request runs through a deterministic pipeline:
**intake -> risk (HIGH/MED/LOW) -> priority (P1 to P4) -> routing (queue) -> SLA -> approval matrix -> external-counsel decision tree -> escalation.**
Requests then roll up into a **board operations pack**: executive summary, board-attention items, SLA breaches, external referrals, and risk/priority/queue breakdowns.

## Controls
Every approval chain ends with a human tier (Reviewer -> Legal Ops Lead -> General
Counsel -> Board note) scaled to value and risk. Escalation rules fire on SLA breach,
high-risk blockers, values above EUR 1 million, and disputes. The rules are short,
readable functions that a lawyer can audit and challenge.

## Evaluation
The bundled demo (`examples/board-pack.md`) turns eight synthetic requests into a
board pack that surfaces three board-attention items, one SLA breach, and three
external-counsel referrals. The test suite covers the general operating layer and
the industrial robotics RaaS deal desk.

## Limitations
Thresholds (value bands, SLA targets, approval tiers) are illustrative defaults to be tuned per business; it operates over a structured representation of requests, not a live intake channel, and is an operations artifact, not legal advice.

## Next steps
Connect intake to Slack/Jira; add real roles/auth for the approval tiers; track SLA timers live; pair with `ai-saas-legal-ops-starter-kit` (playbooks) and `dpa-and-data-transfer-review` (cited DPA checks) as the function's operating core.
