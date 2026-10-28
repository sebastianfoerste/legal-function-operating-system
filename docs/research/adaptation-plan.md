# Adaptation plan, October 2026

The research is in the [landscape](2026-10-competitive-landscape.md),
[matrix](feature-matrix.csv) and [design teardown](design-teardown.md). Review-room detail
is in [Round 3](../../supervised-agent/docs/competitive-research-2026-06-30.md#round-3-review-room-and-supervision-ux).

"Adapt" means re-implementing a pattern within this repository's rules, contracts and
standard-library stack. No competitor code, asset or wording is copied.

## Baseline

Recorded on 2026-10-20 at `351209f` on `main`, before any change.

| Measure | Baseline | After this PR |
| --- | --- | --- |
| Core tests (`make test`, unittest) | 189, OK | 192, OK |
| Agent tests (`make check` in `supervised-agent`, pytest) | 212 passed, 4 skipped | 224 passed, 4 skipped |
| `make demo` then `git diff --exit-code` | clean | clean; no committed example changed |
| `make check`, `make lint`, `make package-check` | pass | pass |
| Review-room HTML | 22,922 bytes | 39,823 bytes, still one self-contained page |

The Python 3.10 interpreter was not available in the container. 3.13 and 3.11 were, and
`make lint` targets 3.10. CI covers the rest.

The axe-core 4.x scan (WCAG 2.0, 2.1 and 2.2 A and AA rules) at 1280px found these
violations on the baseline captures:

| Surface | Baseline | After |
| --- | --- | --- |
| Pages index, control tower, RaaS deal room, customer package | 0 | 0 |
| Knowledge portal | `html-has-lang` (serious) | 0 |
| Agent snapshot `review-room.html` | `html-has-lang` (serious) | 0 |
| Review room as requester | 0 | 0 |
| Review room as matter owner (closed matter and triage matter), specialist, approver | `select-name` (critical) on 2–3 selects | 0 |
| New intake form | — | 0 |
| Review room and Pages index in dark mode | not scanned | 0 |

Artifact sizes at baseline:

| Artifact | Bytes |
| --- | --- |
| `index.html` | 5,977 |
| Control tower | 46,783 |
| RaaS deal room | 13,221 |
| Knowledge portal | 2,893 |
| Agent snapshot | 1,366 |
| Customer packages | 6,653 and 11,738 |

At 390px the matter owner's view of the specialist matter was 14,301px tall. After the
change it is 12,235px, with no horizontal scroll.

CLI transcripts:

- `triage --input examples/requests-template.csv` decided 8 requests.
- `validate` reported 0 errors and 0 warnings in 8 requests.

The MCP listing shows four tools: `triage_requests`, `board_pack`, `dpa_review` and
`legal_request_schema`.

## Best-of candidates

Score = Impact × Evidence ÷ Effort, where Evidence is Observed 3, Claimed 2, Inferred 1
and Effort is S 1, M 2, L 4. Only Fit = pass is ranked. Ties go to items from
`supervised-agent/docs/pilot/RETROSPECTIVE.md`.

The build cap is three features and two design upgrades, in rank order.

### Features

| ID | Candidate | Impact | Evidence | Effort | Fit | Score | Kind | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F1 | Required facts before submission (H1) | 5 | Observed: docassemble, claude-for-legal Matter Intake, RETROSPECTIVE B02 | S | pass | 15 | table stakes | **Built** |
| F2 | Playbook standard and fallback beside each change (H7) | 4 | Observed: claude-for-legal NDA triage table with playbook reference; own playbook fields | S | pass | 12 | table stakes | **Built** |
| F3 | Plain-language requester status (H2) | 4 | Claimed: LawVu My Work, Linear Decline | S | pass | 8 | table stakes | **Built** |
| F4 | "Also open by" presence on a matter (H3, part) | 3 | Observed: Chatwoot heartbeat, Langfuse soft lock; RETROSPECTIVE B20 | M | pass if labelled simulated | 4.5 | differentiator | Specced |
| F5 | Override-pattern report over pilot decisions | 3 | Observed: claude-for-legal playbook monitor | M | pass | 4.5 | differentiator | Specced |
| F6 | Audit-chain timeline (H8, part) | 3 | Observed: Temporal UI | M | pass | 4.5 | differentiator | Specced |
| F7 | KPI tiles with target, delta and as-of; wall-clock timers in the live room (H6) | 3 | Observed: Evidence BigValue | M | pass | 4.5 | table stakes | Specced |
| F8 | Approval-matrix view from `rules.py` and policy (H8, part) | 3 | Claimed: SpotDraft ladder | M | pass | 3 | differentiator | Specced |
| F9 | Static core intake page with per-`type` question files (H1 stretch) | 4 | Observed: docassemble, SurveyJS | L | pass (download only) | 3 | table stakes | Specced |
| F10 | Triage verbs: accept, decline with reason, duplicate, snooze (H3) | 4 | Observed: Plane | L | pass | 3 | table stakes | Specced |
| F11 | Local inbound message adapter, from a synthetic export to `legal-request.v1` drafts | 3 | Claimed: Wordsmith, Checkbox | M | pass (inbound only) | 3 | table stakes | Specced |

### Design upgrades

| ID | Candidate | Impact | Evidence | Effort | Score | Status |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Inline forms, error summary and ARIA in the review room (H4) | 5 | Observed: GOV.UK Frontend; RETROSPECTIVE | M | 7.5 | **Built** |
| D2 | Shared tokens, dark mode and narrow layout for the review room and Pages index (H5, phase 1) | 3 | Observed: GOV.UK, Evidence; own captures | M | 4.5 | **Built** |
| D3 | Print stylesheet for the customer package and board pack | 2 | Inferred | S | 2 | Specced |
| D4 | Migrate control tower, deal room, portal, snapshot and package to the tokens (H5, phase 2) | 2 | Observed: own captures | L | 1.5 | Specced |

Housekeeping, in separate commits:

- the `lang` fix for the portal and snapshot (an axe serious finding);
- `docs/CLI.md`;
- ADR 0002 on the MCP 2.x path.

## Anti-patterns

| Anti-pattern | Who does it | Evidence | Our rule |
| --- | --- | --- | --- |
| Autonomous, "invisible" completion of legal work | Flank | Claimed | Every consequential decision requires human review |
| LLM routing, risk or priority calls | Checkbox (AI triage), Wordsmith (priority classification) | Claimed | No model in the decision path |
| Bots that post outward into Slack, Teams or email | Wordsmith, Flank | Claimed | No external delivery or outreach |
| Role switching that reads as sign-in | Common in demos; not observed in a named product | Inferred | "Selecting an actor is not authentication" |
| Black-box scores | No named product confirmed; vendor snippets show severities and scores without how they are derived. Lavern, by contrast, documents its grounding score as plain string matching (Observed) | Inferred | Every rule outcome carries its reason |
| AGPL code inside MIT | Plane, Mike, SuperDoc are AGPL | Observed | Pattern sources only; no code reused |
| Snooze that keeps the SLA running without saying so, or pauses it silently | Chatwoot has no pause state | Observed | A pause needs a typed reason and shows its start |

## Positioning

Other products in this space take requests in through more channels and draft more of the
work. This repository is the one that can show its working:

- routing, service levels and approval tiers come from tested rules, and the same input
  gives the same output;
- each approval is bound to the exact version it approves;
- a hash-chained event log can block an export;
- no hidden model decides anything.

What this PR adds makes that work visible to the people in the loop. Requesters see which
facts legal needs before they submit, and a plain status afterwards. Reviewers see the
playbook position next to each change, and the evidence next to each resolution.

## Specs

### F1. Required facts before submission (built)

- **User story.** As a business requester, I see the facts legal needs before I open and
  submit a request, so my first attempt is complete.
- **References.**
  - docassemble: required by default; a missing variable is asked next (Observed,
    <https://github.com/jhpyle/docassemble/blob/master/docassemble_base/docassemble/base/parse.py>).
  - claude-for-legal Matter Intake: no write while a gate is open (Observed,
    <https://github.com/anthropics/claude-for-legal/blob/main/litigation-legal/skills/matter-intake/SKILL.md>).
  - LawVu: conditional forms (Claimed, <https://help.lawvu.com/en/articles/6824391-conditional-intake-forms>).
- **Adapted.** The five `REQUIRED_FACTS` are shown with plain labels, pre-filled from the
  synthetic scenario, and checked before the matter is opened. Missing facts are listed
  in an error summary that links to each field.
- **Done differently.**
  - No branching.
  - The server's `intake_complete` gate stays the authority.
  - The page sends only required-fact names with text values; everything else still
    comes from the fixture.
- **Acceptance.**
  - The specialist scenario opened through the form submits on version 1.
  - Without the form, the gate still refuses on `missing fact: business_owner`.
  - Non-required keys and non-text values are refused with status 400.
- **Files.**
  - `supervised-agent/src/pilot/models.py` (`REQUIRED_FACT_LABELS`, `required_fact_checklist`)
  - `src/pilot/service.py`
  - `src/pilot/api.py`
  - `src/pilot/review_room.py`
- **Tests.** `supervised-agent/tests/test_pilot_intake_ux.py`.
- **Risk.** Low. Server checks are unchanged, and the rehearsal goldens are unchanged.

### F2. Playbook position beside each change (built)

- **User story.** As a matter owner or specialist, I see the playbook's standard and
  fallback wording next to the proposed redline, so I decide against the policy and not
  from memory.
- **References.**
  - Ironclad: preferred and fallback per clause (Claimed, support recipe URL in the
    teardown).
  - LegalOn: pass or fail with references (Claimed).
  - claude-for-legal NDA triage: a playbook-reference column (Observed).
- **Adapted.** `PilotService._playbook_position` reads the rule's own
  `standard_position`, `fallback_position` and `rationale` from the playbook stored with
  the version. The room shows them in a "Playbook position" column.
- **Done differently.** Nothing is generated or ranked. The fallback position is
  negotiation information, so it is never sent to the requester view or the customer
  package.
- **Acceptance.**
  - Every change in the review view carries its rule's position.
  - The requester view does not contain the fallback text.
- **Files.** `src/pilot/service.py`, `src/pilot/review_room.py`.
- **Tests.** `test_each_change_shows_the_playbook_wording_it_was_measured_against` and
  `test_requester_view_carries_status_but_no_internal_detail`.
- **Risk.** Low.

### F3. Requester status (built)

- **User story.** As a requester, I see where my request is in plain words, what I need
  to do next and what is withheld.
- **References.**
  - LawVu My Work and status-update request (Claimed).
  - Linear Decline with a visible comment (Claimed).
  - Plane's short status vocabulary (Observed).
- **Adapted.** Six stages:
  1. Not yet submitted
  2. Received by legal
  3. In review
  4. Approved
  5. Ready for you
  6. Closed

  Each stage has one explanation and one next step. Open questions addressed to the
  requester override the next step.
- **Done differently.** No new state or clock; see ADR 0003. No SLA countdown is shown
  to the requester, because pilot service levels are internal.
- **Acceptance.**
  - Every pilot state maps to exactly one stage.
  - A closed matter never reports "waiting on you".
- **Files.** `src/pilot/requester_status.py`, `src/pilot/service.py`,
  `src/pilot/review_room.py`.
- **Tests.** In `test_pilot_intake_ux.py`.
- **Risk.** Low. German labels are not yet aligned with `shared_space.py`; see below.

### D1. Inline forms and ARIA (built)

- **User story.** As any reviewer, I take decisions in forms that tell me what is
  required, without browser dialogs, and the page works with a keyboard and a screen
  reader.
- **References.** GOV.UK Frontend: error summary, error message and focus style
  (Observed, MIT; adapted, no code copied).
- **Adapted.**
  - Every `window.prompt` and `window.confirm` is replaced by an inline form with
    labelled fields, minimum lengths, and an error summary that takes focus and links to
    each field.
  - Escape closes the form and returns focus to the trigger.
  - The required source-support confirmation is a checkbox.
  - Request-revision uses checkboxes of open comments instead of typed IDs.
  - The resolve form shows the evidence cited in the thread (RETROSPECTIVE B33–B36).
  - Navigation is labelled, the active matter carries `aria-current`, selects have labels,
    a polite live region announces results, disabled transitions show a visible reason,
    and pass or fail carries ✓ or ✗ as well as colour.
- **Acceptance.**
  - axe reports no violation on any review-room view at 1280px, in light or dark mode.
  - The page contains no `window.prompt`, `window.confirm`, `innerHTML` or `http(s)://`.
- **Files.** `src/pilot/review_room.py`.
- **Tests.**
  - `test_review_room_takes_decisions_in_labelled_inline_forms`,
    `test_review_room_guards_the_cases_the_browser_test_covers` and the existing page test.
  - `supervised-agent/tests/test_review_room_browser.py` drives the page in Chromium through
    Node Playwright. It is skipped where Node, Playwright or Chromium is missing, as in CI.
    It checks the zero-comment revision reason, error-summary focus and link, Escape and
    `aria-expanded`, hidden form rows at 390px, the "another fact" field, and cancelling
    the intake form.
- **Manual browser check**, before a release or after changing the page. Serve a rehearsal
  copy as in `supervised-agent/docs/pilot/RUNBOOK.md`, open `/pilot`, then:
  1. As the requester, open scenario 2 and press "Open the matter" with the business owner
     empty. An error summary takes focus, and its link focuses the field. Press Cancel: the
     pane says no matter was opened, and focus returns to the scenario button.
  2. Fill the business owner, open the matter and submit it. The status reads "Received by
     legal" on version 1.
  3. As the matter owner, complete triage and assign the specialist and an approver. Start
     the review. "request revision" is disabled and says a comment must exist first.
  4. Accept a change without ticking the confirmation (refused in the form), then with it
     (saved). Open "withdraw matter" and press Escape: focus returns to the button.
  5. At 390px, check that each change is one block, with no empty boxes between changes
     and no horizontal scroll. Repeat one view in dark mode.
- **Risk.** Medium for behaviour, since the commands are the same but the input paths are
  new. It was walked through in a browser: open, submit, assign, start review, accept with
  and without confirmation, escape, and resolve.

### D2. Shared tokens, dark mode and narrow layout (built)

- **User story.** As a reader on a phone or in dark mode, the review room and Pages index
  are legible and consistent.
- **References.** GOV.UK tag and focus rules; Evidence theme tokens (Observed).
- **Adapted.**
  - One `TOKENS_CSS` string, kept in the core with a copy in the agent (ADR 0001).
  - Contrast is tested in both themes.
  - Under 600px the changes table stacks per change, with labelled cells.
- **Done differently.** The other five renderers keep their colours until they are
  migrated (D4).
- **Files.**
  - `src/legal_function_os/design_tokens.py`
  - `supervised-agent/src/pilot/design_tokens.py`
  - `scripts/build_site.py`
  - `src/pilot/review_room.py`
- **Tests.** `tests/test_design_tokens.py`.

### F4. "Also open by" presence (specced)

- **User story.** As a matter owner, I see that the specialist has the same revision
  open, so we do not both write to it (RETROSPECTIVE B20).
- **References.**
  - Chatwoot: 20-second heartbeat presence (Observed, MIT).
  - Langfuse: 5-minute soft lock (Observed, MIT).
  - Plain: header avatars (Claimed).
- **Plan.**
  - `PilotApi` keeps an in-memory map of `(matter, actor) → last view time`, never
    written to the event log.
  - The matter view adds `also_open_by`: other simulated roles that loaded this matter
    within 2 minutes, and the revision they loaded.
  - The badge reads "Also open (simulated local role): Synthetic Specialist C, revision
    14".
  - Clock injectable in tests.
- **Acceptance.**
  - Never shown to requesters.
  - The text always includes "simulated local role".
  - Absent after the window passes.
- **Risk.** It looks like identity. The label rule (rule 5) is the mitigation. Whether
  views may be recorded at all is an owner decision.

### F5. Override-pattern report (specced)

- **Plan.**
  - A deterministic count of `rejected` and `amended` decisions per playbook rule across
    closed pilot matters, flagged when 5 or more fall within 12 months.
  - It goes in `metrics.py` output as a proposal list with no automatic change, as in
    the claude-for-legal monitor (Observed).
- **Acceptance.**
  - Same input, same report.
  - No playbook file is written.

### F6. Audit-chain timeline (specced)

- **Plan.** Replace the three `<details>` lists with one timeline from `history()`
  events:
  - grouped by version;
  - classified as command, refusal, decision or export;
  - showing actor, role, chain position and hash prefix;
  - with a legend.

  Modelled on Temporal UI (Observed, MIT).
- **Acceptance.**
  - The chain status sits at the top.
  - A broken chain highlights the first bad event.
  - Requesters do not see it.

### F7. KPI tiles and live timers (specced)

- **Plan.**
  - Control tower tiles gain target, delta against target, and an as-of time and source,
    following the Evidence BigValue anatomy.
  - The live review room shows elapsed wall-clock and business time from the pilot's
    two clocks via `metrics.to_parent_ledger`. No new clock is added.
  - `as_of` is injectable, and no timestamps appear in committed artifacts.

### F8. Approval-matrix view (specced)

- **Plan.** A static page generated by `make demo`. It renders `rules.approval_chain` over
  value band × risk × flags from the default policy, with each cell listing the chain.
  It is added to `EXPECTED`, `HOSTED`, `CARDS` and `verification_artifacts`.

### F9. Static intake page (specced)

- **Plan.**
  - A page generated from `validation.request_schema()` plus a per-`type` question file
    with forward-only conditions (the LawVu pattern).
  - It emits `legal-request.v1` JSON for download only.
  - It needs portal resources keyed by `type` before it can offer deflection.
- **Risk.** Any new schema field must stay optional (v1 compatibility).

### F10. Triage verbs (specced)

- **Plan.**
  - New pilot commands `decline` (reason of at least 20 characters), `mark_duplicate`
    (pointer to an existing matter) and `snooze` (until a time, or until the requester
    answers), each a hash-chained event.
  - Snooze stops nothing silently: the pilot clocks record it as waiting on the
    requester, with a reason.
  - Needs new states. Update `parent_bridge.CONTRACT_REVIEW_STATE` and
    `scripts/check_shared_contracts.py`.

### F11. Local inbound adapter (specced; the Slack, Teams and email decision)

- **Decision.** Channel intake that reads or writes a live service is rejected, because
  it breaks rule 4 and the no-network core.
- **What is allowed instead.**
  - A local, inbound-only adapter that parses a synthetic message export (JSON lines with
    `syn-` senders and fictional organisations) into `legal-request.v1` drafts.
  - Unknown fields are left blank and named, and the drafts go through `validate`.
  - Nothing is sent back.
- **What it loses compared with Wordsmith or Flank.** Real-time capture and replying in
  the same channel (Inferred).

### D3, D4

- **D3.** `@media print` rules for the customer package and board pack: one page per
  section, no navigation, and the disclaimer on every page.
- **D4.** Move the control tower, deal room, portal, snapshot and customer package onto
  `TOKENS_CSS`, one renderer per commit, with before and after captures. These change
  committed examples, so each needs `make demo` and review.

## Hypothesis verdicts

| Hypothesis | Verdict | Evidence |
| --- | --- | --- |
| H1. Required facts before submission | **Confirmed, built** in the pilot. The core stretch is **modified**: no branching exists to build on, so it is specced as F9 | docassemble, claude-for-legal (Observed); LawVu, Xakia (Claimed) |
| H2. Requester status tracker | **Confirmed, built** in the pilot room. The `shared_space.py` alignment is parked | LawVu (Claimed); Plane (Observed) |
| H3. Triage inbox with presence | **Modified.** Verbs and presence are split, F10 and F4; both specced | Plane, Chatwoot, Langfuse (Observed); Linear (Claimed) |
| H4. Review-room forms and ARIA | **Confirmed, built** (D1) | GOV.UK (Observed); RETROSPECTIVE |
| H5. One shared design system | **Modified.** One token set, applied to two surfaces now (D2) and the rest later (D4) | GOV.UK, Evidence (Observed) |
| H6. KPI dashboard with wall-clock timers | **Modified.** Tile anatomy plus live-room timers, with no new clock; specced as F7 | Evidence (Observed); LawVu (Claimed). Brightflag was not found in any search, so it is not cited |
| H7. Playbook-driven redline UX | **Confirmed, built** (F2). Python-Redlines is **parked**: it bundles a 44 MB .NET binary (ADR 0004, Proposed) | Python-Redlines wheel listing (Observed); Ironclad, LegalOn (Claimed) |
| H8. Visual governance views | **Confirmed, specced** as F6 and F8 | Temporal UI (Observed); SpotDraft (Claimed) |

## Design direction

- Keep the Pages oxblood palette. The research gave no reason to change it, and
  competitor palettes were not visible.
- Tokens extend the Pages names with `--panel`, `--pill-line`, `--on-accent`, `--ok`,
  `--warn`, `--bad`, their backgrounds, and `--focus`, with a dark block (ADR 0001).
- Type: system fonts, Georgia headings and a monospace stack for hashes. No font is
  loaded.
- Contrast: text at least 4.5:1 and focus rings and pill borders at least 3:1, tested.
  State is never shown by colour alone (✓ ✗, "Removed" and "Added" in text).
- At 390px the matter list stacks above the matter, and the redline table becomes one
  block per change with labelled cells.
- States:
  - Empty: "No change proposed", "None".
  - Error: an error summary, and "Refused: …" from the server.
  - Stale: the existing reload message.
  - Loading has no special state; actions are short local calls.
- Microcopy is plain and non-advisory: "Legal will refuse this request until…", "Your
  next step", and a line saying what is withheld.

### ADR needed (not decided here)

- Where presence data lives, and whether a view counts as an audit event (F4).
- New pilot states for decline, duplicate and snooze, and their mapping in the shared
  contract (F10).
- Per-`type` question files: format, location, and how they relate to `request_schema()`
  (F9).
- Requester-stage vocabulary shared between the pilot and the core `shared_space.py`,
  including German labels (F3).

## Needs owner decision

1. **Authentication and the 11 controls in `supervised-agent/docs/pilot/IDENTITY_CONTROLS.md`.**
   None is built. Selecting a role is still not authentication. Presence (F4) makes the
   gap more visible.
2. **`supervised-agent/.github/workflows/`** (`ci.yml`, `pre-commit.yml`,
   `release-gates.yml`). These never run from this repository. Delete them, or keep them
   for the exported repository.
3. **`supervised-agent/src/gemini_client.py`.** It is used only by its own test. The
   decision path keeps `LEGAL_AGENT_EXTERNAL_MODEL_ENABLED` false.
4. **Python-Redlines** (ADR 0004). A new dependency with a bundled native binary, or an
   extension of the stdlib DOCX writer.
5. **AI Act timing after the Digital Omnibus.**
   - `src/legal_function_os/raas_sources.py` states that the Regulation generally applies
     from 2 August 2026 and that product-linked high-risk obligations apply from
     2 August 2027.
   - Search snippets report a provisional agreement that would move Annex III to
     2 December 2027 and Annex I to 2 August 2028 (Claimed; see the landscape).
   - Official Journal publication could not be checked because EUR-Lex was not reachable.
   - Nothing was changed. This needs verification against EUR-Lex and the maintainer's
     legal review.
6. **Remote MCP and HTTP transport.** claude-for-legal wires remote connectors. This
   repository stays local over stdio (rule 4, ADR 0002).
7. **Presence records** (F4). Whether recording who viewed a matter is acceptable in the
   pilot.
8. **Channel intake** (F11). Confirm that a local inbound adapter is wanted, or that
   channel intake stays out.
9. **PyPI publication.** Still not published. Not touched here.
10. **Visual migration of committed reviewer artifacts** (D4). It changes the look of
    published pages.
11. **Candidates found outside the session's repository scope.** The GitHub topic
    listings came from a search tool that reached beyond the attached repository (see the
    landscape's Repository discovery). No matrix row depends on it; keep or drop the
    `legal-operations` topic count that does.
12. **German coverage.** Only one purely German search ran. A follow-up run should add
    German queries (for example "Legal Request Management Rechtsabteilung", "Vertragsprüfung
    Playbook", "Mandatsannahme Software Unternehmensjurist") once vendor sites are reachable.
