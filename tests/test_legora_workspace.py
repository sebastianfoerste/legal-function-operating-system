import hashlib
import zipfile
from xml.etree import ElementTree

import pytest

from src.legal_ops import assess_matter, build_sample_matter
from src.legora_workspace import (
    build_change_set,
    build_matter_list,
    build_timeline,
    comment_on_list_item,
    decide_change,
    render_annotated_docx,
    render_review_room,
    resolve_list_item,
)


def write_source_docx(path, *, include_nested_section: bool = False) -> None:
    content_types = "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>"
    nested_section = (
        "<w:p><w:pPr><w:sectPr/></w:pPr><w:r><w:t>Second section</w:t></w:r></w:p>"
        if include_nested_section
        else ""
    )
    document = f"<?xml version='1.0'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>Original source clause</w:t></w:r></w:p>{nested_section}<w:sectPr/></w:body></w:document>"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("word/document.xml", document)


def test_playbook_changes_and_docx_remain_review_gated(tmp_path) -> None:
    assessment = assess_matter(build_sample_matter())
    source = tmp_path / "source.docx"
    write_source_docx(source)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    change_set = build_change_set(assessment, source)
    with pytest.raises(ValueError, match="every proposed change to be decided"):
        render_annotated_docx(change_set, source, tmp_path / "blocked.docx")
    change_set = decide_change(change_set, change_set.changes[0].id, "accepted")
    for change in list(change_set.changes[1:]):
        change_set = decide_change(change_set, change.id, "rejected")
    with pytest.raises(ValueError, match="must not overwrite"):
        render_annotated_docx(change_set, source, source)
    output = render_annotated_docx(change_set, source, tmp_path / "reviewed.docx")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_digest
    assert zipfile.is_zipfile(output)
    with zipfile.ZipFile(output) as package:
        document = package.read("word/document.xml").decode()
    assert "Original source clause" in document
    assert "<w:ins" in document
    assert change_set.changes[0].proposed_text in document
    root = ElementTree.fromstring(document)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    inserted_changes = ["".join(node.itertext()) for node in root.findall(".//w:ins", namespace)]
    assert inserted_changes == [change_set.changes[0].proposed_text]
    assert document.count("<w:ins") == 1


def test_docx_changes_are_inserted_before_the_final_section_marker(tmp_path) -> None:
    assessment = assess_matter(build_sample_matter())
    source = tmp_path / "multi-section.docx"
    write_source_docx(source, include_nested_section=True)
    change_set = build_change_set(assessment, source)
    for change in list(change_set.changes):
        change_set = decide_change(change_set, change.id, "accepted")
    output = render_annotated_docx(change_set, source, tmp_path / "reviewed.docx")
    with zipfile.ZipFile(output) as package:
        document = package.read("word/document.xml").decode()
    assert document.rfind("<w:ins") < document.rfind("<w:sectPr")


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


def test_local_review_room_has_no_external_dependencies(tmp_path) -> None:
    assessment = assess_matter(build_sample_matter())
    room = render_review_room(
        assessment,
        build_change_set(assessment),
        build_matter_list(assessment),
        tmp_path / "review-room.html",
    )
    content = room.read_text()
    assert "External access and delivery are disabled" in content
    assert "Accept" in content and "Reject" in content and "Reviewer comment" in content
    assert "http://" not in content and "https://" not in content
