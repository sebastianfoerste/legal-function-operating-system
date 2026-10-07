import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import MatterDocument, MatterIntake, ReviewDecision, verify_audit_chain
from src.collaboration_workspace import build_change_set
from src.legal_ops import apply_review_decision, assess_matter, stable_assessment_id
from src.matter_documents import manifest_differences, verify_matter_documents
from src.review_packet import build_review_packet
from tests.pilot_support import document_matter, harness_root

NORTHWIND_INTAKES = {
    "round1": Path("examples/matters/northwind_saas_round1.json"),
    "round2": Path("examples/matters/northwind_saas_round2.json"),
}


def _statuses(matter: MatterIntake, root: Path | None) -> dict[str, str]:
    return {record.document_id: record.status for record in verify_matter_documents(matter, root)}


@pytest.mark.parametrize("path", ["/etc/hosts", "../outside.md", "a/../../b.md", "a\\b.md", "."])
def test_document_path_must_stay_inside_the_documents_root(path):
    with pytest.raises(ValidationError, match="relative to the documents root"):
        MatterDocument(
            document_id="doc",
            title="Synthetic document",
            kind="contract",
            path=path,
            sha256="0" * 64,
            source_ref="synthetic:test",
        )


def test_intake_rejects_duplicate_document_ids(tmp_path):
    matter = document_matter(tmp_path)
    with pytest.raises(ValidationError, match="duplicate document ids"):
        document_matter(tmp_path, documents=[*matter.documents, matter.documents[0]])


def test_documents_are_verified_by_hash(tmp_path):
    matter = document_matter(tmp_path)

    assert _statuses(matter, tmp_path) == {"msa": "verified", "memo": "verified"}
    assert _statuses(matter, None) == {"msa": "not_checked", "memo": "not_checked"}

    (tmp_path / "data/msa.md").write_text("Edited after intake.\n", encoding="utf-8")
    (tmp_path / "matter/memo.md").unlink()
    assert _statuses(matter, tmp_path) == {"msa": "mismatch", "memo": "missing"}


def test_symlink_leaving_the_documents_root_is_refused(tmp_path):
    root = tmp_path / "root"
    matter = document_matter(root)
    outside = tmp_path / "outside.md"
    outside.write_text("Synthetic master agreement text.\n", encoding="utf-8")
    (root / "data/msa.md").unlink()
    (root / "data/msa.md").symlink_to(outside)

    assert _statuses(matter, root)["msa"] == "refused"


def test_changed_document_blocks_export_even_after_approval(tmp_path):
    matter = document_matter(tmp_path)
    (tmp_path / "data/msa.md").write_text("Edited after intake.\n", encoding="utf-8")

    assessment = assess_matter(matter, documents_root=tmp_path)
    approved = apply_review_decision(
        assessment,
        ReviewDecision(
            reviewer="General Counsel",
            state="approved",
            note="Approved in a test to show that the document blocker still holds.",
        ),
    )

    assert "document_integrity" in {finding.category for finding in assessment.findings}
    controls = {control.control_id: control.status for control in assessment.controls}
    assert controls["document-integrity"] == "blocker"
    assert approved.export_allowed is False


def test_verified_documents_are_bound_into_the_audit_chain(tmp_path):
    matter = document_matter(tmp_path)
    assessment = assess_matter(matter, documents_root=tmp_path)

    controls = {control.control_id: control.status for control in assessment.controls}
    assert controls["document-integrity"] == "pass"
    assert controls["source-boundary"] == "pass"
    created = assessment.audit_events[0]
    assert [item["document_id"] for item in created.details["documents"]] == ["msa", "memo"]
    assert verify_audit_chain(assessment.audit_events).verified is True

    swapped = created.model_copy(deep=True)
    swapped.details["documents"][0]["sha256"] = "f" * 64
    assert verify_audit_chain([swapped]).verified is False
    stripped = created.model_copy(update={"details": None})
    assert verify_audit_chain([stripped]).verified is False

    packet = build_review_packet(assessment)
    assert "## Matter Documents" in packet
    assert f"sha256 {matter.documents[0].sha256}" in packet


def test_unchecked_documents_warn_and_hold_the_export_gate(tmp_path):
    assessment = assess_matter(document_matter(tmp_path))
    controls = {control.control_id: control.status for control in assessment.controls}
    assert controls["document-integrity"] == "warning"

    approval = ReviewDecision(
        reviewer="General Counsel",
        state="approved",
        note="Approved in a test without the documents having been checked.",
    )
    assert apply_review_decision(assessment, approval).export_allowed is False
    verified = assess_matter(document_matter(tmp_path), documents_root=tmp_path)
    assert apply_review_decision(verified, approval).export_allowed is True
    with pytest.raises(ValidationError, match="a matter document is unverified"):
        type(assessment).model_validate(
            {
                **apply_review_decision(assessment, approval).model_dump(),
                "export_allowed": True,
            }
        )


def test_change_set_digest_of_an_intake_without_documents_is_unchanged():
    # The recipe build_change_set used before the intake could reference documents.
    matter = MatterIntake.model_validate_json(
        Path("examples/matters/saas_msa_deviation.json").read_text(encoding="utf-8")
    )
    legacy = matter.model_dump(mode="json", exclude={"matter_id", "round_id", "documents"})
    expected = hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()

    assert build_change_set(assess_matter(matter)).source_digest == expected


def test_blocked_document_source_reference_is_a_blocker(tmp_path):
    matter = document_matter(tmp_path)
    blocked = matter.documents[0].model_copy(update={"source_ref": "client:acme/msa.docx"})
    assessment = assess_matter(
        matter.model_copy(update={"documents": [blocked, matter.documents[1]]}),
        documents_root=tmp_path,
    )
    assert "source_boundary" in {finding.category for finding in assessment.findings}


def test_assessment_id_of_an_intake_without_documents_is_unchanged():
    # The id recorded in examples/trust-cockpit-saas-msa-2026-06-30.json, written
    # before the intake could reference documents.
    matter = MatterIntake.model_validate_json(
        Path("examples/matters/saas_msa_deviation.json").read_text(encoding="utf-8")
    )
    assert stable_assessment_id(matter) == "loa_0b5d728ed132582a"
    with_round = matter.model_copy(update={"round_id": "round2"})
    assert stable_assessment_id(with_round) != stable_assessment_id(matter)


def test_manifest_differences_reports_drift(tmp_path):
    matter = document_matter(tmp_path)
    manifest = {
        "matter_id": "test-matter",
        "rounds": [{"round_id": "round1"}, {"round_id": "round2"}],
        "documents": [
            document.model_dump(exclude={"source_ref", "title"}) for document in matter.documents
        ],
    }
    assert manifest_differences(matter, manifest) == []

    manifest["documents"][0]["sha256"] = "a" * 64
    manifest["documents"].append(
        {"document_id": "annex", "kind": "contract", "path": "x.md", "introduced_in": "round1"}
    )
    manifest["documents"][1]["introduced_in"] = "round2"
    differences = manifest_differences(matter, manifest)

    assert any(item.startswith("msa.sha256") for item in differences)
    assert "annex: in the manifest for this round, not in the intake" in differences
    assert "memo: introduced after round round1" in differences


@pytest.mark.parametrize(("round_id", "count"), [("round1", 7), ("round2", 9)])
def test_northwind_intakes_reference_synthetic_documents_only(round_id, count):
    matter = MatterIntake.model_validate_json(
        NORTHWIND_INTAKES[round_id].read_text(encoding="utf-8")
    )

    assert (matter.matter_id, matter.round_id) == ("northwind-saas", round_id)
    assert len(matter.documents) == count
    assert all(document.source_ref.startswith("synthetic:") for document in matter.documents)
    # Selecting data categories or commitments would be a reading of the documents.
    # The intake leaves that to the lawyer who conducts it.
    assert matter.data_categories == [] and matter.customer_commitments == []


@pytest.mark.parametrize("round_id", ["round1", "round2"])
def test_northwind_intakes_match_the_harness_checkout(round_id):
    root = harness_root()
    matter = MatterIntake.model_validate_json(
        NORTHWIND_INTAKES[round_id].read_text(encoding="utf-8")
    )
    manifest = json.loads((root / "matters/northwind-saas/matter.json").read_text(encoding="utf-8"))

    assert manifest_differences(matter, manifest) == []
    assert set(_statuses(matter, root).values()) == {"verified"}
    for document in matter.documents:
        actual = hashlib.sha256((root / document.path).read_bytes()).hexdigest()
        assert actual == document.sha256
