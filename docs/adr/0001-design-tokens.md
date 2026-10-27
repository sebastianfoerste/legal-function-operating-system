# 0001. One token set for generated pages, copied into the agent

- Status: Accepted
- Date: 2026-10-20

## Context

Seven HTML renderers each carried their own inline colours: the Pages index (oxblood,
the only dark mode), the outcome control tower (teal), the RaaS deal room (teal and
red), the knowledge portal, the agent snapshot and the review room (blue). Nothing
shared them. The review room is also bound by rules the others are not:

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
- The Pages index and the review room use the tokens now. The control tower, RaaS
  deal room, knowledge portal, agent snapshot and customer package keep their colours
  until they are migrated one by one, each with before and after captures.

## Consequences

- A palette change is made once in the core module and copied into the agent; the
  root test makes forgetting the copy a CI failure.
- The tokens are a string of CSS custom properties, so any renderer can inline them
  with no build step and no dependency.
- Pages that have not migrated still look different. That is deliberate: those pages
  are committed reviewer artifacts, and changing their look is a separate review.
