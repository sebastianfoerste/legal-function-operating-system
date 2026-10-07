"""Deterministic synthetic DOCX fixtures for the pilot scenarios.

Every party, figure and clause is invented. The builder writes a small but
realistic WordprocessingML package: styles, mixed run formatting, a clause split
across runs, a bookmark, a page-break marker and (optionally) a table, so the
tracked-change engine is exercised against more than a single plain run.
"""

from __future__ import annotations

import io
import zipfile
from typing import Literal
from xml.sax.saxutils import escape

Variant = Literal["routine", "specialist", "blocked"]
Run = tuple[str, str]  # (text, format) where format is "", "b" or "i"

_FIXED_TIME = (2026, 1, 1, 0, 0, 0)
_NAMESPACES = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    'mc:Ignorable="w14"'
)
_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)
_DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:docDefaults><w:rPrDefault><w:rPr>"
    '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/>'
    "</w:rPr></w:rPrDefault>"
    '<w:pPrDefault><w:pPr><w:spacing w:after="120"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:keepNext/><w:spacing w:before="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
    "</w:styles>"
)


def _run(text: str, fmt: str, *, page_break_marker: bool = False) -> str:
    properties = {"b": "<w:rPr><w:b/></w:rPr>", "i": "<w:rPr><w:i/></w:rPr>"}.get(fmt, "")
    parts: list[str] = []
    for index, piece in enumerate(text.split("\t")):
        if index:
            parts.append("<w:tab/>")
        if piece:
            parts.append(f'<w:t xml:space="preserve">{escape(piece)}</w:t>')
    marker = "<w:lastRenderedPageBreak/>" if page_break_marker else ""
    return f"<w:r>{properties}{marker}{''.join(parts)}</w:r>"


def _paragraph(runs: list[Run], style: str = "", *, bookmark: bool = False) -> str:
    properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    start = '<w:bookmarkStart w:id="0" w:name="_SyntheticClause"/>' if bookmark else ""
    end = '<w:bookmarkEnd w:id="0"/>' if bookmark else ""
    body = "".join(
        _run(text, fmt, page_break_marker=(style == "" and index == 0 and text.startswith("5.1")))
        for index, (text, fmt) in enumerate(runs)
    )
    return f"<w:p>{properties}{start}{body}{end}</w:p>"


def _table() -> str:
    def cell(text: str) -> str:
        return (
            '<w:tc><w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
            f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p></w:tc>"
        )

    rows = [
        ("Order summary (synthetic)", "Value"),
        ("Annual contract value", "EUR 480,000"),
        ("Initial term", "36 months"),
    ]
    body = "".join(f"<w:tr>{cell(left)}{cell(right)}</w:tr>" for left, right in rows)
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
        f"{body}</w:tbl>"
    )


def _clauses(variant: Variant) -> list[str]:
    deviating = variant in {"specialist", "blocked"}
    paragraphs = [
        _paragraph([("SYNTHETIC MASTER SUBSCRIPTION AGREEMENT", "")], "Title"),
        _paragraph(
            [
                (
                    "Synthetic training document. Northwind Analytics GmbH (Supplier) and "
                    "Example Retail SE (Customer) are fictitious. Customer draft, "
                    f"variant: {variant}.",
                    "i",
                )
            ]
        ),
        _paragraph([("1. Definitions", "")], "Heading1", bookmark=True),
        _paragraph(
            [
                ("1.1\t", ""),
                ("Fees", "b"),
                (" means the subscription fees set out in the Order Form.", ""),
            ]
        ),
        _paragraph([("2. Fees and Payment", "")], "Heading1"),
        _paragraph(
            [
                (
                    "2.1\tCustomer shall pay undisputed invoices within ninety (90) days of receipt.",
                    "",
                )
            ]
        ),
        _paragraph([("3. Audit", "")], "Heading1"),
        _paragraph(
            [
                ("3.1\tCustomer may audit Supplier's facilities, systems and records ", ""),
                ("at any time", "b"),
                (" and without prior notice.", ""),
            ]
        ),
        _paragraph([("4. Data Protection", "")], "Heading1"),
        _paragraph(
            [
                (
                    "4.1\t"
                    + (
                        "Supplier shall not engage any subprocessor for the processing of "
                        "Customer Personal Data."
                        if deviating
                        else "Supplier may engage the subprocessors listed in Annex 2."
                    ),
                    "",
                )
            ]
        ),
        _paragraph([("5. Limitation of Liability", "")], "Heading1"),
    ]
    if variant == "blocked":
        paragraphs.append(
            _paragraph([("5.1\tSupplier's liability under this Agreement is unlimited.", "")])
        )
    else:
        cap = (
            ("three hundred ", "percent (300%)")
            if deviating
            else ("one hundred ", "percent (100%)")
        )
        paragraphs.append(
            _paragraph(
                [
                    ("5.1\tSupplier's ", ""),
                    ("aggregate liability", "b"),
                    (f" under this Agreement shall not exceed {cap[0]}", ""),
                    (cap[1], "i"),
                    (" of the Fees paid in the twelve (12) months preceding the claim.", ""),
                ]
            )
        )
    if not deviating:
        paragraphs.append(
            _paragraph(
                [
                    (
                        "5.2\tNeither party is liable for indirect or consequential loss, loss of "
                        "profit or loss of data, except where liability cannot be limited or "
                        "excluded by law.",
                        "",
                    )
                ]
            )
        )
    if deviating:
        paragraphs.extend(
            [
                _paragraph([("6. Product Roadmap and Pricing", "")], "Heading1"),
                _paragraph(
                    [
                        (
                            "6.1\tSupplier shall deliver the features described in the Product "
                            "Roadmap no later than 31 December 2026.",
                            "",
                        )
                    ]
                ),
                _paragraph(
                    [
                        (
                            "6.2\tCustomer shall be entitled to the most favourable pricing "
                            "offered by Supplier to any other customer.",
                            "",
                        )
                    ]
                ),
            ]
        )
    paragraphs.append(_paragraph([("7. General", "")], "Heading1"))
    paragraphs.append(_paragraph([("7.1\tThis Agreement is governed by the laws of Germany.", "")]))
    if variant == "specialist":
        paragraphs.append(_table())
    return paragraphs


def build_synthetic_msa(variant: Variant) -> bytes:
    """Build one synthetic customer draft as DOCX bytes; same input, same bytes."""

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {_NAMESPACES}><w:body>{''.join(_clauses(variant))}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1417" w:right="1417" w:bottom="1134" w:left="1417" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    parts = [
        ("[Content_Types].xml", _CONTENT_TYPES),
        ("_rels/.rels", _ROOT_RELS),
        ("word/document.xml", document),
        ("word/styles.xml", _STYLES),
        ("word/_rels/document.xml.rels", _DOCUMENT_RELS),
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for name, payload in parts:
            info = zipfile.ZipInfo(name, date_time=_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()
