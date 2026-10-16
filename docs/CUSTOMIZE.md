# Make the rules your own

The value bands, queues, service levels and approval thresholds are not Python
constants any more. They live in a policy file, a small JSON document that a
legal-ops lead can read, change and keep under version control:

- `legal-function-os init` writes one from a short interview.
- `--policy policy.json` applies it to every command that reads requests.

Without `--policy`, the bundled default policy applies
([`src/legal_function_os/data/default_policy.json`](../src/legal_function_os/data/default_policy.json)).
It holds exactly the values the rules shipped with. Those values are illustrative
guardrails for synthetic requests, not a recommendation. The thresholds you set
are your legal team's judgement.

## In five minutes

```bash
legal-function-os init                                     # answer the questions, writes policy.json
legal-function-os validate --policy policy.json --input requests.csv
legal-function-os triage --policy policy.json --input requests.csv
legal-function-os board-pack --policy policy.json --input requests.csv --out reports
```

Each question shows the current answer in brackets, and Enter keeps it. Pressing
Enter throughout writes the default values under your team's name, and
`init --defaults` does that without asking. `init` will not overwrite an existing
file unless you pass `--force`. The interview asks for:

1. The team or company name, shown when the policy is applied.
2. Your value bands, lowest first (default `none, <50k, 50k-250k, 250k-1m, >1m`).
3. The band from which the Legal Ops Lead signs off.
4. The band from which General Counsel signs off. Requests from this band are at
   least medium risk, and General Counsel also signs off on every high-risk request.
5. The band from which a request is high risk and needs a board note and a
   board-awareness escalation.
6. The band from which a dispute is high risk, flagged for board attention and sent
   to external litigation counsel.
7. Changes to the routing table, written as `type=Queue` (a new type adds a row,
   `type=` removes one).
8. The queue for a request whose type is not in the table.
9. The queue for any request with a non-EEA data transfer.
10. to 13. Response hours and resolution days for each priority, P1 to P4.

Answers are checked as you give them. A band you did not list, an approval tier
below the one before it, or a service level that is not a whole number is asked
again.

## What a policy controls

The file format is published as
[`contracts/legal-function-policy.v1.schema.json`](../contracts/legal-function-policy.v1.schema.json)
(JSON Schema 2020-12).

| Key | Default | What it drives |
| --- | --- | --- |
| `name`, `description` | Default illustrative policy | Shown when the policy is applied, and in `triage` output |
| `value_bands` | `none`, `<50k`, `50k-250k`, `250k-1m`, `>1m` | The values a request's `value_band` may take, lowest first. A request without one is in the first band |
| `routing.by_type` | 10 request types (see [Request types and queues](INPUT_FORMAT.md#request-types-and-queues)) | The queue that owns each request type. A type not in the table is flagged for manual triage |
| `routing.unknown_type` | `General` | The queue for a missing or unknown type |
| `routing.non_eea_transfer` | `Privacy` | The queue for any request with a non-EEA transfer, whatever its type |
| `sla.P1_blocker` … `sla.P4_low` | 4h/1d, 8h/3d, 16h/5d, 40h/10d | Business hours to respond and business days to resolve, by priority |
| `approval.legal_ops_lead_from` | `50k-250k` | Legal Ops Lead joins the approval chain from this band |
| `approval.general_counsel_from` | `250k-1m` | General Counsel joins from this band (and on every high-risk request) |
| `approval.board_note_from` | `>1m` | A board note is required from this band |
| `risk.high_from` | `>1m` | A request at or above this band is high risk |
| `risk.medium_from` | `250k-1m` | A request at or above this band is at least medium risk |
| `risk.dispute_high_from` | `250k-1m` | A dispute at or above this band is high risk |
| `risk.elevated_types` | `corporate`, `fundraising`, `ai_governance` | Request types that are at least medium risk |
| `external_counsel.dispute_from` | `250k-1m` | A dispute at or above this band goes to external litigation counsel |
| `escalation.board_awareness_from` | `>1m` | A request at or above this band is escalated to the board's awareness list |
| `escalation.dispute_board_attention_from` | `250k-1m` | A dispute at or above this band is flagged for board attention |

The three `risk` thresholds and `escalation.board_awareness_from` also carry the
sentence a decision gives when they apply (`reason` or `message`), for example
`"Contract value above €1m."`. These sentences appear in the rationale and the
escalations, so change them together with the band. `init` writes them for you.

A policy changes numbers and names, not the shape of the rules. The following stay
in code, where the tests pin them:

- The fixed risk signals: personal data sent outside the EEA and uncapped
  liability are always high risk, and personal data is at least medium risk.
- How urgency and risk give the priority
  ([Urgency and priority](INPUT_FORMAT.md#urgency-and-priority)).
- The approval roles and their order: Reviewer, Legal Ops Lead, General Counsel,
  Board note. The chain always starts with a human reviewer.
- External corporate counsel for `corporate` and `fundraising` requests, and a
  cross-border AI/privacy specialist for `ai_governance` with a non-EEA transfer.
- The escalations for a missed SLA, a high-risk blocker and an active dispute.

## How a policy is checked

A policy is checked in full before anything is decided or written. Every problem is
reported with its place in the file, and the run stops with exit status 2:

```text
error: policy.json: approval.general_counsel_from: '250k-1M' is not one of the value bands (did you mean '250k-1m'?); use one of none, <50k, 50k-250k, 250k-1m, >1m
error: policy.json: risk.hgh_from: unknown key (did you mean 'high_from'?); prefix your own keys with x_
error: policy.json: risk.high_from: missing
The policy cannot be applied. Nothing was written.
```

- Every key is required except `description`. A misspelled key is an error, not
  ignored, because a threshold you think you set would silently keep its default.
- Every threshold must name one of the file's own `value_bands`.
- The approval tiers must rise in order: Legal Ops Lead, then General Counsel, then
  the board note. `risk.medium_from` may not be above `risk.high_from`.
- Service levels are whole numbers above zero.
- Keys starting with `x_` or `_` are yours (for example `"x_approved_by": "GC, 2026-10-01"`),
  and `"$schema"` may point an editor at the published schema.

Requests are then checked against the policy: with your own value bands, a request
must use one of them, and a type that is not in your routing table gets the
manual-triage warning. The bundled synthetic requests use the default bands, so
they will not pass a policy with different ones.

## Where a policy applies

`--policy` works with `triage`, `board-pack`, `validate`, `capacity` and
`control-tower`, and with the original all-in-one flags (`legal-function-os --policy
policy.json --input requests.json --out reports`), where it applies to every output
they write. Run `legal-function-os --help` for every command.

Treat the file like code. Keep it under version control, review a change before it
is applied, and record who approved the thresholds in an `x_` field. A CI job can
run `legal-function-os validate --policy policy.json --input requests.csv` to stop a
broken policy or request log before a report is built.
