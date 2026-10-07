"""Shared builders for the document and pilot tests. Everything here is fabricated."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from models import MatterIntake, ReviewState
from src.pilot.evidence.session import (
    EvidenceClass,
    PilotReviewDraft,
    PilotReviewSession,
    close_review_session,
    mark_draft_reviewable,
    prepare_review_draft,
    record_material_omission,
    record_recommendation_decision,
    start_review_session,
)

DOCUMENT_TEXTS = {
    "msa": ("contract", "data/msa.md", "Synthetic master agreement text.\n"),
    "memo": ("client_instruction", "matter/memo.md", "Synthetic instruction memo.\n"),
}


def harness_root() -> Path:
    """The sibling harness checkout, for checks that cannot run in CI."""

    value = os.environ.get("CONTRACT_EVAL_HARNESS_ROOT")
    if not value or not Path(value).is_dir():
        pytest.skip("CONTRACT_EVAL_HARNESS_ROOT does not name a harness checkout")
    return Path(value)


def write_documents(root: Path) -> list[dict[str, str]]:
    documents = []
    for document_id, (kind, path, text) in DOCUMENT_TEXTS.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        documents.append(
            {
                "document_id": document_id,
                "title": f"Synthetic {document_id}",
                "kind": kind,
                "path": path,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source_ref": f"synthetic:test-matter/{path}",
                "introduced_in": "round1",
            }
        )
    return documents


def document_matter(root: Path, **overrides) -> MatterIntake:
    fields = {
        "title": "Synthetic vendor paper review",
        "requester": "Head of Legal",
        "business_unit": "Legal",
        "matter_type": "contract",
        "jurisdiction": "Germany",
        "summary": "A fabricated vendor-paper review used to test the supervised workflow.",
        "data_categories": ["business contact data"],
        "customer_commitments": ["annual audit evidence"],
        "source_refs": ["synthetic:test-matter"],
        "matter_id": "test-matter",
        "round_id": "round1",
        "documents": write_documents(root),
    }
    return MatterIntake.model_validate({**fields, **overrides})


def prepared_draft(root: Path) -> PilotReviewDraft:
    return prepare_review_draft(
        document_matter(root),
        documents_root=root,
        intake_at="2026-03-02T09:00:00Z",
        ready_at="2026-03-02T09:00:02Z",
    )


def closed_session(
    draft: PilotReviewDraft,
    reviewer_id: str = "R01",
    evidence_class: EvidenceClass = "practising_lawyer",
    state: ReviewState = "approved",
) -> PilotReviewSession:
    """A full session: one correction, one rejection, one omission, then a decision."""

    first, second = (item.id for item in draft.recommendation_set.recommendations)
    session = start_review_session(
        draft,
        reviewer_id=reviewer_id,
        evidence_class=evidence_class,
        at="2026-03-02T10:00:00Z",
    )
    session = record_recommendation_decision(
        session,
        recommendation_id=first,
        decision="corrected",
        usefulness=3,
        reason="Fabricated reason for a correction.",
        corrected_text="Fabricated replacement wording.",
        at="2026-03-02T10:12:00Z",
    )
    session = mark_draft_reviewable(session, at="2026-03-02T10:20:00Z")
    session = record_recommendation_decision(
        session,
        recommendation_id=second,
        decision="rejected",
        usefulness=1,
        reason="Fabricated reason for a rejection.",
        at="2026-03-02T10:30:00Z",
    )
    session = record_material_omission(
        session, text="Fabricated omission.", at="2026-03-02T10:40:00Z"
    )
    return close_review_session(
        session,
        state=state,
        note="Fabricated decision note written for the test session only.",
        workflow_feedback="Fabricated feedback.",
        at="2026-03-02T10:45:00Z",
    )
