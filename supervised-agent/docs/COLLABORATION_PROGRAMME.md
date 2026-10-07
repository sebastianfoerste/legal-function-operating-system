# Review-workspace programme

The local LegalOps bundle includes a versioned playbook, a digest-bound `document.change-set.v2`, matter Lists, evidence-gated resolutions, hash-chained activity and a static HTML snapshot of the review state.

Proposed changes are document-specific. A playbook rule locates one clause in the source DOCX, verifies the original wording and proposes a change at that locator; without a source document no change is proposed. `render_annotated_docx` writes accepted changes as tracked changes into the located paragraphs of a copy and leaves the source file untouched. It requires the parent assessment and passes the single export-eligibility check in `src/export_gate.py`: an approved assessment, a matching document digest, every change decided and an intact audit chain. A decided change set alone never authorises an export. Rejected changes never enter the export. Blocked source prefixes stop document processing.

The static snapshot saves nothing. Recorded review decisions are taken in the pilot review room; see `docs/pilot/RUNBOOK.md`.

Run `make check`. Generate a local bundle with `python -m src.cli --collaboration-output-dir <dir> --collaboration-source-docx <approved.docx>`. Matter-list due dates and comment timestamps use the reproducible-build `SOURCE_DATE_EPOCH` value, defaulting to Unix epoch zero, so identical inputs produce byte-identical bundles. External access and delivery remain disabled.
