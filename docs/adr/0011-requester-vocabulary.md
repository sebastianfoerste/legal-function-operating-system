# 0011. Requester stages: the pilot's six ids are the vocabulary; the core shared space keeps its v1 words; no German labels

- Status: Accepted
- Date: 2026-11-19
- Answers the ADR-needed item in `docs/research/adaptation-plan.md` on a requester-stage
  vocabulary shared between the pilot and the core `shared_space.py`, including German
  labels (F3, from H2). It settles what
  [ADR 0003](0003-intake-facts-and-requester-status.md) left open under Consequences.

## Context

Two outputs tell a business requester where a request stands.

- **The pilot's requester view**, `supervised-agent/src/pilot/requester_status.py`
  (ADR 0003, extended by [ADR 0010](0010-triage-verbs.md)). It maps the eleven pilot
  states to six stages, in this order: `draft` (Not yet submitted), `received` (Received
  by legal), `in_review` (In review), `approved` (Approved), `ready` (Ready for you) and
  `closed` (Closed). Its labels, explanations and next steps are in English. Since ADR
  0010 the final states `declined` and `duplicate` map to `closed`, with their own label
  and the reason a person in legal typed, and a running snooze keeps a matter at
  `received`.
- **The core shared space**, `src/legal_function_os/shared_space.py`, writes
  `legal-function-os.shared-space.v1` JSON with `--shared-space-output`. An entry is
  shared only when a person documents an approval for that request: a name and a note of
  at least 20 characters. A shared entry has a `status` of `in_review` or `blocked`, the
  owner queue, the response SLA in hours, the request's own `deadline` as
  `next_update_due`, and one of two German sentences as `requester_action`: "Bitte offene
  Informationen nachreichen." when the request awaits business input, otherwise "Keine
  Aktion erforderlich.".

ADR 0003 expected the core shared space to reuse the stage list, and the plan listed
aligning the two, German labels included. Read side by side, they do not line up:

- **The core cannot derive five of the six stages.** A `legal-request.v1` request
  carries no workflow state: nothing in it says whether the request was submitted,
  approved, made ready or closed. The core knows only whether an entry is shared and
  whether it is `blocked`, so `in_review` is the one stage it can name.
- **The two have different gates and withhold different things, on purpose.** The
  pilot's requester view is what the requester role sees of a matter. It never carries
  the queue, the risk, the approval tier, playbook positions, internal comments or the
  service levels, because pilot service levels are internal (F3). The core shows nothing
  until a person documents an approval for the request, and then shows the queue and the
  response SLA, which that person approved sharing.
- **`blocked` means different things.** The core sets it when a request's urgency is
  `blocker` (priority `P1_blocker`) or its response SLA was missed. In
  `legal-workflow-controls.v1` the pilot reports `blocked` for a matter that a charter
  exclusion or a blocked source holds. `complete_triage` refuses such a matter, so a
  matter held when it reaches triage stays there. A matter that an amendment after triage
  brings under a charter exclusion moves to `revised`, cannot be exported, and stays
  `blocked` in the contract until a new version removes the exclusion.
- **Nothing in the repository reads the shared space** except its tests. No page renders
  it, no schema in `contracts/` describes it, no MCP tool returns it and `make demo` does
  not write it. It is JSON a team can use.
- **German wording needs a reviewer and a choice.** German requester wording would be new
  text that no German-speaking reviewer has read, and the form of address (Sie or du)
  belongs to the organisation. The two existing sentences avoid it: one is an infinitive
  request, the other has no verb.

## Decision

1. **The vocabulary.** The pilot's six stage ids, in this order, are the repository's
   requester-stage vocabulary: `draft`, `received`, `in_review`, `approved`, `ready`,
   `closed`. They live in `REQUESTER_STAGES` in
   `supervised-agent/src/pilot/requester_status.py`. Additive only: a new stage needs a
   new ADR, and no id is renamed, removed or moved. Every pilot state
   maps to one of the six; `declined` and `duplicate` map to `closed`. The English labels
   stay the pilot's wording, as ADR 0003 and ADR 0010 set them.
2. **The core keeps its v1 words.** `legal-function-os.shared-space.v1` is unchanged: no
   field is added, renamed or removed, and no value changes. Its `in_review` is the same
   stage as the pilot's `in_review`. Its `blocked` stays a core flag; it is not a
   requester stage and is not added to the vocabulary.
3. **The two German sentences are v1 values.** "Bitte offene Informationen nachreichen."
   and "Keine Aktion erforderlich." stay exactly as they are, because a v1 consumer may
   match them. No German stage label is added, in the pilot or in the core.
4. **German comes back only through a new ADR.** That record names a German-speaking
   reviewer, chooses the form of address, holds the wording as replaceable data (as
   [ADR 0006](0006-intake-question-files.md) does for intake questions, so a team can
   supply its own), and marks the German text with `lang="de"` wherever it is shown.
5. **A pin test.** `tests/test_requester_vocabulary.py`, in the core's test suite, reads
   `requester_status.py` by path, without the agent's dependencies, and checks:
   - the six ids and their order;
   - the stage of each state in the pilot's `State` literal: `intake` is `draft`,
     `triage` and `assignment` are `received`, `review`, `revision_requested` and
     `revised` are `in_review`, `approved` is `approved`, `ready_for_delivery` is
     `ready`, and `closed`, `declined` and `duplicate` are `closed`, so each of the six
     is reached;
   - that the core's `in_review` is one of them and its `blocked` is not;
   - both German sentences, exactly.

   A change to any of these fails the test, so it has to be deliberate.

## Consequences

- No code changes. The pilot's requester view, `legal-function-os.shared-space.v1` and
  `legal-workflow-controls.v1` are unchanged, and `make demo` writes the same examples.
- Three existing behaviours are recorded here, not changed:
  - The pilot shows a matter held in triage, `blocked` in `legal-workflow-controls.v1`,
    to its requester as "Received by legal", with "Legal has the request and is
    assigning a reviewer.". Scenario 3's `PM-BLOCKED-003` shows this. A matter held
    after triage shows its ordinary stage, such as "In review", while the contract says
    `blocked`.
  - The core shares the owner queue and the response SLA in hours with requesters, behind
    the documented approval. The pilot's requester view carries neither.
  - The core reports `blocked` for a request whose urgency is `blocker` or whose response
    SLA was missed, and in the same entry tells the requester "Keine Aktion
    erforderlich.". The word follows urgency and the service level, not something the
    requester can clear.
- A requester surface in the core that wanted the other stages would need a request state
  the core does not have today. Until then, `in_review` and `blocked` are all it can say.
- Owner questions, none blocking:
  - A German requester surface needs a named German-speaking reviewer and a chosen form
    of address.
  - Whether a future `shared-space.v2` should stop sending `owner_queue` and
    `sla_response_hours` to requesters, and what its `blocked` should mean.

## Alternatives rejected

- **Full alignment:** one stage module shared by the pilot and the core, with German
  labels. The core would carry five stage words it cannot derive, and the German labels
  would be unreviewed wording in a form of address nobody chose.
- **Additive English fields in `shared-space.v1`**, such as a `stage` and a `label`
  beside `status`. Additive changes are allowed, but the core could only ever fill
  `in_review`, so the fields would promise a vocabulary the core cannot follow, in an
  output nothing reads.
- **Replacing the German sentences**, with English or with the pilot's wording. A
  consumer that matches the v1 values would break; that is not an additive change.
- **Leaving the item parked.** The plan's "align both" would stay open with nothing that
  could close it, and nothing would stop the two vocabularies drifting apart.
