# 0010. Triage verbs: decline and duplicate are final states, a snooze is a recorded pause

- Status: Accepted
- Date: 2026-11-19
- Amended: 2026-11-20: a withdrawn matter is reported `rejected` in the shared contract,
  not `approved` (owner choice of 2026-11-20); see Decision 9 and Consequences.
- Answers the ADR-needed item in `docs/research/adaptation-plan.md` on new pilot states
  for decline, duplicate and snooze, and their mapping in the shared contract (F10, from
  H3).

## Context

The pilot had nine states, and the only way out of `triage` was `complete_triage`. It
needs the assessment to be current, the sources usable, the matter inside the pilot
charter and the decision authority agreed. A matter that fails one of these cannot
leave triage, and scenario 3 (`PM-BLOCKED-003`) stays there on purpose.

The charter said such a matter "can be withdrawn", and the runbook told the reader to
"withdraw the matter". But `withdraw` needs someone already on the matter, and a matter
owner joins a matter only by completing triage. So the owner could not close a matter
that could not leave triage; only the requester could.

Peers give triage a small set of verbs. Both sources are in the repository's
[landscape](../research/2026-10-competitive-landscape.md#pattern-donors) and
[design teardown](../research/design-teardown.md):

- Linear has Accept, Duplicate, Decline with a comment, and Snooze until a time or new
  activity (Claimed).
- Plane stores pending, rejected (shown as declined), snoozed, accepted and duplicate,
  with `snoozed_till` and `duplicate_to`, and writes each change as an activity record
  (Observed; AGPL, so pattern only).

Four constraints shape it here:

- The plan lists, as an anti-pattern, a snooze that keeps the service level running
  without saying so or pauses it silently. Its rule: a pause needs a typed reason and
  shows its start.
- Nothing may act without a person. A snooze that ends by itself must not do anything
  when it ends.
- The parent's service-event ledger lets a request wait on the business only after work
  has started, resumed, an approval was requested or the request was reopened. The
  response target runs from `submitted` to `acknowledged`, and waits are deducted only
  from the resolution time.
- `legal-workflow-controls.v1` already has `rejected` in its `review_state` enum. Its
  changes must be additive.

## Decision

1. **Two final states.** `decline` moves a matter from `triage` to `declined`, and
   `mark_duplicate` moves it to `duplicate`. Like `closed`, both accept no further
   command. The closing outcome is recorded as `declined_by_legal` or
   `duplicate_of_another_matter`.
2. **Evidence.** Both need `closure_reason_recorded`: a reason of at least 20 visible
   characters. A run of whitespace counts as one, and invisible characters are not
   counted: format characters (general category Cf, such as a zero-width space or a
   word joiner) and, from a fixed list, the other default-ignorable code points (such as
   a combining grapheme joiner or a Hangul filler). The reason is kept as typed, with runs
   of whitespace collapsed to one space.
   `mark_duplicate` also needs `duplicate_original_visible`: the original is another
   matter the owner can see (`_can_read`), and it is not itself a duplicate. An unknown
   ID and one the owner may not see get the same refusal, so the refusal says nothing
   about matters outside the owner's view.
3. **A snooze is not a state.** `snooze` on a matter in triage writes one hash-chained
   event, `matter_snoozed`, with a reason of at least 20 visible characters and exactly
   one of:
   - `until`: a date and time with a time zone, later than now on the command's clock
     and at most 30 days ahead, stored in UTC;
   - `question`: at least 10 visible characters, for the requester.

   The matter stays in triage. A second snooze is refused while one runs.
4. **How a snooze ends.** The requester answers its question with `answer_snooze`, in at
   least 10 visible characters, or the owning matter owner runs `end_snooze`; each writes
   its own event. A triage verb
   (`complete_triage`, `decline`, `mark_duplicate`) or a withdrawal also ends it. When its
   time passes it ends too, and nothing is written and nothing runs: every reader works
   it out from the events with `supervised-agent/src/pilot/snooze.py`, on the matter's one
   clock, scripted or recorded, as the room's timing measures it. The review room, the
   requester view, the parent ledger and the pilot metrics therefore cannot disagree.
5. **Who.** The three verbs run only in triage, and only for an onboarded matter owner.
   Each claims the matter exactly as `complete_triage` does (`TRIAGE_CLAIM_COMMANDS`), so
   another owner can then neither act on it nor see it. Outside triage, an actor who is
   not on the matter is told only that, not the matter's state; this now holds for
   `complete_triage` too, and for every command on a closed, declined or duplicate
   matter. After triage, `withdraw` stays the way to close a matter without delivery.
6. **A person types every reason.** The room's forms start empty and propose no reason,
   no original and no time. The software never declines a matter, marks a duplicate or
   snoozes on its own, and never suggests doing so.
7. **What the requester sees.**
   - Declined: "Closed: declined by legal", "Legal declined this request. The reason is
     below." and the reason as typed.
   - Duplicate: "Closed: duplicate of another matter", "Legal closed this request as a
     duplicate of another matter. The reason is below." and the reason as typed. The
     sentence holds whatever state the original is in: open, delivered, withdrawn or
     declined. The original's matter ID is shown only when the requester also asked for
     that matter.
   - A running snooze: the stage stays "Received by legal", with the reason, its start and
     its end time. With a question, the request is waiting on the requester, the next step
     is "Answer legal's question below." and the room offers an Answer form.

   This extends [ADR 0003](0003-intake-facts-and-requester-status.md). The status is still
   a pure function, now of the state, the closing outcome, the open-question count, the
   running snooze and the closing reason. To get the last two, the requester view now
   reads the matter's events and its closing decision.
8. **Records.** A decline or duplicate is also kept in the decision record, bound to the
   version and content hash it closed, and shows as a decision on the audit-chain
   timeline. The snooze events show as commands.
9. **Shared contract.** `declined` and `duplicate` map to `rejected`, which v1 already
   allows. `rejected` takes precedence over `blocked`: a declined matter that a charter
   exclusion held is no longer pending, so it is reported `rejected`.
   `parent_bridge.CONTRACT_REVIEW_STATE`, `scripts/check_shared_contracts.py` and
   `contracts/README.md` list both.

   Amended on 2026-11-20. A `closed` matter is reported by how it closed, not by its
   state. Only a matter whose approved package the requester accepted
   (`delivered_locally_and_accepted`) is `approved`. A withdrawn matter
   (`withdrawn_without_delivery`) is `rejected`, whatever state it had reached, because a
   withdrawal cancels every sign-off and approval on it. It invalidates the specialist
   sign-offs and final approvals in the decision record. In the same step it records a
   rejected review decision on the assessment stored in the matter version, with the actor
   and the reason they typed, so that assessment is no longer approved or exportable and
   the pilot's own export gate fails its check of it. It does this for every withdrawal,
   whatever the assessment said before. A delivery package prepared before the withdrawal
   stays in the store and in the export folder, but the review room and the package route
   no longer open it. A store in which a matter was withdrawn before this was built keeps
   the assessment as the approval left it. The contract takes neither its state nor its
   note from that assessment, so such a matter is reported `rejected` as well. A closed
   matter with no recorded
   outcome is `rejected` too, so nothing is reported approved unless its delivery was
   accepted. As for a decline, `rejected` takes precedence over `blocked`. The review note
   of a withdrawn matter is the withdrawal reason and the actor recorded for it, not the
   note of an approval that no longer stands. `export_allowed` was already false for every
   closed matter. In the pilot, `rejected` now means that a person closed the matter
   without delivery and no approval stands. It does not say that a reviewer rejected a
   draft. The schema is unchanged and no value is added.
   `parent_bridge.contract_review_state` decides this in one place.
   `supervised-agent/tests/test_pilot_contract_closings.py` guards what it returns and
   what a withdrawal leaves in the store.
   `scripts/check_shared_contracts.py` reads the module's source text and runs none of
   it. It fails if the state table has a `closed` entry, if a closing-outcome entry is
   missing or changed, or if the function does not begin with the closed branch that
   returns `CLOSED_OUTCOME_REVIEW_STATE.get(closed_outcome or "", "rejected")`.
10. **Clocks.**
    - In the parent ledger, a running snooze is a wait on the business. It runs from the
      snooze to the earliest of the answer, `end_snooze`, a triage verb, a withdrawal or
      its `until`. At `until` a synthetic `resumed` entry is written, never later than the
      time the ledger is read (`matter_ledger(..., as_of=...)`).
    - On a request legal has not yet acknowledged, a snooze is legal's first response. It
      is reported as acknowledged, assigned, work started and waiting, all at the time of
      the snooze, because the parent lets a request wait only once work has started.
    - A decline or duplicate on an unacknowledged request is reported as `acknowledged`.
      No resolution target applies to it, as for a withdrawal, and the room says "not
      applicable, declined" or "not applicable, closed as a duplicate".
    - Pilot metrics charge time inside a snooze to `requester_or_missing_facts`, whoever
      acts next.

## Consequences

- A matter owner can close a matter that cannot leave triage, with a reason the requester
  reads. The charter, the runbook and the identity controls say so.
- A snooze meets the response target, since it is legal's first response. An owner could
  snooze a request without reading it; the reason, which the requester sees and the chain
  keeps, is the check.
- While a snooze runs, legal-controlled time stops and elapsed time does not. The room
  shows who snoozed, when, why and until when, and how it ended.
- No scenario script uses the new verbs. The three scripts and the dated rehearsal of
  2026-10-06 are unchanged, and `make demo` writes the same core examples.
- The blocked-matter test now tries 19 commands as each actor: `answer_snooze` and
  `end_snooze` are refused like the rest, and the three triage verbs are tested apart, as
  legitimate ways to close or pause that matter.
- Known and out of scope:
  - Parent tower rows for matters closed without delivery (withdrawn, declined or
    duplicate) stay open, and the tower counts such a row as stalled once it has been
    inactive for the configured time (16 business hours in the bundled outcome config).
    The parent ledger, `legal-function-os.service-event-ledger.v1`, has no event for
    closing without completion. Its only closing event, `completed`, counts the request
    as completed work and measures it against the resolution target, and it cannot
    follow `submitted`, `acknowledged` or `assigned`. Closing these rows needs a new event
    type in that contract, which is its own decision. Until then the review room marks
    their resolution target not applicable and measures them to their closing event, and
    only the rehearsal's parent outcome view shows them open. No scenario script closes a
    matter without delivery.
  - A snooze's `until` is checked on the clock of the command that sets it. A scripted
    matter that later gets a command from the room moves to the recorded clock, as
    before, and its scripted `until` is then read on that clock.

Choices the owner can revisit without a new record: whether a snooze counts as legal's
first response (chosen: yes), the 30-day cap, and whether a duplicate needs a reason
(chosen: yes, because the requester reads it).

Confirmed: 2026-11-20, the owner confirmed the three revisable defaults. A snooze counts
as legal's first response, a snooze lasts at most 30 days, and a duplicate needs a reason.
Nothing in the code changed.

## Alternatives rejected

- **Three new states, including `snoozed`, with a scheduler** that moves the matter back
  when the time passes. A timer would act on the matter without a person, and a third
  state would need its own contract mapping for something that is not a decision.
- **Decline and duplicate as closing outcomes of `closed`.** No new state, but `closed`
  mapped to `approved` whatever the outcome when this was decided, so a declined request
  would have been reported approved in the shared contract. Since 2026-11-20 a closed
  matter is reported by its outcome (Decision 9). The two states stay as built.
- **A duplicate that is only a pointer**, as in Linear and Plane. Here the requester reads
  why their request was closed, so a person writes a reason.
- **Letting any onboarded owner withdraw an unclaimed matter.** It would close the gap,
  but it would give withdrawal, which is also the requester's way out, a second claiming
  rule. The triage verbs share the one claim `complete_triage` already has.
- **Reporting a withdrawn matter by the state it had reached** (2026-11-20).
  `pending_review` or `revision_requested` on a closed matter reads as open work, and
  `approved` would report an approval that the withdrawal cancelled.
- **Reporting `approved` when a final approval was recorded before the withdrawal**
  (2026-11-20). The approval does not stand after the withdrawal. `approved` would then
  cover a delivered matter and one that was never delivered, with the same gate values,
  and the rule would have to say which earlier approvals count.
- **A new `withdrawn` value in the contract** (2026-11-20). It would change the v1 schema.
  This change adds no value.
