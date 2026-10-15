"""Check legal requests against the published request format before any decision.

The rules read a request as a plain dict, so a mistyped value used to change the
outcome without a word: ``">1M"`` instead of ``">1m"`` was read as "no contract
value", which turned a board-attention matter into a low-risk, reviewer-only one.
Validation runs first and reports every problem at once, naming the request and
the field.

Errors stop the run. Warnings do not: a request type the routing table does not
know still goes to the default queue, and its decision says it needs manual
triage. The format is published as ``contracts/legal-request.v1.schema.json``.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from legal_function_os.rules import ROUTING, URGENCIES, VALUE_BANDS

SCHEMA_ID = "legal-function-os.legal-request.v1"
SCHEMA_URL = (
    "https://github.com/sebastianfoerste/legal-function-operating-system/blob/main/"
    "contracts/legal-request.v1.schema.json"
)

REQUIRED_FIELDS = ("id", "title")
BOOLEAN_FIELDS = ("personal_data", "non_eea_transfer", "uncapped_liability", "sla_breached")
TEXT_FIELDS = ("id", "title", "type", "counterparty", "requested_by")
REQUEST_FIELDS = (
    "id",
    "title",
    "type",
    "counterparty",
    "value_band",
    "personal_data",
    "non_eea_transfer",
    "uncapped_liability",
    "urgency",
    "requested_by",
    "sla_breached",
)
# Optional fields read by the workspace, agent-run and shared-space outputs.
AUXILIARY_FIELDS = (
    "description",
    "summary",
    "facts",
    "deadline",
    "dependencies",
    "awaiting_business_input",
)
# Your own fields pass through untouched. These prefixes also exempt them from the
# check for misspelled field names.
EXTENSION_PREFIXES = ("x_", "_")

Severity = Literal["error", "warning"]

# Spreadsheet-style answers that were meant as a JSON boolean.
_BOOLEAN_WORDS = {
    **dict.fromkeys(("true", "yes", "y", "1", "ja", "x"), "true"),
    **dict.fromkeys(("false", "no", "n", "0", "nein"), "false"),
}


@dataclass(frozen=True)
class Issue:
    severity: Severity
    index: int | None  # 0-based position in the input; None for the input as a whole
    request_id: str | None
    field: str | None
    message: str

    def describe(self, locate: Callable[[int], str] | None = None) -> str:
        where: list[str] = []
        if self.index is not None:
            label = locate(self.index) if locate else f"request {self.index + 1}"
            where.append(f"{label} ({self.request_id})" if self.request_id else label)
        if self.field:
            where.append(self.field)
        prefix = ": ".join(where)
        return f"{self.severity}: {prefix}: {self.message}" if prefix else f"{self.severity}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "index": self.index,
            "request_id": self.request_id,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True)
class ValidationReport:
    request_count: int
    issues: tuple[Issue, ...]

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        errors, warnings = len(self.errors), len(self.warnings)
        noun = "request" if self.request_count == 1 else "requests"
        return (
            f"{errors} error{'s' if errors != 1 else ''}, "
            f"{warnings} warning{'s' if warnings != 1 else ''} "
            f"in {self.request_count} {noun}"
        )

    def lines(self, locate: Callable[[int], str] | None = None) -> list[str]:
        return [issue.describe(locate) for issue in self.issues]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "legal-function-os.validation-report.v1",
            "request_schema": SCHEMA_ID,
            "valid": self.ok,
            "request_count": self.request_count,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _normalise(name: str) -> str:
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name.strip())
    return re.sub(r"[\s\-.]+", "_", name).lower()


def suggest(value: str, choices: Sequence[str]) -> str | None:
    """Return the one choice a mistyped value most likely meant, if any."""

    folded = {choice.lower(): choice for choice in choices}
    if value.lower() in folded:
        return folded[value.lower()]
    normalised = {_normalise(choice): choice for choice in choices}
    if _normalise(value) in normalised:
        return normalised[_normalise(value)]
    close = difflib.get_close_matches(value.lower(), list(folded), n=1, cutoff=0.6)
    return folded[close[0]] if close else None


def _hint(value: str, choices: Sequence[str]) -> str:
    guess = suggest(value, choices)
    return f" (did you mean {guess!r}?)" if guess else ""


def _misspelled_field(key: str) -> str | None:
    if key in REQUEST_FIELDS or key in AUXILIARY_FIELDS or key.startswith(EXTENSION_PREFIXES):
        return None
    normalised = _normalise(key)
    if normalised in REQUEST_FIELDS:
        return normalised
    close = difflib.get_close_matches(normalised, REQUEST_FIELDS, n=1, cutoff=0.85)
    return close[0] if close else None


def _kind(value: Any) -> str:
    return {
        bool: "a boolean",
        int: "a number",
        float: "a number",
        str: "a string",
        list: "an array",
        dict: "an object",
    }.get(type(value), type(value).__name__)


def validate_request(request: Any, index: int | None = None) -> list[Issue]:
    """Return the problems with one request, in field order."""

    if not isinstance(request, dict):
        return [Issue("error", index, None, None, f"expected a JSON object, got {_kind(request)}")]

    raw_id = request.get("id")
    request_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None
    issues: list[Issue] = []

    def add(severity: Severity, field: str | None, message: str) -> None:
        issues.append(Issue(severity, index, request_id, field, message))

    for field in REQUIRED_FIELDS:
        value = request.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            add("error", field, "missing; every request needs one")

    for field in TEXT_FIELDS:
        value = request.get(field)
        if value is not None and not isinstance(value, str):
            add("error", field, f"expected a string, got {_kind(value)}")

    request_type = request.get("type")
    if request_type is None or (isinstance(request_type, str) and not request_type.strip()):
        add("warning", "type", "missing; the request needs manual triage")
    elif isinstance(request_type, str) and request_type not in ROUTING:
        add(
            "warning",
            "type",
            f"{request_type!r} is not a request type in the routing table; the request "
            f"needs manual triage{_hint(request_type, list(ROUTING))}",
        )

    band = request.get("value_band")
    if band is not None:
        if not isinstance(band, str):
            add("error", "value_band", f"expected a string, got {_kind(band)}")
        elif band not in VALUE_BANDS:
            add(
                "error",
                "value_band",
                f"{band!r} is not a value band{_hint(band, VALUE_BANDS)}; "
                f"use one of {', '.join(VALUE_BANDS)}",
            )

    urgency = request.get("urgency")
    if urgency is not None:
        if not isinstance(urgency, str):
            add("error", "urgency", f"expected a string, got {_kind(urgency)}")
        elif urgency not in URGENCIES:
            add(
                "error",
                "urgency",
                f"{urgency!r} is not an urgency{_hint(urgency, URGENCIES)}; "
                f"use one of {', '.join(URGENCIES)}",
            )

    for field in BOOLEAN_FIELDS:
        value = request.get(field)
        if value is not None and not isinstance(value, bool):
            meant = _BOOLEAN_WORDS.get(str(value).strip().lower())
            hint = f" (write {meant}, without quotes)" if meant else ""
            add("error", field, f"expected true or false, got {value!r}{hint}")

    for key in request:
        meant = _misspelled_field(str(key))
        if meant:
            add(
                "error",
                str(key),
                f"unknown field, so its value would be ignored (did you mean {meant!r}?); "
                "prefix your own fields with x_",
            )
    return issues


def validate_requests(requests: Any) -> ValidationReport:
    """Validate a whole input: a JSON array of request objects with unique ids."""

    if not isinstance(requests, list):
        issue = Issue(
            "error", None, None, None, f"the input must be a JSON array of requests, got {_kind(requests)}"
        )
        return ValidationReport(0, (issue,))

    issues: list[Issue] = []
    if not requests:
        issues.append(Issue("warning", None, None, None, "the input contains no requests"))
    first_seen: dict[str, int] = {}
    for index, request in enumerate(requests):
        issues.extend(validate_request(request, index))
        request_id = request.get("id") if isinstance(request, dict) else None
        if isinstance(request_id, str) and request_id.strip():
            if request_id in first_seen:
                issues.append(
                    Issue(
                        "error",
                        index,
                        request_id,
                        "id",
                        f"same id as request {first_seen[request_id] + 1}; ids must be unique",
                    )
                )
            else:
                first_seen[request_id] = index
    return ValidationReport(len(requests), tuple(issues))


def request_schema() -> dict[str, Any]:
    """The published JSON Schema for one request (contracts/legal-request.v1.schema.json)."""

    queues = ", ".join(f"{name} ({queue})" for name, queue in ROUTING.items())
    nullable_flag = {"type": ["boolean", "null"]}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_URL,
        "title": "Legal request (legal-function-os, v1)",
        "description": (
            "One legal request as read by legal-function-os. An input file is a JSON "
            "array of these objects, and each id must be unique within it. Omitted and "
            "null optional fields take their default. Fields not listed here pass "
            "through unchanged; prefix your own fields with x_ so they are never "
            "mistaken for a misspelled request field."
        ),
        "type": "object",
        "required": list(REQUIRED_FIELDS),
        "properties": {
            "id": {
                "type": "string",
                "minLength": 1,
                "pattern": r"\S",
                "description": "Unique request identifier, for example REQ-1001.",
            },
            "title": {
                "type": "string",
                "minLength": 1,
                "pattern": r"\S",
                "description": "Short title shown in the board pack and request register.",
            },
            "type": {
                "type": ["string", "null"],
                "description": (
                    f"Request type, which selects the owning queue: {queues}. A non-EEA "
                    "transfer routes to Privacy whatever the type. Any other value, or "
                    "none, goes to General and is flagged for manual triage."
                ),
                "examples": list(ROUTING),
            },
            "counterparty": {
                "type": ["string", "null"],
                "description": "The other party, for the register. Not used in decisions.",
            },
            "value_band": {
                "enum": [*VALUE_BANDS, None],
                "description": (
                    "Contract or claim value band, lowest first. Matched exactly, so "
                    "'>1m' is valid and '>1M' is rejected. Omitted means 'none'."
                ),
            },
            "personal_data": {
                **nullable_flag,
                "description": "Personal data is processed. Default false.",
            },
            "non_eea_transfer": {
                **nullable_flag,
                "description": "Data is transferred outside the EEA. Default false.",
            },
            "uncapped_liability": {
                **nullable_flag,
                "description": "The counterparty asks for uncapped liability. Default false.",
            },
            "urgency": {
                "enum": [*URGENCIES, None],
                "description": "How soon the requester needs an answer. Omitted means 'standard'.",
            },
            "requested_by": {
                "type": ["string", "null"],
                "description": "Requesting team, for example sales or product.",
            },
            "sla_breached": {
                **nullable_flag,
                "description": "The response SLA has already been missed. Default false.",
            },
        },
        "additionalProperties": True,
    }
