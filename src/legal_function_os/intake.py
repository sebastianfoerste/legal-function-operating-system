"""Read legal requests from a file, standard input or the bundled synthetic set."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from legal_function_os.bundled import bundled_path


class InputError(ValueError):
    """The requests could not be read. The message is meant for the person running the CLI."""


@dataclass
class RequestInput:
    requests: Any
    source: str
    # Human labels for each request, e.g. "row 4" for a CSV line; defaults to "request N".
    labels: list[str] = field(default_factory=list)

    def locate(self, index: int) -> str:
        if index < len(self.labels):
            return self.labels[index]
        return f"request {index + 1}"


def _parse_json(text: str, source: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"{source} is not valid JSON: {exc}") from None


def load_requests(path: str | None) -> RequestInput:
    """Load requests from ``path``; ``-`` reads JSON from standard input, None the bundled set."""

    if path is None:
        source = bundled_path("sample_requests.json")
        return RequestInput(_parse_json(source.read_text(encoding="utf-8"), str(source)), str(source))
    if path == "-":
        return RequestInput(_parse_json(sys.stdin.read(), "standard input"), "standard input")
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror or exc}") from None
    return RequestInput(_parse_json(text, path), path)
