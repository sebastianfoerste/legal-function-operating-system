import pytest

from models import verify_audit_chain
from src.pilot_session import (
    PilotReviewDraft,
    PilotReviewSession,
    close_review_session,
    draft_problems,
    is_closed,
    mark_draft_reviewable,
    prepare_review_draft,
    record_change_decision,
    record_material_omission,
    review_sha256,
    session_problems,
    session_timing,
    start_review_session,
)
from tests.pilot_support import closed_session, document_matter, prepared_draft

NOT_IN_CHAIN = "the file is not what the audit chain records"
CLOSE = {
    "state": "approved",
    "note": "Fabricated decision note written for the test session only.",
}


def _started(draft, reviewer_id="R01"):
    return start_review_session(
        draft,
        reviewer_id=reviewer_id,
        evidence_class="practising_lawyer",
        at="2026-03-02T10:00:00Z",
    )


def _all_accepted(session, at="2026-03-02T10:05:00Z"):
    for change in session.change_set.changes:
        session = record_change_decision(
            session, change_id=change.id, decision="accepted", usefulness=4, at=at
        )
    return session


def _edited(model, **paths):
    """A copy of a stored file with fields changed as a text editor would change them."""

    data = model.model_dump(mode="json", by_alias=True)
    for path, value in paths.items():
        target = data
        *parents, leaf = path.split("__")
        for key in parents:
            target = target[int(key) if key.isdigit() else key]
        target[int(leaf) if leaf.isdigit() else leaf] = value
    return type(model).model_validate(data)


def test_draft_is_refused_until_every_document_is_verified(tmp_path):
    matter = document_matter(tmp_path)
    with pytest.raises(ValueError, match="every matter document verified: msa: not_checked"):
        prepare_review_draft(matter)

    (tmp_path / "data/msa.md").write_text("Edited after intake.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="msa: mismatch"):
        prepare_review_draft(matter, documents_root=tmp_path)


def test_draft_binds_recommendations_and_assessment_into_the_audit_chain(tmp_path):
    draft = prepared_draft(tmp_path)

    ready = draft.assessment.audit_events[-1]
    assert ready.event_type == "review_draft_ready"
    assert ready.details["review_sha256"] == draft.review_sha256 == review_sha256(draft.change_set)
    assert ready.details["finding_ids"] == ["change-1", "change-2"]
    assert verify_audit_chain(draft.assessment.audit_events).verified is True
    assert draft_problems(draft) == []
    reloaded = PilotReviewDraft.model_validate_json(draft.model_dump_json(by_alias=True))
    assert draft_problems(reloaded) == []

    with pytest.raises(ValueError, match="cannot precede the last recorded event"):
        prepare_review_draft(
            document_matter(tmp_path),
            documents_root=tmp_path,
            intake_at="2026-03-02T09:00:00Z",
            ready_at="2026-03-02T08:59:59Z",
        )


def test_edited_draft_is_refused_at_session_start_and_at_export(tmp_path):
    draft = prepared_draft(tmp_path)
    session = closed_session(draft)

    reworded = _edited(draft, change_set__changes__0__proposed_text="A rewritten recommendation.")
    assert draft_problems(reworded) == [
        "the draft's recommendations are not the ones its audit chain fixed"
    ]
    # Rewriting the stored hash to match does not help: the chain holds its own copy.
    rehashed = _edited(reworded, review_sha256=review_sha256(reworded.change_set))
    assert draft_problems(rehashed) == [
        "the draft's recommendations are not the ones its audit chain fixed"
    ]
    retitled = _edited(draft, assessment__matter__title="A different matter title")
    assert draft_problems(retitled) == [
        "the draft's assessment is not the one its audit chain fixed"
    ]
    rehashed_document = _edited(
        draft, assessment__document_verifications__0__expected_sha256="0" * 64
    )
    assert draft_problems(rehashed_document) != []

    with pytest.raises(ValueError, match="the draft failed verification"):
        _started(retitled)
    assert session_problems(session, retitled) == draft_problems(retitled)


def test_session_records_every_step_in_the_audit_chain(tmp_path):
    draft = prepared_draft(tmp_path)
    session = closed_session(draft)

    events = session.assessment.audit_events
    assert [event.event_type for event in events] == [
        "assessment_created",
        "review_draft_ready",
        "review_session_started",
        "change_decision_recorded",
        "draft_marked_reviewable",
        "change_decision_recorded",
        "material_omission_recorded",
        "review_decision_applied",
        "review_session_closed",
    ]
    assert {event.actor for event in events[2:]} == {"R01"}
    assert events[5].details == {
        "finding_id": "change-2",
        "decision": "rejected",
        "usefulness": 1,
        "reason": "Fabricated reason for a rejection.",
        "corrected_text": None,
    }
    assert events[7].details == {"state": "approved"}
    assert verify_audit_chain(events).verified is True
    assert session_problems(session, draft) == []
    assert session.assessment.export_allowed is True
    assert session.change_set.changes[0].reviewer == "R01"

    reloaded = PilotReviewSession.model_validate_json(session.model_dump_json(by_alias=True))
    assert session_problems(reloaded, draft) == []


def test_timings_are_read_from_the_audit_events(tmp_path):
    session = closed_session(prepared_draft(tmp_path))
    timing = session_timing(session)

    assert timing.draft_preparation_seconds == 2.0
    assert timing.minutes_to_reviewable_draft == 20.0
    assert timing.elapsed_review_minutes == 45.0
    assert (timing.review_minutes, timing.review_minutes_source) == (45.0, "audit_timestamps")


@pytest.mark.parametrize("declared", [61, 0, -5, float("nan"), float("inf")])
def test_declared_review_time_must_be_positive_and_within_the_session(tmp_path, declared):
    session = _all_accepted(_started(prepared_draft(tmp_path)))
    with pytest.raises(ValueError, match="positive and no more than the elapsed session time"):
        close_review_session(
            session, declared_review_minutes=declared, at="2026-03-02T11:00:00Z", **CLOSE
        )


def test_declared_review_time_is_kept_apart_from_elapsed_time(tmp_path):
    draft = prepared_draft(tmp_path)
    session = close_review_session(
        _all_accepted(_started(draft)),
        declared_review_minutes=40,
        at="2026-03-02T11:00:00Z",
        **CLOSE,
    )
    timing = session_timing(session)

    assert timing.minutes_to_reviewable_draft is None
    assert (timing.review_minutes, timing.elapsed_review_minutes) == (40.0, 60.0)
    assert timing.review_minutes_source == "reviewer_declared"
    reloaded = PilotReviewSession.model_validate_json(session.model_dump_json(by_alias=True))
    assert session_problems(reloaded, draft) == []


def test_rejection_and_correction_need_a_reason(tmp_path):
    session = _started(prepared_draft(tmp_path))
    with pytest.raises(ValueError, match="rejected change needs a written reason"):
        record_change_decision(session, change_id="change-1", decision="rejected", usefulness=2)
    with pytest.raises(ValueError, match="corrected change needs a written reason"):
        record_change_decision(
            session,
            change_id="change-1",
            decision="corrected",
            usefulness=3,
            corrected_text="Fabricated wording.",
        )
    with pytest.raises(ValueError, match="corrected text belongs"):
        record_change_decision(
            session, change_id="change-1", decision="corrected", usefulness=3, reason="Too broad."
        )
    with pytest.raises(ValueError, match="unknown change"):
        record_change_decision(session, change_id="change-9", decision="accepted", usefulness=4)


@pytest.mark.parametrize(
    ("reviewer_id", "evidence_class", "message"),
    [
        ("Jane Doe", "practising_lawyer", "pseudonym of the form R01"),
        ("R01\n", "practising_lawyer", "pseudonym of the form R01"),
        ("R00", "practising_lawyer", "reserved for synthetic examples"),
        ("R000", "author_self_review", "reserved for synthetic examples"),
        ("R01", "synthetic_example", "a synthetic example uses the reviewer id R00"),
    ],
)
def test_reviewer_is_a_pseudonym_and_zero_ids_are_reserved_for_examples(
    tmp_path, reviewer_id, evidence_class, message
):
    with pytest.raises(ValueError, match=message):
        start_review_session(
            prepared_draft(tmp_path), reviewer_id=reviewer_id, evidence_class=evidence_class
        )


def test_session_cannot_close_with_a_pending_recommendation(tmp_path):
    session = _started(prepared_draft(tmp_path))
    session = record_change_decision(
        session, change_id="change-1", decision="accepted", usefulness=4, at="2026-03-02T10:05:00Z"
    )
    with pytest.raises(ValueError, match=r"needs a decision before closing: \['change-2'\]"):
        close_review_session(session, at="2026-03-02T10:30:00Z", **CLOSE)


def test_closed_session_accepts_no_further_events(tmp_path):
    session = closed_session(prepared_draft(tmp_path))
    with pytest.raises(ValueError, match="closed and accepts no further events"):
        record_material_omission(session, text="Late omission.", at="2026-03-02T11:00:00Z")
    with pytest.raises(ValueError, match="already closed"):
        close_review_session(session, state="rejected", note="Fabricated second decision note.")


def test_events_keep_their_order(tmp_path):
    session = _started(prepared_draft(tmp_path))
    with pytest.raises(ValueError, match="cannot precede the last recorded event"):
        mark_draft_reviewable(session, at="2026-03-02T09:59:00Z")
    with pytest.raises(ValueError, match="carries no UTC offset"):
        mark_draft_reviewable(session, at="2026-03-02T10:10:00")
    session = mark_draft_reviewable(session, at="2026-03-02T10:10:00Z")
    with pytest.raises(ValueError, match="already marked reviewable"):
        mark_draft_reviewable(session, at="2026-03-02T10:11:00Z")

    # Closing is an event like any other: it cannot be dated before the last decision.
    decided = _all_accepted(session, at="2026-03-02T12:00:00Z")
    with pytest.raises(ValueError, match="cannot precede the last recorded event"):
        close_review_session(decided, at="2026-03-02T10:30:00Z", **CLOSE)


def test_later_decision_supersedes_and_both_stay_in_the_chain(tmp_path):
    draft = prepared_draft(tmp_path)
    session = record_change_decision(
        _started(draft),
        change_id="change-1",
        decision="accepted",
        usefulness=4,
        at="2026-03-02T10:05:00Z",
    )
    session = record_change_decision(
        session,
        change_id="change-1",
        decision="rejected",
        usefulness=2,
        reason="Fabricated second thought.",
        at="2026-03-02T10:06:00Z",
    )

    recorded = [
        event.details["decision"]
        for event in session.assessment.audit_events
        if event.event_type == "change_decision_recorded"
    ]
    assert recorded == ["accepted", "rejected"]
    assert session.change_set.changes[0].decision == "rejected"
    assert session_problems(session, draft) == []


def test_reviewers_work_on_separate_copies_of_the_draft(tmp_path):
    draft = prepared_draft(tmp_path)
    closed_session(draft, "R01")
    second = _started(draft, "R02")

    assert all(change.decision == "pending" for change in second.change_set.changes)
    assert all(change.decision == "pending" for change in draft.change_set.changes)
    assert session_problems(second, draft) == []


@pytest.mark.parametrize(
    ("edit", "path"),
    [
        ({"evidence_class": "practising_lawyer"}, "evidence_class"),
        ({"reviewer_profile": "Partner, 20 years"}, "reviewer_profile"),
        ({"material_omissions": []}, "material_omissions"),
        ({"declared_review_minutes": 5.0}, "declared_review_minutes"),
        ({"workflow_feedback": "It was excellent."}, "workflow_feedback"),
        ({"change_set__changes__1__reason": "A kinder reason."}, "change_set.changes"),
        ({"change_set__changes__1__usefulness": 4}, "change_set.changes"),
        ({"change_set__changes__0__decided_at": "2026-03-02T10:01:00Z"}, "change_set.changes"),
        ({"change_set__changes__0__proposed_text": "A better one."}, "change_set.changes"),
        ({"assessment__matter__matter_id": "another-matter"}, "assessment.matter"),
        ({"assessment__findings": []}, "assessment.findings"),
        ({"assessment__review_note": "R02: A different note entirely."}, "assessment.review_note"),
    ],
)
def test_no_field_of_a_session_file_can_be_edited_apart_from_its_chain(tmp_path, edit, path):
    draft = prepared_draft(tmp_path)
    session = closed_session(draft, "R02", "author_self_review")

    assert session_problems(_edited(session, **edit), draft) == [f"{path}: {NOT_IN_CHAIN}"]


def test_export_gate_cannot_be_opened_by_editing_the_session_file(tmp_path):
    draft = prepared_draft(tmp_path)
    session = closed_session(draft, state="revision_requested")
    assert session.assessment.export_allowed is False

    opened = _edited(session, assessment__review_state="approved", assessment__export_allowed=True)

    assert session_problems(opened, draft) == [
        f"assessment.export_allowed: {NOT_IN_CHAIN}",
        f"assessment.review_state: {NOT_IN_CHAIN}",
    ]


def test_session_must_continue_the_draft_it_is_exported_against(tmp_path):
    draft = prepared_draft(tmp_path)
    session = closed_session(draft)
    other_draft = prepare_review_draft(
        document_matter(tmp_path),
        documents_root=tmp_path,
        intake_at="2026-03-03T09:00:00Z",
        ready_at="2026-03-03T09:00:02Z",
    )

    assert session_problems(session, other_draft) == ["the session does not continue this draft"]


def test_dropping_events_from_the_chain_leaves_an_inconsistent_file(tmp_path):
    draft = prepared_draft(tmp_path)
    session = closed_session(draft, state="rejected")

    events = session.model_dump(mode="json")["assessment"]["audit_events"]
    cut = _edited(session, assessment__audit_events=events[:-2])

    # The shortened chain still verifies and the session reads as open, but the
    # file still carries the decision the removed events recorded.
    assert verify_audit_chain(cut.assessment.audit_events).verified is True
    assert is_closed(cut) is False
    assert f"assessment.review_state: {NOT_IN_CHAIN}" in session_problems(cut, draft)

    without_omission = _edited(session, assessment__audit_events=events[:6] + events[7:])
    assert session_problems(without_omission, draft)[0].startswith("audit chain not verified")
