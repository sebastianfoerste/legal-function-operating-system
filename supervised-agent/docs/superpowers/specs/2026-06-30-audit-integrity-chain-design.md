# Design: Audit Integrity Chain

Date: 2026-06-30
Status: Approved

## Problem

`CASE_STUDY.md` names an explicit limitation: "the audit trail is in-process, not an
append-only external store." `AuditEvent` records are a flat list with no protection
against silent reordering, deletion, or edits between assessment creation and export.
Round 1 (Trust Cockpit) made the review-gate state legible to a reviewer; it did not
make the audit trail itself tamper-evident.

Round-1 competitive research found the GitHub/app-store/marketplace field competing on
redlining, document Q&A, and workspace convenience — not on verifiable review trails.
This is the same kind of white space the Trust Cockpit exploited.

## Goal

Make the audit trail on a `LegalOpsAssessment` a hash chain: each event commits to the
hash of the event before it. Tampering with any past event is detectable. A broken
chain blocks export, mirroring how blocker findings already block export.

## Design

### `models.py`

- `compute_audit_event_hash(seq, prev_hash, event_type, actor, note, timestamp_utc) -> str`:
  SHA-256 over a canonical (`sort_keys=True`) JSON payload of those six fields. Pure
  stdlib (`hashlib`, `json`); no new imports outside the standard library.
- `AuditEvent` gains three fields: `seq: int` (position, 0-indexed), `prev_hash: str | None`
  (the previous event's `event_hash`, `None` for the first event), `event_hash: str`
  (64-char hex digest).
- New `AuditChainVerification` model: `verified: bool`, `event_count: int`,
  `chain_root_hash: str | None` (the last event's hash when verified), `broken_at_seq: int | None`,
  `reason: str`.
- New `verify_audit_chain(events: list[AuditEvent]) -> AuditChainVerification`: walks the
  list, checking `seq` is sequential from 0, `prev_hash` matches the prior event's
  `event_hash` (or `None` for the first), and the recomputed hash matches the stored
  `event_hash`. An empty list is `verified=False` ("no audit events recorded") — a real
  assessment always has at least one event, so this only matters for hand-built test
  fixtures and hardens the export gate against them.
- `LegalOpsAssessment.validate_export_gate` gets a fourth condition: if `export_allowed`,
  the audit chain must verify, else raise `ValueError` with the verifier's reason.

`models.py` stays a leaf module — no imports from `src/`. This avoids any import cycle
between the schema layer and the modules that build chains.

### `src/audit_chain.py` (new)

One function: `append_audit_event(events, *, event_type, actor, note, timestamp_utc) -> list[AuditEvent]`.
Computes the next `seq`/`prev_hash`/`event_hash` and returns `[*events, new_event]`. This
is the only place that constructs a chain-correct `AuditEvent`.

### Call-site changes

Three existing `AuditEvent(...)` construction sites switch to `append_audit_event`:

- `src/legal_ops.py::assess_matter` — first event (`assessment_created`).
- `src/legal_ops.py::apply_review_decision` — appends `review_decision_applied`.
- `src/review_packet.py::_audit_events_for_packet` — appends `review_packet_generated`
  for the rendered packet's audit-trail section (not persisted back to the assessment).

No other call sites construct `AuditEvent` directly (confirmed by repo-wide grep).

### CLI (`src/cli.py`)

New `--audit-chain-output PATH` flag writes `AuditChainVerification` JSON for the final
assessment (post-approval if `--approve-note` was given). Added to the `_trust_cockpit_command`
helper's optional-paths list so the reproducible command embedded in Trust Cockpit metadata
includes it when used.

### Trust Cockpit (`models.py`, `src/trust_cockpit.py`)

`LegalOpsTrustCockpit` gains `audit_chain: AuditChainVerification`. `build_trust_cockpit`
computes it via `verify_audit_chain(assessment.audit_events)`. The Markdown renderer adds
an "## Audit Chain Integrity" section (verified, event count, chain root hash, reason),
placed after "## Artifact Integrity" — grouping the two integrity-evidence sections together.

### MCP tool (`src/mcp_tools.py`)

8th tool: `legal.audit.verify`. Input: `LegalOpsAssessment` (a reviewer or third party
checks a previously-exported assessment JSON). Output: `AuditChainVerification`. This is
the tool that answers "did anyone alter this audit trail after the fact."

## Error handling

A broken chain surfaces three ways, all sourced from the same `verify_audit_chain` call:
as a `ValidationError` if someone tries to construct an assessment with `export_allowed=True`
over a broken chain; as `verified: false` with a `reason` and `broken_at_seq` in the Trust
Cockpit and the standalone `--audit-chain-output`; and via the `legal.audit.verify` MCP
tool for out-of-band checks. There is no silent-pass path.

## Testing

- New `tests/test_audit_chain.py`: valid chain verifies; tampering with `note`, `actor`,
  `timestamp_utc`, or `event_type` on a past event breaks verification; a dropped or
  reordered event breaks `prev_hash`/`seq` linkage; an empty chain with `export_allowed=True`
  raises `ValidationError`; the full `assess_matter` → `apply_review_decision` flow produces
  a verified two-event chain.
- Extend `tests/test_mcp_tools.py` for `legal.audit.verify` (manifest entry + dispatch).
- Extend `tests/test_cli.py` for `--audit-chain-output`.
- Extend `tests/test_trust_cockpit.py` for the `audit_chain` field and Markdown section.
- `tests/test_legal_ops.py` and `tests/test_models.py` keep passing unchanged — confirmed
  no existing test constructs `AuditEvent` directly or relies on `audit_events` shape
  beyond `event_type` (grep-verified, single existing call site list above).

## Proof and documentation

- Regenerate the existing dated snapshots in place via the canonical CLI command (additive
  schema change, same fixture, same date):
  `examples/source-verified-saas-msa-run-2026-06-30.{md,json}`,
  `examples/trust-cockpit-saas-msa-2026-06-30.{md,json}`.
- New `examples/audit-chain-saas-msa-2026-06-30.json`: standalone verified-chain proof on
  the approved fixture.
- Append a "Round 2: Audit Integrity Chain" section to `docs/competitive-research-2026-06-30.md`
  with targeted searches (tamper-evident / hash-chain / verifiable audit trail, legal) across
  the same GitHub/App Store/Google Play/marketplace surfaces, and a retry on Microsoft
  AppSource and Amazon Appstore (both blocked automated access in round 1).
- Update `README.md` (MCP tool count seven → eight, new flag, new proof links),
  `docs/API.md`, `docs/FEATURES.md`, `docs/code_explanation.md` (`AuditEvent` field list).

## Out of scope

- Persisting the chain to an external append-only store (named in `CASE_STUDY.md` as a
  production next step, not this prototype).
- SLA/escalation engine (deferred per the round-2 direction decision).
- Any change to the existing three export-gate conditions (review state, blocker findings,
  review note) — the chain check is additive, fourth in sequence.
