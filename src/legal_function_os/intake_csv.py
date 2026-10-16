"""Read legal requests from a spreadsheet saved as CSV.

Request logs usually live in a spreadsheet. Save it as CSV and pass the file to
``--input``: the header row names the fields and every other row is one request.

- Headers are matched the way the request format spells them, so "Value band",
  "value-band" and "valueBand" all mean ``value_band``. "Request ID", "Request
  type" and "Requester" are accepted for ``id``, ``type`` and ``requested_by``.
- An empty cell means the field was not given, so its default applies.
- In the yes/no columns, yes/no, true/false, ja/nein, wahr/falsch, 1/0 and x are
  read as booleans. Any other answer is passed on and rejected by validation.
- In ``facts`` and ``dependencies`` each line of a cell is one item.
- Every other value is passed on unchanged, so the same checks apply as for JSON:
  ``>1M`` is still rejected with a suggestion.
- A header that looks like a misspelled request field, such as "Value bnad", stops
  the run. Any other column that is not a request field is passed through, and the
  run notes it, because a header such as "Value band (EUR)" would otherwise be
  ignored silently.

Comma, semicolon and tab delimiters are recognised from the header row, which
covers the CSV dialects Excel writes in English and German locales.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any

from legal_function_os.validation import (
    AUXILIARY_FIELDS,
    BOOLEAN_FIELDS,
    BOOLEAN_WORDS,
    EXTENSION_PREFIXES,
    REQUEST_FIELDS,
    misspelled_field,
    normalise_field_name,
)

HEADER_ALIASES = {
    "request_id": "id",
    "request_type": "type",
    "requester": "requested_by",
}
DELIMITERS = (",", ";", "\t")
YES_NO_COLUMNS = (*BOOLEAN_FIELDS, "awaiting_business_input")
LIST_COLUMNS = ("facts", "dependencies")
KNOWN_COLUMNS = (*REQUEST_FIELDS, *AUXILIARY_FIELDS)


class CsvFormatError(ValueError):
    """The file is not a usable request table. The message names the row or column."""


@dataclass
class CsvRequests:
    requests: list[dict[str, Any]]
    # "row 2" for the first request: the numbering a spreadsheet shows.
    labels: list[str]
    notes: list[str] = field(default_factory=list)


def _delimiter(header_line: str) -> str:
    counts = {delimiter: header_line.count(delimiter) for delimiter in DELIMITERS}
    best = max(DELIMITERS, key=lambda delimiter: counts[delimiter])
    return best if counts[best] else ","


def _field_names(header: list[str]) -> list[str | None]:
    """Map each column to a request field name; None for a blank header cell."""

    fields: list[str | None] = []
    seen: dict[str, int] = {}
    for column, raw in enumerate(header, start=1):
        if not raw.strip():
            fields.append(None)
            continue
        name = normalise_field_name(raw)
        name = HEADER_ALIASES.get(name, name)
        meant = misspelled_field(name)
        if meant:
            raise CsvFormatError(
                f"column {column} is headed {raw.strip()!r}, which is not a request field "
                f"(did you mean {meant!r}?); rename it, or prefix your own column with x_"
            )
        if name in seen:
            raise CsvFormatError(
                f"columns {seen[name]} and {column} both hold {name!r}; keep one of them"
            )
        seen[name] = column
        fields.append(name)
    return fields


def _cell(field: str, raw: str) -> Any:
    value = raw.strip()
    if field in YES_NO_COLUMNS:
        return BOOLEAN_WORDS.get(value.lower(), value)
    if field in LIST_COLUMNS:
        return [line.strip() for line in value.splitlines() if line.strip()]
    return value


def _unknown_columns(header: list[str], fields: list[str | None]) -> list[str]:
    return [
        raw.strip()
        for raw, name in zip(header, fields, strict=True)
        if name is not None and name not in KNOWN_COLUMNS and not name.startswith(EXTENSION_PREFIXES)
    ]


def parse_csv(text: str) -> CsvRequests:
    """Return the requests in ``text``, a label for each one and notes for the reader.

    Row numbers are the ones a spreadsheet shows: the header is row 1. Rows with
    no values at all are skipped.
    """

    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise CsvFormatError("the first row must name the columns, for example id,title,type")
    reader = csv.reader(io.StringIO(text), delimiter=_delimiter(lines[0]))
    header = next(reader)
    fields = _field_names(header)
    if not any(fields):
        raise CsvFormatError("the first row must name the columns, for example id,title,type")

    requests: list[dict[str, Any]] = []
    labels: list[str] = []
    for row_number, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) > len(fields) and any(cell.strip() for cell in row[len(fields) :]):
            raise CsvFormatError(
                f"row {row_number} has {len(row)} cells but the header names {len(fields)} "
                "columns; check for an unquoted delimiter in a cell"
            )
        request: dict[str, Any] = {}
        for column, (field_name, raw) in enumerate(zip(fields, row, strict=False), start=1):
            if not raw.strip():
                continue
            if field_name is None:
                raise CsvFormatError(
                    f"row {row_number} has a value in column {column}, which has no header"
                )
            request[field_name] = _cell(field_name, raw)
        requests.append(request)
        labels.append(f"row {row_number}")

    notes = []
    unknown = _unknown_columns(header, fields)
    if unknown:
        notes.append(
            "columns that are not request fields pass through unchanged: "
            + ", ".join(repr(name) for name in unknown)
            + "; rename a column if it holds a request field, or prefix your own with x_"
        )
    return CsvRequests(requests, labels, notes)
