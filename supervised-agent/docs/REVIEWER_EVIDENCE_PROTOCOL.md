# Reviewer evidence protocol

Status: draft for agreement with reviewers. No session has been held.

This protocol governs a bounded pilot in which practising lawyers take one synthetic
contracting matter through the supervised agent: intake, assessment, review, revision
and export. It states the task, the criteria agreed beforehand, what is recorded, how
reviewers are protected, and the one claim the pilot can support.

It is the second of two tracks in this repository, and the two answer different
questions. The pilot workflow under [`docs/pilot/`](pilot/PILOT_CHARTER.md) asks
whether an in-house team can run a contract review through recorded roles, states and
approvals; it has been rehearsed on scripted, synthetic matters. This track asks what
practising lawyers make of one fixed set of recommendations; it has not been run. A
result from one track says nothing about the other.

## The claim

A completed pilot supports this sentence and no wider one:

> A user pilot on synthetic documents: N review sessions by M practising lawyers on
> one matter round.

The pilot record prints that sentence with its own N and M. It prints three limits
beside it. The documents are synthetic. The pilot covers one matter, and the record
names where the rated recommendations came from. Reviewers working on synthetic
documents show how the workflow behaves under a lawyer's hands. They do not show
adoption inside an organisation, so the pilot is no evidence of an enterprise
implementation.

A record with no session by a practising lawyer other than the author prints "No
reviewer pilot is evidenced". The author's own session and worked examples are stored
and counted as excluded.

## The matter

The matter is `northwind-saas` from `contract-review-eval-harness`: a fictional
customer buying a hosted platform on a fictional vendor's paper. Every document is
fabricated. The harness holds the documents. This repository holds two intakes that
reference them by id, kind, path and SHA-256 hash and copy none of them:

| Round | Intake | Documents |
|---|---|---|
| `round1` | `examples/matters/northwind_saas_round1.json` | 7 |
| `round2` | `examples/matters/northwind_saas_round2.json` | 9 |

A draft is prepared only when every referenced file matches its recorded hash. An
edited document is refused until its new hash is recorded at intake, because a
reviewer's decision is a position on specific text.

The intakes leave `data_categories` and `customer_commitments` empty. Choosing them is
a reading of the documents, and that reading belongs to the lawyer who conducts the
intake.

## What reviewers rate

The agent assesses a matter from the intake's typed fields by fixed rules and does
not read contract text. On the Northwind intakes as committed, its own rules yield a
single recommendation. The pilot therefore puts a different set to reviewers: one
model review of the matter, captured by `contract-review-eval-harness`.

`prepare --harness-review <file>` reads that review. Each of its findings (a conflict,
a position or an escalation) becomes one recommendation under the finding's own id,
with the passages the review quoted. A quoted document that the round does not hold
is marked "not on the file". The draft is bound to the hash by which the harness
identifies the review, and the record states `harness_review` as the source.

Three points follow from this.

- The agent contributes the supervised workflow: verified documents, the review gate,
  recorded decisions and reasons, timings and export. The legal substance under review
  is the model's.
- A capture names the model and the condition that produced the review. The agent
  discards both, and the reviewer's material names neither.
- A review is model output. One with unknown fields, unsafe ids, no findings or
  oversized text is refused before a reviewer sees it.

Without `--harness-review` the recommendations are the agent's own: the action its
rules recommend for each finding, under ids such as `finding-1`. The record then
states `agent_rules`.

## The task

A reviewer receives the documents of one round, `review-packet.md` and
`recommendations.md`, which lists each recommendation with its basis and quoted
passages. The reviewer then:

1. decides each recommendation as `accepted`, `corrected` or `rejected`;
2. scores each for usefulness on the scale below;
3. writes a reason for every correction and rejection, and the replacement wording
   for every correction;
4. marks the moment the draft is fit to hand to a supervising lawyer;
5. records each material issue the draft missed;
6. decides the matter (`approved`, `revision_requested`, `rejected` or `escalated`)
   with a written note, which closes the session.

| Score | Meaning |
|---:|---|
| 4 | Usable as written. I would send it on with my name under it. |
| 3 | Useful after correction. The point is right; wording, severity or action needed fixing. |
| 2 | Not useful. Correct or harmless, but it told me nothing I needed. |
| 1 | Misleading. Wrong in a way that would have cost time or caused harm if relied on. |

The scale is the one the harness uses, so scores from both repositories can be read
side by side.

Each reviewer works on a private copy of the draft and sees no other reviewer's
decisions. A reviewer may change a decision until the session closes. The earlier
decision stays in the audit trail and the later one counts.

## Acceptance criteria

The criteria are agreed with the reviewers before the first session and do not change
afterwards. They are thresholds on measures the record computes over sessions by
practising lawyers.

**Status: proposed by the author, not yet agreed with any reviewer.** No reviewer has
been recruited. The record prints "thresholds: proposed by author" beside every
result until that changes.

| Criterion | Proposed threshold | Why this measure |
|---|---|---|
| Distinct practising lawyers | at least 3 | Fewer is one or two people's taste |
| Recommendations scored 3 or 4 | at least 60 % | The share a lawyer could use, as written or after correction |
| Recommendations scored 1 | at most 10 % | A misleading recommendation costs more than a useless one |
| Material omissions per session | at most 1 | What the review missed, as each reviewer saw it |

Two choices need explaining. The mean usefulness score is reported and is not a
criterion: the scale has no neutral point, and a mean of 2.5 is reached when half the
recommendations are misleading and half are usable. Review time is reported and is
not a criterion: without an unassisted baseline it shows effort and cannot show a
saving.

The thresholds live in `examples/pilot/reviewer-evidence-plan.json`. When the
reviewers have agreed them, `agreed_with_reviewers` is set there in a commit that
precedes the first session, and the record then prints "thresholds: agreed with
reviewers". Every record carries the SHA-256 hash of the plan it was judged against,
so a later change to a threshold is visible in the record. A record with no counted
session reports `not_measured`.

## What is recorded

Each step is one event in the assessment's audit trail. Every event's hash covers the
previous event's hash and the event's own content, including the fields below.

| Step | Event | Recorded |
|---|---|---|
| Intake assessed | `assessment_created` | Each document's id, hash and verification status |
| Draft fixed | `review_draft_ready` | Hash of the recommendations, their ids, hash of the assessment |
| Session opened | `review_session_started` | Pseudonym, evidence class, profile, hash of the recommendations |
| Draft fit to hand on | `draft_marked_reviewable` | Time |
| Decision | `recommendation_decision_recorded` | Recommendation, decision, usefulness, reason, corrected wording |
| Omission | `material_omission_recorded` | The reviewer's description |
| Matter decided | `review_decision_applied` | State and note |
| Session closed | `review_session_closed` | Final state, declared review time, feedback |

The audit trail is the record. At export the session's events are replayed onto the
draft, and the session file is accepted only if the replay reproduces it exactly. A
reason reworded afterwards, an evidence class changed, a recommendation rewritten, an
omission removed, a review state altered: each makes the file differ from its replay,
and the export refuses it and names the field. The draft is checked the same way
against the hashes its own trail holds.

The hash chain is a local integrity check with two limits. It does not prove who made
an entry or when: a person holding the file could rebuild the whole chain. And a
session file cut back to an earlier point, with its fields edited to match, is
consistent again. Both are closed only by a value kept outside the file. `close`
prints the session's audit chain root for that purpose. The reviewer keeps it, and a
record is fixed in time once that root is published somewhere the author cannot
rewrite.

## Timings

| Measure | Definition |
|---|---|
| Time to a reviewable draft | Minutes from the session's start to the reviewer's `draft_marked_reviewable` event. Empty when the reviewer never marks it |
| Review time | Minutes from the session's start to its close, read from the audit trail |
| Declared review time | Optional. The reviewer's own figure for active minutes, where the session was interrupted. It is positive and may not exceed the elapsed time. Each session states which figure it reports, and the summary gives the elapsed median and the number of declared figures beside the review-time median |
| Draft preparation | Seconds from intake to the fixed draft. This is machine time and is reported apart from the reviewer's time |

The clock has a resolution of one second and runs on the machine holding the session.

## Consent and pseudonymity

Before a session the reviewer is told, and agrees to, the following.

- Participation is voluntary.
- The documents are fabricated. The reviewer enters no client, matter or employer
  information in any free-text field.
- The reviewer appears as a pseudonym of the form `R01`. `R00` and every other
  all-zero id are reserved for fabricated examples and cannot be used for a person.
- The record holds the reviewer's decisions, reasons, corrected wording, omissions,
  feedback and timings. It may be published in a public repository, where it is
  permanent and searchable.
- `reviewer_profile` is optional. If used, it stays coarse enough that it cannot
  identify the reviewer among the participants.
- The reviewer may withdraw a session until it is published. After publication it can
  be removed from the current files but remains in the repository's history.

The key that links a pseudonym to a person is kept by the pilot's author outside every
repository, together with the reviewer's consent. The wording of the consent itself is
settled by the author and is not part of this repository.

## Running a session

All commands run inside `supervised-agent/` and write local files only. The working
folder `pilot/` is ignored by Git, so a draft or session file is never committed by
accident. A record is published by copying it into `examples/pilot/` once the reviewer
has agreed.

```bash
python -m src.pilot.evidence.cli verify-documents \
  --input examples/matters/northwind_saas_round1.json \
  --documents-root <harness-checkout> \
  --harness-manifest <harness-checkout>/matters/northwind-saas/matter.json
```

```bash
python -m src.pilot.evidence.cli prepare \
  --input examples/matters/northwind_saas_round1.json \
  --documents-root <harness-checkout> \
  --harness-review <harness-checkout>/captures/matters/northwind-saas/<capture>.json \
  --harness-template <session template written by the harness> \
  --out-dir pilot/round1
```

`prepare` writes `draft.json`, `review-packet.md` and `recommendations.md`. The last
two go to the reviewer together with the documents.

```bash
python -m src.pilot.evidence.cli start --draft pilot/round1/draft.json \
  --session pilot/round1/sessions/R01.json \
  --reviewer R01 --evidence-class practising_lawyer
```

```bash
python -m src.pilot.evidence.cli decide --session pilot/round1/sessions/R01.json \
  --recommendation k1 --decision corrected --usefulness 3 \
  --reason "<reason>" --corrected-text "<replacement wording>"
```

```bash
python -m src.pilot.evidence.cli reviewable --session pilot/round1/sessions/R01.json
```

```bash
python -m src.pilot.evidence.cli omission --session pilot/round1/sessions/R01.json --text "<issue>"
```

```bash
python -m src.pilot.evidence.cli close --session pilot/round1/sessions/R01.json \
  --state approved --note "<decision note of at least 30 characters>"
```

```bash
python -m src.pilot.evidence.cli export --draft pilot/round1/draft.json \
  --session pilot/round1/sessions/R01.json \
  --documents-root <harness-checkout> --out-dir pilot/round1/record
```

A draft is prepared once per round: `prepare` refuses to replace an existing draft,
because sessions held on the first one could not be exported against a second.
Documents are checked by hash when the draft is prepared and again at `export` when
`--documents-root` is given. Between those two points a changed document goes
unnoticed, so the documents root should not be edited while sessions run.

`export` writes `pilot-record.json` and `pilot-record.md`. For each session it asks
the repository's single export gate (`src/export_gate.py`) whether the revised draft
may be written. The gate requires an approved assessment, no blocker, an intact audit
chain, every recommendation decided, and recommendations identical to the ones the
draft fixed. Where it agrees, `export` writes
`reviewed-recommendations-<reviewer>.md`: accepted recommendations as proposed,
corrected ones in the reviewer's wording, rejected ones left out. Where it refuses,
`export` prints the gate's reasons and writes no revised draft.

## Reconciling with the harness

Each session in the record carries `harness_fields`, which uses the field names of the
harness format `contract-review-eval.reviewer-session.v1`:

| Field | Source in this repository |
|---|---|
| `matter_id`, `round_id` | The intake |
| `review_sha256` | The harness's hash of the review, or the hash of the agent's own recommendations |
| `reviewer_id`, `reviewer_profile`, `evidence_class` | The session |
| `minutes_to_reviewable_draft`, `review_minutes` | The timings above |
| `decisions[].finding_id` | The finding's id in the review, or `finding-1` and so on |
| `decisions[].decision`, `.usefulness`, `.reason` | The decision event |
| `material_omissions`, `workflow_feedback` | The omission and closing events |

For a session held on a harness review, `export` also writes
`harness-session-<reviewer>.json`. That file is a complete reviewer session in the
harness's format, bound to the same review hash and the same finding ids. The author
copies it into the harness's `matters/<id>/reviews/` folder, where the harness checks
it against the review before counting it. This repository writes nothing into the
harness.

A session held on the agent's own recommendations gets no such file. Its
`review_sha256` names an output the harness has never seen, so it does not belong in
the harness's `reviews/` folder.

The harness format has no field for a reviewer's replacement wording. A correction
reaches the harness as `corrected` with its reason; the wording itself stays in this
repository's record.

Before reviewers are invited, the harness can write a session template for the same
review (`matter-review-template`). `prepare --harness-template <file>` refuses to
prepare a draft when the review, matter, round or finding ids differ from that
template. The review hash is computed here by the harness's recipe, and a test
compares the two against a harness checkout.

## Worked example

`examples/pilot/synthetic-worked-example/` shows a record's format. It is fabricated:
the reviewer is `R00`, the evidence class is `synthetic_example`, every free-text
field begins with "SYNTHETIC EXAMPLE", and it runs on a sample matter of this
repository, not on the pilot matter. It is excluded from every summary.

## Limits

- One matter and one reviewer workflow. A claim about other matters needs other
  matters.
- The agent does not read contract text. With a harness review as the source, the
  pilot says what lawyers made of one model's review inside this workflow. It says
  nothing about a review the agent produced, because the agent produced none.
- One captured review is one output of one model under one setup. A different capture
  is a different draft with its own hash, and sessions on the two are not pooled.
- A reviewer who sees which passages the review quoted may check those passages and
  no others. Material omissions are recorded for that reason, and they depend on the
  reviewer reading the documents, which the workflow cannot observe.
- Usefulness scores are judgments by a small number of people on fabricated documents.
- Timings measure this workflow on this matter. No unassisted baseline is recorded, so
  the pilot shows no time saving.
