# Case study — legal-function-operating-system

> Running a legal function at scale is an operations problem: consistent triage, enforced approvals, deliberate escalation, and a true board view. Synthetic data only; not legal advice.

## Problem
A first legal hire or GC at a scaling company does not fail on legal knowledge — they fail on operations. Requests arrive from every team, get handled inconsistently, approvals are improvised, external counsel is used reactively, and the board has no reliable picture of legal load and risk. The function runs out of an inbox until it breaks.

## Users
A first legal hire, GC, or legal ops lead building the function — and the leadership/board who need a clear, recurring view of legal risk and load.

## Workflow
Each legal request runs through a deterministic pipeline:
**intake → risk (HIGH/MED/LOW) → priority (P1–P4) → routing (queue) → SLA → approval matrix → external-counsel decision tree → escalation.**
Requests then roll up into a **board operations pack**: executive summary, board-attention items, SLA breaches, external referrals, and risk/priority/queue breakdowns.

## Controls
Every approval chain ends with a human tier (Reviewer → Legal Ops Lead → GC → Board note) scaled to value and risk. Escalation rules fire on SLA breach, high-risk blockers, >€1m, and disputes. The rules are short, readable functions — a lawyer can audit and disagree with each one.

## Evaluation
The bundled demo (`examples/board-pack.md`) turns eight synthetic requests into a board pack that automatically surfaces the three board-attention items (two >€1m deals, one large dispute), the one SLA breach, and three external-counsel referrals — and 17 deterministic tests assert the routing, approval tiers, escalation, and board roll-up.

## Limitations
Thresholds (value bands, SLA targets, approval tiers) are illustrative defaults to be tuned per business; it operates over a structured representation of requests, not a live intake channel, and is an operations artifact, not legal advice.

## Next steps
Connect intake to Slack/Jira; add real roles/auth for the approval tiers; track SLA timers live; pair with `ai-saas-legal-ops-starter-kit` (playbooks) and `dpa-and-data-transfer-review` (cited DPA checks) as the function's operating core.
