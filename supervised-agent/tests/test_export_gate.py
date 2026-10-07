from typing import Any

import pytest

from models import AuditChainVerification, ReviewDecision
from src.export_gate import (
    ExportBlockedError,
    ExportContext,
    RequiredDecision,
    StatefulContext,
    evaluate_export_eligibility,
    require_export_eligibility,
)
from src.legal_ops import apply_review_decision, assess_matter, build_sample_matter

NOTE = "Approved after commercial counsel review of the synthetic MSA deviation."
INTACT = AuditChainVerification(
    verified=True, event_count=3, chain_root_hash="a" * 64, reason="chain intact"
)


def _assessment(approved: bool = True):
    assessment = assess_matter(build_sample_matter())
    if approved:
        assessment = apply_review_decision(
            assessment, ReviewDecision(reviewer="General Counsel", state="approved", note=NOTE)
        )
    return assessment


def _stateful(**overrides) -> StatefulContext:
    values: dict[str, Any] = {
        "matter_id": "PM-TEST",
        "matter_state": "approved",
        "current_version": 2,
        "current_content_hash": "c" * 64,
        "assessment_version": 2,
        "assessment_content_hash": "c" * 64,
        "current_review_hash": "r" * 64,
        "open_blocking_items": [],
        "required_decisions": [
            RequiredDecision(
                requirement="final_approval:General Counsel",
                binds_review_hash=True,
                actor_id="syn-approver-gc",
                version=2,
                content_hash="c" * 64,
                review_hash="r" * 64,
            )
        ],
        "matter_chain": INTACT,
    }
    values.update(overrides)
    return StatefulContext(**values)


def _context(kind="delivery_package", approved=True, **overrides) -> ExportContext:
    assessment = _assessment(approved)
    values: dict[str, Any] = {
        "kind": kind,
        "assessment": assessment,
        "change_set_assessment_id": assessment.assessment_id,
        "recorded_document_sha256": "d" * 64,
        "actual_document_sha256": "d" * 64,
        "change_decisions": {"chg-1": "accepted", "chg-2": "amended"},
        "stateful": _stateful(),
    }
    values.update(overrides)
    return ExportContext(**values)


def _failed(context: ExportContext) -> set[str]:
    result = evaluate_export_eligibility(context)
    return {check.check_id for check in result.checks if check.required and check.status != "pass"}


def test_fully_satisfied_delivery_context_is_eligible() -> None:
    result = evaluate_export_eligibility(_context())
    assert result.eligible and result.external_delivery_allowed is False
    assert {check.status for check in result.checks} == {"pass"}


@pytest.mark.parametrize(
    ("overrides", "failed_check"),
    [
        ({"approved": False}, "assessment_approved"),
        ({"change_decisions": {"chg-1": "accepted", "chg-2": "pending"}}, "changes_decided"),
        ({"change_decisions": {"chg-1": "clarification_requested"}}, "changes_decided"),
        ({"actual_document_sha256": "e" * 64}, "document_hash_matches"),
        ({"change_set_assessment_id": "loa_other_matter_00"}, "assessment_bound_to_version"),
        ({"stateful": _stateful(assessment_version=1)}, "assessment_bound_to_version"),
        ({"stateful": _stateful(assessment_content_hash="0" * 64)}, "assessment_bound_to_version"),
        ({"stateful": _stateful(open_blocking_items=["comment c-001"])}, "no_unresolved_blockers"),
        ({"stateful": _stateful(matter_state="review")}, "matter_state_permits_delivery"),
        ({"stateful": _stateful(required_decisions=[])}, "required_reviewer_decisions"),
        (
            {
                "stateful": _stateful(
                    matter_chain=AuditChainVerification(
                        verified=False,
                        event_count=3,
                        broken_at_seq=1,
                        reason="event_hash mismatch at seq 1",
                    )
                )
            },
            "audit_chain_verified",
        ),
    ],
)
def test_each_condition_blocks_on_its_own(overrides, failed_check) -> None:
    assert failed_check in _failed(_context(**overrides))


@pytest.mark.parametrize(
    ("decision", "phrase"),
    [
        ({"actor_id": None}, "is missing"),
        ({"invalidated": True}, "invalidated by a later change"),
        ({"version": 1}, "not the current version"),
        ({"content_hash": "0" * 64}, "not the current version"),
        ({"review_hash": "0" * 64}, "predates a later change decision"),
    ],
)
def test_approval_must_be_bound_to_the_exact_reviewed_version(decision, phrase) -> None:
    base = _stateful().required_decisions[0].model_dump()
    stale = RequiredDecision(**{**base, **decision})
    context = _context(stateful=_stateful(required_decisions=[stale]))
    with pytest.raises(ExportBlockedError, match=phrase):
        require_export_eligibility(context)


def test_stateless_caller_never_gets_a_delivery_package() -> None:
    context = _context(stateful=None)
    assert "required_reviewer_decisions" in _failed(context)
    reviewed = _context(kind="reviewed_document", stateful=None)
    assert evaluate_export_eligibility(reviewed).eligible


def test_internal_review_needs_no_approval_but_a_clean_source_boundary() -> None:
    draft = _context(kind="internal_review", approved=False, change_decisions={"chg-1": "pending"})
    draft = draft.model_copy(
        update={"stateful": _stateful(matter_state="review", open_blocking_items=["c-1"])}
    )
    assert evaluate_export_eligibility(draft).eligible

    matter = build_sample_matter().model_copy(update={"source_refs": ["privileged:advice-note"]})
    blocked = assess_matter(matter)
    context = ExportContext(
        kind="internal_review",
        assessment=blocked,
        change_set_assessment_id=blocked.assessment_id,
        recorded_document_sha256="d" * 64,
        actual_document_sha256="d" * 64,
        stateful=_stateful(matter_state="triage"),
    )
    assert "source_boundary_clear" in _failed(context)


def test_missing_assessment_blocks_everything() -> None:
    context = ExportContext(kind="delivery_package", stateful=_stateful())
    assert not evaluate_export_eligibility(context).eligible
    assert {"assessment_present", "assessment_approved"} <= _failed(context)
