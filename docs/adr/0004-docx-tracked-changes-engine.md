# 0004. Python-Redlines for Word tracked changes

- Status: Proposed (owner decision)
- Date: 2026-10-20

## Context

The agent writes its own DOCX (`src/docx_redline.py`), which does not support tables.
Reviewers asked for the playbook position beside each change; that is now shown in
the review room. The next step would be a native Word tracked-changes file attributed
to the reviewer, which is where Word-based reviewers such as Definely and Spellbook
work (both Claimed, from search snippets).

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

## Options

1. **Adopt in the agent** as an optional extra. This adds a dependency and a bundled
   native binary, both of which this repository's rules exclude without an owner
   decision. It also adds a subprocess the review gates do not control.
2. **Extend the stdlib DOCX writer** to emit `w:ins`/`w:del` runs with `w:author` and
   `w:date` for the paragraphs it already rewrites. There is no new dependency, but
   the writer is limited to the supported subset (no tables).
3. **Keep the status quo:** the reviewed DOCX plus the review room's table.

## Recommendation

Option 2, if attributed tracked changes are wanted for the trial. Option 1 only if the
owner accepts a bundled .NET binary in the agent's dependency set.
