"""Read legal requests from a JSON or CSV file, standard input or the bundled synthetic set."""

from __future__ import annotations

import codecs
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from legal_function_os.bundled import bundled_path
from legal_function_os.intake_csv import CsvFormatError, parse_csv


class InputError(ValueError):
    """The requests could not be read. The message is meant for the person running the CLI."""


@dataclass
class RequestInput:
    requests: Any
    source: str
    # Human labels for each request, e.g. "row 4" for a CSV line; defaults to "request N".
    labels: list[str] = field(default_factory=list)
    # Things the person running the CLI should know about how the input was read.
    notes: list[str] = field(default_factory=list)

    def locate(self, index: int) -> str:
        if index < len(self.labels):
            return self.labels[index]
        return f"request {index + 1}"


def _parse_json(text: str, source: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"{source} is not valid JSON: {exc}") from None


def _load_csv(path: str) -> RequestInput:
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from None
    notes: list[str] = []
    try:
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            # Excel's "Unicode Text" export.
            text = data.decode("utf-16")
        else:
            text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel's plain "CSV" export uses the Windows code page, not UTF-8.
        text = data.decode("cp1252", errors="replace")
        notes.append(f"{path} is not UTF-8; it was read as Windows-1252 (Excel's CSV default)")
    try:
        table = parse_csv(text)
    except (CsvFormatError, csv.Error) as exc:
        raise InputError(f"{path} is not a usable request table: {exc}") from None
    return RequestInput(table.requests, path, table.labels, [*notes, *table.notes])


CSV_SUFFIXES = (".csv", ".tsv")
SPREADSHEET_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".ods", ".numbers")


def load_requests(path: str | None) -> RequestInput:
    """Load requests from ``path``.

    A ``.csv`` (or ``.tsv``) file holds one request per row; any other file holds a
    JSON array. ``-`` reads JSON from standard input, and None the bundled synthetic set.
    """

    if path is None:
        source = bundled_path("sample_requests.json")
        return RequestInput(_parse_json(source.read_text(encoding="utf-8"), str(source)), str(source))
    if path == "-":
        return RequestInput(_parse_json(sys.stdin.read(), "standard input"), "standard input")
    if path.lower().endswith(CSV_SUFFIXES):
        return _load_csv(path)
    if path.lower().endswith(SPREADSHEET_SUFFIXES):
        raise InputError(
            f"{path} is a spreadsheet workbook; save the sheet as CSV (CSV UTF-8 in Excel) "
            "and pass the .csv file"
        )
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from None
    return RequestInput(_parse_json(text, path), path)
