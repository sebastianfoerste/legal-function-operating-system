import zipfile

import pytest

from src.legal_ops import assess_matter, build_sample_matter
from src.legora_workspace import (
    build_change_set,
    build_matter_list,
    build_timeline,
    decide_change,
    render_annotated_docx,
    render_review_room,
    resolve_list_item,
)


def test_playbook_changes_and_docx_remain_review_gated(tmp_path) -> None:
    assessment = assess_matter(build_sample_matter())
    change_set = build_change_set(assessment)
    with pytest.raises(ValueError, match="every proposed change"):
        render_annotated_docx(change_set, tmp_path / "blocked.docx")
    for change in list(change_set.changes):
        change_set = decide_change(change_set, change.id, "accepted")
    output = render_annotated_docx(change_set, tmp_path / "reviewed.docx")
    assert zipfile.is_zipfile(output)
    assert output != tmp_path / "source.docx"


def test_matter_lists_require_evidence_and_timeline_is_hash_chained() -> None:
    matter_list = build_matter_list(assess_matter(build_sample_matter()))
    with pytest.raises(ValueError, match="evidence"):
        resolve_list_item(matter_list, matter_list.items[0].id, [])
    resolved = resolve_list_item(
        matter_list, matter_list.items[0].id, ["synthetic:review-evidence"]
    )
    assert resolved.items[0].status == "resolved"
    timeline = build_timeline(resolved)
    assert all(
        event.previous_hash == (timeline[index - 1].event_hash if index else None)
        for index, event in enumerate(timeline)
    )


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
    assert "http://" not in content and "https://" not in content
