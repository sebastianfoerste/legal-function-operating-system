import hashlib
import io
import zipfile
from xml.etree import ElementTree

import pytest

from src.docx_redline import (
    DOCUMENT_PART,
    LocatorError,
    RedlineEdit,
    RevisionMark,
    UnsupportedDocumentError,
    apply_tracked_changes,
    has_non_xml_char,
    index_docx,
    list_tracked_changes,
    read_paragraph_texts,
    resolve_edit,
    revision_label,
)
from src.pilot.fixtures import build_synthetic_msa
from src.playbook import Playbook, load_playbook, propose_changes

MARK = RevisionMark(author="Synthetic reviewer", date="2026-01-01T00:00:00Z")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _edits(data: bytes):
    return [
        change.to_edit() for change in propose_changes(index_docx(data), load_playbook()).changes
    ]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _document_xml(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return package.read(DOCUMENT_PART)


def _revision_text(node) -> str:
    parts = []
    for child in node.iter():
        if child.tag in {f"{W}t", f"{W}delText"}:
            parts.append(child.text or "")
        elif child.tag == f"{W}tab":
            parts.append("\t")
    return "".join(parts)


def _distinct_marks(edits) -> dict[str, RevisionMark]:
    return {
        edit.change_id: RevisionMark(f"Simulated role {n}", f"2026-02-0{n}T09:30:0{n}Z")
        for n, edit in enumerate(edits, start=1)
    }


def _repackage(data: bytes, transform) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, "w") as target:
        for member in source.infolist():
            payload = source.read(member.filename)
            target.writestr(
                member, transform(payload) if member.filename == DOCUMENT_PART else payload
            )
    return buffer.getvalue()


def test_fixture_is_deterministic_and_every_rule_finds_its_clause() -> None:
    data = build_synthetic_msa("specialist")
    assert data == build_synthetic_msa("specialist")
    proposal = propose_changes(index_docx(data), load_playbook())
    assert [c.rule_id for c in proposal.changes] == [
        "payment-terms",
        "audit-right",
        "subprocessors",
        "liability-cap",
        "liability-exclusions",
        "roadmap-commitment",
        "most-favoured-customer",
    ]
    # The order-summary table is not read by the engine and must be reported.
    assert len(proposal.problems) == 1 and "w:tbl" in proposal.problems[0]


def test_compliant_wording_produces_no_change() -> None:
    proposal = propose_changes(index_docx(build_synthetic_msa("routine")), load_playbook())
    assert {c.rule_id for c in proposal.changes} == {"payment-terms", "audit-right"}
    assert proposal.problems == []


@pytest.mark.parametrize("variant", ["routine", "specialist"])
def test_rejecting_all_tracked_changes_restores_the_source(variant) -> None:
    source = build_synthetic_msa(variant)
    reviewed, _ = apply_tracked_changes(source, _edits(source), MARK)
    assert read_paragraph_texts(reviewed, "rejected") == read_paragraph_texts(source, "accepted")
    accepted = "\n".join(read_paragraph_texts(reviewed, "accepted"))
    assert "within thirty (30) days" in accepted and "ninety (90) days" not in accepted
    if variant == "specialist":
        assert "one hundred percent (100%)" in accepted
        assert "most favourable pricing" not in accepted
        assert "Neither party is liable for indirect or consequential loss" in accepted


def test_only_edited_paragraphs_change_and_every_other_part_is_byte_identical() -> None:
    source = build_synthetic_msa("specialist")
    edits = _edits(source)
    reviewed, index = apply_tracked_changes(source, edits, MARK)
    with (
        zipfile.ZipFile(io.BytesIO(source)) as before,
        zipfile.ZipFile(io.BytesIO(reviewed)) as after,
    ):
        assert before.namelist() == after.namelist()
        for name in before.namelist():
            if name != DOCUMENT_PART:
                assert before.read(name) == after.read(name), name
    old, new = index.document_xml, _document_xml(reviewed)
    edited = {resolve_edit(index, edit).index for edit in edits}
    cursor = 0
    for paragraph in index.paragraphs:
        if paragraph.index in edited:
            continue
        chunk = old[paragraph.start : paragraph.end]
        cursor = new.index(chunk, cursor) + len(chunk)  # untouched paragraphs survive verbatim
    assert new.startswith(old[: index.paragraphs[0].start])
    assert b'mc:Ignorable="w14"' in new and b"<w:tbl>" in new and b"<w:sectPr>" in new
    ElementTree.fromstring(new)  # still well-formed


def test_run_formatting_is_preserved_when_a_span_crosses_runs() -> None:
    source = build_synthetic_msa("specialist")
    edit = next(e for e in _edits(source) if e.change_id.startswith("chg-liability-cap"))
    reviewed, _ = apply_tracked_changes(source, [edit], MARK)
    root = ElementTree.fromstring(_document_xml(reviewed))
    paragraph = next(
        p for p in root.iter(f"{W}p") if "aggregate liability" in "".join(p.itertext())
    )
    bold = [r for r in paragraph.iter(f"{W}r") if r.find(f"{W}rPr/{W}b") is not None]
    assert ["".join(r.itertext()) for r in bold] == ["aggregate liability"]
    deletions = paragraph.findall(f"{W}del")
    assert ["".join(d.itertext()) for d in deletions] == ["three hundred ", "percent (300%)"]
    assert deletions[1].find(f"{W}r/{W}rPr/{W}i") is not None  # italic kept on the deleted run
    insertion = paragraph.find(f"{W}ins")
    assert "".join(insertion.itertext()) == "one hundred percent (100%)"
    assert insertion.find(f"{W}r/{W}rPr") is None  # takes the formatting where the span starts
    ids = [node.get(f"{W}id") for node in root.iter() if node.tag in {f"{W}ins", f"{W}del"}]
    assert len(ids) == len(set(ids)) and all(i and i != "0" for i in ids)


def test_tracked_changes_carry_author_and_date() -> None:
    source = build_synthetic_msa("routine")
    reviewed, _ = apply_tracked_changes(source, _edits(source), MARK)
    changes = list_tracked_changes(reviewed)
    assert {(c.author, c.date) for c in changes} == {(MARK.author, MARK.date)}
    assert [c.kind for c in changes].count("insertion") == 2


# SHA-256 of word/document.xml from one mark for the whole file, as the writer gave it
# before per-change marks (ADR 0004). The XML is pinned, not the zip, whose deflate output
# can vary with the zlib version.
SINGLE_MARK_DOCUMENT_XML = {
    "routine": "c66c16599026db56e370d23698f77c8c24ea83dc4b2a30ea776f56f7646a33df",
    "specialist": "685727ca69e586234454f930be97ad09fca80ba6f66fc251a0327b5b830e9503",
}


@pytest.mark.parametrize("variant", sorted(SINGLE_MARK_DOCUMENT_XML))
def test_per_change_marks_default_to_the_single_mark_byte_for_byte(variant) -> None:
    source = build_synthetic_msa(variant)
    edits = _edits(source)
    single, _ = apply_tracked_changes(source, edits, MARK)
    digest = hashlib.sha256(_document_xml(single)).hexdigest()
    assert digest == SINGLE_MARK_DOCUMENT_XML[variant]
    for marks in (None, {}, {edit.change_id: MARK for edit in edits}):
        assert apply_tracked_changes(source, edits, MARK, marks=marks)[0] == single


def test_each_tracked_change_carries_the_mark_of_its_own_change() -> None:
    source = build_synthetic_msa("specialist")
    edits = _edits(source)
    marks = _distinct_marks(edits)
    reviewed, index = apply_tracked_changes(source, edits, MARK, marks=marks)
    root = ElementTree.fromstring(_document_xml(reviewed))
    wrappers = [node for node in root.iter() if node.tag in {f"{W}ins", f"{W}del"}]
    ids = [int(node.attrib[f"{W}id"]) for node in wrappers]
    assert len(ids) == len(set(ids)) and min(ids) > index.max_annotation_id
    by_mark: dict[tuple[str, str], list] = {}
    for node in wrappers:
        by_mark.setdefault((node.attrib[f"{W}author"], node.attrib[f"{W}date"]), []).append(node)
    assert set(by_mark) == {(mark.author, mark.date) for mark in marks.values()}
    for edit in edits:
        own = by_mark[(marks[edit.change_id].author, marks[edit.change_id].date)]
        deleted = "".join(_revision_text(node) for node in own if node.tag == f"{W}del")
        inserted = "".join(_revision_text(node) for node in own if node.tag == f"{W}ins")
        assert deleted == ("" if edit.operation == "insert_paragraph_after" else edit.original_text)
        assert inserted == ("" if edit.operation == "delete_paragraph" else edit.new_text)

    # The paragraph mark of an inserted or deleted clause belongs to that clause's change.
    inserted_clause = next(e for e in edits if e.operation == "insert_paragraph_after")
    deleted_clause = next(e for e in edits if e.operation == "delete_paragraph")
    assert inserted_clause.change_id.startswith("chg-liability-exclusions")
    assert deleted_clause.change_id.startswith("chg-most-favoured-customer")
    paragraph_marks = sorted(
        (_local_name(node.tag), node.get(f"{W}author"), node.get(f"{W}date"))
        for node in root.iterfind(f".//{W}pPr/{W}rPr/*")
        if node.tag in {f"{W}ins", f"{W}del"}
    )
    assert paragraph_marks == sorted(
        [
            ("del", marks[deleted_clause.change_id].author, marks[deleted_clause.change_id].date),
            ("ins", marks[inserted_clause.change_id].author, marks[inserted_clause.change_id].date),
        ]
    )

    single, _ = apply_tracked_changes(source, edits, MARK)
    assert read_paragraph_texts(reviewed, "rejected") == read_paragraph_texts(source, "accepted")
    assert read_paragraph_texts(reviewed, "accepted") == read_paragraph_texts(single, "accepted")


@pytest.mark.parametrize("per_change", [False, True])
def test_tracked_change_markup_uses_ins_del_and_deltext(per_change) -> None:
    source = build_synthetic_msa("specialist")
    edits = _edits(source)
    marks = _distinct_marks(edits) if per_change else None
    reviewed, _ = apply_tracked_changes(source, edits, MARK, marks=marks)
    root = ElementTree.fromstring(_document_xml(reviewed))
    in_text: list = []
    paragraph_marks: list = []
    for paragraph in root.iter(f"{W}p"):
        in_text += paragraph.findall(f"{W}ins") + paragraph.findall(f"{W}del")
        paragraph_marks += paragraph.findall(f"{W}pPr/{W}rPr/{W}ins")
        paragraph_marks += paragraph.findall(f"{W}pPr/{W}rPr/{W}del")
    every = [node for node in root.iter() if node.tag in {f"{W}ins", f"{W}del"}]
    assert len(every) == len(in_text) + len(paragraph_marks) and len(paragraph_marks) == 2
    for wrapper in in_text:
        assert wrapper.get(f"{W}id") and wrapper.get(f"{W}author") and wrapper.get(f"{W}date")
        runs = list(wrapper)
        assert runs and all(run.tag == f"{W}r" for run in runs)
        kept, dropped = (
            (f"{W}delText", f"{W}t") if wrapper.tag == f"{W}del" else (f"{W}t", f"{W}delText")
        )
        assert all(run.find(kept) is not None and run.find(dropped) is None for run in runs)
    assert all(len(node) == 0 and node.get(f"{W}author") for node in paragraph_marks)


def test_revision_marks_are_checked_and_made_xml_safe() -> None:
    source = build_synthetic_msa("routine")
    edits = _edits(source)
    first = edits[0].change_id
    with pytest.raises(ValueError, match="revision marks name no edit: chg-unknown"):
        apply_tracked_changes(source, edits, MARK, marks={"chg-unknown": MARK})

    unsafe = RevisionMark("A\x01B\x00 \n  C\ufffe", MARK.date)
    reviewed, _ = apply_tracked_changes(source, edits, MARK, marks={first: unsafe})
    ElementTree.fromstring(_document_xml(reviewed))  # still well-formed
    assert {c.author for c in list_tracked_changes(reviewed)} == {"AB C", MARK.author}
    assert revision_label("x" * 300) == "x" * 255

    for bad in (
        RevisionMark("\x01\x02 \t", MARK.date),
        RevisionMark("Reviewer", "2026-01-01"),
        RevisionMark("Reviewer", "2026-01-01T00:00:00Z\n"),
        RevisionMark("Reviewer", "2026-13-01T00:00:00Z"),
        RevisionMark("Reviewer", "2026-01-01T00:00:00.123456Z"),
    ):
        with pytest.raises(ValueError, match="revision mark"):
            apply_tracked_changes(source, edits, MARK, marks={first: bad})
        with pytest.raises(ValueError, match="revision mark"):
            apply_tracked_changes(source, edits, bad)


def test_locator_survives_a_moved_paragraph_but_not_changed_wording() -> None:
    source = build_synthetic_msa("routine")
    edit = next(e for e in _edits(source) if e.change_id.startswith("chg-payment-terms"))
    stale_position = RedlineEdit(**{**edit.__dict__, "paragraph_index": edit.paragraph_index + 3})
    assert resolve_edit(index_docx(source), stale_position).index == edit.paragraph_index

    reworded = _repackage(source, lambda xml: xml.replace(b"ninety (90) days", b"sixty (60) days"))
    with pytest.raises(LocatorError, match="target not found"):
        apply_tracked_changes(reworded, [edit], MARK)

    shifted = RedlineEdit(**{**edit.__dict__, "start": edit.start + 1, "end": edit.end + 1})
    with pytest.raises(LocatorError, match="original text mismatch"):
        apply_tracked_changes(source, [shifted], MARK)


def test_ambiguous_target_fails_clearly() -> None:
    source = build_synthetic_msa("routine")
    clause = b"<w:p><w:r><w:t>7. General</w:t></w:r></w:p>"
    doubled = _repackage(
        source, lambda xml: xml.replace(b"<w:sectPr>", clause + clause + b"<w:sectPr>")
    )
    index = index_docx(doubled)
    twins = [p for p in index.paragraphs if p.text == "7. General"]
    assert len(twins) == 3
    edit = RedlineEdit("chg-x", "delete_paragraph", 999, twins[0].text_hash, "7. General", "")
    with pytest.raises(LocatorError, match="ambiguous target"):
        apply_tracked_changes(doubled, [edit], MARK)

    rule = (
        load_playbook()
        .rules[0]
        .model_copy(
            update={
                "rule_id": "general",
                "clause_pattern": "General",
                "deviation_pattern": "General",
            }
        )
    )
    playbook = Playbook.model_validate(
        {**load_playbook().model_dump(by_alias=True), "rules": [rule]}
    )
    proposal = propose_changes(index, playbook)
    assert proposal.changes == [] and "ambiguous target" in proposal.problems[0]


def test_unsupported_structures_are_reported_and_never_edited() -> None:
    source = build_synthetic_msa("routine")
    hyperlink = (
        b'<w:p><w:r><w:t xml:space="preserve">2.1\tCustomer shall pay undisputed invoices within </w:t></w:r>'
        b'<w:hyperlink w:anchor="x"><w:r><w:t>ninety (90) days</w:t></w:r></w:hyperlink>'
        b"<w:r><w:t> of receipt.</w:t></w:r></w:p>"
    )
    index = index_docx(source)
    target = next(p for p in index.paragraphs if "undisputed invoices" in p.text)
    original = index.document_xml[target.start : target.end]
    unsupported = _repackage(source, lambda xml: xml.replace(original, hyperlink))
    new_index = index_docx(unsupported)
    paragraph = new_index.paragraphs[target.index]
    assert not paragraph.supported and "w:hyperlink" in (paragraph.unsupported_reason or "")

    proposal = propose_changes(new_index, load_playbook())
    assert "payment-terms" not in {c.rule_id for c in proposal.changes}
    assert any("coverage gap" in problem for problem in proposal.problems)

    edit = next(e for e in _edits(source) if e.change_id.startswith("chg-payment-terms"))
    with pytest.raises(UnsupportedDocumentError, match="outside the supported DOCX subset"):
        apply_tracked_changes(unsupported, [edit], MARK)


def test_existing_tracked_changes_make_a_paragraph_unsupported() -> None:
    source = build_synthetic_msa("routine")
    reviewed, _ = apply_tracked_changes(source, _edits(source), MARK)
    index = index_docx(reviewed)
    assert sum(not p.supported for p in index.paragraphs) == 2
    assert len(index.unexamined) == 2


def test_overlapping_and_conflicting_edits_are_refused() -> None:
    source = build_synthetic_msa("routine")
    edit = next(e for e in _edits(source) if e.change_id.startswith("chg-audit-right"))
    overlap = RedlineEdit(
        "chg-overlap", "replace_span", edit.paragraph_index, edit.paragraph_hash,
        "any time", "no time", edit.start + 3, edit.start + 11,
    )  # fmt: skip
    with pytest.raises(LocatorError, match="overlaps"):
        apply_tracked_changes(source, [edit, overlap], MARK)
    paragraph = index_docx(source).paragraphs[edit.paragraph_index]
    delete = RedlineEdit(
        "chg-delete", "delete_paragraph", paragraph.index, paragraph.text_hash, paragraph.text, ""
    )
    with pytest.raises(LocatorError, match="conflicting changes"):
        apply_tracked_changes(source, [edit, delete], MARK)


def test_non_docx_and_multiline_insertions_are_refused() -> None:
    with pytest.raises(UnsupportedDocumentError, match="must be a DOCX package"):
        index_docx(b"not a zip file")
    source = build_synthetic_msa("routine")
    edit = next(e for e in _edits(source) if e.change_id.startswith("chg-payment-terms"))
    multiline = RedlineEdit(**{**edit.__dict__, "new_text": "thirty\n(30) days"})
    with pytest.raises(UnsupportedDocumentError, match="single-line"):
        apply_tracked_changes(source, [multiline], MARK)


def test_inserted_text_a_word_document_cannot_hold_is_refused() -> None:
    # Written as is into w:t, such a character would leave word/document.xml malformed.
    source = build_synthetic_msa("routine")
    edit = next(e for e in _edits(source) if e.change_id.startswith("chg-payment-terms"))
    for text in ("thirty (30) days\x01", "thirty\x0b(30) days", "thirty days\ufffe", "\ud800"):
        unsafe = RedlineEdit(**{**edit.__dict__, "new_text": text})
        with pytest.raises(UnsupportedDocumentError, match="a Word document cannot hold"):
            apply_tracked_changes(source, [unsafe], MARK)
        assert has_non_xml_char(text)
    assert not has_non_xml_char("forty-five (45) days, \u00a7 3 \u20ac\t\U0001f600")
