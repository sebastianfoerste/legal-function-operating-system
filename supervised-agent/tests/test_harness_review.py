import copy
import json
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from models import MatterIntake
from src import pilot_cli
from src.harness_review import (
    SESSION_SCHEMA,
    HarnessMatterReview,
    change_set_from_harness_review,
    load_harness_review,
    template_differences,
)
from src.pilot_record import build_pilot_record, render_recommendations, write_pilot_record
from src.pilot_session import (
    close_review_session,
    draft_problems,
    prepare_review_draft,
    record_change_decision,
    session_problems,
    start_review_session,
)
from tests.pilot_support import document_matter, harness_root, prepared_draft

# A fabricated review in the harness's output format. It has no legal content: it
# exists to exercise the mapping, and it cites the two fabricated test documents.
TOY_REVIEW: dict[str, Any] = {
    "schema": "contract-review-eval.matter-review.v1",
    "conflicts": [
        {
            "finding_id": "k1",
            "summary": "Toy conflict.",
            "materiality": "high",
            "evidence": ["c1", "c2"],
        }
    ],
    "positions": [
        {
            "finding_id": "p1",
            "summary": "Toy position.",
            "action": "negotiate",
            "materiality": "medium",
            "playbook_rule": "TB-01",
            "evidence": ["c1"],
        }
    ],
    "escalations": [
        {
            "finding_id": "e1",
            "question": "Toy question?",
            "reason": "Toy reason.",
            "evidence": ["c3"],
        }
    ],
    "citations": [
        {"citation_id": "c1", "document_id": "msa", "quote": "Synthetic master agreement text."},
        {"citation_id": "c2", "document_id": "memo", "quote": "Synthetic instruction memo."},
        {"citation_id": "c3", "document_id": "annex", "quote": "A document not on the file."},
    ],
}


def _review(**changes) -> HarnessMatterReview:
    return HarnessMatterReview.model_validate({**copy.deepcopy(TOY_REVIEW), **changes})


def _draft(tmp_path):
    return prepare_review_draft(
        document_matter(tmp_path),
        documents_root=tmp_path,
        harness_review=_review(),
        intake_at="2026-03-02T09:00:00Z",
        ready_at="2026-03-02T09:00:02Z",
    )


def _closed(draft, reviewer_id="R01", evidence_class="practising_lawyer"):
    session = start_review_session(
        draft, reviewer_id=reviewer_id, evidence_class=evidence_class, at="2026-03-02T10:00:00Z"
    )
    for change in draft.change_set.changes:
        session = record_change_decision(
            session,
            change_id=change.id,
            decision="accepted" if change.id == "k1" else "rejected",
            usefulness=4 if change.id == "k1" else 2,
            reason="" if change.id == "k1" else "Fabricated reason for a rejection.",
            at="2026-03-02T10:10:00Z",
        )
    return close_review_session(
        session,
        state="revision_requested",
        note="Fabricated decision note written for the test session only.",
        at="2026-03-02T10:30:00Z",
    )


def test_review_hash_ignores_key_order_and_omitted_defaults():
    reordered = copy.deepcopy(TOY_REVIEW)
    reordered["escalations"][0] = dict(reversed(list(reordered["escalations"][0].items())))
    explicit = copy.deepcopy(TOY_REVIEW)
    explicit["conflicts"][0]["evidence"] = []
    explicit["escalations"].append(
        {"finding_id": "e2", "question": "Another?", "reason": "Toy.", "evidence": []}
    )
    explicit["positions"][0]["playbook_rule"] = None
    sparse = copy.deepcopy(explicit)
    del sparse["schema"]
    del sparse["conflicts"][0]["evidence"]
    del sparse["escalations"][1]["evidence"]
    del sparse["positions"][0]["playbook_rule"]

    def digest(raw):
        return HarnessMatterReview.model_validate(raw).canonical_sha256()

    assert digest(reordered) == digest(TOY_REVIEW)
    assert digest(sparse) == digest(explicit)
    assert digest(explicit) != digest(TOY_REVIEW)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"confidence": 0.9}, "Extra inputs are not permitted"),
        ({"conflicts": [{**TOY_REVIEW["conflicts"][0], "finding_id": "k1; rm -rf"}]}, "pattern"),
        ({"conflicts": [], "positions": [], "escalations": []}, "between 1 and 200 findings"),
        ({"positions": [{**TOY_REVIEW["positions"][0], "finding_id": "k1"}]}, "duplicate finding"),
        ({"citations": TOY_REVIEW["citations"][:1]}, "unknown citation ids"),
        ({"citations": [{**TOY_REVIEW["citations"][0], "quote": "x" * 4001}]}, "at most 4000"),
    ],
)
def test_malformed_model_output_is_refused(changes, message):
    with pytest.raises(ValidationError, match=message):
        _review(**changes)


def test_capture_is_read_without_its_origin(tmp_path):
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "schema": "contract-review-eval.matter-capture.v1",
                "status": "returned",
                "condition_id": "matter",
                "model": "some-model",
                "raw_text": json.dumps(TOY_REVIEW),
            }
        ),
        encoding="utf-8",
    )
    bare = tmp_path / "review.json"
    bare.write_text(json.dumps(TOY_REVIEW), encoding="utf-8")
    failed = tmp_path / "failed.json"
    failed.write_text(
        json.dumps({"schema": "contract-review-eval.matter-capture.v1", "status": "failed"}),
        encoding="utf-8",
    )

    assert load_harness_review(capture) == load_harness_review(bare) == _review()
    with pytest.raises(ValueError, match="failed attempt"):
        load_harness_review(failed)


def test_each_finding_becomes_one_recommendation_under_its_own_id(tmp_path):
    change_set = change_set_from_harness_review(_review(), document_matter(tmp_path))
    changes = {change.id: change for change in change_set.changes}

    assert list(changes) == ["k1", "p1", "e1"]
    assert changes["k1"].proposed_text == "Toy conflict."
    assert changes["k1"].locator == "conflict | documents: msa, memo"
    assert changes["k1"].original_text.splitlines() == [
        "[msa] Synthetic master agreement text.",
        "[memo] Synthetic instruction memo.",
    ]
    assert changes["k1"].source_refs == [
        "synthetic:test-matter/data/msa.md",
        "synthetic:test-matter/matter/memo.md",
    ]
    assert changes["p1"].rationale == (
        "Recommended action: negotiate. Materiality: medium. Playbook rule: TB-01."
    )
    assert (changes["e1"].proposed_text, changes["e1"].rationale) == (
        "Toy question?",
        "Toy reason.",
    )
    # A citation of a document the round does not hold is shown to the reviewer as such.
    assert changes["e1"].locator == "escalation | documents: annex (not on the file)"
    assert changes["e1"].source_refs == []
    assert change_set.source_digest == _review().canonical_sha256()


def test_draft_on_a_harness_review_is_bound_to_the_harness_hash(tmp_path):
    draft = _draft(tmp_path)

    assert draft.review_source == "harness_review"
    assert draft.review_sha256 == _review().canonical_sha256()
    details = draft.assessment.audit_events[-1].details
    assert (details["review_source"], details["review_sha256"]) == (
        "harness_review",
        draft.review_sha256,
    )
    assert details["finding_ids"] == ["k1", "p1", "e1"]
    assert draft_problems(draft) == []
    # The rule-based findings stay in the assessment; they are not what is rated.
    assert [change.id for change in draft.change_set.changes] == ["k1", "p1", "e1"]

    reworded = draft.model_copy(deep=True)
    reworded.change_set.changes[0].proposed_text = "A rewritten finding."
    assert draft_problems(reworded) == [
        "the draft's recommendations are not the ones its audit chain fixed"
    ]
    relabelled = draft.model_copy(update={"review_source": "agent_rules"})
    assert draft_problems(relabelled) != []

    document = render_recommendations(draft)
    assert "output of a model" in document and "## p1" in document
    assert "> [msa] Synthetic master agreement text." in document

    with pytest.raises(ValueError, match="names its matter and round"):
        prepare_review_draft(
            document_matter(tmp_path, matter_id=None),
            documents_root=tmp_path,
            harness_review=_review(),
        )


def test_session_on_a_harness_review_exports_a_harness_reviewer_session(tmp_path):
    draft = _draft(tmp_path)
    session = _closed(draft)
    assert session_problems(session, draft) == []

    record = build_pilot_record(draft, [session], generated_at="2026-03-02T12:00:00Z")
    harness_session = record.sessions[0].harness_session

    assert record.review_source == "harness_review"
    assert harness_session == {"schema": SESSION_SCHEMA, **record.sessions[0].harness_fields}
    assert harness_session["review_sha256"] == _review().canonical_sha256()
    assert [item["finding_id"] for item in harness_session["decisions"]] == ["k1", "p1", "e1"]
    assert any("captured by contract-review-eval-harness" in limit for limit in record.claim_limits)
    assert not any("rule-based" in limit for limit in record.claim_limits)

    write_pilot_record(record, tmp_path / "record")
    written = json.loads((tmp_path / "record/harness-session-R01.json").read_text("utf-8"))
    assert written == harness_session


def test_session_on_the_agents_own_rules_exports_no_harness_session(tmp_path):
    from tests.pilot_support import closed_session

    draft = prepared_draft(tmp_path / "rules")
    record = build_pilot_record(draft, [closed_session(draft)])

    assert record.review_source == "agent_rules"
    assert record.sessions[0].harness_session is None
    write_pilot_record(record, tmp_path / "record")
    assert not list((tmp_path / "record").glob("harness-session-*.json"))


def test_template_differences_names_what_does_not_match(tmp_path):
    review, matter = _review(), document_matter(tmp_path)
    template = {
        "matter_id": "test-matter",
        "round_id": "round1",
        "review_sha256": review.canonical_sha256(),
        "decisions": [{"finding_id": item} for item in ("e1", "k1", "p1")],
    }
    assert template_differences(review, matter, template) == []

    template["review_sha256"] = "0" * 64
    template["decisions"].pop()
    differences = template_differences(review, matter, template)
    assert differences[0].startswith("review_sha256: here")
    assert differences[1].startswith("finding ids: here ['e1', 'k1', 'p1']")


def test_cli_prepares_a_draft_from_a_harness_review(tmp_path, capsys):
    root = tmp_path / "documents"
    matter = document_matter(root)
    intake = tmp_path / "intake.json"
    intake.write_text(matter.model_dump_json(), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps(TOY_REVIEW), encoding="utf-8")
    template = tmp_path / "template.json"
    template.write_text(
        json.dumps({"matter_id": "test-matter", "round_id": "round2", "decisions": []}),
        encoding="utf-8",
    )
    prepare = ["prepare", "--input", str(intake), "--documents-root", str(root)]
    prepare += ["--harness-review", str(review), "--out-dir", str(tmp_path / "pilot")]

    assert pilot_cli.main([*prepare, "--harness-template", str(template)]) == 1
    assert "not the one the template names" in capsys.readouterr().out
    assert pilot_cli.main(prepare) == 0
    assert "draft ready (harness_review)" in capsys.readouterr().out
    assert "## k1" in (tmp_path / "pilot/recommendations.md").read_text(encoding="utf-8")


def test_hash_and_session_agree_with_the_harness_itself(tmp_path):
    root = harness_root()
    sys.path.insert(0, str(root / "src"))
    try:
        from contract_eval.matter import MatterReview
        from contract_eval.reviewer_sessions import (
            ReviewerSession,
            blank_session,
            validate_against_review,
        )
    finally:
        sys.path.remove(str(root / "src"))
    fixtures = root / "tests/fixtures/mini_matter"
    raw = json.loads((fixtures / "matters/toy/fixtures/round1.matter.json").read_text("utf-8"))
    manifest = json.loads((fixtures / "matters/toy/matter.json").read_text("utf-8"))
    theirs = MatterReview.model_validate(raw)
    mine = HarnessMatterReview.model_validate(raw)

    assert mine.canonical_sha256() == theirs.canonical_sha256()

    matter = MatterIntake(
        title="Toy widget supply (harness test fixture)",
        requester="Test",
        business_unit="Test",
        matter_type="contract",
        jurisdiction="none",
        summary="The harness's own toy matter, used to check the two formats agree.",
        source_refs=["synthetic:contract-review-eval-harness/tests/fixtures/mini_matter"],
        matter_id=manifest["matter_id"],
        round_id="round1",
        documents=[
            {**document, "source_ref": f"synthetic:mini_matter/{document['path']}"}
            for document in manifest["documents"]
            if document["introduced_in"] == "round1"
        ],
    )
    assert template_differences(mine, matter, blank_session("toy", "round1", theirs)) == []

    draft = prepare_review_draft(
        matter,
        documents_root=fixtures,
        harness_review=mine,
        intake_at="2026-03-02T09:00:00Z",
        ready_at="2026-03-02T09:00:02Z",
    )
    session = start_review_session(
        draft, reviewer_id="R00", evidence_class="synthetic_example", at="2026-03-02T10:00:00Z"
    )
    for change in draft.change_set.changes:
        session = record_change_decision(
            session,
            change_id=change.id,
            decision="accepted",
            usefulness=4,
            at="2026-03-02T10:05:00Z",
        )
    session = close_review_session(
        session,
        state="revision_requested",
        note="Fabricated decision note written for the test session only.",
        at="2026-03-02T10:30:00Z",
    )
    exported = build_pilot_record(draft, [session]).sessions[0].harness_session

    harness_session = ReviewerSession.model_validate(exported)
    validate_against_review(harness_session, theirs)
    assert harness_session.evidence_class == "synthetic_example"
