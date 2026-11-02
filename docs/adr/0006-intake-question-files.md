# 0006. Intake questions live in one file per policy, keyed by request type

- Status: Accepted
- Date: 2026-11-02
- Answers the "ADR needed" item for F9 in `docs/research/adaptation-plan.md`: the format
  and location of per-type question files, and how they relate to `request_schema()`.

## Context

The pilot rehearsal refused the specialist matter's first intake for one missing fact
and created a second version before any review (`supervised-agent/docs/pilot/RETROSPECTIVE.md`,
step B02). F1 fixed that in the pilot. The core request contract
(`contracts/legal-request.v1.schema.json`) requires only `id` and `title` and has no
branching, so a team outside the pilot has nothing that asks a requester the right
questions for the kind of request.

Peers ask per request type, with conditions:

- docassemble: every field is required unless marked optional, and a missing variable is
  asked next (Observed).
- LawVu: conditional intake forms where only earlier fields can control later ones
  (Claimed).
- SurveyJS: a JSON definition with `visibleIf` expressions (Observed).

Three constraints shape it here:

- The request contract is `legal-request.v1`. Any change must stay backward-compatible,
  and a new field would widen the misspelling check that rejects files today.
- The core is deterministic and stdlib-only, and generated pages are self-contained:
  no network, no CDN, no submit. "Do not add external delivery, publication, filing or
  outreach actions."
- `request_schema()` describes fields for developers. It takes no policy, its
  descriptions name queues, and it does not say which fields a requester should be asked.

## Decision

- **One question file**, `src/legal_function_os/data/intake_questions.json`, with
  `"schema": "legal-function-os.intake-questions.v1"`. It holds wording for the request
  fields (`fields`) and a question set per request type (`types`). It is one file, not one
  per type, because a policy's type keys are free text (spaces and `/` are allowed) and
  because one file keeps the whole questionnaire in one reviewable diff.
  `legal-function-os intake-page --questions PATH` reads a team's own file.
- **The contract and the policy own the fields.** Which request fields exist, their
  order and their control come from `request_schema()`. Value bands and request types
  come from the policy, as validation reads them, and urgencies from the rules. The
  question file adds words, per-type questions, `also_required` (optional fields a type
  makes required, such as the other party for a contract) and conditions. It cannot add,
  relax or rename a request field or hide a decision field; it can leave an optional
  field unasked or make it required.
- **Every request field has a place**, checked by a test: always asked and required
  (`title`, `type`, `value_band`, the three flags, `urgency`), optional (`counterparty`,
  `requested_by`, `description`, `deadline`), legal's own and never asked (`sla_breached`,
  `awaiting_business_input`, `summary`, `dependencies`), or set by the page (`id` is
  `REQ-DRAFT`; `facts` holds the type answers). A new contract field fails the build
  until it is placed.
- **Decision fields are always asked, and nothing is preselected.** A field left out
  of a file takes its default (false or none), which can lower risk or change routing,
  so the page never lets that happen silently. The bundled hints for the three flags say
  "Not sure? Choose Yes and say why": an unsure Yes adds review, while an unsure No
  silently lowers it. A team can change that wording in its own file.
- **Type answers go into `facts`** as `"key: value"`, sorted by key, as the pilot's bridge
  writes them (`parent_bridge.parent_request`). A type question can never write a
  top-level field. The labels of the value bands, urgencies and request types do decide
  what a requester's choice saves, so a change to them needs the same review as a policy
  change; two answers with one label are refused.
- **Conditions are data, forward-only.** `"show_if": {"field": NAME, "in": [VALUES]}`
  names an answer given above the question: the value band, one of the three yes/no
  flags, the urgency, or an earlier yes/no or choice question of the same type. `type` is not a condition (put the question
  under the type), free text cannot control anything, and every value is checked against
  the controller's answers. A question whose controller is hidden is hidden. The checker
  reports a later, unknown or self reference with its path, so the dependency graph is
  acyclic by construction and is evaluated in one pass from the top.
- **The checker is the authority**, in the style of `policy.parse_policy`: every problem
  with its JSON path, did-you-mean hints, `x_` and `_` keys ignored, no published JSON
  Schema for now. A policy mismatch is a note, not an error: a type the policy lacks is
  not used, and a policy type with no question set is offered under its key. A condition
  on the value band must name bands of the policy in use, even under a type it lacks.
  Policy text the page carries (its name, bands and type keys) must hold no link and no
  unpaired surrogate.
- **v1 evolves additively.** New optional keys may be added within v1. Removing or
  renaming a key, or changing what one means, needs v2. An optional request field missing
  from a file is not asked (a note), so a later optional contract field does not break a
  team's file; a decision field missing from a file is an error.
- **The page sends nothing.** It has no `<form>` and no network or navigation code (no
  `location`, no `window.open`), and its Content-Security-Policy (hashes of its one
  script and style; `default-src`, `connect-src` and `form-action` set to `'none'`)
  blocks every fetch, form post, frame and resource load and any injected script. CSP
  has no directive for top-level navigation, so the script's own code is what keeps the
  page from opening anything. Its only
  output is a local download of a JSON array holding one `legal-request.v1` object, which
  `validate` and `triage` read. Unanswered optional fields are left out, never null.
- **The page script and `intake_page.py` implement the same rules.** A test runs the
  page's own script in Node, with no browser, on every answer the page can accept, under
  the default and a custom policy, and compares the saved text, the problems, the review
  and the file name with the Python reference, which is itself checked against
  `validate_requests`. A browser test drives the real page in the CI agent job.

## Consequences

- A requester gets the questions legal needs for their kind of request, an error summary,
  and a "Check your answers" step that shows the exact file before it is saved.
- `legal-request.v1` and every other contract are unchanged.
- Every file has the id `REQ-DRAFT`. Legal renumbers before combining files; otherwise
  `validate` reports the duplicate id.
- Type answers reach the files, the agent runs and the operational list through `facts`,
  but not the board pack.
- Text the page trims uses one whitespace set shared by Python and the script (Python's
  `isspace()` set plus U+FEFF), so a title the page keeps is never blank to validation.
- The root CI test job now relies on Node, which `ubuntu-latest` ships; with
  `REQUIRE_JS_TESTS=1` a missing Node fails the job instead of skipping the parity test.
- Deflection (offering a resource instead of a request) waits for approved resources
  keyed by type; it is specced as F9a.

## Alternatives rejected

- **One file per type** (`questions/<type>.json`): type keys would need escaping, and a
  team would review several files for one questionnaire.
- **Questions in the policy file**: the policy is `legal-function-policy.v1`, read by every
  command; questions change more often and are owned by different people.
- **A new optional request field for the answers** (for example `answers`): it would
  change `legal-request.v1`, widen the misspelling check and reject files that already use
  that key.
- **An expression language** (SurveyJS `visibleIf`): it needs a parser in two languages
  and allows backward and circular references.
- **A provenance key** (`x_intake`) naming the question file: it costs nothing in the
  contract, but nothing reads it; left out until legal ops asks for it.
