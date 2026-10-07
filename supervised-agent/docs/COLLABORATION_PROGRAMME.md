# Review-workspace programme

The local LegalOps bundle includes versioned playbook positions, a digest-bound `document.change-set.v1`, matter Lists, evidence-gated resolutions, hash-chained activity and a self-contained HTML review room.

`render_annotated_docx` copies the reviewed source DOCX, preserves its package content and inserts reviewed wording only: an accepted change as proposed, a corrected change in the reviewer's wording. Every proposed change must be decided by a named reviewer, and a correction or rejection needs a written reason. Rejected changes never enter the export. Blocked source prefixes stop document processing.

Run `make check`. Generate a local bundle with `python -m src.cli --collaboration-output-dir <dir> --collaboration-source-docx <approved.docx>`. Matter-list due dates and comment timestamps use the reproducible-build `SOURCE_DATE_EPOCH` value, defaulting to Unix epoch zero, so identical inputs produce byte-identical bundles. External access and delivery remain disabled.
