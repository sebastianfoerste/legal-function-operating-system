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
| Control tower and RaaS deal room at 320 and 390px (D4 scan, 2026-11-18) | `scrollable-region-focusable` (serious) on the wide tables | 0 (D4) |

The 1280px scan missed that serious finding: the wide tables scroll only at phone
width, inside a section the keyboard could not reach. The D4 scan of 2026-11-18 ran
axe-core 4.14 at 320, 390 and 1280px in light and dark mode, with the best-practice
rules as well. It also found `region` and `landmark-one-main` (moderate) on the portal,
the snapshot and the customer package, and sideways scroll on the snapshot and the
package at phone width. After D4 none of the five pages has a violation or sideways
scroll (decision 10). Captures stay local.

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
| F4 | "Also open by" presence on a matter (H3, part) | 3 | Observed: Chatwoot heartbeat, Langfuse soft lock; RETROSPECTIVE B20 | M | pass if labelled simulated | 4.5 | differentiator | **Built** |
| F5 | Override-pattern report over pilot decisions | 3 | Observed: claude-for-legal playbook monitor | M | pass | 4.5 | differentiator | **Built** |
| F6 | Audit-chain timeline (H8, part) | 3 | Observed: Temporal UI | M | pass | 4.5 | differentiator | **Built** |
| F7 | KPI tiles with target, delta and as-of; wall-clock timers in the live room (H6) | 3 | Observed: Evidence BigValue | M | pass | 4.5 | table stakes | **Built** |
| F8 | Approval-matrix view from `rules.py` and policy (H8, part) | 3 | Claimed: SpotDraft ladder | M | pass | 3 | differentiator | **Built** |
| F9 | Static core intake page with per-`type` question files (H1 stretch) | 4 | Observed: docassemble, SurveyJS | L | pass (download only) | 3 | table stakes | **Built** |
| F10 | Triage verbs: accept, decline with reason, duplicate, snooze (H3) | 4 | Observed: Plane | L | pass | 3 | table stakes | **Built** |
| F11 | Local inbound message adapter, from a synthetic export to `legal-request.v1` drafts | 3 | Claimed: Wordsmith, Checkbox | M | pass (inbound only) | 3 | table stakes | **Built** |

### Design upgrades

| ID | Candidate | Impact | Evidence | Effort | Score | Status |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Inline forms, error summary and ARIA in the review room (H4) | 5 | Observed: GOV.UK Frontend; RETROSPECTIVE | M | 7.5 | **Built** |
| D2 | Shared tokens, dark mode and narrow layout for the review room and Pages index (H5, phase 1) | 3 | Observed: GOV.UK, Evidence; own captures | M | 4.5 | **Built** |
| D3 | Print stylesheet for the customer package and board pack | 2 | Inferred | S | 2 | **Built** (customer package); board pack withdrawn |
| D4 | Migrate control tower, deal room, portal, snapshot and package to the tokens (H5, phase 2) | 2 | Observed: own captures | L | 1.5 | **Built** |

Housekeeping, in separate commits:

- the `lang` fix for the portal and snapshot (an axe serious finding);
- `docs/CLI.md`;
- ADR 0002 on the MCP 2.x path.

## Anti-patterns

| Anti-pattern | Who does it | Evidence | Our rule |
| --- | --- | --- | --- |
| Autonomous, "invisible" completion of legal work | Flank | Claimed | Every consequential decision requires human review |
| LLM routing, risk or priority calls | Checkbox (AI triage), Wordsmith (priority classification), BRYTER (AI legal front door triage) | Claimed | No model in the decision path |
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
- **Tests.** In `test_pilot_intake_ux.py`. `tests/test_requester_vocabulary.py` pins the
  six stage ids, the stage of every pilot state and the core's words (ADR 0011).
- **Risk.** Low. The core shared space keeps its own v1 words, including two German
  next-step sentences; [ADR 0011](../adr/0011-requester-vocabulary.md) records why, and
  no German stage labels are added.

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
- **Done differently.** The other five renderers kept their colours until D4 migrated
  them (decision 10).
- **Files.**
  - `src/legal_function_os/design_tokens.py`
  - `supervised-agent/src/pilot/design_tokens.py`
  - `scripts/build_site.py`
  - `src/pilot/review_room.py`
- **Tests.** `tests/test_design_tokens.py`.

### F4. "Also open by" presence (built)

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
- **Risk.** It looks like identity. The mitigation is the rule "Selecting an actor is not
  authentication": the line says "simulated local role, not authentication".
- **Built** (ADR 0005, owner decision 7 answered: in memory only).
  - `src/pilot/presence.py`: a lock-guarded board, 120-second window, injectable clock.
  - Views and command responses note the reviewer; an open room checks in every 30
    seconds through `POST /pilot/api/matters/{id}/presence`.
  - The room shows "Also open in the last two minutes (simulated local role, not
    authentication): …" with each reviewer's revision, and a pinned warning with a reload
    button that names the newest revision when the matter has moved on.
  - Follow-up fixes from the review of the merged change (#22): "older than yours" is
    relative to the viewer's loaded revision; the warning follows later writes and stays
    in view; the live text holds no clock; expired entries are dropped for every matter;
    the no-persistence and stop-polling tests now check what they claim.
  - Requesters are never shown or recorded. Nothing reaches the store, the event log or
    an export.
  - Tests: `supervised-agent/tests/test_pilot_presence.py`, and the presence and stale
    steps in `supervised-agent/tests/test_review_room_browser.py`.

### F5. Override-pattern report (built)

- **Plan.**
  - A deterministic count of `rejected` and `amended` decisions per playbook rule across
    closed pilot matters, flagged when 5 or more fall within 12 months.
  - It goes in `metrics.py` output as a proposal list with no automatic change, as in
    the claude-for-legal monitor (Observed).
- **Acceptance.**
  - Same input, same report.
  - No playbook file is written.
- **Built.**
  - `override_patterns()` in `supervised-agent/src/pilot/metrics.py`. It counts, per playbook
    rule, the closed matters whose final version keeps a `rejected` or `amended` decision.
    Each matter counts once per rule.
  - Each override is timed by its `change_decided` event, on the report's own clock
    (scripted for rehearsals, operational otherwise).
  - The 365-day window ends at the latest decision, not at the time the report is built,
    so the same store always gives the same report.
  - A rule with 5 or more overrides becomes a proposal. Its suggestion depends on the
    direction of the overrides (keep the counterparty's wording, rewrite, or both), and
    it quotes the reviewers' recorded reasons. No wording is generated.
  - The report is the "Playbook override patterns" section of `pilot-metrics.md` and
    `.json`. It feeds step 5 of the retrospective template.
  - Tests: `supervised-agent/tests/test_pilot_override_patterns.py` and the rehearsal test.
  - Done differently from the claude-for-legal monitor: no proposed wording and no write
    path. A lawyer revises the playbook as a new version.
  - **Decided on 2026-10-29:** a matter withdrawn during review counts as closed, as the
    plan says. Its reviewer recorded the override before the withdrawal, so it is still a
    signal about the playbook. A test pins this.

### F6. Audit-chain timeline (built)

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
- **Built.**
  - `build_timeline()` in `supervised-agent/src/pilot/timeline.py`. It reads the matter's
    event rows once, in chain order, and splits them into runs of one version.
  - A refusal records no version, so it goes with the version in force; an amendment is
    the last event of the version it replaced.
  - A table classifies all 22 event types the service writes. A test reads every event
    write under `src/pilot` and fails when one uses a type that is not in the table, or
    names it any way but a plain string.
  - Each event shows its class, type, actor, role, chain position and a 12-character hash
    prefix. Its "Chain record" shows the full hashes, both clocks (labelled) and the
    payload as JSON, in place of Temporal's separate JSON view.
  - The legend counts each class.
  - The chain status comes first and covers exactly the rows shown, because
    `PilotStore.check_events` checks those same rows. When the chain is broken, it gives
    the reason, says which positions are verified and which are missing, and links to the
    first event that is not verified.
  - The first bad event is marked, and every later event is marked "not verified". When
    an event's link to the one before it does not match, the one before is marked too,
    because either may have been rewritten.
  - A tampered row never stops the view: a payload or value that cannot be parsed or
    hashed is reported as a break, and a stored position that is not a number is shown
    as stored.
  - Decisions later set aside stay listed under their version with the reason.
    Findings, which are not events, keep their own list.
  - The timeline is part of the review view only, which requesters never get.
  - Tests: `supervised-agent/tests/test_pilot_timeline.py` and a browser check in
    `supervised-agent/tests/test_review_room_browser.py`.

### F7. KPI tiles and live timers (built)

- **Plan.**
  - Control tower tiles gain target, delta against target, and an as-of time and source,
    following the Evidence BigValue anatomy.
  - The live review room shows elapsed wall-clock and business time from the pilot's
    two clocks via `metrics.to_parent_ledger`. No new clock is added.
  - `as_of` is injectable, and no timestamps appear in committed artifacts.
- **Built: control tower tiles.**
  - `outcome_control_tower.py` adds `kpi_tiles`. Each tile has a title, value, target,
    signed delta, the standing in words (with ✓ or ✗ on the page), an as-of time and
    a source.
  - Targets are optional, under `kpi_targets` in the outcome config: throughput rate,
    response SLA attainment and stalled requests. Which direction is better is fixed per
    KPI in code. A rate target has at most 3 decimal places, the precision of the
    measured rate, so a tile is never shown as met and missed at once. The bundled config
    sets synthetic targets (70%, 90%, none stalled).
  - The as-of time is the ledger's own `as_of_utc`. Nothing reads the system clock, so
    the committed artifacts carry no generation time.
  - Not taken from Evidence: the neutral range and the sparkline, because a snapshot has
    no series.
  - Request rows now carry their response and resolution targets in business hours.
- **Built: time on a matter in the review room.**
  - `supervised-agent/src/pilot/timing.py` measures the matter with the parent tower
    over its events. The events are mapped by `ledger.matter_ledger`, which moved out of
    `metrics.py`, so the room and `metrics.to_parent_ledger` always agree.
  - The mapping now starts legal's time when the request is submitted to legal, not
    when the requester opens the draft. It waits on the business while any clarification
    to the requester is open, not only until the first answer. This also corrects the
    rehearsal's parent outcome report.
  - One clock per matter, never mixed: scripted when every event other than a refused
    command has a scripted time, otherwise the time the server recorded.
  - An open matter is measured to the service clock's `now`, which tests inject; it is
    read after the events, so no event shown is later. A closed one is measured to its
    closing event, and an open rehearsal matter to its latest scripted step, refusals
    included.
  - An open matter already past its response or resolution target is shown as past
    target, since it can no longer meet it.
  - The "Time on this matter" section shows elapsed calendar time, business time (with
    legal and waiting on the business), first response and resolution against their
    targets, the clock and the calendar.
  - It is measured each time the matter is loaded or changed. The page adds no clock
    and does not tick.
  - Requesters do not see it. A time that cannot be read leaves the section saying why;
    it never stops the room.
- **Fixed on the way.** The tower's Markdown and HTML failed when no first response had
  been measured yet.
- **Tests.** New cases in `tests/test_outcome_control_tower.py`,
  `supervised-agent/tests/test_pilot_timing.py`, and the review room browser test.

### F8. Approval-matrix view (built)

- **Plan.** A static page generated by `make demo`. It renders `rules.approval_chain` over
  value band × risk × flags from the default policy, with each cell listing the chain.
  It is added to `EXPECTED`, `HOSTED`, `CARDS` and `verification_artifacts`.
- **Built.**
  - `src/legal_function_os/approval_matrix.py` writes `examples/approval-matrix.md`,
    `.json` and `.html` from `make demo`. The `approval-matrix` command and the
    `--approval-matrix-output` flag write the same for any policy and requests. With
    `--policy` and no `--input`, the command places no request: the bundled sample
    requests are written for the default policy.
  - Each cell is `rules.approval_chain` for one value band and risk level, so the matrix
    cannot drift from the rules.
  - The chain depends on value band and risk only, so the flags enter through risk. The
    page lists, as a ladder after SpotDraft's (Claimed), who each threshold adds and
    what sets the risk, both read from the policy.
  - A combination no request can reach is marked "Not reachable" with the reason.
    Reachability comes from running `rules.assess_risk` over every band, flag and kind of
    request type; a test fails if `assess_risk` reads another field through `get`, `[]`
    or `in`.
  - Each portfolio request is placed in the cell its decision names, which highlights
    the path it takes (the teardown's "matched path").
  - The page uses the shared design tokens (light, dark, narrow layout) and is
    self-contained. It was added to `EXPECTED`, `HOSTED`, `CARDS` and
    `verification_artifacts`.
  - Tests: `tests/test_approval_matrix.py`.
  - A review found 14 problems in the page, the Markdown, the command, the docs and
    the tests, fixed in a follow-up: a blank elevated type broke reachability; a cell
    holding a request is now always reachable; `--policy` without `--input` places no
    request; Markdown flattens line breaks and gives the reason a cell is not
    reachable; long band names wrap instead of being cut off, and short request IDs
    and bands no longer break at the hyphen; the placement marker no longer uses ✓,
    which elsewhere in the project means pass; and the tests now cover a policy with
    every threshold on its own band, the exact ladder text and every enumerated input.

### F9. Static intake page (built)

- **Plan.**
  - A page generated from `validation.request_schema()` plus a per-`type` question file
    with forward-only conditions (the LawVu pattern).
  - It emits `legal-request.v1` JSON for download only.
  - It needs portal resources keyed by `type` before it can offer deflection.
- **Risk.** Any new schema field must stay optional (v1 compatibility).
- **Built.**
  - `src/legal_function_os/intake_page.py` writes `examples/intake-page.html` from
    `make demo`, and the `intake-page` command writes it for any policy and question
    file. The format and its rules are [ADR 0006](../adr/0006-intake-question-files.md).
  - The request fields, their order and controls come from `request_schema()`; value
    bands and request types from the policy. The question file
    (`src/legal_function_os/data/intake_questions.json`) adds wording, a question set per
    type, `also_required` and `show_if` conditions, which may name only an answer given
    above the question; it can leave an optional field unasked, never a decision field. A test places every contract field, so a new one fails the
    build until it is placed.
  - The decision fields are always asked, with nothing preselected. Type answers go into
    `facts`, sorted by key as the pilot's bridge writes them; the commercial-contract
    questions are the pilot's required facts, and a test reads them from
    `supervised-agent/src/pilot/models.py`.
  - The page shows an error summary (D1 pattern), a "Check your answers" step with the
    exact file, and saves it locally. It has no form and no network or navigation code,
    and a hashed Content-Security-Policy blocks every fetch, form post and resource load.
  - Tests: `tests/test_intake_page.py` checks about 11,500 answer combinations per
    policy against an independent statement of what is missing, runs the roughly 1,500
    the page accepts through `validate_requests`, and runs all of them through the page's
    own script in Node against the Python reference; `tests/test_intake_page_browser.py`
    drives the page in Chromium in the CI agent job, including going back to it.
- **Done differently.**
  - One question file keyed by type, not one file per type (type keys are free text).
  - The page numbers nothing: every file is `REQ-DRAFT` and legal renumbers.
  - No deflection in F9; it came later as F9a, from a team's own guidance file
    ([ADR 0012](../adr/0012-intake-guidance.md)).
  - No submit and no legacy all-in-one flag: the page does not read requests.

### F9a. Deflection by type (built)

- **Plan.** Offer approved guidance for the chosen request type before the requester
  saves a file, for example a template or an answered question.
- **Prerequisites.**
  - Guidance resources with an approval record, a `source_ref` and an optional `type`
    key, additive to the knowledge portal's `portal.share.v1`. Today's portal resources
    are other requests' passages with `approved: True` set in code, so they cannot be
    shown to a requester (ADR 0003).
  - The page shows the resources for the chosen type with their source, abstains when
    there are none, and never blocks, replaces or delays the download.
- **Risk.** Deflection text without an approval record would be advice the page gives on
  its own; the portal's rule (cite an approved resource or abstain) applies.
- **Built** ([ADR 0012](../adr/0012-intake-guidance.md)).
  - `legal-function-os intake-page --guidance PATH` reads a team's own guidance file,
    `legal-function-os.intake-guidance.v1`. A resource has the four `portal.share.v1`
    keys, an optional `type`, `prepared_by` and a review record, `approval`: who reviewed
    the text for requesters (`by`), when (`on`) and `text_sha256`, the SHA-256 of the
    type, title, passage and source as the file gives them. A text changed after its
    review no longer matches, and the message names the digest it has now.
  - Every problem is reported at once with its place, and nothing is written: a missing
    or stale record, a review recorded by the person who prepared the text (compared
    after folding case, spacing and invisible characters), a date that is not one, a
    link or unpaired surrogate, a passage over 800 characters, more than three resources
    for a type, a repeated id, look-alike titles in a type, or an unknown key. A resource
    with no type, or a type the policy lacks, is a note. A portal document is refused.
  - The page shows the chosen type's guidance as static text at the top of its section,
    under "Guidance from legal for this kind of request" and a line saying it is general
    information, not legal advice, and optional. Each text shows its source and "Legal's
    guidance file records that NAME reviewed this text for requesters on DATE." It has
    no link or control and never blocks, replaces or delays the download, and no word
    the page adds says approved.
  - Guidance stays out of the page script and its data block, so the checks, the review
    and the saved file are the same with and without it. A browser test saves the same
    answers from both pages and compares the files byte for byte.
    `examples/intake-page.html` changed only in its style block and style hash.
  - Tests: `tests/test_intake_guidance.py`, and `GuidedPageBrowserTests` in
    `tests/test_intake_page_browser.py`.
- **Done differently.**
  - Nothing is bundled, so the default page, `make demo` and the Pages copy show no
    guidance: a bundled synthetic review record would be an approval nobody gave.
  - The record names who reviewed which text and when, bound to the text by its digest,
    instead of the portal's `approved` flag. `portal.share.v1` is unchanged, and its
    resources cannot be used as guidance.
  - The page never matches a requester's words against guidance; the type the
    requester chooses is the only key.
  - A review record is not authentication: anyone who can edit the file can type a name
    and copy a digest. The core reads no clock, so old guidance is not refused by age.
  - Left to the owner, not blocking: whether a clearly labelled example should ever
    appear on Pages (recommended: no), and who in a real team may record a review.

### F10. Triage verbs (built)

- **Plan.**
  - New pilot commands `decline` (reason of at least 20 characters), `mark_duplicate`
    (pointer to an existing matter) and `snooze` (until a time, or until the requester
    answers), each a hash-chained event.
  - Snooze stops nothing silently: the pilot clocks record it as waiting on the
    requester, with a reason.
  - Needs new states. Update `parent_bridge.CONTRACT_REVIEW_STATE` and
    `scripts/check_shared_contracts.py`.
- **Built** ([ADR 0010](../adr/0010-triage-verbs.md)).
  - `decline` and `mark_duplicate` move a matter from `triage` to two new final states,
    `declined` and `duplicate`, which accept no further command. Both need a reason of at
    least 20 characters. A duplicate names an original the owner can see that is not
    itself a duplicate; an unknown and a hidden matter get the same refusal. Each is also
    kept in the decision record, bound to the version it closed.
  - A snooze is not a state. `snooze` records a reason of at least 20 characters and
    either a time with a time zone, at most 30 days ahead, or a question for the
    requester. The requester's answer (`answer_snooze`), the owner's `end_snooze`, a
    triage verb or a withdrawal ends it, and so does its time passing, which writes no
    event: `src/pilot/snooze.py` works it out from the events on the matter's clock for
    every reader.
  - All three run only in triage, for an onboarded matter owner, and claim the matter as
    `complete_triage` does. So a matter owner can now close a matter that cannot leave
    triage; before, only the requester could withdraw it.
  - A person types every reason the requester sees; the room proposes none. The requester
    sees "Closed: declined by legal" or "Closed: duplicate of another matter" with the
    reason, and the original only if they asked for it too. During a snooze the stage stays
    "Received by legal", with the reason, and with a question the room offers an Answer
    form.
  - Shared contract: both new states map to `rejected`, which takes precedence over
    `blocked`. Clocks: a snooze is a wait on the business in the parent ledger and in the
    pilot metrics; on a request legal has not acknowledged it is legal's first response.
    A decline or duplicate has no resolution target, as for a withdrawal.
  - Tests: `supervised-agent/tests/test_pilot_triage_verbs.py`, and the triage step in
    `supervised-agent/tests/test_review_room_browser.py`. The blocked-matter test now
    tries 19 commands as each actor.
- **Done differently.**
  - Only decline and duplicate are states. A `snoozed` state would need a timer to leave
    it, which would act on the matter without a person.
  - No `accept` verb: `complete_triage` is accept.
- **Known, out of scope.** A withdrawn matter is still reported `approved` in the shared
  contract, and parent tower rows for matters closed without delivery stay open.

### F11. Local inbound adapter (built; the Slack, Teams and email decision)

- **Decision.** Channel intake that reads or writes a live service is rejected, because
  it breaks the rule "Do not add external delivery, publication, filing or outreach
  actions" and the no-network core.
- **What is allowed instead.**
  - A local, inbound-only adapter that parses a synthetic message export (JSON lines with
    `syn-` senders and fictional organisations) into `legal-request.v1` drafts.
  - Unknown fields are left blank and named, and the drafts go through `validate`.
  - Nothing is sent back.
- **What it loses compared with Wordsmith or Flank.** Real-time capture and replying in
  the same channel (Inferred).
- **Built.**
  - `src/legal_function_os/message_drafts.py` and the `message-drafts` command read a
    JSON-lines export (`message_id`, `sender`, `text`; optional `channel`, `sent_at`,
    `subject`) and write `message-drafts.json` and `message-drafts.md`. `make demo` writes
    them from the bundled export, `src/legal_function_os/data/sample_messages.jsonl`, to
    `examples/`. The format and its rules are [ADR 0009](../adr/0009-message-drafts.md).
  - Every sender must be a `syn-` handle, the pilot's pattern. That marks the data as
    synthetic and says nothing about who sent a message; senders are not verified.
  - Values are copied only from labelled lines, matched like CSV headers, and as written.
    Prose, quoted replies and list items are not read. Labels for fields legal sets,
    misspelled labels and fields given two different ways are noted and not copied.
  - Every draft holds the seven fields the intake page always asks. One a message does not
    state is `""` and named. Every blank but `type` is an error, so `validate` and `triage`
    refuse the draft until legal fills it; left out, the field would take its default and
    could lower the risk. A blank `type` is only a warning: the draft validates, and
    `triage` decides it, marked for manual triage, without the type's own rules, so legal
    fills it before triage.
  - Drafts are `REQ-DRAFT-1` and so on in message order, with the message id in
    `x_message_id`; nothing goes into `facts`.
  - It is a CLI command, not an MCP tool, and it imports no network, mail or process
    module.
  - Tests: `tests/test_message_drafts.py` (the export checks, the mapping, the committed
    examples, the MCP and import boundaries), `tests/test_bundled_data.py` and
    `tests/test_cli_subcommands.py` (every command is in `docs/CLI.md`).
- **Done differently.**
  - `.eml` and mailbox files, real chat exports and replies stay out; each needs a new
    owner decision.
  - A label that misspells a request field is noted the way a CSV header is, so `Urgent`
    is not taken for `urgency`; the field stays blank and named.

### D3, D4 (built)

- **D3.** `@media print` rules for the customer package and board pack: one page per
  section, no navigation, and the disclaimer on every page.
  - **Built for the customer package** (decision 10). Each numbered section starts a
    new page and table headers repeat. An `@page` footer prints the synthetic-data
    notice (the internal-review notice for a draft) and "Page N of M" on every page.
    The package has no navigation to hide. The footer was checked in Chromium only.
  - **Withdrawn for the board pack.** It has no HTML page, only Markdown and JSON, so a
    print stylesheet would mean a new artifact. An HTML board pack would be a new
    candidate.
- **D4.** Move the control tower, deal room, portal, snapshot and customer package onto
  `TOKENS_CSS`, one renderer per commit, with before and after captures. These change
  committed examples, so each needs `make demo` and review.
  - **Built** (decision 10), one commit per renderer. Wording and layout stayed the
    same: at 1280px the control tower, portal and packages are as tall as before, and
    the deal room is 5px taller. Each page gained dark mode, a phone layout and
    `PRINT_CSS`, the shared print block, which prints the light palette. The control
    tower, deal room and portal also gained a focus ring; the snapshot and package
    have nothing to focus.
  - Only `examples/legal-outcome-control-tower.html` and `examples/raas-deal-room.html`
    changed among the committed examples. The deal room's EUR-Lex links are unchanged.
  - `tests/test_reviewer_pages_browser.py` checks the two published pages and the
    portal in a browser: no sideways scroll at 320 and 390px, dark mode, keyboard reach
    of every scrolling table, and light print in dark mode.

## Hypothesis verdicts

| Hypothesis | Verdict | Evidence |
| --- | --- | --- |
| H1. Required facts before submission | **Confirmed, built** in the pilot. The core stretch is **modified** and built as F9: a static intake page with per-type questions that saves a request file. Deflection is built as F9a from a team's own guidance file, each text with a review record, and none is bundled (ADR 0012) | docassemble, claude-for-legal (Observed); LawVu, Xakia (Claimed) |
| H2. Requester status tracker | **Confirmed, built** in the pilot room. The core shared space keeps its own v1 words (ADR 0011): its `in_review` is the pilot's stage, `blocked` stays a core flag, and no German labels are added | LawVu, Legisway (Claimed); Plane (Observed) |
| H3. Triage inbox with presence | **Modified.** Verbs and presence are split, F10 and F4. F4 is built (in memory only); F10 is built (ADR 0010): decline and duplicate are final states, and a snooze is a recorded pause with a typed reason, not a state | Plane, Chatwoot, Langfuse (Observed); Linear (Claimed) |
| H4. Review-room forms and ARIA | **Confirmed, built** (D1) | GOV.UK (Observed); RETROSPECTIVE |
| H5. One shared design system | **Modified.** One token set, applied to two surfaces first (D2) and to the other five in D4, built | GOV.UK, Evidence (Observed) |
| H6. KPI dashboard with wall-clock timers | **Modified.** Tile anatomy plus live-room timers, with no new clock; built as F7 | Evidence (Observed); LawVu (Claimed). Brightflag was not found in any search, so it is not cited |
| H7. Playbook-driven redline UX | **Confirmed, built** (F2). Python-Redlines is **not adopted**: it bundles a 44 MB .NET binary (ADR 0004, Accepted); tracked changes are attributed per change in the stdlib writer | Python-Redlines wheel listing (Observed); Ironclad, LegalOn (Claimed) |
| H8. Visual governance views | **Confirmed.** F6 and F8 are built | Temporal UI (Observed); SpotDraft (Claimed) |

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

- ~~Where presence data lives, and whether a view counts as an audit event (F4).~~ Decided in ADR 0005.
- ~~New pilot states for decline, duplicate and snooze, and their mapping in the shared
  contract (F10).~~ Decided in ADR 0010.
- ~~Per-`type` question files: format, location, and how they relate to `request_schema()`
  (F9).~~ Decided in ADR 0006.
- ~~Requester-stage vocabulary shared between the pilot and the core `shared_space.py`,
  including German labels (F3).~~ Decided in ADR 0011.

## Needs owner decision

1. **Authentication and the 11 controls in `supervised-agent/docs/pilot/IDENTITY_CONTROLS.md`.**
   **Decided on 2026-11-18** (ADR 0008): authentication is not built here. Sign-in through
   OIDC or SAML needs the organisation's identity provider and network access, and this
   repository uses neither. Controls 1 to 11 in
   `supervised-agent/docs/pilot/IDENTITY_CONTROLS.md` stay preconditions for practitioner
   use. What is built is local hardening of the pilot server. It is not authentication. The
   server refuses to start on an address that is not loopback. It answers only its own
   `Host` names, as before. It refuses a request whose `Origin` is not its own. No page on
   another origin may frame it. Its request log leaves out presence check-ins that reach
   the review-room API. Tests now prove that a final approval is refused when the
   approver holds too low a tier, is also the requester or matter owner, or decided a
   change; no command can make the matter owner the approver, so that test writes the
   assignment directly into the store. These rules compare actor IDs, not people. A
   per-start secret was considered and not built: anyone at the machine could still read
   it, and it would look like a sign-in. Selecting a role is still not authentication.
   Since 2026-11-19 no command can change a registered actor either, which narrows control
   3 ([follow-up 2](#follow-ups-after-the-owner-decisions-2026-11-19)).
2. **`supervised-agent/.github/workflows/`** (`ci.yml`, `pre-commit.yml`,
   `release-gates.yml`). **Decided on 2026-11-18: deleted.** GitHub runs workflows only
   from the root `.github/workflows`, so these never ran here. The root CI's `agent` job
   already runs the agent's full gate (`make -C supervised-agent check`, with pinned tools
   and browser tests). The export target, `legal-ops-agent`, is archived, and a path
   export could not pass its own pilot tests without the parent package. The agent's
   `dependabot.yml` and `CODEOWNERS` were removed with them for the same reason, and its
   `.pre-commit-config.yaml` because the only thing set up to run it was that `pre-commit`
   workflow. `tests/test_agent_gate.py` keeps it that way.
3. **`supervised-agent/src/gemini_client.py`.** **Decided on 2026-11-18: removed.** The
   agent has no external model client. The client, its test, the unused Gemini model list
   `src/config.py`, `.env.example` and the `LEGAL_AGENT_EXTERNAL_MODEL_ENABLED` switch are
   gone. `google-genai` and the unused `python-dotenv` left the runtime lockfile, which now
   pins pydantic and its four dependencies. A model call would be a new, reviewed change
   with its own controls, not a setting. `supervised-agent/tests/test_no_external_model.py`
   checks the lockfile, the imports and `mcp.json`.
4. **Python-Redlines** (ADR 0004). **Decided on 2026-11-18:** not adopted. It would add a
   dependency and a 44 MB bundled .NET binary that runs as a subprocess. Word tracked
   changes stay in the stdlib writer, `supervised-agent/src/docx_redline.py`. That writer
   already wrote `w:ins` and `w:del` with an author and a date, but with one label and the
   export time for the whole file. Now each tracked change names the simulated local role
   that decided it and the time that decision was recorded. In an internal draft every
   label starts "DRAFT, not approved", and an undecided change is marked as a playbook
   proposal. A change decided as "rejected" writes no tracked change. The names are
   simulated local roles, not authenticated identities. Tables, Word comments and
   `w:trackRevisions` stay out of scope. Python-Redlines comes back only through a new
   ADR, if the owner accepts a bundled binary.
5. **AI Act timing after the Digital Omnibus.** **Settled on 2026-10-29 by PR #15.**
   - `src/legal_function_os/raas_sources.py` now follows the amending regulation and
     records when each source was re-checked against the EUR-Lex consolidated texts. That
     file is the record; this plan restates no date or citation.
   - The research for this plan saw only search snippets (Claimed) and could not reach
     EUR-Lex, so it changed nothing.
6. **Remote MCP and HTTP transport.** **Decided on 2026-11-18** (ADR 0007): the MCP
   server stays a local process. The MCP client starts it and talks to it over stdio. It
   offers no HTTP or SSE transport and no transport, host or port option. It does not
   authenticate callers, because nothing reaches it over a network. The plugin's
   `.mcp.json` starts only this local server and connects no remote services, unlike
   claude-for-legal, which wires remote connectors. A remote server would need real
   authentication (decision 1) and would send request data over a network. Remote
   connectors would add signing, posting and filing, against the rule "Do not add
   external delivery, publication, filing or outreach actions". Tests in
   `tests/test_mcp_server.py` keep it this way. Reopening this needs a new ADR that
   settles authentication first.
7. **Presence records** (F4). **Decided on 2026-10-28:** in memory only, never stored or
   logged, never shown to or recorded for requesters (ADR 0005).
8. **Channel intake** (F11). **Decided on 2026-11-18** (ADR 0009): a local inbound
   adapter is built; live channel intake stays out. `legal-function-os message-drafts`
   reads a message export saved as JSON lines, one message per line, and every sender must
   be a synthetic `syn-` handle. That check marks the data as synthetic; it is not an
   identity, and senders are not verified. The command connects to no Slack, Teams or mail
   service, captures nothing live and sends nothing back. It copies only labelled lines
   such as `Value band: <50k`, with labels matched the way CSV headers are, and reads
   nothing from the rest of the text. The subject becomes the title, and the whole text
   the description. Every draft holds every field the intake page always asks. A field the
   message does not state is left blank (`""`) and named. Every blank but `type` is an
   error, so `validate` and `triage` refuse the draft until a person in legal fills it;
   left out, the field would take its default and could lower the risk. A blank `type` is
   only a warning: the draft validates, and `triage` decides it, marked for manual triage,
   without the type's own rules, which can lower the risk, so legal fills it before
   triage. Drafts are numbered `REQ-DRAFT-1`, `REQ-DRAFT-2` and so on in
   message order, each keeps its message id in `x_message_id`, and legal renumbers them.
   It is a CLI command, not an MCP tool, so no model feeds it messages or fills its
   blanks. `.eml` and mailbox files, real chat exports and replies stay out; each would
   need a new owner decision.
9. **PyPI publication.** **Decided on 2026-11-18: publish later, and only the owner
   publishes.** The package is not on PyPI, and PyPI had no project named
   `legal-function-os` when this was decided (HTTP 404). Until it is published, the
   repository says so and gives only install commands from git or from a clone. A test,
   `tests/test_install_docs.py`, fails if a user-facing file tells anyone to install it
   by name. The owner publishes when all of these hold:
   - A release pull request raises `__version__` above 0.3.0, moves the changelog's
     Unreleased section under the new version, and updates `CITATION.cff`.
   - In the same pull request, the README works as the PyPI page: install by name,
     absolute links and an absolute image. The by-name test and the git-only wording are
     removed.
   - On PyPI, a trusted publisher for `legal-function-os` names this repository,
     `release.yml` and the environment `pypi`.
   - The GitHub environment `pypi` requires the owner's approval.
   - The repository variable `PYPI_PUBLISH` is `true`.
   - The owner publishes a GitHub release tagged `v<version>`. A manual run of the
     workflow skips the tag check, so it is not used.

   The last four steps are the owner's alone.
10. **Visual migration of committed reviewer artifacts** (D4), with print rules (D3).
    **Decided on 2026-11-18**, as recommended at the owner's request:
    - All five renderers moved to the shared tokens, one renderer per commit: the control
      tower, the RaaS deal room, the knowledge portal, the agent snapshot and the
      customer package.
    - Layout and wording stay the same. Colours, fonts, dark mode and the phone layout
      change. The control tower, deal room and portal gain a focus ring; the snapshot
      and customer package have nothing to focus.
    - Each commit has before and after captures, kept locally, and its message records
      the axe and sideways-scroll numbers. axe finds no violation at 320, 390 and 1280px
      in light or dark mode.
    - The same commits fix what axe found:
      - tables that scroll at phone width but could not take keyboard focus (control
        tower, deal room);
      - content outside a main landmark (portal, snapshot, package);
      - sideways scrolling (snapshot, package).
    - The deal room keeps its EUR-Lex source links unchanged; a test pins them.
    - A shared print block makes every migrated page print in the light palette.
    - D3 is narrowed to the customer package. Each numbered section starts on a new
      page, and table headers repeat. The synthetic-data notice and the page number
      print at the foot of every page.
    - The board pack has no HTML page, so it stays Markdown and JSON. An HTML board pack
      would be a new candidate.
    - The dated rehearsal of 6 October 2026 is a record and is not regenerated.
    - The published control tower and deal room change only when the owner merges and
      the Pages workflow publishes.
11. **Candidates found outside the session's repository scope.** **Decided on 2026-11-18:
    dropped.** The `legal-operations` topic count came from a GitHub search that reached
    beyond the session's repository scope, so the landscape no longer states it. Its
    Repository discovery keeps the disclosure. The open-source picture rests on the 17
    cloned repositories and the owner's curated lists, as weak evidence. No matrix row or
    verdict changed.
12. **German coverage.** **Decided on 2026-11-18: run now, at search level.** Twelve German
    searches ran, including the three named here; see the landscape's
    [German follow-up](2026-10-competitive-landscape.md#german-follow-up-2026-11-18).
    The vendor pages tried were still not reachable, so every new fact is Claimed. The
    matrix gained otris and DEPLAW, and the Wolters Kluwer, BRYTER and Onit rows were
    updated. No hypothesis verdict changed. Reading the vendor pages waits until the owner
    allows those hosts in the environment's network settings.
13. **Intake page defaults** (F9). **Decided on 2026-11-03** (ADR 0006): the page is hosted
    on Pages with its made-up-details notice; the three decision flags keep the "Not sure?
    Choose Yes and say why" hint; every file is `REQ-DRAFT` and legal renumbers; no
    `x_intake` key.
    - The bundled wording was reviewed on 2026-11-04 for accuracy and requester safety.
    - **The open legal and policy questions were settled on 2026-11-11**, at the owner's
      request of 2026-11-10, after research against EUR-Lex primary sources:
      [Intake wording: legal and policy review](2026-11-intake-legal-review.md). In short:
      - "who decides what the data is used for", with a joint-controller answer;
      - personal data includes data that can be linked to a person, such as IDs, IP
        addresses or coded data;
      - access from outside the EEA is reported, the UK and Switzerland are named as outside;
      - a plain definition of sub-processor;
      - `uncapped_liability` means our side's liability is or would be uncapped (no cap in
        the draft, or claims with no cap), not the usual exceptions;
      - a value band is the yearly value for anything longer than a year, the total
        otherwise, the amount claimed for a claim and the amount lent or invested for a
        loan or an investment; a figure on a boundary goes in the band that starts there,
        so EUR 250,000 is `250k-1m` (`>1m` means over EUR 1 million);
      - the pilot's label reads "Changes the other party asked for".
    - What remains a lawyer's call in a given case is listed at the end of that memo.

## Follow-ups after the owner decisions (2026-11-19)

Five small corrections made after the decisions above. None needed the owner.

1. **The agent's word filter is removed.** `supervised-agent/src/intelligence_core.py`
   replaced words such as "leverage" and "delve" in any text it was given. Its only
   caller was the Gemini client removed under decision 3. Applied to a contract it would
   have rewritten defined terms ("Leverage Ratio" became "use Ratio"), so it and its test
   were removed rather than wired in elsewhere.
2. **A registered pilot actor cannot be changed.** `register_actor` used to replace an
   actor without writing an event, and the export gate reads the author of each recorded
   decision as stored now: re-registering the General Counsel approver with a lower tier
   made a recorded approval stop counting. It now refuses a change to an actor's display
   name, role, specialty, approval tier or availability. Registering the same actor again
   keeps its onboarding, so `pilot seed` no longer resets it. The approval-refusal tests
   write their promotions directly into the store. Control 3 in `IDENTITY_CONTROLS.md` is
   narrower but stays open ([ADR 0008](../adr/0008-pilot-local-hardening.md), amended).
3. **The research documents quote rules in their own words.** The design teardown and this
   plan named rules by numbers that no rule list uses. The landscape's counts now follow
   the matrix: in 15 rows every capability cell is unknown, so 52 rows hold capability
   data. Flank, Josef, Eudia and GC AI are listed as adjacent products, as the matrix has
   them. `tests/test_research_docs.py` recomputes the counts and rings from the matrix.
4. **CI rejects a dirty tree after the agent gate.** The CI agent job ends with a step that
   fails if the agent gate or the browser tests changed a tracked file or left an untracked
   one; `tests/test_agent_gate.py` keeps it the last step.
5. **Stale statements are corrected.** The agent reports `"external_processing": "none"`,
   because no setting can turn external processing on. The agent README counts nine
   MCP-style tools and says that `supervised-agent/mcp.json` starts the runtime canary, an
   HTTP server on a loopback address, not an MCP stdio server; whether to keep, remove or
   replace that file is the owner's call, and a stdio server would add the `mcp` SDK to the
   agent as a new dependency. The agent's contributing guide names `make check` and
   `scenario-docs` instead of a `make demo` it does not have. The Round 3 research note has
   a dated update saying its parked patterns are built, and the root `.gitignore` no
   longer excepts the removed `.env.example`.
