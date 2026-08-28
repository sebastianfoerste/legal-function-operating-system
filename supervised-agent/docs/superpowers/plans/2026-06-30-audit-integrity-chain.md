# Audit Integrity Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the audit trail on a `LegalOpsAssessment` a tamper-evident SHA-256 hash chain, block export when the chain doesn't verify, and surface the result through the CLI, the Trust Cockpit, and a new MCP tool.

**Architecture:** `models.py` owns the hash function, the chain fields on `AuditEvent`, and a `verify_audit_chain` walker (kept dependency-free so the schema layer stays a leaf module). A new `src/audit_chain.py` owns the one piece of builder logic (`append_audit_event`) that the existing audit-event call sites switch to. The export gate, CLI, Trust Cockpit, and MCP surface all consume `verify_audit_chain` from `models.py`.

**Tech Stack:** Python 3.13, Pydantic v2, stdlib `hashlib`/`json` only — no new dependencies.

## Global Constraints

- Python `>=3.13` (`pyproject.toml`). Match existing full type-hint style.
- Black line length 100, `target-version = ["py313"]`. Run `black .` before committing.
- Ruff: `select = ["E", "F", "I", "B"]`, `ignore = ["E501"]` — imports must be isort-ordered (stdlib, then third-party, then local `models`/`src.*`, alphabetical within each group, uppercase identifiers sort before lowercase).
- MyPy: `disallow_untyped_defs = false`, several error codes disabled — keep type hints consistent with surrounding code but don't chase exhaustive strictness beyond what's already there.
- `make check` (Ruff, Black --check, MyPy, Pytest, compileall) must pass before any task is considered done.
- No new runtime dependencies. No external network calls from application code (design principle: deterministic, offline, local-only).
- `models.py` must not import from `src/` (avoids the only realistic circular-import risk in this codebase).
- Conventional commit messages, lowercase, imperative mood, no emojis. Commit after every task.
- Do not run `git push` as part of any task — stop after the final task and ask the user.
- Baseline before this plan: 39 tests collected (`python -m pytest -q --collect-only`). This plan adds 7 new test functions: 4 in Task 1, 1 in Task 2, 1 in Task 3, 1 in Task 7 (all in `tests/test_audit_chain.py`, `tests/test_models.py`, and `tests/test_mcp_tools.py` respectively) — expect 46 after Task 10. If your count differs, find the discrepancy before touching docs that cite the number.
- Until Task 4 lands, `AuditEvent` requires `seq`/`event_hash` but `src/legal_ops.py` and `src/review_packet.py` still construct it without them — every test file that calls `assess_matter`, `apply_review_decision`, or `build_review_packet` (i.e. everything except `tests/test_audit_chain.py` and `tests/test_models.py`) will fail with a `ValidationError` in that window. That's expected, not a regression — don't run the full suite as a correctness check until Task 4's commit.

---

### Task 1: Hash chain primitives in `models.py`

**Files:**
- Modify: `models.py:1-5` (imports), `models.py:89-95` (`AuditEvent`)
- Test: `tests/test_audit_chain.py` (new file)

**Interfaces:**
- Produces: `compute_audit_event_hash(seq: int, prev_hash: str | None, event_type: str, actor: str, note: str, timestamp_utc: str) -> str`, `AuditEvent` with new fields `seq: int`, `prev_hash: str | None`, `event_hash: str`, `AuditChainVerification` (fields: `verified: bool`, `event_count: int`, `chain_root_hash: str | None`, `broken_at_seq: int | None`, `reason: str`), `verify_audit_chain(events: list[AuditEvent]) -> AuditChainVerification`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_audit_chain.py`:

```python
from models import verify_audit_chain


def test_verify_audit_chain_rejects_empty_chain():
    result = verify_audit_chain([])

    assert result.verified is False
    assert result.event_count == 0
    assert result.reason == "no audit events recorded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_audit_chain.py -v`
Expected: FAIL with `ImportError: cannot import name 'verify_audit_chain' from 'models'`

- [ ] **Step 3: Add the hash chain primitives to `models.py`**

Replace the import block at the top of `models.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
```

with:

```python
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
```

Replace the existing `AuditEvent` class:

```python
class AuditEvent(BaseModel):
    """Audit event for the supervised legal-ops workflow."""

    event_type: AuditEventType
    actor: str = Field(..., min_length=2)
    note: str = Field(..., min_length=12)
    timestamp_utc: str = Field(..., min_length=10)
```

with:

```python
def compute_audit_event_hash(
    seq: int,
    prev_hash: str | None,
    event_type: str,
    actor: str,
    note: str,
    timestamp_utc: str,
) -> str:
    """Canonical SHA-256 digest for one position in the audit hash chain."""

    payload = json.dumps(
        {
            "seq": seq,
            "prev_hash": prev_hash,
            "event_type": event_type,
            "actor": actor,
            "note": note,
            "timestamp_utc": timestamp_utc,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditEvent(BaseModel):
    """Audit event for the supervised legal-ops workflow.

    Events form a hash chain: each event_hash commits to prev_hash plus the
    event's own content, so altering, reordering or dropping a past event is
    detectable by verify_audit_chain.
    """

    event_type: AuditEventType
    actor: str = Field(..., min_length=2)
    note: str = Field(..., min_length=12)
    timestamp_utc: str = Field(..., min_length=10)
    seq: int = Field(..., ge=0)
    prev_hash: str | None = None
    event_hash: str = Field(..., min_length=64, max_length=64)


class AuditChainVerification(BaseModel):
    """Result of walking an audit event hash chain."""

    verified: bool
    event_count: int = Field(..., ge=0)
    chain_root_hash: str | None = None
    broken_at_seq: int | None = None
    reason: str


def verify_audit_chain(events: list[AuditEvent]) -> AuditChainVerification:
    """Recompute and check every link in an audit event hash chain."""

    if not events:
        return AuditChainVerification(
            verified=False,
            event_count=0,
            chain_root_hash=None,
            broken_at_seq=None,
            reason="no audit events recorded",
        )

    expected_prev: str | None = None
    for index, event in enumerate(events):
        if event.seq != index:
            return AuditChainVerification(
                verified=False,
                event_count=len(events),
                chain_root_hash=None,
                broken_at_seq=event.seq,
                reason=f"sequence gap at seq {event.seq}",
            )
        if event.prev_hash != expected_prev:
            return AuditChainVerification(
                verified=False,
                event_count=len(events),
                chain_root_hash=None,
                broken_at_seq=event.seq,
                reason=f"prev_hash mismatch at seq {event.seq}",
            )
        recomputed = compute_audit_event_hash(
            event.seq,
            event.prev_hash,
            event.event_type,
            event.actor,
            event.note,
            event.timestamp_utc,
        )
        if recomputed != event.event_hash:
            return AuditChainVerification(
                verified=False,
                event_count=len(events),
                chain_root_hash=None,
                broken_at_seq=event.seq,
                reason=f"event_hash mismatch at seq {event.seq}",
            )
        expected_prev = event.event_hash

    return AuditChainVerification(
        verified=True,
        event_count=len(events),
        chain_root_hash=expected_prev,
        broken_at_seq=None,
        reason="chain intact",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_audit_chain.py -v`
Expected: `1 passed`

- [ ] **Step 5: Add the remaining chain-construction and tamper-detection tests**

A hand-written `event_hash` would prove nothing here — the point of these tests is
that the digest must be the real computed one, or verification correctly rejects it.
Replace the entire contents of `tests/test_audit_chain.py` (written in Step 1) with:

```python
from models import AuditEvent, compute_audit_event_hash, verify_audit_chain


def _build_event(
    seq: int,
    prev_hash: str | None,
    event_type: str,
    actor: str,
    note: str,
    timestamp_utc: str,
) -> AuditEvent:
    return AuditEvent(
        event_type=event_type,
        actor=actor,
        note=note,
        timestamp_utc=timestamp_utc,
        seq=seq,
        prev_hash=prev_hash,
        event_hash=compute_audit_event_hash(seq, prev_hash, event_type, actor, note, timestamp_utc),
    )


def test_verify_audit_chain_rejects_empty_chain():
    result = verify_audit_chain([])

    assert result.verified is False
    assert result.event_count == 0
    assert result.reason == "no audit events recorded"


def test_verify_audit_chain_accepts_valid_chain():
    first = _build_event(
        0, None, "assessment_created", "LegalOps Agent",
        "Assessment created from typed matter intake.", "2026-06-30T10:00:00Z",
    )
    second = _build_event(
        1, first.event_hash, "review_decision_applied", "General Counsel",
        "Approved after privacy review of the synthetic matter facts.", "2026-06-30T11:00:00Z",
    )

    result = verify_audit_chain([first, second])

    assert result.verified is True
    assert result.event_count == 2
    assert result.chain_root_hash == second.event_hash
    assert result.broken_at_seq is None


def test_verify_audit_chain_detects_tampered_note():
    first = _build_event(
        0, None, "assessment_created", "LegalOps Agent",
        "Assessment created from typed matter intake.", "2026-06-30T10:00:00Z",
    )
    tampered = first.model_copy(update={"note": "Assessment created from a different intake."})

    result = verify_audit_chain([tampered])

    assert result.verified is False
    assert result.broken_at_seq == 0
    assert "event_hash mismatch" in result.reason


def test_verify_audit_chain_detects_broken_prev_hash_link():
    first = _build_event(
        0, None, "assessment_created", "LegalOps Agent",
        "Assessment created from typed matter intake.", "2026-06-30T10:00:00Z",
    )
    second = _build_event(
        1, first.event_hash, "review_decision_applied", "General Counsel",
        "Approved after privacy review of the synthetic matter facts.", "2026-06-30T11:00:00Z",
    )
    broken_second = second.model_copy(update={"prev_hash": "0" * 64})

    result = verify_audit_chain([first, broken_second])

    assert result.verified is False
    assert result.broken_at_seq == 1
    assert "prev_hash mismatch" in result.reason
```

The file now contains exactly the helper `_build_event` plus four `test_*` functions:
`test_verify_audit_chain_rejects_empty_chain`, `test_verify_audit_chain_accepts_valid_chain`,
`test_verify_audit_chain_detects_tampered_note`, `test_verify_audit_chain_detects_broken_prev_hash_link`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_audit_chain.py -v`
Expected: `4 passed`

- [ ] **Step 7: Lint, format, type-check**

Run: `python -m ruff check models.py tests/test_audit_chain.py && python -m black models.py tests/test_audit_chain.py && python -m mypy models.py`
Expected: no errors; Black may reformat — re-run `pytest` after if it does.

- [ ] **Step 8: Commit**

```bash
git add models.py tests/test_audit_chain.py
git commit -m "feat: add audit event hash chain primitives"
```

---

### Task 2: `append_audit_event` builder in `src/audit_chain.py`

**Files:**
- Create: `src/audit_chain.py`
- Test: `tests/test_audit_chain.py` (extend)

**Interfaces:**
- Consumes: `models.AuditEvent`, `models.AuditEventType`, `models.compute_audit_event_hash` (Task 1).
- Produces: `append_audit_event(events: list[AuditEvent], *, event_type: AuditEventType, actor: str, note: str, timestamp_utc: str) -> list[AuditEvent]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_audit_chain.py`:

```python
from src.audit_chain import append_audit_event


def test_append_audit_event_builds_linked_chain():
    events = append_audit_event(
        [],
        event_type="assessment_created",
        actor="LegalOps Agent",
        note="Assessment created from typed matter intake.",
        timestamp_utc="2026-06-30T10:00:00Z",
    )
    events = append_audit_event(
        events,
        event_type="review_decision_applied",
        actor="General Counsel",
        note="Approved after privacy review of the synthetic matter facts.",
        timestamp_utc="2026-06-30T11:00:00Z",
    )

    assert [event.seq for event in events] == [0, 1]
    assert events[0].prev_hash is None
    assert events[1].prev_hash == events[0].event_hash
    assert len(events[1].event_hash) == 64
    assert verify_audit_chain(events).verified is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_audit_chain.py::test_append_audit_event_builds_linked_chain -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.audit_chain'`

- [ ] **Step 3: Create `src/audit_chain.py`**

```python
from __future__ import annotations

from models import AuditEvent, AuditEventType, compute_audit_event_hash


def append_audit_event(
    events: list[AuditEvent],
    *,
    event_type: AuditEventType,
    actor: str,
    note: str,
    timestamp_utc: str,
) -> list[AuditEvent]:
    """Return events plus one new chain-linked AuditEvent."""

    seq = len(events)
    prev_hash = events[-1].event_hash if events else None
    event_hash = compute_audit_event_hash(seq, prev_hash, event_type, actor, note, timestamp_utc)
    new_event = AuditEvent(
        event_type=event_type,
        actor=actor,
        note=note,
        timestamp_utc=timestamp_utc,
        seq=seq,
        prev_hash=prev_hash,
        event_hash=event_hash,
    )
    return [*events, new_event]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_audit_chain.py -v`
Expected: `5 passed`

- [ ] **Step 5: Lint, format, type-check**

Run: `python -m ruff check src/audit_chain.py tests/test_audit_chain.py && python -m black src/audit_chain.py tests/test_audit_chain.py && python -m mypy src/audit_chain.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/audit_chain.py tests/test_audit_chain.py
git commit -m "feat: add chain-linked audit event builder"
```

---

### Task 3: Wire the chain check into the export gate

**Files:**
- Modify: `models.py` (`LegalOpsAssessment.validate_export_gate`)
- Test: `tests/test_models.py` (extend)

**Interfaces:**
- Consumes: `verify_audit_chain` (Task 1, same module — no import needed).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
def test_assessment_export_requires_verified_audit_chain():
    matter = MatterIntake(
        title="Enterprise customer DPA review",
        requester="Sales",
        business_unit="Enterprise",
        matter_type="privacy",
        jurisdiction="EU",
        summary="Customer asks for changes to data processing terms and audit controls.",
    )
    finding = RiskFinding(
        category="privacy",
        severity="medium",
        summary="Data processing terms require review.",
        evidence="DPA request",
        recommended_action="Review roles, subprocessors and transfer basis.",
    )
    routing = RoutingDecision(
        owner_role="Privacy Counsel",
        reviewers=["Privacy Counsel"],
        rationale="Privacy matter requires specialist review before export.",
        sla_hours=24,
    )

    with pytest.raises(ValidationError):
        LegalOpsAssessment(
            assessment_id="loa_test12345",
            created_at_utc="2026-06-02T12:00:00Z",
            matter=matter,
            findings=[finding],
            routing=routing,
            review_state="approved",
            review_note="General Counsel: Approved after privacy review of the synthetic matter.",
            export_allowed=True,
            audit_events=[],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_models.py::test_assessment_export_requires_verified_audit_chain -v`
Expected: FAIL — `LegalOpsAssessment` is constructed without raising (empty `audit_events` is currently accepted).

- [ ] **Step 3: Add the fourth export-gate condition**

In `models.py`, replace the `validate_export_gate` method:

```python
    @model_validator(mode="after")
    def validate_export_gate(self) -> "LegalOpsAssessment":
        if self.export_allowed and self.review_state != "approved":
            raise ValueError("export requires approved review state")
        if self.export_allowed and any(finding.severity == "blocker" for finding in self.findings):
            raise ValueError("export is blocked while blocker findings remain")
        if self.export_allowed and not self.review_note:
            raise ValueError("export requires a documented review note")
        return self
```

with:

```python
    @model_validator(mode="after")
    def validate_export_gate(self) -> "LegalOpsAssessment":
        if self.export_allowed and self.review_state != "approved":
            raise ValueError("export requires approved review state")
        if self.export_allowed and any(finding.severity == "blocker" for finding in self.findings):
            raise ValueError("export is blocked while blocker findings remain")
        if self.export_allowed and not self.review_note:
            raise ValueError("export requires a documented review note")
        if self.export_allowed:
            chain_check = verify_audit_chain(self.audit_events)
            if not chain_check.verified:
                raise ValueError(
                    f"export is blocked while the audit chain is not verified: {chain_check.reason}"
                )
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_models.py -v`
Expected: `5 passed` (the 4 existing `test_models.py` tests plus the new one). The two
existing export-gate tests (`test_assessment_export_requires_approved_state`,
`test_assessment_export_requires_review_note`) still raise on their own earlier
conditions, so they never reach the new chain check — this confirms they still pass
unmodified.

Do not run the full suite (`python -m pytest -q`) yet. `src/legal_ops.py` and
`src/review_packet.py` still construct `AuditEvent` the old way (no `seq`/`event_hash`),
so every test file that calls `assess_matter`, `apply_review_decision`, or
`build_review_packet` will currently fail with `ValidationError: ... seq ... Field
required`. That's expected until Task 4 fixes those call sites, not something to debug
now.

- [ ] **Step 5: Lint, format, type-check**

Run: `python -m ruff check models.py tests/test_models.py && python -m black models.py tests/test_models.py && python -m mypy models.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: block export when the audit chain does not verify"
```

---

### Task 4: Switch existing audit-event call sites to the chain builder

**Files:**
- Modify: `src/legal_ops.py:1-19` (imports), `src/legal_ops.py` (`assess_matter`, `apply_review_decision`)
- Modify: `src/review_packet.py:1-6` (imports), `src/review_packet.py` (`_audit_events_for_packet`)
- Test: `tests/test_legal_ops.py` (extend)

**Interfaces:**
- Consumes: `append_audit_event` (Task 2), `verify_audit_chain` (Task 1).

- [ ] **Step 1: Write the failing test**

In `tests/test_legal_ops.py`, change the import line:

```python
from models import MatterIntake, ReviewDecision
```

to:

```python
from models import MatterIntake, ReviewDecision, verify_audit_chain
```

Then replace `test_apply_review_decision_allows_export_without_blockers`:

```python
def test_apply_review_decision_allows_export_without_blockers():
    assessment = assess_matter(build_sample_matter())
    reviewed = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note="Approved after privacy, AI governance and customer commitment review.",
        ),
    )
    assert reviewed.review_state == "approved"
    assert reviewed.export_allowed is True
    assert reviewed.review_note is not None
    assert reviewed.audit_events[-1].event_type == "review_decision_applied"
```

with:

```python
def test_apply_review_decision_allows_export_without_blockers():
    assessment = assess_matter(build_sample_matter())
    reviewed = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note="Approved after privacy, AI governance and customer commitment review.",
        ),
    )
    assert reviewed.review_state == "approved"
    assert reviewed.export_allowed is True
    assert reviewed.review_note is not None
    assert reviewed.audit_events[-1].event_type == "review_decision_applied"
    assert [event.seq for event in reviewed.audit_events] == [0, 1]
    chain_result = verify_audit_chain(reviewed.audit_events)
    assert chain_result.verified is True
    assert chain_result.event_count == 2
```

This currently fails not because of an import error, but because `assess_matter` and
`apply_review_decision` still build `AuditEvent` directly without `seq`/`prev_hash`/
`event_hash`, which `AuditEvent` now requires (Task 1) — so this whole test file is
already broken at collection time after Task 1 landed. That's expected; Step 3 fixes it.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_legal_ops.py -v`
Expected: FAIL — `ValidationError: 2 validation errors for AuditEvent ... event_hash ... Field required`

- [ ] **Step 3: Switch `src/legal_ops.py` to the chain builder**

Replace the import block:

```python
from models import (
    AuditEvent,
    ControlCheck,
    ControlStatus,
    CustomerCommitmentRecord,
    LegalOpsAssessment,
    MatterIntake,
    ReviewDecision,
    RiskFinding,
    RoutingDecision,
    SourceVerificationRecord,
)
from src.source_verification import verify_source_refs
```

with:

```python
from models import (
    ControlCheck,
    ControlStatus,
    CustomerCommitmentRecord,
    LegalOpsAssessment,
    MatterIntake,
    ReviewDecision,
    RiskFinding,
    RoutingDecision,
    SourceVerificationRecord,
)
from src.audit_chain import append_audit_event
from src.source_verification import verify_source_refs
```

In `assess_matter`, replace:

```python
        audit_events=[
            AuditEvent(
                event_type="assessment_created",
                actor=SYSTEM_ACTOR,
                note="Assessment created from typed matter intake.",
                timestamp_utc=created_at,
            )
        ],
```

with:

```python
        audit_events=append_audit_event(
            [],
            event_type="assessment_created",
            actor=SYSTEM_ACTOR,
            note="Assessment created from typed matter intake.",
            timestamp_utc=created_at,
        ),
```

In `apply_review_decision`, replace:

```python
    audit_events = [
        *assessment.audit_events,
        AuditEvent(
            event_type="review_decision_applied",
            actor=decision.reviewer,
            note=decision.note,
            timestamp_utc=utc_now_iso(),
        ),
    ]
```

with:

```python
    audit_events = append_audit_event(
        assessment.audit_events,
        event_type="review_decision_applied",
        actor=decision.reviewer,
        note=decision.note,
        timestamp_utc=utc_now_iso(),
    )
```

- [ ] **Step 4: Switch `src/review_packet.py` to the chain builder**

Replace:

```python
from models import AuditEvent, LegalOpsAssessment
```

with:

```python
from models import AuditEvent, LegalOpsAssessment
from src.audit_chain import append_audit_event
```

Replace:

```python
def _audit_events_for_packet(assessment: LegalOpsAssessment) -> list[AuditEvent]:
    return [
        *assessment.audit_events,
        AuditEvent(
            event_type="review_packet_generated",
            actor=PACKET_ACTOR,
            note="Review packet generated for human legal review.",
            timestamp_utc=_utc_now_iso(),
        ),
    ]
```

with:

```python
def _audit_events_for_packet(assessment: LegalOpsAssessment) -> list[AuditEvent]:
    return append_audit_event(
        assessment.audit_events,
        event_type="review_packet_generated",
        actor=PACKET_ACTOR,
        note="Review packet generated for human legal review.",
        timestamp_utc=_utc_now_iso(),
    )
```

`AuditEvent` stays imported in `review_packet.py` — it's still used in the
`list[AuditEvent]` return-type annotation.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_legal_ops.py tests/test_review_packet.py -v`
Expected: all passing, including
`tests/test_legal_ops.py::test_apply_review_decision_allows_export_without_blockers`
and the golden-snapshot test `test_blocked_review_packet_matches_golden_snapshot`
(the golden file only pins `timestamp`/`event_type`/`actor`/`note` text, none of
which changed, so it should pass unmodified).

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all passing, 45 collected (39 baseline + 4 from Task 1 + 1 from Task 2 + 1
from Task 3; the remaining 1 new test lands in Task 7, bringing the eventual total to
46). If your running count differs, that's a signal to stop and check which step was
skipped, not to edit this number.

- [ ] **Step 7: Lint, format, type-check**

Run: `python -m ruff check src/legal_ops.py src/review_packet.py tests/test_legal_ops.py && python -m black src/legal_ops.py src/review_packet.py tests/test_legal_ops.py && python -m mypy src/legal_ops.py src/review_packet.py`
Expected: no errors. Ruff should confirm `AuditEvent` is no longer flagged as unused
in `src/legal_ops.py` (it's no longer imported there) and is still used in
`src/review_packet.py`.

- [ ] **Step 8: Commit**

```bash
git add src/legal_ops.py src/review_packet.py tests/test_legal_ops.py
git commit -m "refactor: build audit events through the chain-linked builder"
```

---

### Task 5: CLI `--audit-chain-output`

**Files:**
- Modify: `src/cli.py`
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `verify_audit_chain` (Task 1).

- [ ] **Step 1: Write the failing test**

In `tests/test_cli.py`, add `audit_chain_output = tmp_path / "audit-chain.json"` to the
setup block and the new flag to the parsed args, and add assertions at the end. Replace
the whole file with:

```python
import json

from src.cli import build_parser, run


def test_cli_writes_json_and_review_packet(tmp_path):
    json_output = tmp_path / "assessment.json"
    packet_output = tmp_path / "packet.md"
    commitments_output = tmp_path / "commitments.json"
    sources_output = tmp_path / "sources.json"
    review_runner_output = tmp_path / "review-runner.json"
    manifest_output = tmp_path / "manifest.json"
    trust_cockpit_output = tmp_path / "trust-cockpit.md"
    trust_cockpit_json_output = tmp_path / "trust-cockpit.json"
    audit_chain_output = tmp_path / "audit-chain.json"
    parser = build_parser()
    args = parser.parse_args(
        [
            "--input",
            "examples/matters/enterprise_dpa.json",
            "--json-output",
            str(json_output),
            "--packet-output",
            str(packet_output),
            "--commitments-output",
            str(commitments_output),
            "--sources-output",
            str(sources_output),
            "--review-runner-output",
            str(review_runner_output),
            "--manifest-output",
            str(manifest_output),
            "--trust-cockpit-output",
            str(trust_cockpit_output),
            "--trust-cockpit-json-output",
            str(trust_cockpit_json_output),
            "--audit-chain-output",
            str(audit_chain_output),
        ]
    )

    payload = run(args)

    assert payload["export_allowed"] is False
    assert json.loads(json_output.read_text(encoding="utf-8"))["assessment_id"].startswith("loa_")
    assert "LegalOps Review Packet" in packet_output.read_text(encoding="utf-8")
    commitments = json.loads(commitments_output.read_text(encoding="utf-8"))
    assert commitments["assessment_id"] == payload["assessment_id"]
    assert len(commitments["commitments"]) == 3
    sources = json.loads(sources_output.read_text(encoding="utf-8"))
    assert sources["assessment_id"] == payload["assessment_id"]
    assert sources["source_verifications"][0]["status"] == "pass"
    review_runner = json.loads(review_runner_output.read_text(encoding="utf-8"))
    assert review_runner["schema"] == "legal-ops-agent.source-verified-review-packet-run.v1"
    assert review_runner["assessment_id"] == payload["assessment_id"]
    assert review_runner["policy_envelope"]["external_actions_allowed"] is False
    assert "LegalOps Review Packet" in review_runner["markdown_packet"]
    manifest = json.loads(manifest_output.read_text(encoding="utf-8"))
    assert manifest["schema"] == "legal-ops-agent.artifact-manifest.v1"
    assert manifest["assessment_id"] == payload["assessment_id"]
    assert manifest["local_integrity_signature"]["algorithm"] == "sha256"
    assert len(manifest["local_integrity_signature"]["value"]) == 64
    assert {item["name"] for item in manifest["artifacts"]} == {
        "assessment_json",
        "review_packet_markdown",
        "customer_commitment_register_json",
        "source_verification_json",
        "source_verified_review_packet_runner_json",
    }
    trust_cockpit = json.loads(trust_cockpit_json_output.read_text(encoding="utf-8"))
    assert trust_cockpit["schema"] == "legal-ops-agent.trust-cockpit.v1"
    assert trust_cockpit["assessment_id"] == payload["assessment_id"]
    assert trust_cockpit["decision_summary"]["export_allowed"] is False
    assert trust_cockpit["review_gate"]["external_actions_allowed"] is False
    assert trust_cockpit["artifact_summary"]["artifact_count"] == 5
    assert "LegalOps Trust Cockpit" in trust_cockpit_output.read_text(encoding="utf-8")
    audit_chain = json.loads(audit_chain_output.read_text(encoding="utf-8"))
    assert audit_chain["verified"] is True
    assert audit_chain["event_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_cli.py -v`
Expected: FAIL with `error: unrecognized arguments: --audit-chain-output ...`

- [ ] **Step 3: Add the flag and the output block**

In `src/cli.py`, replace the import line:

```python
from models import MatterIntake, ReviewDecision
```

with:

```python
from models import MatterIntake, ReviewDecision, verify_audit_chain
```

Replace:

```python
    parser.add_argument(
        "--trust-cockpit-json-output",
        type=Path,
        help="Write a source-verified trust cockpit JSON snapshot.",
    )
    parser.add_argument("--approve-note", help="Apply an approval note after assessment.")
```

with:

```python
    parser.add_argument(
        "--trust-cockpit-json-output",
        type=Path,
        help="Write a source-verified trust cockpit JSON snapshot.",
    )
    parser.add_argument(
        "--audit-chain-output",
        type=Path,
        help="Write the tamper-evident audit chain verification JSON to this path.",
    )
    parser.add_argument("--approve-note", help="Apply an approval note after assessment.")
```

Replace the `optional_paths` list in `_trust_cockpit_command`:

```python
    optional_paths = [
        ("--input", args.input),
        ("--json-output", args.json_output),
        ("--packet-output", args.packet_output),
        ("--commitments-output", args.commitments_output),
        ("--sources-output", args.sources_output),
        ("--review-runner-output", args.review_runner_output),
        ("--manifest-output", args.manifest_output),
        ("--trust-cockpit-output", args.trust_cockpit_output),
        ("--trust-cockpit-json-output", args.trust_cockpit_json_output),
    ]
```

with:

```python
    optional_paths = [
        ("--input", args.input),
        ("--json-output", args.json_output),
        ("--packet-output", args.packet_output),
        ("--commitments-output", args.commitments_output),
        ("--sources-output", args.sources_output),
        ("--review-runner-output", args.review_runner_output),
        ("--manifest-output", args.manifest_output),
        ("--audit-chain-output", args.audit_chain_output),
        ("--trust-cockpit-output", args.trust_cockpit_output),
        ("--trust-cockpit-json-output", args.trust_cockpit_json_output),
    ]
```

Replace:

```python
    if args.manifest_output:
        manifest_payload = build_artifact_manifest(assessment, artifacts)
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(
            json.dumps(manifest_payload, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.trust_cockpit_output or args.trust_cockpit_json_output:
```

with:

```python
    if args.manifest_output:
        manifest_payload = build_artifact_manifest(assessment, artifacts)
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(
            json.dumps(manifest_payload, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.audit_chain_output:
        chain_verification = verify_audit_chain(assessment.audit_events)
        args.audit_chain_output.parent.mkdir(parents=True, exist_ok=True)
        args.audit_chain_output.write_text(
            json.dumps(chain_verification.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
    if args.trust_cockpit_output or args.trust_cockpit_json_output:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_cli.py -v`
Expected: `1 passed`

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all passing.

- [ ] **Step 6: Lint, format, type-check**

Run: `python -m ruff check src/cli.py tests/test_cli.py && python -m black src/cli.py tests/test_cli.py && python -m mypy src/cli.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/cli.py tests/test_cli.py
git commit -m "feat: add --audit-chain-output to the CLI"
```

---

### Task 6: Trust Cockpit audit chain section

**Files:**
- Modify: `models.py` (`LegalOpsTrustCockpit`)
- Modify: `src/trust_cockpit.py`
- Test: `tests/test_trust_cockpit.py` (extend)

**Interfaces:**
- Consumes: `verify_audit_chain`, `AuditChainVerification` (Task 1).
- Produces: `LegalOpsTrustCockpit.audit_chain: AuditChainVerification`.

- [ ] **Step 1: Write the failing test**

In `tests/test_trust_cockpit.py`, add these two assertions to the end of
`test_trust_cockpit_summarizes_source_verified_saas_msa_fixture`:

```python
    assert cockpit.audit_chain.verified is True
    assert cockpit.audit_chain.event_count == 1
    assert "Audit Chain Integrity" in cockpit.markdown
```

and these two to the end of `test_trust_cockpit_ready_after_human_approval_without_blockers`:

```python
    assert cockpit.audit_chain.verified is True
    assert cockpit.audit_chain.event_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_trust_cockpit.py -v`
Expected: FAIL with `AttributeError: 'LegalOpsTrustCockpit' object has no attribute 'audit_chain'`

- [ ] **Step 3: Add the field to `LegalOpsTrustCockpit`**

In `models.py`, replace:

```python
    artifact_summary: TrustCockpitArtifactSummary
    next_actions: list[str]
    markdown: str
```

with:

```python
    artifact_summary: TrustCockpitArtifactSummary
    audit_chain: AuditChainVerification
    next_actions: list[str]
    markdown: str
```

- [ ] **Step 4: Compute and render the audit chain in `src/trust_cockpit.py`**

Replace the import block:

```python
from models import (
    CustomerCommitmentRecord,
    LegalOpsAssessment,
    LegalOpsTrustCockpit,
    SourceVerifiedReviewPacketRun,
    TrustCockpitArtifactDigest,
    TrustCockpitArtifactSummary,
    TrustCockpitCommitmentSummary,
    TrustCockpitDecisionSummary,
    TrustCockpitMetadata,
    TrustCockpitReviewGateSummary,
    TrustCockpitSourceSummary,
)
```

with:

```python
from models import (
    AuditChainVerification,
    CustomerCommitmentRecord,
    LegalOpsAssessment,
    LegalOpsTrustCockpit,
    SourceVerifiedReviewPacketRun,
    TrustCockpitArtifactDigest,
    TrustCockpitArtifactSummary,
    TrustCockpitCommitmentSummary,
    TrustCockpitDecisionSummary,
    TrustCockpitMetadata,
    TrustCockpitReviewGateSummary,
    TrustCockpitSourceSummary,
    verify_audit_chain,
)
```

Add a render helper right after `_render_artifacts`:

```python
def _render_audit_chain(chain: AuditChainVerification) -> list[str]:
    return [
        f"- Verified: {_format_bool(chain.verified)}",
        f"- Events: {chain.event_count}",
        f"- Chain root hash: {chain.chain_root_hash or 'none'}",
        f"- Reason: {chain.reason}",
    ]
```

In `render_trust_cockpit_markdown`, replace:

```python
    lines.extend(["", "## Artifact Integrity"])
    lines.extend(_render_artifacts(cockpit.artifact_summary))
    lines.extend(["", "## Next Actions"])
    lines.extend(f"- {action}" for action in cockpit.next_actions)
    return "\n".join(lines) + "\n"
```

with:

```python
    lines.extend(["", "## Artifact Integrity"])
    lines.extend(_render_artifacts(cockpit.artifact_summary))
    lines.extend(["", "## Audit Chain Integrity"])
    lines.extend(_render_audit_chain(cockpit.audit_chain))
    lines.extend(["", "## Next Actions"])
    lines.extend(f"- {action}" for action in cockpit.next_actions)
    return "\n".join(lines) + "\n"
```

In `build_trust_cockpit`, replace:

```python
    run = source_verified_run or build_source_verified_review_packet_run(assessment)
    commitments = _safe_commitments(assessment)
    artifact_summary = _artifact_summary(artifact_manifest)
    cockpit = LegalOpsTrustCockpit(
```

with:

```python
    run = source_verified_run or build_source_verified_review_packet_run(assessment)
    commitments = _safe_commitments(assessment)
    artifact_summary = _artifact_summary(artifact_manifest)
    audit_chain = verify_audit_chain(assessment.audit_events)
    cockpit = LegalOpsTrustCockpit(
```

and replace:

```python
        artifact_summary=artifact_summary,
        next_actions=_next_actions(assessment, run),
        markdown="pending",
    )
```

with:

```python
        artifact_summary=artifact_summary,
        audit_chain=audit_chain,
        next_actions=_next_actions(assessment, run),
        markdown="pending",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_trust_cockpit.py -v`
Expected: `3 passed`

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all passing.

- [ ] **Step 7: Lint, format, type-check**

Run: `python -m ruff check models.py src/trust_cockpit.py tests/test_trust_cockpit.py && python -m black models.py src/trust_cockpit.py tests/test_trust_cockpit.py && python -m mypy models.py src/trust_cockpit.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add models.py src/trust_cockpit.py tests/test_trust_cockpit.py
git commit -m "feat: surface audit chain integrity in the trust cockpit"
```

---

### Task 7: `legal.audit.verify` MCP tool

**Files:**
- Modify: `src/mcp_tools.py`
- Test: `tests/test_mcp_tools.py` (extend)

**Interfaces:**
- Consumes: `verify_audit_chain`, `AuditChainVerification` (Task 1).

- [ ] **Step 1: Write the failing tests**

In `tests/test_mcp_tools.py`, replace:

```python
def test_mcp_manifest_exposes_controlled_tools():
    manifest = legal_ops_mcp_manifest()
    tool_names = {tool["name"] for tool in manifest["tools"]}
    assert tool_names == {
        "legal.matter.assess",
        "legal.review.decide",
        "legal.review.packet",
        "legal.review.packet.run",
        "legal.review.trust_cockpit",
        "legal.sources.list",
        "legal.sources.verify",
    }
```

with:

```python
def test_mcp_manifest_exposes_controlled_tools():
    manifest = legal_ops_mcp_manifest()
    tool_names = {tool["name"] for tool in manifest["tools"]}
    assert tool_names == {
        "legal.matter.assess",
        "legal.review.decide",
        "legal.review.packet",
        "legal.review.packet.run",
        "legal.review.trust_cockpit",
        "legal.audit.verify",
        "legal.sources.list",
        "legal.sources.verify",
    }
```

Append a new test at the end of the file:

```python
def test_mcp_audit_verify_tool_returns_chain_report():
    assessment = run_tool("legal.matter.assess", build_sample_matter().model_dump(mode="json"))
    result = run_tool("legal.audit.verify", assessment)

    assert result["verified"] is True
    assert result["event_count"] == 1
    assert result["chain_root_hash"] == assessment["audit_events"][0]["event_hash"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_mcp_tools.py -v`
Expected: FAIL — the manifest test fails on the missing `legal.audit.verify` name, and
the new test fails with `ValueError: unsupported tool: legal.audit.verify`.

- [ ] **Step 3: Add the tool to the manifest and dispatcher**

In `src/mcp_tools.py`, replace the import line:

```python
from models import LegalOpsAssessment, LegalOpsTrustCockpit, MatterIntake, ReviewDecision
```

with:

```python
from models import (
    AuditChainVerification,
    LegalOpsAssessment,
    LegalOpsTrustCockpit,
    MatterIntake,
    ReviewDecision,
    verify_audit_chain,
)
```

Replace the `legal.review.trust_cockpit` manifest entry and the closing of the tools list:

```python
            {
                "name": "legal.review.trust_cockpit",
                "description": (
                    "Assess a matter and return a local trust cockpit with review gates, "
                    "source boundaries and artifact evidence fields."
                ),
                "input_schema": MatterIntake.model_json_schema(),
                "output_schema": LegalOpsTrustCockpit.model_json_schema(),
            },
        ],
    }
```

with:

```python
            {
                "name": "legal.review.trust_cockpit",
                "description": (
                    "Assess a matter and return a local trust cockpit with review gates, "
                    "source boundaries and artifact evidence fields."
                ),
                "input_schema": MatterIntake.model_json_schema(),
                "output_schema": LegalOpsTrustCockpit.model_json_schema(),
            },
            {
                "name": "legal.audit.verify",
                "description": (
                    "Verify the tamper-evident hash chain on an assessment's audit trail."
                ),
                "input_schema": LegalOpsAssessment.model_json_schema(),
                "output_schema": AuditChainVerification.model_json_schema(),
            },
        ],
    }
```

Replace the end of `run_tool`:

```python
    if name == "legal.review.trust_cockpit":
        matter = MatterIntake.model_validate(payload)
        assessment = assess_matter(matter)
        cockpit = build_trust_cockpit(assessment, fixture="mcp:legal.review.trust_cockpit")
        return cockpit.model_dump(mode="json", by_alias=True)

    raise ValueError(f"unsupported tool: {name}")
```

with:

```python
    if name == "legal.review.trust_cockpit":
        matter = MatterIntake.model_validate(payload)
        assessment = assess_matter(matter)
        cockpit = build_trust_cockpit(assessment, fixture="mcp:legal.review.trust_cockpit")
        return cockpit.model_dump(mode="json", by_alias=True)

    if name == "legal.audit.verify":
        assessment = LegalOpsAssessment.model_validate(payload)
        return verify_audit_chain(assessment.audit_events).model_dump(mode="json")

    raise ValueError(f"unsupported tool: {name}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_mcp_tools.py -v`
Expected: `8 passed`

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: `46 passed`. This is the full count for the plan — if it doesn't match,
stop and reconcile before moving to Task 8 (which cites this number in docs).

- [ ] **Step 6: Lint, format, type-check**

Run: `python -m ruff check src/mcp_tools.py tests/test_mcp_tools.py && python -m black src/mcp_tools.py tests/test_mcp_tools.py && python -m mypy src/mcp_tools.py`
Expected: no errors.

- [ ] **Step 7: Compile check**

Run: `python -m compileall master_orchestrator.py models.py src runtime_agent tests`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add src/mcp_tools.py tests/test_mcp_tools.py
git commit -m "feat: add legal.audit.verify MCP tool"
```

---

### Task 8: Documentation and proof artifacts

**Files:**
- Modify: `README.md`
- Modify: `docs/API.md`
- Modify: `docs/FEATURES.md`
- Modify: `docs/code_explanation.md`
- Modify: `CASE_STUDY.md`
- Regenerate: `examples/trust-cockpit-saas-msa-2026-06-30.md`, `examples/trust-cockpit-saas-msa-2026-06-30.json`
- Create: `examples/audit-chain-saas-msa-2026-06-30.json`

No new tests — this task documents and proves Tasks 1–7. Verification is "the
documented commands produce the claimed output," checked at the end of the task.

- [ ] **Step 1: Regenerate the dated trust cockpit proof snapshot**

Run, from the repo root with the virtualenv active:

```bash
python -m src.cli \
  --input examples/matters/saas_msa_deviation.json \
  --json-output demo_output/assessment.json \
  --packet-output demo_output/review-packet.md \
  --commitments-output demo_output/customer-commitments.json \
  --sources-output demo_output/source-verification.json \
  --review-runner-output demo_output/source-verified-review-runner.json \
  --manifest-output demo_output/artifact-manifest.json \
  --trust-cockpit-output examples/trust-cockpit-saas-msa-2026-06-30.md \
  --trust-cockpit-json-output examples/trust-cockpit-saas-msa-2026-06-30.json
```

Expected: command exits 0;
`examples/trust-cockpit-saas-msa-2026-06-30.json` now contains an `"audit_chain"`
object with `"verified": true` and `"event_count": 1`; the `.md` file now has an
"## Audit Chain Integrity" section.

- [ ] **Step 2: Generate the standalone audit chain proof artifact**

Run:

```bash
python -m src.cli \
  --input examples/matters/saas_msa_deviation.json \
  --approve-note "Approved after commercial counsel review of the synthetic SaaS MSA deviation for the round-2 audit integrity chain proof." \
  --reviewer "General Counsel" \
  --audit-chain-output examples/audit-chain-saas-msa-2026-06-30.json
```

Expected: command exits 0; `examples/audit-chain-saas-msa-2026-06-30.json` shows
`"verified": true`, `"event_count": 2`, and a non-null `"chain_root_hash"`.

- [ ] **Step 3: Update `README.md`**

Replace:

```markdown
CI: passing. Deterministic test suite: 39 checks.
```

with:

```markdown
CI: passing. Deterministic test suite: 46 checks.
```

In the "What it checks / does" table, replace:

```markdown
| Trust Cockpit | Reviewer evidence | Shows review state, source boundary, export gate, commitments and artifact integrity |
```

with:

```markdown
| Trust Cockpit | Reviewer evidence | Shows review state, source boundary, export gate, commitments and artifact integrity |
| Audit Integrity Chain | Tamper evidence | Hash-chains every audit event; export is blocked if the chain does not verify |
```

After the "## Committed trust cockpit proof" section (ends with the paragraph about
"local artifact digests and next actions."), insert a new section before
"## Core workflow":

```markdown

## Committed audit chain proof

The audit trail is a SHA-256 hash chain: each event commits to the hash of the one
before it, so altering, reordering or dropping a past event is detectable, and export
is blocked if the chain does not verify.

- [`examples/audit-chain-saas-msa-2026-06-30.json`](examples/audit-chain-saas-msa-2026-06-30.json)

The snapshot is generated from the same synthetic SaaS MSA fixture after a documented
human approval, and shows a two-event chain (`assessment_created`,
`review_decision_applied`) that verifies.
```

In "## Repository structure", replace:

```markdown
- [`src/trust_cockpit.py`](src/trust_cockpit.py): Reviewer-facing trust cockpit builder and renderers.
```

with:

```markdown
- [`src/trust_cockpit.py`](src/trust_cockpit.py): Reviewer-facing trust cockpit builder and renderers.
- [`src/audit_chain.py`](src/audit_chain.py): Tamper-evident hash chain builder for the audit trail.
```

In "## Generate review artifacts", replace:

```bash
python -m src.cli \
  --input examples/matters/saas_msa_deviation.json \
  --json-output demo_output/assessment.json \
  --packet-output demo_output/review-packet.md \
  --commitments-output demo_output/customer-commitments.json \
  --sources-output demo_output/source-verification.json \
  --review-runner-output demo_output/source-verified-review-runner.json \
  --manifest-output demo_output/artifact-manifest.json \
  --trust-cockpit-output demo_output/trust-cockpit.md \
  --trust-cockpit-json-output demo_output/trust-cockpit.json
```

with:

```bash
python -m src.cli \
  --input examples/matters/saas_msa_deviation.json \
  --json-output demo_output/assessment.json \
  --packet-output demo_output/review-packet.md \
  --commitments-output demo_output/customer-commitments.json \
  --sources-output demo_output/source-verification.json \
  --review-runner-output demo_output/source-verified-review-runner.json \
  --manifest-output demo_output/artifact-manifest.json \
  --audit-chain-output demo_output/audit-chain.json \
  --trust-cockpit-output demo_output/trust-cockpit.md \
  --trust-cockpit-json-output demo_output/trust-cockpit.json
```

In "## MCP surface", replace:

```markdown
`mcp.json` exposes a local `legal-ops-agent` server with seven controlled tools:

- `legal.matter.assess`: create a structured assessment from a typed legal matter.
- `legal.review.decide`: apply a documented human review decision.
- `legal.review.packet`: render a markdown review packet from an assessment.
- `legal.review.packet.run`: assess a matter and return the source-verified packet, source manifest and policy envelope in one payload.
- `legal.review.trust_cockpit`: assess a matter and return reviewer evidence for review gates, source boundary, commitments and artifact integrity.
- `legal.sources.list`: show the public or synthetic source boundary for the demo.
- `legal.sources.verify`: verify source-reference boundaries without fetching external content.
```

with:

```markdown
`mcp.json` exposes a local `legal-ops-agent` server with eight controlled tools:

- `legal.matter.assess`: create a structured assessment from a typed legal matter.
- `legal.review.decide`: apply a documented human review decision.
- `legal.review.packet`: render a markdown review packet from an assessment.
- `legal.review.packet.run`: assess a matter and return the source-verified packet, source manifest and policy envelope in one payload.
- `legal.review.trust_cockpit`: assess a matter and return reviewer evidence for review gates, source boundary, commitments and artifact integrity.
- `legal.audit.verify`: verify the tamper-evident hash chain on an assessment's audit trail.
- `legal.sources.list`: show the public or synthetic source boundary for the demo.
- `legal.sources.verify`: verify source-reference boundaries without fetching external content.
```

In "## Known limitations", replace:

```markdown
3. The audit trail is in-process, not an append-only external store.
4. Roles/permissions are modelled, not enforced against a real IdP.
Next production step: real auth for approval tiers, ticketing integration, live SLA
tracking, and a persisted append-only audit log.
```

with:

```markdown
3. The audit trail is tamper-evident (hash-chained, verifiable with `legal.audit.verify`)
   but still in-process, not persisted to an append-only external store.
4. Roles/permissions are modelled, not enforced against a real IdP.
Next production step: real auth for approval tiers, ticketing integration, live SLA
tracking, and persisting the hash-chained audit log to an append-only external store.
```

- [ ] **Step 4: Update `docs/API.md`**

After the `## legal.review.trust_cockpit` section (ends with its example call's closing
` ``` `) and before `## legal.sources.verify`, insert:

```markdown
## `legal.audit.verify`

Purpose: verify the tamper-evident hash chain on an assessment's audit trail.

Input schema: `LegalOpsAssessment.model_json_schema()`.

Output schema: `AuditChainVerification.model_json_schema()`.

Safety limits:

1. The tool only recomputes hashes over the supplied assessment; it has no external effects.
2. A broken or empty chain reports `verified: false` with a `reason` and `broken_at_seq`.
3. The same check runs inside the export gate: an assessment cannot carry `export_allowed: true` over an unverified chain.

Example call:

```json
{
  "name": "legal.audit.verify",
  "arguments": "<LegalOpsAssessment JSON>"
}
```
```

- [ ] **Step 5: Update `docs/FEATURES.md`**

After the "## LegalOps Trust Cockpit" section (ends with its four-item implementation
list) and before "## Review Packets And Artifact Manifests", insert:

```markdown
## Audit Integrity Chain

Hash-chains every audit event: each event commits to the hash of the one before it,
so altering, reordering or dropping a past event is detectable. Export is blocked if
the chain does not verify, in addition to the existing review-state, blocker-finding
and review-note conditions. Surfaced in the Trust Cockpit, a standalone CLI output and
a dedicated MCP tool.

Implementation:

1. `models.py`
2. `src/audit_chain.py`
3. `tests/test_audit_chain.py`
```

- [ ] **Step 6: Update `docs/code_explanation.md`**

Replace:

```markdown
- `AuditEvent`
- `ReviewDecision`
- `LegalOpsAssessment`

The export gate is enforced at model level. A record cannot set `export_allowed=true` unless the review state is `approved`, a written review note is present and no blocker finding remains.
```

with:

```markdown
- `AuditEvent`
- `AuditChainVerification`
- `ReviewDecision`
- `LegalOpsAssessment`

The export gate is enforced at model level. A record cannot set `export_allowed=true` unless the review state is `approved`, a written review note is present, no blocker finding remains and the audit event hash chain verifies.
```

Replace:

```markdown
- Applies a human review decision with an audit note.

### `src/source_verification.py`
```

with:

```markdown
- Applies a human review decision with an audit note.

### `src/audit_chain.py`

Builds chain-linked audit events. `append_audit_event` computes each event's `seq`, `prev_hash` and `event_hash` so the trail is tamper-evident; `models.verify_audit_chain` recomputes and checks the chain.

### `src/source_verification.py`
```

- [ ] **Step 7: Update `CASE_STUDY.md`**

Replace:

```markdown
## Controls
The agent cannot release output on its own. The approval gate is the spine: a requested change leaves the matter blocked until a human resolves it, and the override is recorded with a justification. Provenance and the audit trail are first-class, not afterthoughts.
```

with:

```markdown
## Controls
The agent cannot release output on its own. The approval gate is the spine: a requested change leaves the matter blocked until a human resolves it, and the override is recorded with a justification. Provenance and the audit trail are first-class, not afterthoughts. The audit trail is a SHA-256 hash chain — each event commits to the one before it, so tampering after the fact is detectable, and export is blocked if the chain does not verify.
```

- [ ] **Step 8: Verify the documented commands actually match reality**

Run:

```bash
python -m pytest -q
```

Expected: `46 passed`.

Run:

```bash
grep -c "audit_chain" examples/trust-cockpit-saas-msa-2026-06-30.json examples/audit-chain-saas-msa-2026-06-30.json
```

Expected: a nonzero count in both (sanity check the regenerated/created files actually
contain the new field).

- [ ] **Step 9: Commit**

```bash
git add README.md docs/API.md docs/FEATURES.md docs/code_explanation.md CASE_STUDY.md \
  examples/trust-cockpit-saas-msa-2026-06-30.md examples/trust-cockpit-saas-msa-2026-06-30.json \
  examples/audit-chain-saas-msa-2026-06-30.json
git commit -m "docs: document the audit integrity chain and regenerate proof snapshots"
```

---

### Task 9: Competitive research, round 2

**Files:**
- Modify: `docs/competitive-research-2026-06-30.md`

No tests — this is a research and writing task. Verification is in Step 4.

- [ ] **Step 1: Run targeted searches**

Using whatever web search capability is available in the execution environment, run
these queries and record what comes back (repository names, app names, one-line
descriptions, and the URL of each search):

- GitHub: `tamper-evident audit log legal`
- GitHub: `hash chain audit trail compliance`
- GitHub: `verifiable audit trail SaaS`
- Apple App Store (iTunes Search API, same pattern as round 1):
  `https://itunes.apple.com/search?term=audit%20trail%20compliance&country=us&entity=software&limit=20`
- Google Play: `https://play.google.com/store/search?q=audit%20trail%20compliance&c=apps&hl=en_US&gl=US`
- Chrome Web Store: `https://chromewebstore.google.com/search/tamper%20evident%20audit`
- Google Workspace Marketplace: `https://workspace.google.com/marketplace/search/audit%20trail`
- Slack Marketplace: `https://slack.com/marketplace/search?q=audit%20trail`
- Retry, since round 1 reported both blocked: Microsoft AppSource
  (`https://appsource.microsoft.com/en-us/marketplace/apps?search=audit%20trail&page=1`)
  and Amazon Appstore (`https://www.amazon.com/s?k=audit+trail+compliance&i=mobile-apps`).

- [ ] **Step 2: Draft the round-2 section**

Append to `docs/competitive-research-2026-06-30.md`, following the existing file's
structure (`## Search Surfaces` / signals by surface / `## Product Implication` /
`## Source Links`). Use this skeleton, filling in the bracketed parts with what Step 1
actually found — do not invent results:

```markdown

## Round 2: Audit Integrity Chain

Date: 2026-06-30

Purpose: check whether tamper-evident or hash-chained audit trails are a contested
space before committing to it as the round-2 differentiator.

### Search Surfaces

- GitHub repository search for `tamper-evident audit log legal`, `hash chain audit
  trail compliance`, and `verifiable audit trail SaaS`.
- Apple App Store and Google Play searches for `audit trail compliance`.
- Chrome Web Store, Google Workspace Marketplace, and Slack Marketplace searches for
  `audit trail`.
- Retried Microsoft AppSource and Amazon Appstore (both blocked automated access in
  round 1) with the same `audit trail` query.

### GitHub Signals

[List what actually came back: repo names, stars/activity if visible, one line on
what each does. If results cluster around generic "audit log" libraries (e.g.
event-sourcing frameworks) rather than legal/compliance tooling, say so explicitly —
that's itself a finding.]

### App Store And Marketplace Signals

[Summarize what came back across Apple, Google Play, Chrome Web Store, Workspace
Marketplace, and Slack. Note whether AppSource/Amazon were reachable this time.]

### Product Implication

[State plainly whether the audit integrity chain is still white space after this
deeper look, or whether something close to it exists. Either answer is fine — this
section exists to be honest, not to justify the feature after the fact.]

### Source Links

- GitHub tamper-evident audit log search: <https://github.com/search?q=tamper-evident+audit+log+legal&type=repositories>
- GitHub hash chain audit trail search: <https://github.com/search?q=hash+chain+audit+trail+compliance&type=repositories>
- GitHub verifiable audit trail search: <https://github.com/search?q=verifiable+audit+trail+SaaS&type=repositories>
- Apple App Store audit trail API: <https://itunes.apple.com/search?term=audit%20trail%20compliance&country=us&entity=software&limit=20>
- Google Play audit trail search: <https://play.google.com/store/search?q=audit%20trail%20compliance&c=apps&hl=en_US&gl=US>
- Chrome Web Store audit trail search: <https://chromewebstore.google.com/search/tamper%20evident%20audit>
- Google Workspace Marketplace audit trail search: <https://workspace.google.com/marketplace/search/audit%20trail>
- Slack Marketplace audit trail search: <https://slack.com/marketplace/search?q=audit%20trail>
- Microsoft AppSource audit trail search attempted: <https://appsource.microsoft.com/en-us/marketplace/apps?search=audit%20trail&page=1>
- Amazon Appstore audit trail search attempted: <https://www.amazon.com/s?k=audit+trail+compliance&i=mobile-apps>
```

- [ ] **Step 3: Append the filled-in section to the file**

Add the completed section (from Step 2, with real findings substituted for the
bracketed placeholders) to the end of `docs/competitive-research-2026-06-30.md`.

- [ ] **Step 4: Verify**

Run: `grep -c "Round 2" docs/competitive-research-2026-06-30.md`
Expected: `1` (the new section header).

Confirm no bracketed placeholder text (`[List`, `[Summarize`, `[State`) remains in the
committed file:

Run: `grep -n '^\[' docs/competitive-research-2026-06-30.md`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add docs/competitive-research-2026-06-30.md
git commit -m "docs: add round-2 competitive research for the audit integrity chain"
```

---

### Task 10: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full check**

Run: `make check`
Expected: Ruff, Black, MyPy, Pytest (46 passed), and `compileall` all pass.

- [ ] **Step 2: Diff hygiene**

Run: `git diff --check`
Expected: no output (no trailing-whitespace or conflict-marker issues).

- [ ] **Step 3: Secret scan**

Run: `git diff origin/main -- . | grep -iE "api[_-]?key|secret|password|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY" || echo "clean"`
Expected: `clean`.

- [ ] **Step 4: Confirm working tree is committed**

Run: `git status --short`
Expected: no output (everything from Tasks 1–9 is committed).

- [ ] **Step 5: Report and stop**

Summarize for the user: tasks completed, final test count, files changed, and the new
proof artifact paths. Do **not** run `git push`. Ask the user whether to push before
doing so — this repo's instructions require an explicit push confirmation.

---
