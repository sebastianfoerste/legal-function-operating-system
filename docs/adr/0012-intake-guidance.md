# 0012. Intake guidance: a team's own reviewed texts, nothing bundled

- Status: Accepted
- Date: 2026-11-19
- Answers F9a in `docs/research/adaptation-plan.md` (deflection by type), which
  [ADR 0006](0006-intake-question-files.md) left waiting for reviewed resources keyed by
  request type.

## Context

F9a asks the intake page to offer guidance for the chosen request type before the
requester saves a file, for example a template or an answered question. The plan set
three conditions. Each resource carries a review record, a `source_ref` and an optional
`type`, in addition to the keys of a knowledge-portal resource (`portal.share.v1`). The
page shows the resources for the chosen type with their source, and abstains when there
are none. Nothing blocks, replaces or delays the download. Its risk: deflection text
without a review record would be advice the page gives on its own.

What the repository has does not meet those conditions:

- The knowledge portal (`build_knowledge_portal` in `collaboration_workspace.py`) builds
  its resources from other requests' summaries and from workflow descriptions, and sets
  `approved: True` on each in code. No person reviewed any of them for a requester.
  [ADR 0009](0009-message-drafts.md) already records that a message text can reach the
  portal as a passage marked approved that was never reviewed.
- [ADR 0003](0003-intake-facts-and-requester-status.md) keeps internal content out of
  what a requester sees. Other requests' summaries are internal content.
- The repository holds synthetic data only. Guidance it bundled would be text no lawyer
  reviewed, carrying a made-up review record, on a page that is published on Pages.
- The core reads no clock, so it cannot tell a recent review from an old one.

## Decision

1. **A team's own file; nothing is bundled.** `legal-function-os intake-page --guidance
   PATH` reads a guidance file with `"schema": "legal-function-os.intake-guidance.v1"`.
   Without one the page shows no guidance and says nothing about it, so the default
   page, `make demo`, `examples/intake-page.html` and the Pages copy have none.
2. **The format.** The top level has `schema`, `name` and a list `resources`. A resource
   has the four keys of a `portal.share.v1` resource (`id`, `title`, `passage`,
   `source_ref`), an optional `type` (a request type of the policy), `prepared_by`, and a
   review record `approval` with `by`, `on` (the date of the review, `YYYY-MM-DD`) and
   `text_sha256`. Keys starting with `x_` or `_` are ignored. Any other key is an error
   with a did-you-mean hint; `approved` is told that a flag is not a review record. New
   optional keys may be added within v1; removing or renaming a key, or changing what
   one means, needs v2.
3. **A review is bound to the text it reviewed.** `text_sha256` is the SHA-256, in
   lower-case hex, of what a requester reads: `type`, `title`, `passage` and
   `source_ref` as the file gives them, as JSON with sorted keys, no spaces and UTF-8
   text (a missing `type` is null). A text changed after its review no longer matches,
   and the problem names the digest the text has now. A record with no digest yet is
   told the same digest, which the reviewer records after reading that text. `id`,
   `prepared_by` and the record itself are not part of the digest.
4. **Every problem is reported at once, with its place, and nothing is written**, as for
   a question file:
   - a resource with no review record, or a record with a field missing;
   - a digest that is not one, or that does not match the text;
   - `by` naming the person in `prepared_by`, compared after folding case, compatibility
     forms (NFKC), runs of whitespace and invisible characters;
   - an `on` that is not a calendar date written `YYYY-MM-DD`;
   - a link (`http://` or `https://`) or an unpaired surrogate in any text;
   - a passage over 800 characters, or more than three resources for one type;
   - a repeated `id`, or two titles in one type that read the same;
   - a key the format does not know.

   A resource with no `type`, or with a type the policy does not have, is a note and is
   not shown. A `portal.share.v1` document is refused: its resources have no review
   record.
5. **What the page shows.** At the top of the chosen type's section, above its
   questions, static text with no link and no control, marked as a note:
   - the heading "Guidance from legal for this kind of request";
   - the fixed line "General information, not legal advice about your request. Reading
     it is optional: you can still answer the questions and save a request file for
     legal.";
   - for each resource, its title, its passage, and "Source: SOURCE. Legal's guidance
     file records that NAME reviewed this text for requesters on DATE."

   The footer adds "Guidance: NAME." with the file's name. A type with no guidance shows
   none. The words the page adds never say approve, approved or approval, and never say
   the software checked what a text says.
6. **Guidance stays out of the page script and its data block.** The page never matches
   a requester's answers against guidance: the requester sees it by choosing the type,
   as with the type's questions. The script, its data and the script hash in the
   Content-Security-Policy are byte-identical with and without guidance, so the checks,
   the "Check your answers" step and the saved file cannot change. A browser test saves
   the same answers from a page with guidance and one without and compares the files
   byte for byte.
7. **The question sheet lists it.** `legal-function-os intake-page --guidance PATH`
   without `--out` prints each type's guidance under its questions, with who prepared
   and who reviewed each text, the date and the digest, so legal ops can read everything
   the page will show in one place.
8. **No new tool and no contract change.** `legal-request.v1`, `portal.share.v1`, the
   question format and the policy are unchanged. The `intake-page` command is not an MCP
   tool. `intake-page --format json` adds a `guidance` key to the resolved form only when
   a file is given.

## Consequences

- A team can point requesters at its own template or answer for a kind of request. The
  requester can still answer every question and save a file; nothing is blocked or
  delayed.
- **A review record is not authentication.** Anyone who can edit the file can type a
  name and copy the digest the check names. The digest guarantees only that a text
  changed after its review was recorded is not shown until a new review is recorded.
  Who may record a review, and how the file is kept (under version control, with each
  change reviewed, as for a policy), is the team's process.
- Stale guidance is not enforced. The core reads no clock, so a text reviewed long ago
  is shown as long as it is unchanged. The page shows the date, and the team decides
  when to review again.
- Every requester who opens the type sees the reviewer's name.
- A source is named, not linked: the page is self-contained and carries no link. A
  requester who needs the source asks legal.
- The default page, `make demo` and the Pages copy show no guidance, so the published
  demo does not show the feature. The tests and the question sheet do.
- The page's style block gained the guidance rules once, for every page, so the style
  hash in the Content-Security-Policy of `examples/intake-page.html` changed. Its script
  and script hash did not.

## Alternatives rejected

- **Bundled synthetic guidance**, so that the demo shows the feature. Its review record
  would be made up: an approval nobody gave, on a published page.
- **Guidance in the question file.** The questions are wording legal ops owns
  ([ADR 0006](0006-intake-question-files.md)); guidance is legal content with its own
  review, by other people and at another pace. A team can use its questions without
  guidance, and the question format stays as it is.
- **A knowledge-portal document as the input.** Its resources are other requests'
  passages and workflow descriptions marked `approved: True` in code, never reviewed for
  requesters, and they carry internal content (ADR 0003).
- **Matching the requester's words against guidance**, to suggest a text from the title
  or description. The page would then pick the advice a requester reads, by a keyword
  rule or a model. The type the requester chooses is the only key.
- **A link to each source.** The page loads and links nothing.

## Left to the owner

These do not block the decision:

- whether a clearly labelled example guidance block should ever appear on Pages
  (recommended: no, for the reason under the first rejected alternative);
- who in a real team may record a review.
