# 0004. Word tracked changes stay in the stdlib writer; Python-Redlines not adopted

- Status: Accepted
- Date: proposed 2026-10-20, decided 2026-11-18
- Answers owner decision 4 in `docs/research/adaptation-plan.md` (Python-Redlines).

## Context

The agent writes its own DOCX (`supervised-agent/src/docx_redline.py`), which does not
support tables. Reviewers asked for the playbook position beside each change; that is now
shown in the review room. The next step would be a native Word tracked-changes file
attributed to the reviewer, which is where Word-based reviewers such as Definely and
Spellbook work (both Claimed, from search snippets).

When this record was proposed it read as if the writer did not yet emit Word tracked
changes. It did. Observed while deciding:

- Since PR #13 (2026-10-07) the writer has written each change as `w:ins` or `w:del` with
  `w:id`, `w:author` and `w:date`, deleted text as `w:delText`, and the paragraph mark of
  an inserted or deleted clause under `w:pPr/w:rPr`. Rejecting every tracked change gives
  back the customer draft, and every byte outside an edited paragraph is copied unchanged.
- What it lacked was attribution. One label and one date applied to the whole file: the
  pilot wrote "Approved review (synthetic pilot)" or "DRAFT proposal, not approved", dated
  with the export time, and the stateless `render_annotated_docx` wrote "Legal reviewer".
  The three DOCX files in the rehearsal of 2026-10-06 each carry one author and the export
  time on every change.
- Because the date was the export time, exporting the same internal review twice gave a
  different `draft-redline.docx`.
- Only `PilotService.decide_change` records who decided a change and when (`decided_by`,
  `decided_at`), and a carried-forward decision keeps both.

Python-Redlines (<https://github.com/JSv4/Python-Redlines>) is MIT-licensed, and so is
its Docxodus engine. It was evaluated in a scratch environment outside the repository
on 2026-10-20 without being run:

- The source repository commits no binaries (Observed).
- `python-redlines` 1.0.0 is a 7 KB wrapper. The engine comes from the
  `python-redlines-docxodus` extra (Observed on PyPI).
- `python_redlines_docxodus-1.0.0-py3-none-manylinux2014_x86_64.whl` is 44 MB. It
  contains `_binaries/linux-x64.tar.gz` (44,493,360 bytes), a prebuilt .NET
  executable that the wrapper runs through `subprocess` (Observed by listing the
  wheel).
- It produces a redline by comparing two documents, so the stdlib writer would still
  have to build the target document first (Claimed; not checked while deciding).

## Options

1. **Adopt in the agent** as an optional extra. This adds a dependency and a bundled
   native binary, both of which this repository's rules exclude without an owner
   decision. It also adds a subprocess the review gates do not control.
2. **Extend the stdlib DOCX writer** to emit `w:ins`/`w:del` runs with `w:author` and
   `w:date` for the paragraphs it already rewrites. There is no new dependency, but
   the writer is limited to the supported subset (no tables). As worded, this already
   existed; the open part was attributing each change to the reviewer who decided it.
3. **Keep the status quo:** the reviewed DOCX plus the review room's table.

## Decision

Option 2, narrowed to what was missing: per-change attribution in the stdlib writer.
Python-Redlines is not adopted.

1. `apply_tracked_changes` and `write_reviewed_docx` take an optional `marks` mapping,
   keyed by change ID, beside the single mark. Each `w:ins` and `w:del` of a change,
   including the paragraph mark of an inserted or deleted clause, carries that change's
   author and date. Without `marks` the output is byte for byte what it was. A key that
   names no edit is refused. An author keeps only characters XML 1.0 allows, on one line,
   at most 255 of them, and must not end up empty; a date must be UTC to the second.
2. The pilot gives each change its own mark. In a delivery package the author is
   "Simulated local role: <display name> (<actor ID>)" of the role that recorded the
   decision, and the date is when that decision was recorded, to the second. In an
   internal review draft every author starts "DRAFT, not approved."; a change nobody has
   decided yet reads "Playbook proposal, no reviewer decision yet" and is dated when the
   matter version was recorded. A change decided as "rejected" writes no tracked change,
   so the customer's wording stays, as before.
3. Section 3 of the package and of the draft says that each tracked change names the
   simulated local role that decided it and when, and that these names are not
   authenticated identities.
4. The stateless `render_annotated_docx` has no recorded reviewer. Its label becomes
   "Legal reviewer (not authenticated)", still dated from `SOURCE_DATE_EPOCH`.

## Consequences

- No dependency, binary or subprocess is added. The writer is still tested with
  `zipfile` and `xml.etree` only.
- A reviewed document no longer depends on the time it was exported: exporting the same
  internal review twice gives the same `draft-redline.docx` (tested).
- The names in Word are simulated local roles, and the package says they are not
  authenticated identities. Selecting an actor is not authentication. `decided_by` is not
  part of the reviewed-state hash, as before;
  editing it in the store would change the Word author without staling the approval. The
  same field is already printed in the package's "Decided by" column, and access to the
  store is control 10 in `supervised-agent/docs/pilot/IDENTITY_CONTROLS.md`.
- Accepting a tracked change in Word makes it part of the text; "accepted" in the pilot
  means the reviewer took the playbook proposal. They are different steps by different
  people. "Accept all" in Word gives the reviewed wording and "Reject all" gives the
  customer draft. The runbook says this.
- Tables, Word comments (for example the reasons for rejected changes, which stay in the
  issue list) and `w:trackRevisions` in `word/settings.xml` stay out of scope: each would
  add package parts, and every part other than `word/document.xml` is copied unchanged.
- The committed rehearsal of 2026-10-06 predates this change and keeps one label per
  file. It is a dated record and is not regenerated; a fresh rehearsal shows the
  per-change labels.
- Word display was not checked here; step 5 of the case study (open the reviewed
  documents in Word) stays with a person who has Word.
- Tests: `supervised-agent/tests/test_docx_redline.py` (per-change marks, unchanged
  single-mark output, `w:ins`/`w:del`/`w:delText` markup, checked and XML-safe marks),
  `tests/test_pilot_workflow.py` (the deciding role and decision time in the delivery
  package, the draft prefix, export-time independence) and
  `tests/test_collaboration_workspace.py` (the stateless label).
- Python-Redlines comes back only through a new ADR, if the owner accepts a bundled
  binary.
