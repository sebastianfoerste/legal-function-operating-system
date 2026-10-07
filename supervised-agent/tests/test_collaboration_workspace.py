import hashlib
import zipfile

import pytest

from models import ReviewDecision
from src.collaboration_workspace import (
    build_change_set,
    build_matter_list,
    build_timeline,
    comment_on_list_item,
    decide_change,
    render_annotated_docx,
    render_review_room,
    resolve_list_item,
)
from src.docx_redline import list_tracked_changes, read_paragraph_texts
from src.export_gate import ExportBlockedError
from src.legal_ops import apply_review_decision, assess_matter, build_sample_matter
from src.pilot.fixtures import build_synthetic_msa

APPROVAL_NOTE = "Approved after commercial counsel review of the synthetic MSA deviation."


def _approved(assessment):
    return apply_review_decision(
        assessment, ReviewDecision(reviewer="General Counsel", state="approved", note=APPROVAL_NOTE)
    )


def _decide_all(change_set, decision="accepted"):
    for change in list(change_set.changes):
        change_set = decide_change(change_set, change.id, decision)
    return change_set


def test_decided_change_set_cannot_export_while_assessment_is_unapproved(tmp_path) -> None:
    """Regression: a fully decided change set used to export under an unapproved assessment."""

    assessment = assess_matter(build_sample_matter())
    source = tmp_path / "source.docx"
    source.write_bytes(build_synthetic_msa("routine"))
    change_set = _decide_all(build_change_set(assessment, source))
    assert change_set.all_changes_decided
    assert assessment.review_state == "needs_review" and not assessment.export_allowed

    with pytest.raises(ExportBlockedError, match="assessment_approved"):
        render_annotated_docx(change_set, source, tmp_path / "out.docx", assessment=assessment)
    assert not (tmp_path / "out.docx").exists()

    with pytest.raises(TypeError):
        render_annotated_docx(change_set, source, tmp_path / "out.docx")  # type: ignore[call-arg]


def test_change_set_is_bound_to_its_assessment(tmp_path) -> None:
    source = tmp_path / "source.docx"
    source.write_bytes(build_synthetic_msa("routine"))
    change_set = _decide_all(build_change_set(assess_matter(build_sample_matter()), source))
    other = build_sample_matter().model_copy(update={"title": "A different approved matter"})
    with pytest.raises(ExportBlockedError, match="different assessment"):
        render_annotated_docx(
            change_set, source, tmp_path / "out.docx", assessment=_approved(assess_matter(other))
        )


def test_document_specific_changes_are_tracked_at_their_locator(tmp_path) -> None:
    assessment = assess_matter(build_sample_matter())
    source = tmp_path / "source.docx"
    source.write_bytes(build_synthetic_msa("routine"))
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    change_set = build_change_set(assessment, source)
    assert [change.rule_id for change in change_set.changes] == ["payment-terms", "audit-right"]
    assert all(change.anchor is not None and change.original_text for change in change_set.changes)

    with pytest.raises(ExportBlockedError, match="every proposed change to be decided"):
        render_annotated_docx(
            change_set, source, tmp_path / "blocked.docx", assessment=_approved(assessment)
        )
    change_set = decide_change(change_set, change_set.changes[0].id, "accepted")
    change_set = decide_change(change_set, change_set.changes[1].id, "rejected")
    with pytest.raises(ValueError, match="must not overwrite"):
        render_annotated_docx(change_set, source, source, assessment=_approved(assessment))

    output = render_annotated_docx(
        change_set, source, tmp_path / "reviewed.docx", assessment=_approved(assessment)
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_digest
    assert zipfile.is_zipfile(output)
    reviewed = output.read_bytes()
    assert read_paragraph_texts(reviewed, "rejected") == read_paragraph_texts(
        source.read_bytes(), "accepted"
    )
    accepted_view = "\n".join(read_paragraph_texts(reviewed, "accepted"))
    assert "within thirty (30) days of receipt" in accepted_view
    assert "at any time and without prior notice" in accepted_view  # rejected change not applied
    assert [(c.kind, c.text) for c in list_tracked_changes(reviewed)] == [
        ("deletion", "ninety (90) days"),
        ("insertion", "thirty (30) days"),
    ]


def test_changed_source_document_is_refused(tmp_path) -> None:
    assessment = assess_matter(build_sample_matter())
    source = tmp_path / "source.docx"
    source.write_bytes(build_synthetic_msa("routine"))
    change_set = _decide_all(build_change_set(assessment, source))
    source.write_bytes(build_synthetic_msa("specialist"))
    with pytest.raises(ExportBlockedError, match="digest does not match"):
        render_annotated_docx(
            change_set, source, tmp_path / "out.docx", assessment=_approved(assessment)
        )


def test_no_generic_wording_is_proposed_without_a_document() -> None:
    change_set = build_change_set(assess_matter(build_sample_matter()))
    assert change_set.changes == []
    assert change_set.schema_id == "document.change-set.v2"


def test_blocked_source_prevents_document_processing(tmp_path) -> None:
    matter = build_sample_matter().model_copy(update={"source_refs": ["confidential:memo"]})
    with pytest.raises(ValueError, match="blocked source references"):
        build_change_set(assess_matter(matter))


def test_matter_lists_require_evidence_and_timeline_is_hash_chained() -> None:
    matter_list = build_matter_list(assess_matter(build_sample_matter()))
    assert matter_list == build_matter_list(assess_matter(build_sample_matter()))
    assert matter_list.items[0].due_at == "1970-01-15T00:00:00+00:00"
    with pytest.raises(ValueError, match="evidence"):
        resolve_list_item(matter_list, matter_list.items[0].id, [])
    resolved = resolve_list_item(
        matter_list, matter_list.items[0].id, ["synthetic:review-evidence"]
    )
    resolved = comment_on_list_item(resolved, resolved.items[0].id, "Reviewer", "Checked")
    assert resolved.items[0].status == "resolved"
    assert resolved.items[0].comments[0]["createdAt"] == "1970-01-01T00:00:00+00:00"
    timeline = build_timeline(resolved)
    assert all(
        event.previous_hash == (timeline[index - 1].event_hash if index else None)
        for index, event in enumerate(timeline)
    )
    assert {event.event_type for event in timeline} >= {
        "matter_list_item_resolved",
        "matter_list_item_commented",
    }
    comment_event = next(event for event in timeline if event.event_type.endswith("commented"))
    assert comment_event.occurred_at == resolved.items[0].comments[0]["createdAt"]


def test_source_date_epoch_rejects_out_of_range_values(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "999999999999999999999")
    with pytest.raises(ValueError, match="valid integer Unix timestamp"):
        build_matter_list(assess_matter(build_sample_matter()))


def test_static_review_room_snapshot_offers_no_unsaved_controls(tmp_path) -> None:
    assessment = assess_matter(build_sample_matter())
    source = tmp_path / "source.docx"
    source.write_bytes(build_synthetic_msa("routine"))
    room = render_review_room(
        assessment,
        build_change_set(assessment, source),
        build_matter_list(assessment),
        tmp_path / "review-room.html",
    )
    content = room.read_text()
    assert "Nothing on this page is saved" in content
    assert "External access and delivery are disabled" in content
    assert "<button" not in content and "<script" not in content
    assert "ninety (90) days" in content
    assert "http://" not in content and "https://" not in content
