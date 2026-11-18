"""Tracked changes for a defined subset of DOCX structures.

Supported subset
----------------
* Body-level paragraphs only (direct children of ``w:body``). Paragraphs inside
  tables, text boxes, headers, footers and footnotes are not addressable.
* Paragraph children: ``w:pPr``, ``w:r``, ``w:bookmarkStart``, ``w:bookmarkEnd``,
  ``w:proofErr``.
* Run children: ``w:rPr``, ``w:t``, ``w:tab``, ``w:br`` without a type, and
  ``w:lastRenderedPageBreak``.

A paragraph containing anything else (hyperlinks, fields, content controls,
drawings, comment ranges, existing tracked changes) is indexed as unsupported, and
an edit that targets it fails. Only the bytes of an edited paragraph are replaced;
every other byte of ``word/document.xml`` and every other package part is copied
unchanged.

Revision marks
--------------
Every tracked change is a ``w:ins`` or ``w:del`` carrying ``w:id``, ``w:author`` and
``w:date``; deleted text is written as ``w:delText``, and an inserted or deleted
paragraph also marks its paragraph mark under ``w:pPr/w:rPr``. One revision mark
applies to every change unless a mark is given for a change by its ``change_id``, so
the author and date may differ per change. An author keeps only characters XML 1.0
allows, on one line, at most 255 of them; a date is UTC to the second
(``YYYY-MM-DDTHH:MM:SSZ``). No ``word/settings.xml``, comments or tables are written.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET
from xml.parsers import expat

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DOCUMENT_PART = "word/document.xml"
Operation = Literal["replace_span", "insert_paragraph_after", "delete_paragraph"]
TextView = Literal["accepted", "rejected"]

_PARAGRAPH_CHILDREN = {"pPr", "r", "bookmarkStart", "bookmarkEnd", "proofErr"}
_ZERO_WIDTH_RUN_CHILDREN = {"lastRenderedPageBreak"}
_CLAUSE_REF = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s")
_ANNOTATION_ID = re.compile(rb'w:id="(\d+)"')
# Characters outside the XML 1.0 Char production; ElementTree would write them unescaped.
_NOT_XML_CHAR = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
_REVISION_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


class UnsupportedDocumentError(ValueError):
    """The document or the targeted paragraph is outside the supported subset."""


class LocatorError(ValueError):
    """A change could not be resolved to exactly one verified location."""


def _w(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Paragraph:
    index: int
    start: int
    end: int
    text: str
    text_hash: str
    supported: bool
    unsupported_reason: str | None
    clause_ref: str | None


@dataclass(frozen=True)
class DocumentIndex:
    sha256: str
    document_xml: bytes
    paragraphs: tuple[Paragraph, ...]
    namespaces: tuple[tuple[str, str], ...]
    max_annotation_id: int
    # Body-level content the engine does not read, as (element name, content digest).
    unexamined: tuple[tuple[str, str], ...] = ()

    def paragraph(self, index: int) -> Paragraph:
        return self.paragraphs[index]


@dataclass(frozen=True)
class RedlineEdit:
    change_id: str
    operation: Operation
    paragraph_index: int
    paragraph_hash: str
    original_text: str
    new_text: str
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class RevisionMark:
    author: str
    date: str


def revision_label(text: str) -> str:
    """An author label that XML can hold: no control characters, one line, at most 255."""

    return " ".join(_NOT_XML_CHAR.sub("", text).split())[:255].rstrip()


def _checked_mark(mark: RevisionMark) -> RevisionMark:
    author = revision_label(mark.author)
    if not author:
        raise ValueError("revision mark author is empty without the characters XML cannot hold")
    problem = f"revision mark date must be UTC to the second (YYYY-MM-DDTHH:MM:SSZ): {mark.date!r}"
    if not _REVISION_DATE.fullmatch(mark.date):
        raise ValueError(problem)
    try:
        datetime.strptime(mark.date, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(problem) from error
    return RevisionMark(author=author, date=mark.date)


@dataclass(frozen=True)
class TrackedChange:
    kind: Literal["insertion", "deletion"]
    author: str
    date: str
    text: str


def _scan(xml: bytes) -> tuple[list[tuple[str, int, int]], list[tuple[str, str]]]:
    """Return the byte range of every body-level element and the root namespace declarations."""

    ranges: list[tuple[str, int, int]] = []
    namespaces: list[tuple[str, str]] = []
    stack: list[str] = []
    open_start: list[int] = []
    parser = expat.ParserCreate(namespace_separator=" ")
    body = f"{W_NS} body"

    def start_namespace(prefix: str | None, uri: str) -> None:
        if not stack and prefix:
            namespaces.append((prefix, uri))

    def start_element(name: str, _attrs: dict[str, str]) -> None:
        stack.append(name)
        if len(stack) == 3 and stack[1] == body:
            open_start.append(parser.CurrentByteIndex)

    def end_element(name: str) -> None:
        if len(stack) == 3 and stack[1] == body:
            end = xml.index(b">", parser.CurrentByteIndex) + 1
            ranges.append((name.rsplit(" ", 1)[-1], open_start.pop(), end))
        stack.pop()

    parser.StartNamespaceDeclHandler = start_namespace
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(xml, True)
    except expat.ExpatError as error:
        raise UnsupportedDocumentError(f"word/document.xml is not well-formed: {error}") from error
    return ranges, namespaces


def _parse_fragment(fragment: bytes, namespaces: tuple[tuple[str, str], ...]) -> ET.Element:
    declarations = "".join(f' xmlns:{prefix}="{uri}"' for prefix, uri in namespaces)
    wrapped = f"<wrapper{declarations}>".encode() + fragment + b"</wrapper>"
    try:
        return ET.fromstring(wrapped)[0]
    except (ET.ParseError, IndexError) as error:
        raise UnsupportedDocumentError(f"paragraph could not be parsed: {error}") from error


def _run_atoms(run: ET.Element) -> list[tuple[str, object]] | None:
    """Flatten a run into character atoms; ``None`` when the run is unsupported."""

    atoms: list[tuple[str, object]] = []
    for child in run:
        name = _local(child.tag)
        if name == "rPr":
            continue
        if name == "t":
            atoms.extend(("char", char) for char in (child.text or ""))
        elif name == "tab":
            atoms.append(("char", "\t"))
        elif name == "br" and not child.attrib:
            atoms.append(("char", "\n"))
        elif name in _ZERO_WIDTH_RUN_CHILDREN:
            atoms.append(("zero", child))
        else:
            return None
    return atoms


def _paragraph_text(element: ET.Element) -> tuple[str, str | None]:
    parts: list[str] = []
    for child in element:
        name = _local(child.tag)
        if name not in _PARAGRAPH_CHILDREN:
            return "", f"unsupported paragraph content: w:{name}"
        if name != "r":
            continue
        atoms = _run_atoms(child)
        if atoms is None:
            return "", "unsupported run content"
        parts.extend(str(value) for kind, value in atoms if kind == "char")
    return "".join(parts), None


def index_docx(data: bytes) -> DocumentIndex:
    """Index the body-level paragraphs of a DOCX package."""

    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise UnsupportedDocumentError("source document must be a DOCX package")
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        if DOCUMENT_PART not in package.namelist():
            raise UnsupportedDocumentError("DOCX package has no word/document.xml")
        xml = package.read(DOCUMENT_PART)
    if xml[:2] in {b"\xff\xfe", b"\xfe\xff"}:
        raise UnsupportedDocumentError("word/document.xml must be UTF-8 encoded")
    ranges, namespaces = _scan(xml)
    namespace_tuple = tuple(namespaces)
    paragraphs: list[Paragraph] = []
    unexamined: list[tuple[str, str]] = []
    for name, start, end in ranges:
        if name == "sectPr":
            continue
        if name != "p":
            unexamined.append((name, hashlib.sha256(xml[start:end]).hexdigest()[:16]))
            continue
        element = _parse_fragment(xml[start:end], namespace_tuple)
        text, reason = _paragraph_text(element)
        clause = _CLAUSE_REF.match(text)
        if reason is not None:
            unexamined.append(("p", hashlib.sha256(xml[start:end]).hexdigest()[:16]))
        paragraphs.append(
            Paragraph(
                index=len(paragraphs),
                start=start,
                end=end,
                text=text,
                text_hash=text_hash(text) if reason is None else "",
                supported=reason is None,
                unsupported_reason=reason,
                clause_ref=clause.group(1) if clause else None,
            )
        )
    ids = [int(match) for match in _ANNOTATION_ID.findall(xml)]
    return DocumentIndex(
        sha256=hashlib.sha256(data).hexdigest(),
        document_xml=xml,
        paragraphs=tuple(paragraphs),
        namespaces=namespace_tuple,
        max_annotation_id=max(ids, default=0),
        unexamined=tuple(unexamined),
    )


def resolve_edit(index: DocumentIndex, edit: RedlineEdit) -> Paragraph:
    """Resolve an edit to one paragraph and verify the original text is still there."""

    candidates = [p for p in index.paragraphs if p.supported and p.text_hash == edit.paragraph_hash]
    if not candidates:
        target = (
            index.paragraphs[edit.paragraph_index]
            if 0 <= edit.paragraph_index < len(index.paragraphs)
            else None
        )
        if target is not None and not target.supported:
            raise UnsupportedDocumentError(
                f"{edit.change_id}: paragraph {edit.paragraph_index} is outside the supported "
                f"DOCX subset ({target.unsupported_reason})"
            )
        raise LocatorError(
            f"{edit.change_id}: target not found; the paragraph text recorded at the locator "
            "is no longer in the document"
        )
    if len(candidates) > 1:
        candidates = [p for p in candidates if p.index == edit.paragraph_index]
        if len(candidates) != 1:
            raise LocatorError(
                f"{edit.change_id}: ambiguous target; several paragraphs carry identical text "
                "and the recorded position matches none of them"
            )
    paragraph = candidates[0]
    if edit.operation == "replace_span":
        if edit.start is None or edit.end is None or not 0 <= edit.start < edit.end:
            raise LocatorError(f"{edit.change_id}: replace_span needs a non-empty character span")
        if paragraph.text[edit.start : edit.end] != edit.original_text:
            raise LocatorError(
                f"{edit.change_id}: original text mismatch at the recorded span; "
                "the change was proposed against different wording"
            )
    elif edit.operation == "delete_paragraph":
        if paragraph.text != edit.original_text:
            raise LocatorError(f"{edit.change_id}: original text mismatch for paragraph deletion")
    if edit.operation != "delete_paragraph" and (
        not edit.new_text or re.search(r"[\t\n\r]", edit.new_text)
    ):
        raise UnsupportedDocumentError(
            f"{edit.change_id}: inserted text must be non-empty single-line text"
        )
    return paragraph


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    new_text: str
    change_id: str


class _Marker:
    """Hands out revision wrappers with unique ids and the mark of their own change."""

    def __init__(
        self, mark: RevisionMark, first_id: int, marks: Mapping[str, RevisionMark]
    ) -> None:
        self._mark = _checked_mark(mark)
        self._marks = {change_id: _checked_mark(m) for change_id, m in marks.items()}
        self._next_id = first_id

    def element(self, local: str, change_id: str) -> ET.Element:
        mark = self._marks.get(change_id, self._mark)
        element = ET.Element(
            _w(local),
            {
                _w("id"): str(self._next_id),
                _w("author"): mark.author,
                _w("date"): mark.date,
            },
        )
        self._next_id += 1
        return element


def _build_run(
    properties: ET.Element | None, atoms: Sequence[tuple[str, object]], deleted: bool
) -> ET.Element:
    run = ET.Element(_w("r"))
    if properties is not None:
        run.append(copy.deepcopy(properties))
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            text = ET.SubElement(run, _w("delText" if deleted else "t"))
            text.set(XML_SPACE, "preserve")
            text.text = "".join(buffer)
            buffer.clear()

    for kind, value in atoms:
        if kind == "zero":
            flush()
            if isinstance(value, ET.Element):
                run.append(copy.deepcopy(value))
        elif value == "\t":
            flush()
            ET.SubElement(run, _w("tab"))
        elif value == "\n":
            flush()
            ET.SubElement(run, _w("br"))
        else:
            buffer.append(str(value))
    flush()
    return run


def _wrap(marker: _Marker, local: str, run: ET.Element, change_id: str) -> ET.Element:
    wrapper = marker.element(local, change_id)
    wrapper.append(run)
    return wrapper


def _apply_spans(paragraph: ET.Element, spans: list[_Span], marker: _Marker) -> None:
    rebuilt: list[ET.Element] = []
    first_properties: dict[str, ET.Element | None] = {}
    position = 0
    for child in list(paragraph):
        if _local(child.tag) != "r":
            rebuilt.append(child)
            continue
        atoms = _run_atoms(child) or []
        properties = child.find(_w("rPr"))
        offsets: list[int] = []
        cursor = position
        for kind, _value in atoms:
            offsets.append(cursor)
            cursor += 1 if kind == "char" else 0
        run_start, run_end = position, cursor
        position = run_end
        overlapping = [s for s in spans if s.start < run_end and s.end > run_start]
        # A run holding only zero-width markers has no characters to split.
        if not overlapping or run_start == run_end:
            rebuilt.append(child)
            continue
        cuts = sorted(
            {run_start, run_end}
            | {max(run_start, s.start) for s in overlapping}
            | {min(run_end, s.end) for s in overlapping}
        )
        for left, right in zip(cuts, cuts[1:], strict=False):
            last = right == run_end
            segment = [
                atom
                for atom, offset in zip(atoms, offsets, strict=True)
                if left <= offset < right or (last and offset == run_end and atom[0] == "zero")
            ]
            span = next((s for s in overlapping if s.start <= left and right <= s.end), None)
            if span is None:
                rebuilt.append(_build_run(properties, segment, deleted=False))
                continue
            rebuilt.append(
                _wrap(marker, "del", _build_run(properties, segment, deleted=True), span.change_id)
            )
            # The replacement starts where the deleted text started, so it takes that
            # run's formatting even when the span ends in differently formatted text.
            first_properties.setdefault(span.change_id, properties)
            if right == span.end:
                inserted = [("char", char) for char in span.new_text]
                rebuilt.append(
                    _wrap(
                        marker,
                        "ins",
                        _build_run(first_properties[span.change_id], inserted, deleted=False),
                        span.change_id,
                    )
                )
    paragraph[:] = rebuilt


def _mark_paragraph(paragraph: ET.Element, marker: _Marker, local: str, change_id: str) -> None:
    """Mark the paragraph mark itself as inserted or deleted."""

    properties = paragraph.find(_w("pPr"))
    if properties is None:
        properties = ET.Element(_w("pPr"))
        paragraph.insert(0, properties)
    if properties.find(_w("sectPr")) is not None:
        raise UnsupportedDocumentError("a paragraph carrying a section break cannot be changed")
    run_properties = properties.find(_w("rPr"))
    if run_properties is None:
        run_properties = ET.SubElement(properties, _w("rPr"))
    run_properties.insert(0, marker.element(local, change_id))


def _delete_paragraph(paragraph: ET.Element, marker: _Marker, change_id: str) -> None:
    rebuilt: list[ET.Element] = []
    for child in list(paragraph):
        if _local(child.tag) != "r":
            rebuilt.append(child)
            continue
        atoms = _run_atoms(child) or []
        run = _build_run(child.find(_w("rPr")), atoms, deleted=True)
        rebuilt.append(_wrap(marker, "del", run, change_id))
    paragraph[:] = rebuilt
    _mark_paragraph(paragraph, marker, "del", change_id)


def _inserted_paragraph(
    anchor: ET.Element, text: str, marker: _Marker, change_id: str
) -> ET.Element:
    paragraph = ET.Element(_w("p"))
    anchor_properties = anchor.find(_w("pPr"))
    if anchor_properties is not None:
        properties = copy.deepcopy(anchor_properties)
        for stale in properties.findall(_w("rPr")) + properties.findall(_w("sectPr")):
            properties.remove(stale)
        paragraph.append(properties)
    first_run = anchor.find(_w("r"))
    run_properties = first_run.find(_w("rPr")) if first_run is not None else None
    atoms: list[tuple[str, object]] = [("char", char) for char in text]
    run = _build_run(run_properties, atoms, deleted=False)
    paragraph.append(_wrap(marker, "ins", run, change_id))
    _mark_paragraph(paragraph, marker, "ins", change_id)
    return paragraph


def _serialise(element: ET.Element, namespaces: tuple[tuple[str, str], ...]) -> bytes:
    for prefix, uri in namespaces:
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            # ElementTree reserves prefixes of the form ns<number>; it will pick its own.
            continue
    return ET.tostring(element, encoding="unicode").encode("utf-8")


def apply_tracked_changes(
    source: bytes,
    edits: list[RedlineEdit],
    mark: RevisionMark,
    *,
    marks: Mapping[str, RevisionMark] | None = None,
) -> tuple[bytes, DocumentIndex]:
    """Return a new DOCX with the edits applied as tracked changes.

    ``mark`` is the author and date of every change that ``marks`` does not name by
    its ``change_id``. Without ``marks`` the output is byte for byte what one mark
    for the whole file gives.
    """

    per_change = dict(marks or {})
    unknown = sorted(set(per_change) - {edit.change_id for edit in edits})
    if unknown:
        raise ValueError(f"revision marks name no edit: {', '.join(unknown)}")
    index = index_docx(source)
    by_paragraph: dict[int, list[RedlineEdit]] = {}
    for edit in edits:
        by_paragraph.setdefault(resolve_edit(index, edit).index, []).append(edit)

    marker = _Marker(mark, index.max_annotation_id + 1, per_change)
    replacements: list[tuple[int, int, bytes]] = []
    for paragraph_index in sorted(by_paragraph):
        paragraph = index.paragraphs[paragraph_index]
        group = by_paragraph[paragraph_index]
        spans = sorted(
            (
                _Span(e.start or 0, e.end or 0, e.new_text, e.change_id)
                for e in group
                if e.operation == "replace_span"
            ),
            key=lambda span: span.start,
        )
        deletions = [e for e in group if e.operation == "delete_paragraph"]
        insertions = [e for e in group if e.operation == "insert_paragraph_after"]
        if deletions and (spans or len(deletions) > 1):
            raise LocatorError(
                f"{deletions[0].change_id}: conflicting changes target the same paragraph"
            )
        for earlier, later in zip(spans, spans[1:], strict=False):
            if later.start < earlier.end:
                raise LocatorError(
                    f"{later.change_id}: overlaps {earlier.change_id} in the same paragraph"
                )
        element = _parse_fragment(
            index.document_xml[paragraph.start : paragraph.end], index.namespaces
        )
        anchor = copy.deepcopy(element)
        if spans:
            _apply_spans(element, spans, marker)
        if deletions:
            _delete_paragraph(element, marker, deletions[0].change_id)
        payload = _serialise(element, index.namespaces)
        for insertion in insertions:
            payload += _serialise(
                _inserted_paragraph(anchor, insertion.new_text, marker, insertion.change_id),
                index.namespaces,
            )
        replacements.append((paragraph.start, paragraph.end, payload))

    document_xml = index.document_xml
    for start, end, payload in sorted(replacements, reverse=True):
        document_xml = document_xml[:start] + payload + document_xml[end:]

    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source)) as source_package,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target_package,
    ):
        for member in source_package.infolist():
            payload = source_package.read(member.filename)
            if member.filename == DOCUMENT_PART:
                payload = document_xml
            target_package.writestr(member, payload)
    return buffer.getvalue(), index


def _body_paragraphs(data: bytes) -> list[ET.Element]:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        root = ET.fromstring(package.read(DOCUMENT_PART))
    body = root.find(_w("body"))
    return [] if body is None else [child for child in body if child.tag == _w("p")]


def _has_mark(paragraph: ET.Element, local: str) -> bool:
    return paragraph.find(f"{_w('pPr')}/{_w('rPr')}/{_w(local)}") is not None


def read_paragraph_texts(data: bytes, view: TextView) -> list[str]:
    """Body paragraph texts with every tracked change accepted or rejected.

    Used to prove integrity: the rejected view of a reviewed document must equal the
    source document, paragraph for paragraph.
    """

    keep_text = _w("t") if view == "accepted" else _w("delText")
    skip_wrapper = _w("del") if view == "accepted" else _w("ins")
    dropped_mark = "del" if view == "accepted" else "ins"
    texts: list[str] = []
    for paragraph in _body_paragraphs(data):
        if _has_mark(paragraph, dropped_mark):
            continue
        parts: list[str] = []

        def walk(element: ET.Element, parts: list[str] = parts) -> None:
            for child in element:
                if child.tag == skip_wrapper:
                    continue
                if child.tag in {_w("t"), keep_text}:
                    parts.append(child.text or "")
                elif child.tag == _w("tab"):
                    parts.append("\t")
                elif child.tag == _w("br"):
                    parts.append("\n")
                elif child.tag != _w("pPr"):
                    walk(child)

        walk(paragraph)
        texts.append("".join(parts))
    return texts


def list_tracked_changes(data: bytes) -> list[TrackedChange]:
    changes: list[TrackedChange] = []
    for paragraph in _body_paragraphs(data):
        for element in paragraph.iter():
            if element.tag not in {_w("ins"), _w("del")} or not element.findall(_w("r")):
                continue
            kind: Literal["insertion", "deletion"] = (
                "insertion" if element.tag == _w("ins") else "deletion"
            )
            text = "".join(
                node.text or "" for node in element.iter() if node.tag in {_w("t"), _w("delText")}
            )
            changes.append(
                TrackedChange(
                    kind=kind,
                    author=element.get(_w("author"), ""),
                    date=element.get(_w("date"), ""),
                    text=text,
                )
            )
    return changes


def write_reviewed_docx(
    source: Path,
    output: Path,
    edits: list[RedlineEdit],
    mark: RevisionMark,
    *,
    marks: Mapping[str, RevisionMark] | None = None,
) -> Path:
    if source.resolve() == output.resolve():
        raise ValueError("reviewed DOCX output must not overwrite the source document")
    reviewed, _ = apply_tracked_changes(source.read_bytes(), edits, mark, marks=marks)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(reviewed)
    return output
