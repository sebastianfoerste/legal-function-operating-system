# Design teardown, October 2026

Companion to the [competitive landscape](2026-10-competitive-landscape.md). Access date
for every source is 2026-10-20. Tags: **Observed** (source code or a repository page read
directly), **Claimed** (search snippet only, since vendor sites were unreachable), and
**Inferred** (our reasoning). Vendor UI was not seen, so vendor design-language cells are
mostly unknown. Where the open-source code shows the design, it is described instead.

Capture files named below are this repository's own screenshots, kept in the git-ignored
`research/_captures/baseline/` and `research/_captures/after/` folders. They are not
committed.

## Top 8 teardowns

### 1. Claude for Legal (Anthropic, Apache-2.0)

Sources: <https://github.com/anthropics/claude-for-legal>; the files cited are under
`commercial-legal/` and `litigation-legal/`. All Observed.

- **Job and buyer.** Twelve Claude plugins for in-house and law-firm lawyers, at
  version 1.0.2. They ship through the same plugin marketplace as this repository.
- **Core flow.** The Matter Intake skill asks ten fixed sections in order, each with a
  closed vocabulary.
  - The conflicts check is a hard gate. There are three ways forward: clear it, mark it
    pending with an owner and a due date, or record a permanent override.
  - Before writing, the skill shows the row it will write and asks for edits.
- **Uncertainty.**
  - Provenance tags on citations, with `[model knowledge — verify]` as the default.
  - A "draft the options, not the decision" rule for next steps.
  - The NDA triager falls back to YELLOW when no attorney has reviewed the playbook
    positions.
- **Trust mechanics.**
  - The Escalation Router only drafts the message.
  - The playbook monitor proposes a revision after 5 deviations in 12 months, shows the
    exact −/+ diff, and writes only on an explicit yes.
  - Agents never call each other; hand-offs are validated against an allowlist.
- **Integrations.** Remote HTTP MCP servers for Ironclad, DocuSign, iManage, TopCounsel,
  Definely, Slack and Google Drive. `CONNECTORS.md` asks that write tools need
  confirmation and that results carry provenance.
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adopt | Name every gap before writing | `src/pilot/review_room.py` intake form, built here |
  | Adapt | The 5-in-12-months override monitor, as a deterministic report over pilot decisions | `src/pilot/metrics.py`, built (F5) |
  | Reject | LLM drafting in the decision path | — |

### 2. Checkbox

Sources: <https://www.checkbox.ai/software/legal-intake-software>,
<https://blog.checkbox.ai/blog/implementation-guide/which-tools-let-in-house-lawyers-route-requests-automatically-based-on-region-and-matter-type-6b76cb>,
<https://capterra.com/p/207146/Checkbox/reviews/>. All Claimed.

- **Core flow.** Email, Slack, Teams or a web form, then one record, classification and
  routing by matter type, business unit, expertise and capacity. Low-risk questions go to
  self-service; exceptions become tracked work.
- **Design language.** Unknown; no UI was seen. Reviewers ask for smoother responsiveness
  and say rule-heavy projects get unwieldy (paraphrased).
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adopt | One canonical record whatever the channel | Already true via `contracts/legal-request.v1.schema.json` |
  | Adapt | Routing on explicit attributes. Here it is rules, not classification | `rules.py`, unchanged |
  | Reject | Opaque AI triage | — |

### 3. LawVu

Sources: <https://help.lawvu.com/en/articles/6824391-conditional-intake-forms>,
<https://help.lawvu.com/en/articles/5913119-the-lawvu-business-portal-for-business-users>,
<https://help.lawvu.com/en/articles/15266786-lawvu-mcp-server>. All Claimed.

- **Core flow.**
  - Conditional "controlling fields": only earlier fields can control later ones.
  - Requesters see a "My Work" grid and can ask for a status update.
- **Trust mechanics.** The MCP server is off by default, and the vendor recommends human
  approval for any write an AI starts.
- **Design language.** A grid list with a preview pane; other details unknown.
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adopt | Forward-only conditions, if branching is added | Specced as F9 |
  | Adapt | A requester list of own matters with plain stages | `src/pilot/requester_status.py`, built |
  | Reject | An MCP write surface | Rule 4 |

### 4. Ironclad

Sources:
<https://support.ironcladapp.com/hc/en-us/articles/34018339425303-Recipe-Build-a-Playbook-to-Help-Legal-Reduce-Negotiation-Time>,
<https://support.ironcladapp.com/hc/en-us/articles/34164717490327-Recipe-Build-an-AI-Playbook-for-Non-Legal-Users-to-Handle-First-Pass-Redlining>,
<https://g2.com/products/ironclad/reviews?page=2>. All Claimed.

- **Core flow.**
  - Each playbook clause has preferred language, fallbacks and approvers.
  - Clauses that do not match land in a "Needs Review" section.
  - Redline options are listed from the fewest changes to the most.
  - Skipping a change can require an extra approver.
- **Design language.** Reviewers report search that is hard to use, a steep learning
  curve and noisy approval notifications (paraphrased).
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adopt | Preferred and fallback position beside each change | `review_room.py` "Playbook position" column, built |
  | Adapt | "Needs Review" bucket | Already present as the pilot's coverage-gap comments |
  | Reject | Generated redline variants | — |

### 5. LegalOn

Sources: <https://legalontech.com/post/ai-ready-playbooks>,
<https://www.legalontech.com/products/contract-review>,
<https://www.legalontech.com/post/matter-dashboard-a-real-time-view-of-legals-work-and-impact>.
All Claimed.

- **Core flow.**
  - Choose a playbook (bundled or your own).
  - See pass or fail per rule with clickable references and Low, Medium or High
    severity.
  - Redlines are grounded in fallback and preferred language.
- **Reporting.** A matter dashboard by type, with drill-down by custom field.
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adopt | Pass or fail per rule, each with a reference | Already present: source verification per change |
  | Adapt | Dashboard drill-down | Specced as F7 |
  | Reject | AI-authored playbooks without a lawyer's sign-off | — |

### 6. SpotDraft

Sources: <https://releases.spotdraft.com/announcements/conditional-assignment-of-approvers>,
<https://help.spotdraft.com/hc/en-us/articles/27553480729757>,
<https://help.spotdraft.com/articles/7592920219-using-advanced-mode-in-condition-builder>.
All Claimed.

- **Core flow.** Intake variables feed a library of named conditions, and an If / Else If
  / Else ladder assigns approvers. Direct and conditional assignment are separate modes.
- **Design language.** A visible ladder of branches, with a formula mode for power users.
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adapt | Render `rules.approval_chain` as a matrix of value band × risk × flags, with the matched path highlighted | `scripts/build_site.py` + `rules.py` (F8, from H8), specced |
  | Adopt | A mandatory Else | Already true: the chain always ends with a human tier |

### 7. Linear Triage and Plane Intake

Sources:
- Linear: <https://linear.app/docs/triage>, <https://linear.app/docs/snooze> (Claimed).
- Plane: <https://github.com/makeplane/plane/blob/preview/apps/api/plane/db/models/intake.py>,
  <https://github.com/makeplane/plane/blob/preview/apps/api/plane/bgtasks/issue_activities_task.py>
  (Observed, AGPL, pattern only).

- **Core flow.** Four verbs: Accept, Duplicate, Decline with a reason, and Snooze until a
  time or new activity. Linear binds them to number keys. Plane stores
  pending/rejected/snoozed/accepted/duplicate, with `snoozed_till` and `duplicate_to`.
  Each change becomes an activity row with old and new values, actor and time.
- **Design language.** Open and Closed tabs; decline needs a confirmation step; snooze
  shows "N days to go" (Observed in Plane's locale file).
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adapt | Triage verbs as new pilot commands, each a hash-chained event; Duplicate and Snooze need new states | `state_machine.py`, `parent_bridge.CONTRACT_REVIEW_STATE`, `scripts/check_shared_contracts.py` (F10, from H3; specced, Effort L) |
  | Reject | Snooze that silently pauses an SLA | Pause needs a typed reason |

### 8. Wordsmith and Flank (channel intake)

Sources: <https://wordsmith.ai/integrations>, <https://sacra.com/c/wordsmith/>,
<https://insightpartners.com/ideas/flank-raises-10m-to-scale-autonomous-legal-agents-embedded-invisible-and-built-for-the-enterprise>.
All Claimed.

- **Core flow.** A request in Slack, Teams or email is classified and enriched from CRM
  and CLM, then answered in the same channel. Lawyers see only the exceptions. Flank
  presents its agents as invisible, with no separate interface.
- **What channel intake gains.** No login, and demand that would otherwise arrive by
  untracked email is captured.
- **What a local adapter loses.** The reply in the same channel and real-time capture.
  Inferred.
- **Verdicts.**

  | Verdict | Pattern | Where |
  | --- | --- | --- |
  | Adapt | A local, inbound-only adapter that parses a synthetic message export into `legal-request.v1` drafts, with every unknown field left blank and named | Specced as F11 |
  | Reject | Posting back to the channel; invisible completion | Rule 4 and rule 1 |

## Design donors read in source (Observed)

- **GOV.UK Frontend** (MIT code; no crown, header, footer or GDS Transport):
  - an error summary with `role="alert"` that takes focus and links to each field;
  - per-field error text tied to the field by `aria-describedby`;
  - a 3px focus ring;
  - tags with dark text on a tint.

  Adapted in the review room's inline forms. No code or wording was copied; the summary
  heading is a common phrase.
  <https://github.com/alphagov/govuk-frontend/tree/main/packages/govuk-frontend/src/govuk/components/error-summary>
- **Temporal UI** (MIT):
  - compact, feed and JSON event views;
  - grouping of scheduled, started and completed events;
  - classification and principal per event;
  - a status legend.

  This is the model for the F6 audit timeline (from H8), built.
  <https://github.com/temporalio/ui/blob/main/src/lib/types/events.ts>
- **Evidence** (MIT): the BigValue tile has a title, a formatted value, a comparison with
  `down_is_good` and a neutral range, and a sparkline. This is the model for the F7 KPI
  tile (from H6), specced.
  <https://github.com/evidence-dev/evidence/blob/main/core/src/user-components/tags/bigvalue/BigValue.svelte>
- **Chatwoot** (MIT core; SLA in `enterprise/`):
  - heartbeat presence with a 20-second window;
  - three statuses: online, busy and offline;
  - SLA statuses: active, hit, missed and active_with_misses;
  - no pause state.

  <https://github.com/chatwoot/chatwoot/blob/develop/lib/online_status_tracker.rb>

## Pattern summary per repository surface

Each row gives an observation about this repository, its evidence tag, the capture file,
a verdict, and the file the verdict would change.

### Intake

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Opening a scenario created a matter at once; a missing fact surfaced only as a refusal after submit | Observed | `baseline/room-requester-1280.png` | Adapt, built: the intake form with five required facts and an error summary, in `src/pilot/review_room.py` (after: `after/room-intake-form-1280.png`) |
| Core request schema requires only `id` and `title`, with no branching | Observed (`contracts/legal-request.v1.schema.json`) | — | Adapt, specced (F9): a per-`type` question file and a static intake page that emits JSON for download only |

### Triage

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Triage queue shows state and version only; no owner or routing reason in the list | Observed | `baseline/room-owner-triage-1280.png` | Adapt, not yet specced (from H3): queue and approval tier on each list entry. F10 covers only the triage verbs; this would be a separate small item |

### Approvals

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Disabled transitions explained only in a hover title | Observed | `baseline/room-owner-1280.png` | Adopt, built: a visible "Needs role" text tied by `aria-describedby` |
| Approval notes taken in `window.prompt` | Observed | — | Adopt, built: inline forms with minimum lengths shown |

### Review

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Redline table had no playbook position; colour alone told removed from added | Observed | `baseline/room-owner-1280.png` | Adopt, built: "Playbook position" column with "Removed" and "Added" written out |
| At 390px the owner view was 14,301px tall with crushed columns | Observed | `baseline/room-owner-390.png` | Adopt, built: stacked rows under 600px, 12,235px tall, no horizontal scroll (`after/room-owner-390.png`) |
| Resolve control did not show the cited evidence | Observed, RETROSPECTIVE B33–B36 | — | Adopt, built: "Evidence cited in this thread" inside the resolve form |
| Stale-version refusal already explicit | Observed | — | Keep |

### Audit and export

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| History in three `<details>` lists; chain status one line | Observed | `baseline/room-approver-1280.png` | Adapt, built (F6, from H8): a grouped timeline per Temporal UI, with actor, classification and chain position, in `src/pilot/timeline.py` and `review_room.py` |
| Export eligibility table clear; pass or fail shown by colour only | Observed | — | Adopt, built: ✓ and ✗ added |

### KPIs

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Control tower tiles (for example 87.5% response SLA attainment) show a value and a label; the snapshot time is one line for the whole page, and no tile shows a target or delta | Observed (`examples/legal-outcome-control-tower.html`) | `baseline/control-tower-1280.png` | Adapt, specced (F7, from H6): Evidence-style tile in `outcome_control_tower.py` |

### Board pack and knowledge portal

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Board pack is Markdown and JSON only | Observed | — | Keep; a print stylesheet is specced as D3 |
| Portal abstains with "insufficient evidence" | Observed | `baseline/knowledge-portal-1280.png` | Keep |
| Portal had no `lang` attribute (axe serious) | Observed | — | Fixed |

### Requester status

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Requester saw the raw state name (`triage`) | Observed | `baseline/room-requester-1280.png` | Adopt, built: six plain stages, a next step and a withheld line (`src/pilot/requester_status.py`) |
| German labels exist only in the core shared space | Observed (`shared_space.py`) | — | Specced: align both |

### Cross-artifact

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Seven palettes; only the Pages index had dark mode; "Public Sans" named but never loaded | Observed | all baseline captures | Adopt, partly built: shared tokens in the index and the review room (ADR 0001) |
| The "simulated roles" banner is present on every room view | Observed | — | Keep |

### MCP and CLI

| Observation | Tag | Capture | Verdict and file |
| --- | --- | --- | --- |
| Four snake_case tools, read-only annotations, contract errors raised as `InputRejected` | Observed (`mcp_server.py`) | — | Keep; ADR 0002 maps the error shape for 2.x |
| The CLI epilog cited a missing `docs/CLI.md` | Observed | — | Fixed: `docs/CLI.md` written |
