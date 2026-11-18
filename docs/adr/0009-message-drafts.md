# 0009. Message drafts: a local, inbound-only adapter for channel intake

- Status: Accepted
- Date: 2026-11-18
- Answers owner decision 8 in `docs/research/adaptation-plan.md` (channel intake, F11):
  a local inbound adapter is built, and live channel intake stays out.

## Context

Competitors take requests where people already write. Checkbox takes email, Slack,
Teams and web forms into one record; Flank works inside Slack, Teams and email;
Wordsmith answers in the same channel. All of this is Claimed, from the repository's
own [landscape](../research/2026-10-competitive-landscape.md). Here, requests arrive only
as JSON, CSV, standard input or an intake-page file.

Three facts shape what can be built:

- A live connector (a Slack or Teams API, IMAP polling, a webhook) needs network access
  and credentials and reads real data, and a reply is outward delivery. That breaks the
  no-network core, "Synthetic data only" and "Do not add external delivery,
  publication, filing or outreach actions". The plan lists bots that post into Slack,
  Teams or email as an anti-pattern.
- The rules give every missing decision field its lowest-risk default: the three flags
  are false, a missing value band is the lowest and a missing urgency is `standard`
  (`rules.py`). Observed while deciding: a draft holding only an id and a title that
  says "uncapped liability and EU customer data going to the US" passes `validate` with
  one warning, and `triage` decides it LOW, P3, Reviewer only, "No elevated-risk signals
  detected". [ADR 0006](0006-intake-question-files.md) already decided that a decision
  field never takes its default silently.
- `facts` is not neutral. `agent_run` marks "Collect supporting facts" complete whenever
  `facts` is non-empty, so provenance written there would make a draft look further
  along than it is.

## Decision

1. **A CLI command, `legal-function-os message-drafts`**, reads one local message export
   and writes `legal-request.v1` drafts (`message-drafts.json`, which `validate` reads,
   and `message-drafts.md` for a reviewer). It is a CLI command, never an MCP tool, so no
   model feeds it messages fetched from a live channel or fills its blanks. It has no
   network, mail or process code; a test reads its imports.
2. **The export format** is JSON lines, one message object per line, with the keys
   `message_id`, `sender` and `text` (required) and `channel`, `sent_at` and `subject`
   (optional). Keys starting with `x_` or `_` are ignored; any other key is an error with
   a did-you-mean hint. Every problem is reported at once with its line number, and
   nothing is written. The bundled export is
   `src/legal_function_os/data/sample_messages.jsonl`. Within this version, new optional
   keys may be added; removing or renaming a key, or changing what one means, needs a new
   format version.
3. **Synthetic senders only.** Every `sender` must match `syn-[a-z0-9-]+`, the pilot's
   pattern for synthetic actor ids. This marks the export as synthetic data. It says
   nothing about who sent a message: senders are not verified, as selecting an actor in
   the pilot is not authentication.
4. **Copy, never infer.** Values come only from labelled lines at the start of a line,
   such as `Value band: <50k`. Labels are matched as CSV headers are ("Value band",
   "value-band" and "valueBand" mean `value_band`; "Request type" and "Requester" mean
   `type` and `requested_by`), and yes/no answers are read with the CSV words. A value is
   copied as written, so `>1M` stays and validation names it. A quoted reply line, a list
   item and the rest of the prose are not read. A label naming a field legal sets (`id`,
   `sla_breached`, `awaiting_business_input`, `summary`, `dependencies`, `facts`) or one
   that looks like a misspelled field is noted and not copied; a field given two
   different ways is noted and not copied. The subject is the title (else a `Title:`
   line), and the whole text is the description.
5. **Blanks are written, not left out.** Every draft holds every field the intake page
   always asks (`title`, `type`, `value_band`, the three flags, `urgency`). One the
   message does not state is `""` and named, so `validate` and `triage` refuse the draft
   until a person in legal fills it. Left out, it would take its default and could lower
   the risk without a word.
6. **Numbering and provenance.** Drafts are `REQ-DRAFT-1`, `REQ-DRAFT-2` and so on in
   message order, and legal renumbers them. Each keeps its message id in `x_message_id`,
   which the contract passes through unchanged. Nothing goes into `facts`.
7. **It sends and decides nothing.** No reply, no acknowledgement, no risk, priority,
   queue, service level or approval chain. The output says so, and says that senders are
   not verified.

## Consequences

- A team with requests in a channel can turn a saved export into drafts that show what
  was copied, what is blank and what was noted, with no model involved.
- Drafts are invalid by design until filled. Someone who deletes a blank key instead of
  filling it gets the default, as with any hand-written JSON. The output, the input format
  docs and this record say "fill, do not delete"; closing this fully would need a contract
  change, which v1 does not allow.
- The format exists only here. Real Slack, Teams or mail exports would have to be
  converted, and they would carry real people's data, which this repository does not
  process. The command is a pattern for synthetic data, not an integration.
- Drafts from two exports share ids, and `validate` reports the duplicates until legal
  renumbers, as with intake-page files (ADR 0006).
- The message text becomes the `description`. The legacy `--collaboration-output-dir`
  turns a description into a knowledge-portal passage marked approved; with synthetic
  data that is acceptable, but the passage was never reviewed.
- `x_message_id` lets the person completing a draft find the message and ask its sender.
  ADR 0006 left out the `x_intake` provenance key because nothing read it; here a person
  reads it.
- `legal-request.v1` and every other contract are unchanged. The wheel ships the
  `.jsonl` export, and `make package-check` runs the command from it.

## Alternatives rejected

- **Decline: channel intake stays out.** No code, but the intake-channel gap stays
  unanswered and the specced F11 keeps no bounded shape.
- **`.eml` and mailbox files through the standard `email` package.** A real format with
  no dependency, but real mail carries real addresses, headers and attachments, and
  HTML-only bodies and encoded subjects (Observed) would roughly double the work. It
  would need a new owner decision.
- **A live connector or a reply in the channel** (Slack or Teams API, IMAP, a webhook).
  It matches what competitors claim, but it needs network access and credentials, reads
  real data and adds outreach. It would need a new owner decision.
- **An MCP tool `message_drafts(messages)`.** It would take data, not paths, but the
  realistic input would be messages a model fetched through a live connector, and the
  model would be the obvious party to fill the blanks, which puts a model on the
  risk-relevant fields.
- **Leaving unstated decision fields out**, so drafts pass `validate` at once. Observed:
  such a draft triages LOW on facts nobody gave, against ADR 0006.
