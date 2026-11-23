# 0001. One token set for generated pages, copied into the agent

- Status: Accepted
- Date: 2026-10-20
- Amended: 2026-11-18, owner decision 10 in `docs/research/adaptation-plan.md`: the
  remaining five renderers moved onto the tokens, and a shared print block was added.

## Context

Seven HTML renderers each carried their own inline colours: the Pages index (oxblood,
the only dark mode), the outcome control tower (teal), the RaaS deal room (teal and
red), the knowledge portal, the agent snapshot, the customer package and the review
room (blue). Nothing shared them. The review room is also bound by rules the others
are not:

- it must stay self-contained, with no external script, style or font;
- the agent is exported on its own with `make agent-export`, so non-pilot agent code
  may not import the root package, and the review room should not depend on the
  parent package being importable just to render.

## Decision

- `src/legal_function_os/design_tokens.py` holds the canonical `TOKENS_CSS`: the Pages
  palette extended with `--panel`, `--pill-line`, `--on-accent`, state colours and
  backgrounds (`--ok`, `--warn`, `--bad` and their `-bg`), `--focus`, and system,
  Georgia and monospace font stacks. It has a dark block under
  `prefers-color-scheme`. No font is loaded.
- `supervised-agent/src/pilot/design_tokens.py` keeps a byte-identical copy.
  `tests/test_design_tokens.py` at the root fails when the copies differ. It also
  checks that both themes meet WCAG 2.2 AA: 4.5:1 for every text token on every
  surface and state background, and 3:1 for the focus ring and pill borders.
- The Pages index and the review room used the tokens first. The control tower, RaaS
  deal room, knowledge portal, agent snapshot and customer package followed on
  2026-11-18, one renderer per commit, each with before and after captures kept
  locally. Their wording and layout stayed the same; their colours, fonts, dark mode,
  phone layout and print changed. The control tower, deal room and portal gained a
  focus ring; the snapshot and customer package have nothing to focus. The approval
  matrix and the intake page were built on the tokens. Every generated HTML page now
  uses them.
- `PRINT_CSS`, next to `TOKENS_CSS` in both copies, restates the light tokens inside
  `@media print`, so a page viewed in dark mode still prints dark ink on a light page.
  It is derived from the light block of `TOKENS_CSS`, so the two cannot drift, and the
  root test checks that its values are the light theme. It also repeats table headers
  on each printed page and keeps rows and cards whole. The five migrated pages append it
  after their own rules; the Pages index, review room, approval matrix and intake page
  do not use it yet. The customer package adds its own page rules on top (spec D3).
- The five migrated pages use only text and background pairs that the contrast test
  checks: text tokens on `--bg`, `--surface`, `--panel` and the state backgrounds, and
  no text on `--accent-soft`.

## Consequences

- A palette change is made once in the core module and copied into the agent; the
  root test makes forgetting the copy a CI failure.
- The tokens are a string of CSS custom properties, so any renderer can inline them
  with no build step and no dependency.
- All seven renderers share one palette and dark mode. The five with something to
  focus (the Pages index, review room, control tower, deal room and portal) draw the
  same 3px `--focus` outline; the snapshot and customer package have nothing focusable. The published
  control tower and deal room look different from before (oxblood and warm off-white
  instead of teal and cool grey); they change on the Pages site only when the owner
  merges and the Pages workflow publishes.
- Margin-box page footers in the customer package were checked in Chromium only. In a
  browser without them, the notice still prints once, at the top of the first page.
- The dated rehearsal of 2026-10-06 keeps the packages it wrote with the older look; it
  is a record and is not regenerated.
