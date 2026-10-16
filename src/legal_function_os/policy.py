"""The policy the rules apply: value bands, queues, service levels and thresholds.

These values used to be constants in ``rules.py``, so making the rules your own
meant editing Python. They now live in a JSON file. ``legal-function-os init``
writes one from a short interview, ``--policy policy.json`` applies it, and the
bundled ``data/default_policy.json`` holds exactly the values the rules shipped
with, so the committed examples do not change.

A policy sets numbers and names. It does not change the shape of the rules: which
signals raise risk, how urgency maps to priority, and the order of the approval
chain stay in code, where the tests pin them. A policy is checked in full before
it is used, and every problem is reported with its place in the file. The format
is published as ``contracts/legal-function-policy.v1.schema.json``.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from legal_function_os.bundled import bundled_path

SCHEMA_ID = "legal-function-os.policy.v1"
SCHEMA_URL = (
    "https://github.com/sebastianfoerste/legal-function-operating-system/blob/main/"
    "contracts/legal-function-policy.v1.schema.json"
)
DEFAULT_POLICY_FILE = "default_policy.json"
PRIORITIES = ("P1_blocker", "P2_high", "P3_standard", "P4_low")
# Keys a policy file may carry besides the ones below: a JSON Schema reference for
# editors, and your own notes.
EXTENSION_PREFIXES = ("x_", "_")


class PolicyError(ValueError):
    """A policy file that cannot be applied. ``problems`` lists every reason."""

    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        noun = "problem" if len(problems) == 1 else "problems"
        super().__init__(f"{source}: {len(problems)} {noun}: " + "; ".join(problems))


@dataclass(frozen=True)
class Threshold:
    """A value band from which a rule applies, and the sentence the decision gives for it."""

    value_band: str
    text: str


@dataclass(frozen=True)
class SlaTarget:
    response_hours: int
    resolution_days: int


@dataclass(frozen=True)
class Policy:
    name: str
    description: str
    value_bands: tuple[str, ...]
    routing: Mapping[str, str]
    unknown_type_queue: str
    non_eea_transfer_queue: str
    sla: Mapping[str, SlaTarget]
    legal_ops_lead_from: str
    general_counsel_from: str
    board_note_from: str
    high_risk_from: Threshold
    medium_risk_from: Threshold
    dispute_high_risk_from: Threshold
    elevated_types: tuple[str, ...]
    dispute_counsel_from: str
    board_awareness_from: Threshold
    dispute_board_attention_from: str
    source: str = field(default="bundled default policy", compare=False)

    def band_index(self, band: str | None) -> int:
        """Position of a value band. A missing band is the lowest; an unknown one is an error."""

        if band is None:
            return 0
        try:
            return self.value_bands.index(band)
        except ValueError:
            raise ValueError(
                f"unknown value_band {band!r}; expected one of {', '.join(self.value_bands)}"
            ) from None

    def reaches(self, band: str | None, threshold: str) -> bool:
        """True when ``band`` is at or above the ``threshold`` band."""

        return self.band_index(band) >= self.value_bands.index(threshold)

    def to_dict(self) -> dict[str, Any]:
        def threshold(value: Threshold, text_key: str) -> dict[str, str]:
            return {"value_band": value.value_band, text_key: value.text}

        return {
            "schema": SCHEMA_ID,
            "name": self.name,
            "description": self.description,
            "value_bands": list(self.value_bands),
            "routing": {
                "by_type": dict(self.routing),
                "unknown_type": self.unknown_type_queue,
                "non_eea_transfer": self.non_eea_transfer_queue,
            },
            "sla": {
                priority: {
                    "response_hours": target.response_hours,
                    "resolution_days": target.resolution_days,
                }
                for priority, target in self.sla.items()
            },
            "approval": {
                "legal_ops_lead_from": self.legal_ops_lead_from,
                "general_counsel_from": self.general_counsel_from,
                "board_note_from": self.board_note_from,
            },
            "risk": {
                "high_from": threshold(self.high_risk_from, "reason"),
                "medium_from": threshold(self.medium_risk_from, "reason"),
                "dispute_high_from": threshold(self.dispute_high_risk_from, "reason"),
                "elevated_types": list(self.elevated_types),
            },
            "external_counsel": {"dispute_from": self.dispute_counsel_from},
            "escalation": {
                "board_awareness_from": threshold(self.board_awareness_from, "message"),
                "dispute_board_attention_from": self.dispute_board_attention_from,
            },
        }

    def queues(self) -> list[str]:
        """Every queue the policy can route to, in first-mention order."""

        names = [*self.routing.values(), self.non_eea_transfer_queue, self.unknown_type_queue]
        return list(dict.fromkeys(names))


# --- Checking ----------------------------------------------------------------

# Allowed keys per object, so a misspelled key is reported instead of ignored.
_KEYS: dict[str, tuple[str, ...]] = {
    "": (
        "$schema",
        "schema",
        "name",
        "description",
        "value_bands",
        "routing",
        "sla",
        "approval",
        "risk",
        "external_counsel",
        "escalation",
    ),
    "routing": ("by_type", "unknown_type", "non_eea_transfer"),
    "approval": ("legal_ops_lead_from", "general_counsel_from", "board_note_from"),
    "risk": ("high_from", "medium_from", "dispute_high_from", "elevated_types"),
    "external_counsel": ("dispute_from",),
    "escalation": ("board_awareness_from", "dispute_board_attention_from"),
    "sla.*": ("response_hours", "resolution_days"),
    "threshold:reason": ("value_band", "reason"),
    "threshold:message": ("value_band", "message"),
}

_OPTIONAL = ("$schema", "description")


class _Checker:
    def __init__(self) -> None:
        self.problems: list[str] = []

    def problem(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}" if where else message)

    def obj(self, data: Any, where: str, keys: str) -> dict[str, Any]:
        if not isinstance(data, dict):
            self.problem(where, f"expected an object, got {_kind(data)}")
            return {}
        allowed = _KEYS[keys]
        for key in data:
            if key in allowed or str(key).startswith(EXTENSION_PREFIXES):
                continue
            close = difflib.get_close_matches(str(key), allowed, n=1, cutoff=0.6)
            hint = f" (did you mean {close[0]!r}?)" if close else ""
            self.problem(_join(where, str(key)), f"unknown key{hint}; prefix your own keys with x_")
        for key in allowed:
            if key not in data and key not in _OPTIONAL:
                self.problem(_join(where, key), "missing")
        return data

    def text(self, data: dict[str, Any], key: str, where: str) -> str:
        value = data.get(key)
        if key not in data:
            return ""
        if not isinstance(value, str) or not value.strip():
            self.problem(_join(where, key), f"expected non-empty text, got {_kind(value)}")
            return ""
        return value

    def band(self, data: dict[str, Any], key: str, where: str, bands: tuple[str, ...]) -> str:
        value = self.text(data, key, where)
        if not bands:
            return ""  # the value_bands problem is reported; nothing to check against
        if value and value not in bands:
            close = difflib.get_close_matches(value, bands, n=1, cutoff=0.6)
            hint = f" (did you mean {close[0]!r}?)" if close else ""
            self.problem(
                _join(where, key),
                f"{value!r} is not one of the value bands{hint}; use one of {', '.join(bands)}",
            )
            return ""
        return value

    def threshold(
        self, data: dict[str, Any], key: str, where: str, bands: tuple[str, ...], text_key: str
    ) -> Threshold:
        if key not in data:
            return Threshold("", "")
        inner = self.obj(data[key], _join(where, key), f"threshold:{text_key}")
        return Threshold(
            self.band(inner, "value_band", _join(where, key), bands),
            self.text(inner, text_key, _join(where, key)),
        )

    def positive_int(self, data: dict[str, Any], key: str, where: str) -> int:
        value = data.get(key)
        if key not in data:
            return 0
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            self.problem(_join(where, key), f"expected a whole number above 0, got {value!r}")
            return 0
        return value

    def order(self, bands: tuple[str, ...], lower: tuple[str, str], upper: tuple[str, str]) -> None:
        """Report ``lower`` set above ``upper``; both are (place, band)."""

        (low_where, low), (high_where, high) = lower, upper
        if low and high and bands.index(low) > bands.index(high):
            self.problem(
                low_where,
                f"{low!r} is above {high_where} ({high!r}); a lower tier cannot start "
                "at a higher value",
            )


def _join(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _kind(value: Any) -> str:
    return {
        bool: "a boolean",
        int: "a number",
        float: "a number",
        str: "text",
        list: "an array",
        dict: "an object",
        type(None): "null",
    }.get(type(value), type(value).__name__)


def parse_policy(data: Any, source: str = "policy") -> Policy:
    """Check a decoded policy file and return it, or raise PolicyError listing every problem."""

    check = _Checker()
    root = check.obj(data, "", "")
    schema = root.get("schema")
    if "schema" in root and schema != SCHEMA_ID:
        check.problem("schema", f"expected {SCHEMA_ID!r}, got {schema!r}")
    name = check.text(root, "name", "")
    description = root.get("description", "")
    if not isinstance(description, str):
        check.problem("description", f"expected text, got {_kind(description)}")
        description = ""

    bands: tuple[str, ...] = ()
    raw_bands = root.get("value_bands")
    if "value_bands" in root:
        if (
            not isinstance(raw_bands, list)
            or len(raw_bands) < 2
            or not all(isinstance(band, str) and band.strip() for band in raw_bands)
        ):
            check.problem("value_bands", "expected at least two non-empty band names, lowest first")
        elif len(set(raw_bands)) != len(raw_bands):
            check.problem("value_bands", "each band name may appear only once")
        else:
            bands = tuple(raw_bands)

    routing_data = check.obj(root.get("routing", {}), "routing", "routing") if "routing" in root else {}
    by_type: dict[str, str] = {}
    raw_routing = routing_data.get("by_type")
    if "by_type" in routing_data:
        if not isinstance(raw_routing, dict) or not raw_routing:
            check.problem("routing.by_type", "expected an object of request type to queue name")
        else:
            for request_type, queue in raw_routing.items():
                if not str(request_type).strip() or not isinstance(queue, str) or not queue.strip():
                    check.problem(
                        f"routing.by_type.{request_type}", "expected a request type and a queue name"
                    )
                else:
                    by_type[str(request_type)] = queue
    unknown_queue = check.text(routing_data, "unknown_type", "routing")
    transfer_queue = check.text(routing_data, "non_eea_transfer", "routing")

    sla: dict[str, SlaTarget] = {}
    if "sla" in root:
        sla_data = root["sla"]
        if not isinstance(sla_data, dict):
            check.problem("sla", f"expected an object, got {_kind(sla_data)}")
        else:
            for priority in sla_data:
                if priority not in PRIORITIES and not str(priority).startswith(EXTENSION_PREFIXES):
                    check.problem(
                        f"sla.{priority}", f"unknown priority; use {', '.join(PRIORITIES)}"
                    )
            for priority in PRIORITIES:
                if priority not in sla_data:
                    check.problem(f"sla.{priority}", "missing")
                    continue
                target = check.obj(sla_data[priority], f"sla.{priority}", "sla.*")
                sla[priority] = SlaTarget(
                    check.positive_int(target, "response_hours", f"sla.{priority}"),
                    check.positive_int(target, "resolution_days", f"sla.{priority}"),
                )

    approval = check.obj(root.get("approval", {}), "approval", "approval") if "approval" in root else {}
    lead = check.band(approval, "legal_ops_lead_from", "approval", bands)
    counsel = check.band(approval, "general_counsel_from", "approval", bands)
    board = check.band(approval, "board_note_from", "approval", bands)
    check.order(bands, ("approval.legal_ops_lead_from", lead), ("approval.general_counsel_from", counsel))
    check.order(bands, ("approval.general_counsel_from", counsel), ("approval.board_note_from", board))

    risk = check.obj(root.get("risk", {}), "risk", "risk") if "risk" in root else {}
    high = check.threshold(risk, "high_from", "risk", bands, "reason")
    medium = check.threshold(risk, "medium_from", "risk", bands, "reason")
    dispute_high = check.threshold(risk, "dispute_high_from", "risk", bands, "reason")
    check.order(bands, ("risk.medium_from", medium.value_band), ("risk.high_from", high.value_band))
    elevated: tuple[str, ...] = ()
    if "elevated_types" in risk:
        raw_elevated = risk["elevated_types"]
        if not isinstance(raw_elevated, list) or not all(isinstance(t, str) for t in raw_elevated):
            check.problem("risk.elevated_types", "expected an array of request types")
        else:
            elevated = tuple(raw_elevated)

    counsel_data = (
        check.obj(root.get("external_counsel", {}), "external_counsel", "external_counsel")
        if "external_counsel" in root
        else {}
    )
    dispute_counsel = check.band(counsel_data, "dispute_from", "external_counsel", bands)

    escalation = (
        check.obj(root.get("escalation", {}), "escalation", "escalation") if "escalation" in root else {}
    )
    awareness = check.threshold(escalation, "board_awareness_from", "escalation", bands, "message")
    dispute_board = check.band(escalation, "dispute_board_attention_from", "escalation", bands)

    if check.problems:
        raise PolicyError(source, check.problems)
    return Policy(
        name=name,
        description=description,
        value_bands=bands,
        routing=by_type,
        unknown_type_queue=unknown_queue,
        non_eea_transfer_queue=transfer_queue,
        sla=sla,
        legal_ops_lead_from=lead,
        general_counsel_from=counsel,
        board_note_from=board,
        high_risk_from=high,
        medium_risk_from=medium,
        dispute_high_risk_from=dispute_high,
        elevated_types=elevated,
        dispute_counsel_from=dispute_counsel,
        board_awareness_from=awareness,
        dispute_board_attention_from=dispute_board,
        source=source,
    )


def load_policy(path: str | None = None) -> Policy:
    """Read and check a policy file; None means the bundled default policy."""

    if path is None:
        return default_policy()
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise PolicyError(path, [f"cannot read the file: {exc.strerror or exc}"]) from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PolicyError(path, [f"not valid JSON: {exc}"]) from None
    return parse_policy(data, path)


@lru_cache(maxsize=1)
def default_policy() -> Policy:
    """The bundled default policy: the values the rules shipped with."""

    path = bundled_path(DEFAULT_POLICY_FILE)
    return parse_policy(json.loads(path.read_text(encoding="utf-8")), "bundled default policy")


def render_policy_json(policy: Policy) -> str:
    """A policy as the JSON file ``init`` writes and ``--policy`` reads."""

    return json.dumps(policy.to_dict(), indent=2, ensure_ascii=False) + "\n"


# --- Published format --------------------------------------------------------


def policy_schema() -> dict[str, Any]:
    """The JSON Schema for a policy file (contracts/legal-function-policy.v1.schema.json).

    The checks the schema cannot express, such as a threshold naming one of the
    file's own value bands or the approval tiers rising in order, are made by
    ``parse_policy`` and described in docs/CUSTOMIZE.md.
    """

    text = {"type": "string", "minLength": 1, "pattern": r"\S"}
    extensions: dict[str, Any] = {"^(x_|_)": {}}

    def strict(properties: dict[str, Any], description: str) -> dict[str, Any]:
        return {
            "type": "object",
            "description": description,
            "required": list(properties),
            "properties": properties,
            "patternProperties": extensions,
            "additionalProperties": False,
        }

    def band(description: str) -> dict[str, Any]:
        return {**text, "description": f"{description} Must be one of value_bands."}

    def threshold(text_key: str, description: str, text_description: str) -> dict[str, Any]:
        return strict(
            {
                "value_band": band("The lowest value band the rule applies to."),
                text_key: {**text, "description": text_description},
            },
            description,
        )

    target = strict(
        {
            "response_hours": {"type": "integer", "minimum": 1, "description": "Business hours to respond."},
            "resolution_days": {"type": "integer", "minimum": 1, "description": "Business days to resolve."},
        },
        "Service level for one priority.",
    )
    root = strict(
        {
            "schema": {"const": SCHEMA_ID, "description": "Format version."},
            "name": {**text, "description": "Whose policy this is, shown when it is applied."},
            "description": {"type": "string", "description": "What the policy is for."},
            "value_bands": {
                "type": "array",
                "minItems": 2,
                "uniqueItems": True,
                "items": text,
                "description": (
                    "Contract or claim value bands, lowest first. A request's value_band "
                    "must be one of these; a request without one is in the first band."
                ),
            },
            "routing": strict(
                {
                    "by_type": {
                        "type": "object",
                        "minProperties": 1,
                        "additionalProperties": text,
                        "description": "Queue that owns each request type.",
                    },
                    "unknown_type": {
                        **text,
                        "description": "Queue for a request whose type is not listed; it is flagged for manual triage.",
                    },
                    "non_eea_transfer": {
                        **text,
                        "description": "Queue for any request with a non-EEA data transfer, whatever its type.",
                    },
                },
                "Which queue owns a request.",
            ),
            "sla": strict(
                {priority: target for priority in PRIORITIES},
                "Response and resolution targets by priority.",
            ),
            "approval": strict(
                {
                    "legal_ops_lead_from": band("Legal Ops Lead signs off from this band."),
                    "general_counsel_from": band(
                        "General Counsel signs off from this band, and on every high-risk request."
                    ),
                    "board_note_from": band("A board note is required from this band."),
                },
                "Approval tiers. Each tier starts at or above the one before it.",
            ),
            "risk": strict(
                {
                    "high_from": threshold("reason", "Value from which a request is high risk.", "Reason given."),
                    "medium_from": threshold(
                        "reason", "Value from which a request is at least medium risk.", "Reason given."
                    ),
                    "dispute_high_from": threshold(
                        "reason", "Value from which a dispute is high risk.", "Reason given."
                    ),
                    "elevated_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Request types that are at least medium risk.",
                    },
                },
                "Value thresholds for risk. Personal data, non-EEA transfers and uncapped liability are fixed rules.",
            ),
            "external_counsel": strict(
                {"dispute_from": band("A dispute goes to external litigation counsel from this band.")},
                "When external counsel is indicated.",
            ),
            "escalation": strict(
                {
                    "board_awareness_from": threshold(
                        "message",
                        "Value from which a request is escalated to the board's awareness list.",
                        "Escalation message.",
                    ),
                    "dispute_board_attention_from": band(
                        "A dispute is flagged for board attention from this band."
                    ),
                },
                "Escalations and board attention.",
            ),
        },
        "",
    )
    root.pop("description")
    root["properties"]["$schema"] = {"type": "string", "description": "Optional schema reference for editors."}
    root["required"] = [key for key in root["required"] if key not in _OPTIONAL]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_URL,
        "title": "Legal function policy (legal-function-os, v1)",
        "description": (
            "The value bands, queues, service levels and thresholds legal-function-os "
            "applies. Write one with legal-function-os init and apply it with --policy. "
            "Keys starting with x_ or _ are yours and are ignored."
        ),
        **root,
    }
