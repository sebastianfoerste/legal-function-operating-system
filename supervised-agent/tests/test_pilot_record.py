import itertools
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src import pilot_cli, pilot_record
from src.pilot_example import OUTPUT_DIR, build_example_record
from src.pilot_record import (
    HARNESS_SESSION_FIELDS,
    AcceptanceResult,
    PilotRecord,
    build_pilot_record,
    render_pilot_record_markdown,
    render_reviewed_recommendations,
)
from src.pilot_session import start_review_session
from tests.evidence_support import closed_session, harness_root, prepared_draft, write_documents


def test_record_lists_decisions_reasons_omissions_and_timings_per_session(tmp_path):
    draft = prepared_draft(tmp_path)
    record = build_pilot_record(
        draft,
        [closed_session(draft, "R01"), closed_session(draft, "R02", "author_self_review")],
        generated_at="2026-03-02T12:00:00Z",
    )

    session = record.sessions[0]
    assert session.accepted == []
    assert [(item.finding_id, item.corrected_text) for item in session.corrected] == [
        ("finding-1", "Fabricated replacement wording.")
    ]
    assert [(item.finding_id, item.reason) for item in session.rejected] == [
        ("finding-2", "Fabricated reason for a rejection.")
    ]
    assert session.material_omissions == ["Fabricated omission."]
    assert session.timing.minutes_to_reviewable_draft == 20.0
    assert session.audit_chain.verified is True
    assert [item.document_id for item in record.documents] == ["msa", "memo"]


def test_only_practising_lawyer_sessions_count_toward_the_summary(tmp_path):
    draft = prepared_draft(tmp_path)
    record = build_pilot_record(
        draft,
        [closed_session(draft, "R01"), closed_session(draft, "R02", "author_self_review")],
    )

    summary = record.summary
    assert (summary.measured, summary.sessions, summary.sessions_excluded) == (True, 1, 1)
    assert (summary.accepted_rate, summary.corrected_rate, summary.rejected_rate) == (0.0, 0.5, 0.5)
    assert summary.mean_usefulness == 2.0
    assert summary.median_review_minutes == 45.0
    assert summary.median_elapsed_review_minutes == 45.0
    assert summary.sessions_with_declared_review_time == 0
    assert summary.material_omissions == 1
    assert record.claim.startswith("A user pilot on synthetic documents: 1 review session(s)")
    assert any("Not an enterprise implementation" in limit for limit in record.claim_limits)
    assert record.acceptance.status in {"criteria_not_set", "met", "not_met"}


def test_author_and_synthetic_sessions_alone_support_no_pilot_claim(tmp_path):
    draft = prepared_draft(tmp_path)
    record = build_pilot_record(
        draft,
        [
            closed_session(draft, "R00", "synthetic_example"),
            closed_session(draft, "R02", "author_self_review"),
        ],
    )

    assert (record.summary.measured, record.summary.sessions_excluded) == (False, 2)
    assert record.claim.startswith("No reviewer pilot is evidenced")
    assert record.acceptance.status == "not_measured"
    assert "fabricated session (R00)" in render_pilot_record_markdown(record)


def test_acceptance_reports_the_agreed_criteria(tmp_path, monkeypatch):
    draft = prepared_draft(tmp_path)
    sessions = [closed_session(draft, "R01")]

    def criteria(summary):
        return [
            AcceptanceResult(
                criterion="reviewers", threshold=">= 1", observed=str(summary.reviewers), met=True
            ),
            AcceptanceResult(
                criterion="material omissions",
                threshold="0",
                observed=str(summary.material_omissions),
                met=summary.material_omissions == 0,
            ),
        ]

    monkeypatch.setattr(pilot_record, "evaluate_acceptance", lambda summary: [])
    assert build_pilot_record(draft, sessions).acceptance.status == "criteria_not_set"
    monkeypatch.setattr(pilot_record, "evaluate_acceptance", criteria)
    acceptance = build_pilot_record(draft, sessions).acceptance
    assert (acceptance.status, len(acceptance.results)) == ("not_met", 2)


def test_proposed_criteria_are_reported_as_proposed_until_reviewers_agree(tmp_path, monkeypatch):
    draft = prepared_draft(tmp_path)
    # One reviewer; one recommendation scored 3, one scored 1; one omission.
    record = build_pilot_record(draft, [closed_session(draft, "R01")])

    summary, acceptance = record.summary, record.acceptance
    assert (summary.usable_rate, summary.misleading_rate) == (0.5, 0.5)
    assert summary.material_omissions_per_session == 1.0
    assert (acceptance.status, acceptance.basis) == ("not_met", "proposed_by_author")
    assert {item.criterion: item.met for item in acceptance.results} == {
        "distinct practising lawyers": False,
        "recommendations scored 3 or 4": False,
        "recommendations scored 1 (misleading)": False,
        "material omissions per session": True,
    }
    assert "thresholds: proposed by author" in render_pilot_record_markdown(record)

    monkeypatch.setattr(pilot_record, "CRITERIA_AGREED_WITH_REVIEWERS", True)
    agreed = build_pilot_record(draft, [closed_session(draft, "R01")]).acceptance
    assert agreed.basis == "agreed_with_reviewers"


def test_record_refuses_open_tampered_and_duplicate_sessions(tmp_path):
    draft = prepared_draft(tmp_path)
    session = closed_session(draft)

    opened = start_review_session(
        draft, reviewer_id="R03", evidence_class="practising_lawyer", at="2026-03-02T10:00:00Z"
    )
    with pytest.raises(ValueError, match="is not closed"):
        build_pilot_record(draft, [opened])
    with pytest.raises(ValueError, match="more than one session for reviewers"):
        build_pilot_record(draft, [session, session])
    tampered = session.model_copy(deep=True)
    tampered.recommendation_set.recommendations[1].usefulness = 4
    with pytest.raises(ValueError, match="failed verification"):
        build_pilot_record(draft, [tampered])


def test_session_fields_follow_the_harness_reviewer_session_format(tmp_path):
    draft = prepared_draft(tmp_path)
    fields = build_pilot_record(draft, [closed_session(draft)]).sessions[0].harness_fields

    assert tuple(fields) == HARNESS_SESSION_FIELDS
    assert set(fields["decisions"][0]) == {"finding_id", "decision", "usefulness", "reason"}
    assert (fields["matter_id"], fields["round_id"]) == ("test-matter", "round1")
    # The harness schema id is withheld: review_sha256 names this agent's
    # recommendations, and a harness session is bound to a harness review output.
    assert "schema" not in fields


def test_session_fields_validate_under_the_harness_model(tmp_path):
    root = harness_root()
    sys.path.insert(0, str(root / "src"))
    try:
        from contract_eval.reviewer_sessions import SESSION_SCHEMA, ReviewerSession
    finally:
        sys.path.remove(str(root / "src"))
    draft = prepared_draft(tmp_path)
    fields = build_pilot_record(draft, [closed_session(draft)]).sessions[0].harness_fields

    session = ReviewerSession.model_validate({"schema": SESSION_SCHEMA, **fields})

    assert session.reviewer_id == "R01"
    assert [decision.decision for decision in session.decisions] == ["corrected", "rejected"]


def test_revised_draft_is_exported_only_after_approval(tmp_path):
    draft = prepared_draft(tmp_path)

    with pytest.raises(ValueError, match="closed session that approved the matter"):
        render_reviewed_recommendations(closed_session(draft, state="revision_requested"))

    revised = render_reviewed_recommendations(closed_session(draft))
    assert "Fabricated replacement wording." in revised
    assert "## finding-2" not in revised
    assert "Rejected and left out: 1" in revised


def test_committed_worked_example_is_current_and_labelled_synthetic():
    record = build_example_record()
    committed = PilotRecord.model_validate_json(
        (OUTPUT_DIR / "pilot-record.json").read_text(encoding="utf-8")
    )

    assert committed == record
    assert (OUTPUT_DIR / "pilot-record.md").read_text(
        encoding="utf-8"
    ) == render_pilot_record_markdown(record)
    fields = record.sessions[0].harness_fields
    assert (fields["reviewer_id"], fields["evidence_class"]) == ("R00", "synthetic_example")
    free_text = [
        fields["reviewer_profile"],
        fields["workflow_feedback"],
        *fields["material_omissions"],
        *(decision["reason"] for decision in fields["decisions"]),
    ]
    assert all(text.startswith("SYNTHETIC EXAMPLE") for text in free_text)
    assert record.summary.measured is False


def test_cli_carries_a_matter_from_intake_to_export(tmp_path, monkeypatch, capsys):
    root = tmp_path / "documents"
    intake = tmp_path / "intake.json"
    intake.write_text(
        json.dumps(
            {
                "title": "Synthetic vendor paper review",
                "requester": "Head of Legal",
                "business_unit": "Legal",
                "matter_type": "contract",
                "jurisdiction": "Germany",
                "summary": "A fabricated vendor-paper review used to test the supervised workflow.",
                "data_categories": ["business contact data"],
                "source_refs": ["synthetic:test-matter"],
                "matter_id": "test-matter",
                "round_id": "round1",
                "documents": write_documents(root),
            }
        ),
        encoding="utf-8",
    )
    # The audit clock has one-second resolution; the session needs time to pass.
    start = datetime.now(tz=UTC).replace(microsecond=0) + timedelta(minutes=1)
    ticks = (start + timedelta(minutes=5 * step) for step in itertools.count())
    monkeypatch.setattr(
        "src.pilot_session.utc_now_iso",
        lambda: next(ticks).isoformat().replace("+00:00", "Z"),
    )
    out, session = tmp_path / "pilot", tmp_path / "pilot/sessions/R01.json"

    def run(*argv: str) -> int:
        return pilot_cli.main([str(item) for item in argv])

    assert run("verify-documents", "--input", intake, "--documents-root", root) == 0
    assert run("prepare", "--input", intake, "--out-dir", out) == 1
    assert "refused" in capsys.readouterr().out
    assert run("prepare", "--input", intake, "--documents-root", root, "--out-dir", out) == 0
    draft = out / "draft.json"
    start_args = ("start", "--draft", draft, "--session", session, "--reviewer", "R01")
    assert run(*start_args, "--evidence-class", "practising_lawyer") == 0
    assert run(*start_args, "--evidence-class", "practising_lawyer") == 1
    decide = ("decide", "--session", session, "--recommendation", "finding-1", "--usefulness", "3")
    corrected = (*decide, "--decision", "corrected", "--reason", "Fabricated reason.")
    close = ("close", "--session", session, "--state", "approved")
    assert run(*decide, "--decision", "rejected") == 1
    assert run(*corrected) == 1
    assert run(*close, "--note", "Fabricated note for the test session only.") == 1
    assert run(*corrected, "--corrected-text", "Fabricated wording.") == 0
    assert run("reviewable", "--session", session) == 0
    assert run("omission", "--session", session, "--text", "Fabricated omission.") == 0
    assert run(*close, "--note", "Fabricated note for the test session only.") == 0
    assert "audit chain root: " in capsys.readouterr().out
    export = ("export", "--draft", draft, "--session", session, "--out-dir", out / "record")
    assert run(*export, "--documents-root", root) == 0
    # A second draft would orphan the session, and a missing file is a refusal too.
    assert run("prepare", "--input", intake, "--documents-root", root, "--out-dir", out) == 1
    assert run("reviewable", "--session", tmp_path / "missing.json") == 1
    (root / "data/msa.md").write_text("Edited after the draft.\n", encoding="utf-8")
    assert run(*export, "--documents-root", root) == 1
    assert "documents changed since the draft was prepared" in capsys.readouterr().out

    record = PilotRecord.model_validate_json(
        (out / "record/pilot-record.json").read_text(encoding="utf-8")
    )
    assert record.sessions[0].timing.review_minutes > 0
    assert record.sessions[0].corrected[0].corrected_text == "Fabricated wording."
    assert "Fabricated wording." in (out / "record/reviewed-recommendations-R01.md").read_text(
        encoding="utf-8"
    )
    assert Path(out / "review-packet.md").exists()
