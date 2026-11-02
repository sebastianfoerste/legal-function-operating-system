"""A static page that helps a business requester prepare a legal request file.

The page asks the request fields of ``validation.request_schema()``, offers the value
bands and request types of the policy, and asks a few more questions for the chosen
request type from a question file (``data/intake_questions.json`` by default). It
checks the answers, shows the exact file, and saves it on the requester's device as
``legal-request.v1`` JSON, which ``legal-function-os validate`` and ``triage`` read.

Nothing is sent. The page has no form and no network or navigation code, and its
Content-Security-Policy blocks every fetch, form post, frame and resource load and any
injected script, so a local download is its only output. It decides nothing: no risk, priority, queue or approval chain is shown, and a
person in legal reviews every file. A question may depend only on an answer given
above it (forward-only conditions), which ``build_intake_form`` checks when the page is
built, so a requester never has to go back up the page.

The page script and this module implement the same rules: ``clean_text``,
``evaluate``, ``check_answers``, ``request_from_answers``, ``review_rows``,
``render_download`` and ``download_name``. A test runs the script in Node on every
answer the page can accept and compares the results with this module. Deterministic:
nothing reads a clock.
"""

from __future__ import annotations

import base64
import difflib
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from legal_function_os.bundled import bundled_path
from legal_function_os.design_tokens import TOKENS_CSS
from legal_function_os.policy import Policy, default_policy
from legal_function_os.rules import URGENCIES
from legal_function_os.validation import EXTENSION_PREFIXES, request_schema

SCHEMA = "legal-function-os.intake-page.v1"
QUESTIONS_SCHEMA = "legal-function-os.intake-questions.v1"
QUESTIONS_FILE = "intake_questions.json"
BUNDLED_SOURCE = "bundled intake questions"
PAGE_FILE = "intake-page.html"
# The page cannot number a request: legal gives it a register number.
DRAFT_ID = "REQ-DRAFT"

# How each request field reaches the file. A test checks that these, with id and facts,
# cover request_schema() exactly, so a new contract field has to be placed on purpose.
ALWAYS_ASKED = (
    "title",
    "type",
    "value_band",
    "personal_data",
    "non_eea_transfer",
    "uncapped_liability",
    "urgency",
)
# Asked when the question file words them; a type can make them required.
OPTIONAL_FIELDS = ("counterparty", "requested_by", "description", "deadline")
# Legal's own state, never asked of a requester.
NOT_ASKED = ("sla_breached", "awaiting_business_input", "summary", "dependencies")
# id is DRAFT_ID; facts holds the answers to the type questions.
SET_BY_PAGE = ("id", "facts")
# Request fields a type question may depend on. They are asked above every type question.
CONTROLLERS = ("value_band", "personal_data", "non_eea_transfer", "uncapped_liability", "urgency")
KINDS = ("text", "textarea", "yes_no", "choice")
QUESTION_KEY = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
MAX_OPTIONS = 20
NOT_GIVEN = "Not given"
YES_NO = ({"label": "Yes", "value": True}, {"label": "No", "value": False})
# Python's str.isspace() set plus U+FEFF. Validation calls value.strip(), which removes
# the isspace() set, and JavaScript's trim() removes a different set, so the page and
# this module trim with this one set: what the page keeps is never blank to validation.
WHITESPACE = (
    "\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_SURROGATE = re.compile("[\ud800-\udfff]")
_SLUG = re.compile("[^A-Za-z0-9]+")

_TOP_KEYS = ("schema", "name", "description", "fields", "types")
# A key that is not in the file at all, which check.obj already reports as missing; a
# key that is there with the value null is a wrong type like any other.
_ABSENT = object()
_FIELD_KEYS = ("label", "hint", "error")
_TYPE_KEYS = ("label", "hint", "also_required", "questions")
_QUESTION_KEYS = ("key", "label", "hint", "error", "kind", "options", "required", "show_if")


class IntakeQuestionsError(ValueError):
    """A question file that cannot be used; ``problems`` lists every reason."""

    def __init__(self, source: str, problems: list[str]) -> None:
        super().__init__(f"{source}: " + "; ".join(problems))
        self.source = source
        self.problems = problems


def clean_text(value: Any) -> str:
    """An answer as the page saves it: an unpaired surrogate becomes U+FFFD and the
    WHITESPACE set is trimmed from both ends."""

    text = value if isinstance(value, str) else ""
    return _SURROGATE.sub("\ufffd", text).strip(WHITESPACE)


def load_intake_questions(path: str | None = None) -> tuple[Any, str]:
    """The question file at ``path`` (the bundled one without), and its name for messages."""

    source = BUNDLED_SOURCE if path is None else path
    try:
        file = bundled_path(QUESTIONS_FILE) if path is None else Path(path)
        text = file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise IntakeQuestionsError(source, [f"cannot read the file: {exc.strerror or exc}"]) from None
    try:
        return json.loads(text), source
    except json.JSONDecodeError as exc:
        raise IntakeQuestionsError(source, [f"not valid JSON: {exc}"]) from None


def _join(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "a boolean"
    if value is None:
        return "null"
    return {str: "text", int: "a number", float: "a number", list: "a list", dict: "an object"}.get(
        type(value), type(value).__name__
    )


def _hint(value: str, choices: tuple[str, ...] | list[str]) -> str:
    close = difflib.get_close_matches(value, list(choices), n=1, cutoff=0.6)
    return f" (did you mean {close[0]!r}?)" if close else ""


class _Check:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []

    def problem(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}" if where else message)

    def obj(self, data: Any, where: str, allowed: tuple[str, ...], required: tuple[str, ...]) -> dict:
        if not isinstance(data, dict):
            self.problem(where, f"expected an object, got {_kind(data)}")
            return {}
        for key in data:
            if key in allowed or str(key).startswith(EXTENSION_PREFIXES):
                continue
            if key == "show_if":
                self.problem(
                    _join(where, key),
                    "only a type question can have a condition; a request field is always asked",
                )
                continue
            self.problem(
                _join(where, str(key)),
                f"unknown key{_hint(str(key), allowed)}; prefix your own keys with x_",
            )
        for key in required:
            if key not in data:
                self.problem(_join(where, key), "missing")
        return data

    def plain(self, value: Any, place: str) -> str:
        """Text the page shows: not blank, no unpaired surrogate, no link."""

        if not isinstance(value, str) or not clean_text(value):
            self.problem(place, f"expected non-empty text, got {_kind(value)}")
            return ""
        if _SURROGATE.search(value):
            self.problem(place, "contains an unpaired surrogate; the page could not save it")
            return ""
        if "http://" in value.lower() or "https://" in value.lower():
            self.problem(place, "must not contain a link (http:// or https://); the page is self-contained")
            return ""
        return value

    def text(self, data: dict, key: str, where: str) -> str:
        return self.plain(data[key], _join(where, key)) if key in data else ""

    def flag(self, data: dict, key: str, where: str, default: bool) -> bool:
        if key not in data:
            return default
        if not isinstance(data[key], bool):
            self.problem(_join(where, key), f"expected true or false, got {_kind(data[key])}")
            return default
        return bool(data[key])


def _schema_control(name: str, prop: dict[str, Any]) -> str:
    """The control the contract's JSON type gives a field. A contract change that
    breaks this mapping stops the build instead of producing a wrong page."""

    kinds = prop.get("type")
    if name == "type" and kinds == ["string", "null"]:
        return "radio"
    if "enum" in prop or kinds == ["boolean", "null"]:
        return "radio"
    if kinds in ("string", ["string", "null"]):
        return "textarea" if name == "description" else "text"
    raise RuntimeError(f"the request contract changed: no page control for {name} ({prop})")


def _default_error(label: str, control: str) -> str:
    return f"{'Choose' if control == 'radio' else 'Enter'} an answer to: {label}"


def _field_entries(check: _Check, raw: Any, properties: dict[str, Any]) -> dict[str, dict]:
    if not isinstance(raw, dict):
        if raw is not _ABSENT:
            check.problem("fields", f"expected an object, got {_kind(raw)}")
        return {}
    askable = (*ALWAYS_ASKED, *OPTIONAL_FIELDS)
    entries = {}
    for name, entry in raw.items():
        where = _join("fields", str(name))
        if str(name).startswith(EXTENSION_PREFIXES):
            continue
        if name == "id":
            check.problem(where, f"the page sets id to {DRAFT_ID}; legal gives the register number")
        elif name == "facts":
            check.problem(where, "facts are filled from the type questions; ask them under types")
        elif name in NOT_ASKED:
            check.problem(where, "legal's own field; the page never asks it")
        elif name not in askable:
            check.problem(where, f"not a request field the page asks{_hint(str(name), askable)}")
        else:
            entries[name] = entry
    for name in ALWAYS_ASKED:
        if name not in raw:
            check.problem(_join("fields", name), "missing; the page always asks it")
    for name in properties:
        if name in OPTIONAL_FIELDS and name not in raw:
            check.notes.append(f"the question file does not word {name}, so the page does not ask it")
    return entries


def _option_labels(
    check: _Check, entry: dict, where: str, values: tuple[str, ...], exact: bool
) -> dict[str, str]:
    if "options" not in entry:
        return {}
    raw = entry["options"]
    place = _join(where, "options")
    if not isinstance(raw, dict):
        check.problem(place, f"expected an object of value to label, got {_kind(raw)}")
        return {}
    labels = {}
    for value in raw:
        if value not in values:
            if str(value).startswith(EXTENSION_PREFIXES):
                continue
            if exact:
                check.problem(
                    _join(place, str(value)),
                    f"not one of {', '.join(values)}{_hint(str(value), values)}",
                )
            else:
                check.notes.append(f"{place}.{value}: the policy has no value band {value!r}; label ignored")
            continue
        text = check.text(raw, value, place)
        if text:
            labels[value] = text
    if exact:
        for value in values:
            if value not in raw:
                check.problem(_join(place, value), "missing; label every urgency")
    return labels


def _fields(
    check: _Check, entries: dict[str, dict], properties: dict[str, Any], policy: Policy
) -> list[dict[str, Any]]:
    fields = []
    for name, prop in properties.items():
        if name not in entries:
            continue
        where = _join("fields", name)
        allowed = list(_FIELD_KEYS)
        if name in OPTIONAL_FIELDS:
            allowed.append("required")
        if name in ("value_band", "urgency"):
            allowed.append("options")
        if name == "type":
            allowed.append("not_sure")
        required = ("label", "not_sure") if name == "type" else ("label",)
        entry = check.obj(entries[name], where, tuple(allowed), required)
        control = _schema_control(name, prop)
        label = check.text(entry, "label", where)
        item: dict[str, Any] = {
            "name": name,
            "id": f"f-{name}",
            "label": label,
            "hint": check.text(entry, "hint", where),
            "error": check.text(entry, "error", where) or _default_error(label, control),
            "control": control,
            "required": name in ALWAYS_ASKED or check.flag(entry, "required", where, False),
        }
        if name == "type":
            item["not_sure"] = check.text(entry, "not_sure", where)
        elif name == "value_band":
            labels = _option_labels(check, entry, where, policy.value_bands, exact=False)
            item["options"] = [{"label": labels.get(b, b), "value": b} for b in policy.value_bands]
        elif name == "urgency":
            labels = _option_labels(check, entry, where, URGENCIES, exact=True)
            item["options"] = [{"label": labels.get(u, u), "value": u} for u in URGENCIES]
        elif control == "radio":
            item["options"] = [dict(option) for option in YES_NO]
        fields.append(item)
    return fields


def _condition(
    check: _Check,
    raw: Any,
    where: str,
    key: str,
    questions: list[Any],
    index: int,
    domains: dict[str, list[Any] | None],
    fields: dict[str, dict],
) -> dict[str, Any] | None:
    cond = check.obj(raw, where, ("field", "in"), ("field", "in"))
    if not cond:
        return None
    name = cond.get("field")
    place = _join(where, "field")
    rule = "a condition can only name an answer given above it"
    if not isinstance(name, str):
        check.problem(place, f"expected the name of an earlier answer, got {_kind(name)}")
        return None
    later = [j for j, q in enumerate(questions) if isinstance(q, dict) and q.get("key") == name]
    if name == key:
        check.problem(place, f"names its own question; {rule}")
        return None
    if name == "type":
        check.problem(place, '"type" cannot be a condition; put the question under types.<type> instead')
        return None
    if name not in domains:
        if name in fields or any(q.get("key") == name for q in questions[:index] if isinstance(q, dict)):
            check.problem(place, f'"{name}" is free text and cannot control a question; use yes_no or choice')
        elif later and later[0] > index:
            check.problem(place, f'"{name}" is asked later (questions[{later[0]}]); {rule} (forward-only)')
        else:
            check.problem(place, f'"{name}" is not asked before this question{_hint(name, list(domains))}')
        return None
    values = cond.get("in")
    place = _join(where, "in")
    if not isinstance(values, list) or not values:
        check.problem(place, f"expected a non-empty list of answers, got {_kind(values)}")
        return None
    domain = domains[name]
    if domain is None:
        return None
    kept: list[Any] = []
    for i, value in enumerate(values):
        if any(value is v or (type(value) is type(v) and value == v) for v in kept):
            check.problem(f"{place}[{i}]", f"{value!r} is listed twice")
        elif not any(type(value) is type(v) and value == v for v in domain):
            shown = ", ".join(json.dumps(v, ensure_ascii=False) for v in domain)
            check.problem(
                f"{place}[{i}]",
                f"{json.dumps(value, ensure_ascii=False)} is not an answer to {name!r}; use one of {shown}",
            )
        else:
            kept.append(value)
    return {"field": name, "in": kept} if len(kept) == len(values) else None


def _question(
    check: _Check,
    raw: Any,
    where: str,
    type_index: int,
    questions: list[Any],
    index: int,
    seen: set[str],
    domains: dict[str, list[Any] | None],
    fields: dict[str, dict],
    properties: dict[str, Any],
) -> dict[str, Any] | None:
    entry = check.obj(raw, where, _QUESTION_KEYS, ("key", "label", "kind"))
    if not entry:
        return None
    key = entry.get("key")
    ok = True
    if not isinstance(key, str) or not QUESTION_KEY.match(key):
        check.problem(
            _join(where, "key"),
            "expected lower-case letters, digits and _, starting with a letter, up to 40 characters",
        )
        key, ok = "", False
    elif key in properties:
        check.problem(_join(where, "key"), f'"{key}" is a request field; choose another key')
        ok = False
    elif key in seen:
        check.problem(_join(where, "key"), f'"{key}" is used twice in this type')
        ok = False
    kind = entry.get("kind")
    if "kind" in entry and kind not in KINDS:
        check.problem(_join(where, "kind"), f"expected one of {', '.join(KINDS)}, got {kind!r}")
    if kind not in KINDS:
        ok = False
    label = check.text(entry, "label", where)
    options: list[dict[str, Any]] = []
    if kind == "choice":
        raw_options = entry.get("options")
        if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= MAX_OPTIONS:
            check.problem(
                _join(where, "options"), f"expected a list of 2 to {MAX_OPTIONS} answers, got {_kind(raw_options)}"
            )
            ok = False
        else:
            for i, option in enumerate(raw_options):
                place = f"{_join(where, 'options')}[{i}]"
                text = check.plain(option, place)
                if not text:
                    ok = False
                elif clean_text(text) != text:
                    check.problem(place, "has spaces at the start or end")
                    ok = False
                elif any(o["value"] == text for o in options):
                    check.problem(place, f"{text!r} is listed twice")
                    ok = False
                else:
                    options.append({"label": text, "value": text})
    elif "options" in entry and kind in KINDS:
        check.problem(_join(where, "options"), "only a choice question has options")
        ok = False
    if kind == "yes_no":
        options = [dict(option) for option in YES_NO]
    control = "radio" if kind in ("yes_no", "choice") else str(kind)
    # A later question can depend on this one only if its answers are a closed set. The
    # set is known even when this question has another problem, so that problem is
    # reported once, not again at every question that depends on it.
    if key and key not in domains and kind not in ("text", "textarea"):
        complete = kind == "yes_no" or (
            kind == "choice" and isinstance(entry.get("options"), list) and len(options) == len(entry["options"])
        )
        # None: a question with choices whose own kind or options are wrong. A condition
        # naming it adds no second problem; the build fails at the question itself.
        domains[key] = [o["value"] for o in options] if complete and options else None
    cond = None
    if "show_if" in entry:
        cond = _condition(check, entry["show_if"], _join(where, "show_if"), str(key), questions, index, domains, fields)
        ok = ok and cond is not None
    if key:
        seen.add(key)
    if not ok or not label:
        return None
    item: dict[str, Any] = {
        "name": key,
        "id": f"q{type_index}-{key}",
        "label": label,
        "hint": check.text(entry, "hint", where),
        "error": check.text(entry, "error", where) or _default_error(label, control),
        "kind": kind,
        "control": control,
        "required": check.flag(entry, "required", where, True),
    }
    if options:
        item["options"] = options
    if cond:
        item["show_if"] = cond
    return item


def _types(
    check: _Check, raw: Any, policy: Policy, fields: list[dict[str, Any]], properties: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        if raw is not _ABSENT:
            check.problem("types", f"expected an object, got {_kind(raw)}")
        return []
    by_name = {f["name"]: f for f in fields}
    base_domains: dict[str, list[Any] | None] = {
        f["name"]: [o["value"] for o in f["options"]] for f in fields if f["name"] in CONTROLLERS
    }
    resolved: dict[str, dict[str, Any]] = {}
    for type_key, entry in raw.items():
        if str(type_key).startswith(EXTENSION_PREFIXES):
            continue
        where = _join("types", str(type_key))
        index = list(policy.routing).index(type_key) if type_key in policy.routing else -1
        body = check.obj(entry, where, _TYPE_KEYS, ("label", "questions"))
        label = check.text(body, "label", where)
        also: list[str] = []
        raw_also = body.get("also_required", [])
        if not isinstance(raw_also, list):
            check.problem(_join(where, "also_required"), f"expected a list of fields, got {_kind(raw_also)}")
        else:
            for i, name in enumerate(raw_also):
                place = f"{_join(where, 'also_required')}[{i}]"
                if name not in OPTIONAL_FIELDS:
                    check.problem(place, f"expected one of {', '.join(OPTIONAL_FIELDS)}, got {name!r}")
                elif name not in by_name:
                    check.problem(place, f'"{name}" is not asked: word it under fields first')
                elif name in also:
                    check.problem(place, f'"{name}" is listed twice')
                else:
                    also.append(name)
        raw_questions = body.get("questions", [])
        questions: list[dict[str, Any]] = []
        if not isinstance(raw_questions, list):
            check.problem(_join(where, "questions"), f"expected a list of questions, got {_kind(raw_questions)}")
        else:
            domains = dict(base_domains)
            seen: set[str] = set()
            for i, question in enumerate(raw_questions):
                item = _question(
                    check, question, f"{_join(where, 'questions')}[{i}]", max(index, 0),
                    raw_questions, i, seen, domains, by_name, properties,
                )
                if item:
                    questions.append(item)
        if index < 0:
            check.notes.append(
                f'intake questions for "{type_key}" are not used: the policy has no request type "{type_key}"'
            )
            continue
        resolved[str(type_key)] = {
            "key": type_key,
            "id": f"type-{index}",
            "label": label,
            "hint": check.text(body, "hint", where),
            "also_required": also,
            "questions": questions,
        }
    types = []
    for index, type_key in enumerate(policy.routing):
        if type_key not in resolved:
            check.notes.append(
                f'request type "{type_key}" has no intake questions; the page offers it as "{type_key}"'
            )
            resolved[type_key] = {
                "key": type_key, "id": f"type-{index}", "label": type_key, "hint": "",
                "also_required": [], "questions": [],
            }
        types.append(resolved[type_key])
    return types


def _check_policy(check: _Check, policy: Policy) -> None:
    """The policy text the page shows or saves: its name, value bands and request types.
    parse_policy accepts any text there, but the page carries no link, and a file with
    an unpaired surrogate could not be saved."""

    named = [("policy name", policy.name)]
    named += [("policy value band", band) for band in policy.value_bands]
    named += [("policy request type", key) for key in policy.routing]
    for what, value in named:
        place = f"{what} {ascii(value)}"
        if _SURROGATE.search(value):
            check.problem(place, "contains an unpaired surrogate; the page could not save it")
        elif "http://" in value.lower() or "https://" in value.lower():
            check.problem(place, "must not contain a link (http:// or https://); the page is self-contained")


def build_intake_form(
    questions: Any, policy: Policy | None = None, source: str = BUNDLED_SOURCE
) -> dict[str, Any]:
    """Check a question file against the contract and ``policy`` (the bundled default
    without one) and return the resolved form the page is built from."""

    rules = policy if policy is not None else default_policy()
    properties = request_schema()["properties"]
    check = _Check()
    top = check.obj(questions, "", _TOP_KEYS, ("schema", "name", "fields", "types"))
    if "schema" in top and top["schema"] != QUESTIONS_SCHEMA:
        check.problem("schema", f"expected {QUESTIONS_SCHEMA!r}, got {top['schema']!r}")
    name = check.text(top, "name", "")
    _check_policy(check, rules)
    entries = _field_entries(check, top.get("fields", _ABSENT), properties)
    fields = _fields(check, entries, properties, rules)
    types = _types(check, top.get("types", _ABSENT), rules, fields, properties)
    for item in fields:
        if item["name"] == "type":
            item["options"] = [{"label": t["label"], "value": t["key"]} for t in types]
            item["options"].append({"label": item.pop("not_sure"), "value": None})
    # Two answers with one label would look alike on the page and in the review.
    for item in fields:
        seen: dict[str, Any] = {}
        for option in item.get("options", []):
            label = option["label"]
            if label and label in seen:
                check.problem(
                    _join("fields", item["name"]),
                    f"{label!r} labels both {seen[label]!r} and {option['value']!r}; give each answer its own label",
                )
            seen.setdefault(label, option["value"])
    if check.problems:
        raise IntakeQuestionsError(source, check.problems)
    return {
        "schema": SCHEMA,
        "policy": rules.name,
        "questions": name,
        "draft_id": DRAFT_ID,
        "not_given": NOT_GIVEN,
        "order": list(properties),
        "fields": fields,
        "types": types,
        "notes": check.notes,
    }


# --- The rules the page script also implements --------------------------------------


def _value(item: dict[str, Any], raw: Any) -> tuple[bool, Any]:
    """Whether an answer is given, and its value. A radio answer is the option index
    as text, as the page reads it; anything else is no answer."""

    if item["control"] == "radio":
        for i, option in enumerate(item["options"]):
            if raw == str(i):
                return True, option["value"]
        return False, None
    text = clean_text(raw)
    return text != "", text


def evaluate(form: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """The chosen type, which of its questions show, and every answer given.

    ``answers`` is ``{"fields": {name: text}, "questions": {key: text}}``, the second
    for the chosen type only. A question shows when it has no condition, or when the
    answer it names is given, shown and listed in the condition; so a question that
    depends on a hidden one is hidden too.
    """

    given_fields = answers.get("fields") or {}
    given_questions = answers.get("questions") or {}
    values: dict[str, Any] = {}
    for item in form["fields"]:
        ok, value = _value(item, given_fields.get(item["name"], ""))
        if ok:
            values[item["name"]] = value
    chosen = None
    if values.get("type") is not None:
        chosen = next(i for i, t in enumerate(form["types"]) if t["key"] == values["type"])
    visible = []
    if chosen is not None:
        for question in form["types"][chosen]["questions"]:
            cond = question.get("show_if")
            shown = cond is None or (
                cond["field"] in values
                and any(type(values[cond["field"]]) is type(v) and values[cond["field"]] == v for v in cond["in"])
            )
            visible.append(shown)
            if shown:
                ok, value = _value(question, given_questions.get(question["name"], ""))
                if ok:
                    values[question["name"]] = value
    return {"type": chosen, "visible": visible, "values": values}


def required_fields(form: dict[str, Any], state: dict[str, Any]) -> dict[str, bool]:
    """Which request fields must be answered, given the chosen type."""

    chosen = state["type"]
    also = form["types"][chosen]["also_required"] if chosen is not None else []
    return {item["name"]: item["required"] or item["name"] in also for item in form["fields"]}


def check_answers(form: dict[str, Any], answers: dict[str, Any]) -> list[dict[str, str]]:
    """Every required answer that is missing, in page order, with its message."""

    state = evaluate(form, answers)
    required = required_fields(form, state)
    problems = [
        {"id": item["id"], "message": item["error"]}
        for item in form["fields"]
        if required[item["name"]] and item["name"] not in state["values"]
    ]
    if state["type"] is not None:
        for question, shown in zip(form["types"][state["type"]]["questions"], state["visible"], strict=True):
            if shown and question["required"] and question["name"] not in state["values"]:
                problems.append({"id": question["id"], "message": question["error"]})
    return problems


def _fact_text(question: dict[str, Any], value: Any) -> str:
    if question["kind"] == "yes_no":
        return "yes" if value else "no"
    return str(value)


def request_from_answers(form: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
    """The legal-request.v1 object the page saves, keys in contract order.

    An answer that is not given is left out, never null or "". The answers to the
    type questions become ``facts`` as "key: value", sorted by key as the pilot's
    bridge writes them (``sorted(intake.facts.items())``).
    """

    state = evaluate(form, answers)
    values = state["values"]
    pairs = []
    if state["type"] is not None:
        for question, shown in zip(form["types"][state["type"]]["questions"], state["visible"], strict=True):
            if shown and question["name"] in values:
                pairs.append((question["name"], _fact_text(question, values[question["name"]])))
    facts = [f"{key}: {text}" for key, text in sorted(pairs)]
    fields = {item["name"] for item in form["fields"]}
    request: dict[str, Any] = {}
    for name in form["order"]:
        if name == "id":
            request["id"] = form["draft_id"]
        elif name == "facts":
            if facts:
                request["facts"] = facts
        elif name in fields and values.get(name) is not None:
            request[name] = values[name]
    return request


def _answer_text(item: dict[str, Any], values: dict[str, Any], not_given: str) -> str:
    if item["name"] not in values:
        return not_given
    value = values[item["name"]]
    if item["control"] == "radio":
        for option in item["options"]:
            if type(option["value"]) is type(value) and option["value"] == value:
                return str(option["label"])
        return not_given
    return str(value)


def review_rows(form: dict[str, Any], answers: dict[str, Any]) -> list[dict[str, str]]:
    """The "Check your answers" list: every question asked, in page order."""

    state = evaluate(form, answers)
    values = state["values"]
    rows = [
        {"id": item["id"], "label": item["label"], "answer": _answer_text(item, values, form["not_given"])}
        for item in form["fields"]
    ]
    if state["type"] is not None:
        for question, shown in zip(form["types"][state["type"]]["questions"], state["visible"], strict=True):
            if shown:
                rows.append(
                    {
                        "id": question["id"],
                        "label": question["label"],
                        "answer": _answer_text(question, values, form["not_given"]),
                    }
                )
    return rows


def render_download(request: dict[str, Any]) -> str:
    """The file's exact text: a JSON array of one request, as the page writes it."""

    return json.dumps([request], indent=2, ensure_ascii=False) + "\n"


def download_name(request: dict[str, Any]) -> str:
    """legal-request-<title in ASCII letters and digits>.json, or legal-request.json."""

    slug = _SLUG.sub("-", str(request.get("title", ""))).strip("-").lower()[:50].strip("-")
    return f"legal-request-{slug}.json" if slug else "legal-request.json"


# --- Outputs ------------------------------------------------------------------------


def _md_line(value: Any) -> str:
    return " ".join(str(value).split())


def _need(item: dict[str, Any]) -> str:
    return "required" if item["required"] else "optional"


def _option_list(item: dict[str, Any]) -> str:
    return "; ".join(_md_line(o["label"]) for o in item["options"])


def _condition_words(form_type: dict[str, Any], fields: list[dict[str, Any]], cond: dict[str, Any]) -> str:
    by_name = {f["name"]: f for f in fields} | {q["name"]: q for q in form_type["questions"]}
    controller = by_name[cond["field"]]
    labels = [
        str(o["label"])
        for o in controller["options"]
        if any(type(o["value"]) is type(v) and o["value"] == v for v in cond["in"])
    ]
    return f'Shown when "{_md_line(controller["label"])}" is {" or ".join(_md_line(x) for x in labels)}.'


def render_intake_markdown(form: dict[str, Any]) -> str:
    """The question sheet: what the page asks, for legal ops to review."""

    lines = [
        "# Intake questions",
        "",
        f"Questions: {_md_line(form['questions'])}. Value bands and request types follow the "
        f"policy: {_md_line(form['policy'])}.",
        "",
        "The intake page saves a legal-request.v1 file on the requester's device. It sends "
        f"nothing and decides nothing. Every file gets the reference {form['draft_id']}; legal "
        "gives it a register number.",
        "",
        "## About the request",
        "",
    ]
    for item in form["fields"]:
        line = f"- **{_md_line(item['label'])}** (`{item['name']}`), {_need(item)}."
        if item["control"] == "radio":
            line += f" Choices: {_option_list(item)}."
        if item["hint"]:
            line += f" Hint: {_md_line(item['hint'])}"
        lines.append(line)
    for form_type in form["types"]:
        lines += ["", f"## {_md_line(form_type['label'])} (`{form_type['key']}`)", ""]
        if form_type["also_required"]:
            names = {f["name"]: f["label"] for f in form["fields"]}
            also = ", ".join(_md_line(names[n]) for n in form_type["also_required"])
            lines += [f"Also required for this type: {also}.", ""]
        if not form_type["questions"]:
            lines.append("No further questions.")
        for number, question in enumerate(form_type["questions"], 1):
            line = (
                f"{number}. **{_md_line(question['label'])}** (`{question['name']}`, "
                f"{question['kind']}), {_need(question)}."
            )
            if question["kind"] == "choice":
                line += f" Choices: {_option_list(question)}."
            if "show_if" in question:
                line += " " + _condition_words(form_type, form["fields"], question["show_if"])
            lines.append(line)
    if form["notes"]:
        lines += ["", "## Notes", ""]
        lines += [f"- {_md_line(note)}" for note in form["notes"]]
    return "\n".join(lines) + "\n"


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _described(item: dict[str, Any]) -> str:
    return f' aria-describedby="{item["id"]}-hint"' if item["hint"] else ""


def _parts(item: dict[str, Any], optional_mark: str) -> tuple[str, str, str]:
    """The label text, hint and error markup shared by every control (GOV.UK order)."""

    label = _esc(item["label"]) + optional_mark
    hint = f'<p class="hint" id="{item["id"]}-hint">{_esc(item["hint"])}</p>' if item["hint"] else ""
    error = (
        f'<p class="field-error" id="{item["id"]}-error" hidden><span class="visually-hidden">Error: '
        f'</span><span id="{item["id"]}-error-text"></span></p>'
    )
    return label, hint, error


def _control_html(item: dict[str, Any], optional_mark: str, hidden: bool = False) -> str:
    i = item["id"]
    label, hint, error = _parts(item, optional_mark)
    wrapper = f'<div class="field" id="{i}-field"{" hidden" if hidden else ""}>'
    if item["control"] == "radio":
        options = "".join(
            f'<div class="option"><input type="radio" id="{i}-{n}" name="{i}" value="{n}">'
            f'<label for="{i}-{n}">{_esc(o["label"])}</label></div>'
            for n, o in enumerate(item["options"])
        )
        return (
            f'{wrapper}<fieldset id="{i}"{_described(item)}><legend>{label}</legend>{hint}{error}'
            f'<div class="options">{options}</div></fieldset></div>'
        )
    if item["control"] == "textarea":
        control = f'<textarea id="{i}" rows="5"{_described(item)}></textarea>'
    else:
        control = f'<input type="text" id="{i}"{_described(item)}>'
    return f'{wrapper}<label for="{i}">{label}</label>{hint}{error}{control}</div>'


def _field_html(item: dict[str, Any]) -> str:
    mark = "" if item["required"] else f' <span class="optional" id="{item["id"]}-optional">(optional)</span>'
    return _control_html(item, mark)


def _type_html(form_type: dict[str, Any]) -> str:
    questions = "".join(
        _control_html(q, "" if q["required"] else ' <span class="optional">(optional)</span>', "show_if" in q)
        for q in form_type["questions"]
    ) or '<p class="muted">No further questions for this type.</p>'
    hint = f'<p class="hint">{_esc(form_type["hint"])}</p>' if form_type["hint"] else ""
    return (
        f'<section class="type" id="{form_type["id"]}" aria-labelledby="{form_type["id"]}-h" hidden>'
        f'<h2 id="{form_type["id"]}-h">{_esc(form_type["label"])}: a few more questions</h2>'
        f"{hint}{questions}</section>"
    )


def _spec_json(form: dict[str, Any]) -> str:
    """The form as a JSON data block that cannot end its own script element."""

    text = json.dumps(form, ensure_ascii=True, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _sha256(text: str) -> str:
    return "sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


def _js_whitespace() -> str:
    return "".join(f"\\u{ord(c):04x}" for c in WHITESPACE)


def page_script() -> str:
    """The page's one script, exactly as the page carries it."""

    return _SCRIPT.replace("__WS__", _js_whitespace())


def page_style() -> str:
    return TOKENS_CSS + _STYLE


def render_intake_html(form: dict[str, Any]) -> str:
    """The self-contained intake page. Its CSP allows only its own script and style."""

    script, style = page_script(), page_style()
    csp = (
        f"default-src 'none'; script-src '{_sha256(script)}'; style-src '{_sha256(style)}'; "
        "img-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'"
    )
    slots = {
        "CSP": csp,
        "STYLE": style,
        "FIELDS": "".join(_field_html(item) for item in form["fields"]),
        "TYPES": "".join(_type_html(t) for t in form["types"]),
        "DRAFT": _esc(form["draft_id"]),
        "POLICY": _esc(form["policy"]),
        "QUESTIONS": _esc(form["questions"]),
        "SPEC": _spec_json(form),
        "SCRIPT": script,
    }
    # One pass, so text inserted into one slot is never read as another slot's name.
    page = re.sub(r"__([A-Z]+)__", lambda m: slots[m.group(1)], _PAGE)
    lowered = page.lower()
    if "http://" in lowered or "https://" in lowered:
        raise ValueError("the intake page would load or link something from the network")
    return page


def write_intake_page(form: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    # Rendered and encoded first, so a page that cannot be built leaves nothing behind.
    data = render_intake_html(form).encode("utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / PAGE_FILE
    path.write_bytes(data)
    return {"html": path}


_STYLE = """* { box-sizing:border-box; }
[hidden] { display:none !important; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 var(--font); }
main { max-width:760px; margin:0 auto; padding:40px 20px 64px; }
h1 { margin:0 0 12px; font:600 32px/1.15 var(--font-head); }
h2 { margin:0 0 12px; font-size:20px; }
h3 { margin:20px 0 8px; font-size:16px; }
.eyebrow { margin:0 0 6px; color:var(--accent); font-weight:700; font-size:12px; letter-spacing:.08em; text-transform:uppercase; }
.muted { color:var(--muted); }
.notice { margin:16px 0; padding:14px 16px; background:var(--warn-bg); border-left:4px solid var(--warn); border-radius:6px; }
.notice p { margin:4px 0; }
section { margin-top:18px; padding:20px; background:var(--surface); border:1px solid var(--line); border-radius:10px; overflow-wrap:break-word; }
.field { margin:0 0 22px; }
.field.has-error { padding-left:14px; border-left:4px solid var(--bad); }
label, legend { display:block; font-weight:700; }
fieldset { margin:0; padding:0; border:0; min-width:0; }
legend { padding:0; margin-bottom:4px; }
.optional { font-weight:400; color:var(--muted); }
.hint { margin:2px 0 8px; color:var(--muted); }
.field-error { margin:2px 0 8px; color:var(--bad); font-weight:700; }
input[type=text], textarea { display:block; width:100%; padding:8px 10px; font:inherit; color:var(--ink); background:var(--surface); border:2px solid var(--pill-line); border-radius:4px; }
.options { display:grid; gap:8px; }
.option { display:flex; gap:10px; align-items:flex-start; }
.option input { width:22px; height:22px; margin:2px 0 0; flex:none; accent-color:var(--accent); }
.option label { font-weight:400; }
input:focus-visible, textarea:focus-visible, button:focus-visible, a:focus-visible, [tabindex]:focus-visible { outline:3px solid var(--focus); outline-offset:2px; }
button { font:inherit; font-weight:700; padding:10px 18px; color:var(--on-accent); background:var(--accent); border:0; border-radius:6px; cursor:pointer; }
a { color:var(--accent); }
.error-summary { margin:16px 0; padding:16px; border:4px solid var(--bad); background:var(--bad-bg); border-radius:6px; }
.error-summary h2 { margin:0 0 8px; }
.error-summary ul { margin:0; padding-left:20px; }
.error-summary a { color:var(--bad); font-weight:700; }
dl.review { margin:0; }
.review-row { display:grid; grid-template-columns:minmax(0,2fr) minmax(0,3fr) auto; gap:4px 16px; padding:10px 0; border-bottom:1px solid var(--line); }
.review-row dt { font-weight:700; }
.review-row dd { margin:0; white-space:pre-wrap; overflow-wrap:anywhere; }
pre.file { margin:0; padding:12px; background:var(--panel); border:1px solid var(--line); border-radius:6px; font:13px/1.45 var(--font-mono); white-space:pre-wrap; overflow-wrap:anywhere; }
.actions { margin-top:20px; }
.actions p { margin:8px 0 0; }
.status { margin:16px 0; font-weight:700; overflow-wrap:anywhere; }
.visually-hidden { position:absolute !important; width:1px; height:1px; margin:-1px; padding:0; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }
footer { margin-top:28px; font-size:14px; }
@media (max-width:640px) {
  main { padding:28px 16px 48px; }
  h1 { font-size:26px; }
  section { padding:16px; }
  button { width:100%; }
  .review-row { grid-template-columns:minmax(0,1fr) auto; }
  .review-row dd.answer { grid-column:1 / -1; grid-row:2; }
}
"""

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<title>Prepare a legal request</title>
<style>__STYLE__</style>
</head>
<body>
<main>
<p class="eyebrow">Legal request · synthetic demonstration</p>
<h1>Prepare a legal request</h1>
<div class="notice">
<p>This page sends nothing. It saves a request file on this device, and you give the file to legal yourself. A person in legal reviews every request and makes every decision. Nothing here is legal advice.</p>
<p><strong>Demonstration only:</strong> use made-up details, never real client, customer or personal data.</p>
</div>
<noscript><p class="notice">This page needs JavaScript to check your answers and save the file. Nothing is sent either way.</p></noscript>
<div class="error-summary" id="error-summary" role="alert" tabindex="-1" hidden></div>
<div id="questions">
<section aria-labelledby="about-h"><h2 id="about-h">About the request</h2>__FIELDS__</section>
__TYPES__
<div class="actions"><button type="button" id="check">Check your answers</button></div>
</div>
<section id="review" aria-labelledby="review-h" tabindex="-1" hidden>
<h2 id="review-h">Check your answers</h2>
<p>This is everything the file holds. Its reference is __DRAFT__ until legal gives it a register number.</p>
<dl class="review" id="review-list"></dl>
<h3 id="file-h">The file, exactly as it will be saved</h3>
<pre class="file" id="file"></pre>
<div class="actions"><button type="button" id="save">Save request file</button>
<p class="muted">Saves the file on this device. Nothing is sent.</p></div>
</section>
<p class="status" id="status" role="status"></p>
<footer class="muted">Value bands and request types follow the policy: __POLICY__. Questions: __QUESTIONS__.</footer>
<script type="application/json" id="intake-spec">__SPEC__</script>
<script>__SCRIPT__</script>
</main>
</body>
</html>
"""

_SCRIPT = r"""(function () {
  "use strict";
  var WS = "__WS__";
  var SPACE = {}, w;
  for (w = 0; w < WS.length; w++) SPACE[WS.charAt(w)] = true;
  function trim(text) {
    var start = 0, end = text.length;
    while (start < end && SPACE[text.charAt(start)] === true) start++;
    while (end > start && SPACE[text.charAt(end - 1)] === true) end--;
    return text.slice(start, end);
  }

  function wellFormed(text) {
    var out = "", i, c, d;
    for (i = 0; i < text.length; i++) {
      c = text.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff) {
        d = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
        if (d >= 0xdc00 && d <= 0xdfff) { out += text.charAt(i) + text.charAt(i + 1); i++; }
        else { out += "\ufffd"; }
      } else if (c >= 0xdc00 && c <= 0xdfff) {
        out += "\ufffd";
      } else {
        out += text.charAt(i);
      }
    }
    return out;
  }
  function clean(value) { return trim(wellFormed(typeof value === "string" ? value : "")); }
  function has(obj, key) { return Object.prototype.hasOwnProperty.call(obj, key); }
  function listed(list, value) {
    for (var i = 0; i < list.length; i++) if (list[i] === value) return true;
    return false;
  }

  function core(form) {
    function value(item, raw) {
      if (item.control === "radio") {
        for (var i = 0; i < item.options.length; i++) {
          if (raw === String(i)) return { ok: true, value: item.options[i].value };
        }
        return { ok: false, value: null };
      }
      var text = clean(raw);
      return { ok: text !== "", value: text };
    }
    function evaluate(answers) {
      var given = answers.fields || {}, asked = answers.questions || {};
      var values = {}, visible = [], chosen = null, i, r;
      for (i = 0; i < form.fields.length; i++) {
        var f = form.fields[i];
        r = value(f, has(given, f.name) ? given[f.name] : "");
        if (r.ok) values[f.name] = r.value;
      }
      if (has(values, "type") && values.type !== null) {
        for (i = 0; i < form.types.length; i++) {
          if (form.types[i].key === values.type) { chosen = i; break; }
        }
      }
      if (chosen !== null) {
        var qs = form.types[chosen].questions;
        for (i = 0; i < qs.length; i++) {
          var c = qs[i].show_if;
          var shown = !c || (has(values, c.field) && listed(c["in"], values[c.field]));
          visible.push(shown);
          if (shown) {
            r = value(qs[i], has(asked, qs[i].name) ? asked[qs[i].name] : "");
            if (r.ok) values[qs[i].name] = r.value;
          }
        }
      }
      return { type: chosen, visible: visible, values: values };
    }
    function required(state) {
      var also = state.type === null ? [] : form.types[state.type].also_required, out = {};
      for (var i = 0; i < form.fields.length; i++) {
        out[form.fields[i].name] = form.fields[i].required || listed(also, form.fields[i].name);
      }
      return out;
    }
    function check(answers) {
      var state = evaluate(answers), req = required(state), problems = [], i;
      for (i = 0; i < form.fields.length; i++) {
        var f = form.fields[i];
        if (req[f.name] && !has(state.values, f.name)) problems.push({ id: f.id, message: f.error });
      }
      if (state.type !== null) {
        var qs = form.types[state.type].questions;
        for (i = 0; i < qs.length; i++) {
          if (state.visible[i] && qs[i].required && !has(state.values, qs[i].name)) {
            problems.push({ id: qs[i].id, message: qs[i].error });
          }
        }
      }
      return problems;
    }
    function build(answers) {
      var state = evaluate(answers), out = {}, pairs = [], facts = [], names = {}, i;
      if (state.type !== null) {
        var qs = form.types[state.type].questions;
        for (i = 0; i < qs.length; i++) {
          if (state.visible[i] && has(state.values, qs[i].name)) {
            var v = state.values[qs[i].name];
            pairs.push([qs[i].name, qs[i].kind === "yes_no" ? (v ? "yes" : "no") : String(v)]);
          }
        }
      }
      pairs.sort(function (a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; });
      for (i = 0; i < pairs.length; i++) facts.push(pairs[i][0] + ": " + pairs[i][1]);
      for (i = 0; i < form.fields.length; i++) names[form.fields[i].name] = true;
      for (i = 0; i < form.order.length; i++) {
        var name = form.order[i];
        if (name === "id") out.id = form.draft_id;
        else if (name === "facts") { if (facts.length) out.facts = facts; }
        else if (has(names, name) && has(state.values, name) && state.values[name] !== null) out[name] = state.values[name];
      }
      return out;
    }
    function answerText(item, values) {
      if (!has(values, item.name)) return form.not_given;
      var v = values[item.name];
      if (item.control !== "radio") return String(v);
      for (var i = 0; i < item.options.length; i++) {
        if (item.options[i].value === v) return String(item.options[i].label);
      }
      return form.not_given;
    }
    function rows(answers) {
      var state = evaluate(answers), out = [], i;
      for (i = 0; i < form.fields.length; i++) {
        out.push({ id: form.fields[i].id, label: form.fields[i].label, answer: answerText(form.fields[i], state.values) });
      }
      if (state.type !== null) {
        var qs = form.types[state.type].questions;
        for (i = 0; i < qs.length; i++) {
          if (state.visible[i]) out.push({ id: qs[i].id, label: qs[i].label, answer: answerText(qs[i], state.values) });
        }
      }
      return out;
    }
    function download(answers) { return JSON.stringify([build(answers)], null, 2) + "\n"; }
    function name(answers) {
      var title = build(answers).title;
      var slug = String(title || "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase().slice(0, 50).replace(/^-+|-+$/g, "");
      return slug ? "legal-request-" + slug + ".json" : "legal-request.json";
    }
    return { evaluate: evaluate, required: required, check: check, build: build, rows: rows, download: download, name: name };
  }

  if (typeof document === "undefined") {
    globalThis.intakeCore = core;
    return;
  }

  var form = JSON.parse(document.getElementById("intake-spec").textContent);
  var app = core(form);
  var items = {}, described = {}, place = {}, summaryItems = {}, baseTitle = document.title, announced = null, reviewed = null, objectUrl = null, errored = [];
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    for (var key in attrs) if (has(attrs, key)) node.setAttribute(key, attrs[key]);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function say(text) { var s = $("status"); s.textContent = ""; s.textContent = text; }
  function remember(item) {
    items[item.id] = item;
    var node = $(item.id);
    described[item.id] = node && node.getAttribute("aria-describedby") ? node.getAttribute("aria-describedby") : "";
  }
  var i, j;
  for (i = 0; i < form.fields.length; i++) remember(form.fields[i]);
  for (i = 0; i < form.types.length; i++) {
    for (j = 0; j < form.types[i].questions.length; j++) {
      remember(form.types[i].questions[j]);
      place[form.types[i].questions[j].id] = [i, j];
    }
  }
  // A radio group is reached at its chosen answer, or at its first one.
  function target(id) {
    var item = items[id];
    if (item.control !== "radio") return id;
    for (var n = 0; n < item.options.length; n++) {
      var radio = $(id + "-" + n);
      if (radio && radio.checked) return id + "-" + n;
    }
    return id + "-0";
  }
  function focus(id) { var node = $(target(id)); if (node) node.focus(); }
  function read(item) {
    if (item.control === "radio") {
      for (var n = 0; n < item.options.length; n++) {
        var radio = $(item.id + "-" + n);
        if (radio && radio.checked) return String(n);
      }
      return "";
    }
    var node = $(item.id);
    return node ? node.value : "";
  }
  function answers() {
    var a = { fields: {}, questions: {} }, n;
    for (n = 0; n < form.fields.length; n++) a.fields[form.fields[n].name] = read(form.fields[n]);
    var chosen = app.evaluate(a).type;
    if (chosen !== null) {
      var qs = form.types[chosen].questions;
      for (n = 0; n < qs.length; n++) a.questions[qs[n].name] = read(qs[n]);
    }
    return a;
  }
  function sync() {
    var a = answers(), state = app.evaluate(a), req = app.required(state), n;
    for (n = 0; n < form.types.length; n++) $(form.types[n].id).hidden = n !== state.type;
    if (state.type !== null) {
      var qs = form.types[state.type].questions;
      for (n = 0; n < qs.length; n++) $(qs[n].id + "-field").hidden = !state.visible[n];
    }
    for (n = 0; n < form.fields.length; n++) {
      var mark = $(form.fields[n].id + "-optional");
      if (mark) mark.hidden = req[form.fields[n].name];
    }
    dropHiddenErrors(state);
    if (reviewed !== null && app.download(a) !== reviewed) {
      $("review").hidden = true;
      reviewed = null;
      say("You changed an answer. Check your answers again before you save the file.");
    }
  }
  // Said once the requester leaves the type question, not at every arrow key in it.
  function announceType() {
    var state = app.evaluate(answers()), n, count = 0;
    if (state.type === announced) return;
    announced = state.type;
    if (state.type === null) { say("No further questions for this answer."); return; }
    for (n = 0; n < state.visible.length; n++) if (state.visible[n]) count++;
    var label = form.types[state.type].label;
    say(count === 0 ? "No further questions for " + label + "." :
      count + (count === 1 ? " more question for " + label + " appears" : " more questions for " + label + " appear") +
      " after the questions about the request.");
  }
  function unmark(id) {
    $(id + "-error").hidden = true;
    $(id + "-error-text").textContent = "";
    $(id + "-field").classList.remove("has-error");
    if (described[id]) $(id).setAttribute("aria-describedby", described[id]);
    else $(id).removeAttribute("aria-describedby");
    if (items[id].control !== "radio") $(id).removeAttribute("aria-invalid");
  }
  function clearErrors() {
    for (var n = 0; n < errored.length; n++) unmark(errored[n]);
    errored = [];
    summaryItems = {};
    var summary = $("error-summary");
    summary.hidden = true;
    clear(summary);
    document.title = baseTitle;
  }
  // A question hidden since the last check is no longer asked for.
  function dropHiddenErrors(state) {
    var kept = [], n;
    for (n = 0; n < errored.length; n++) {
      var id = errored[n], at = place[id];
      if (at && (at[0] !== state.type || !state.visible[at[1]])) {
        unmark(id);
        summaryItems[id].parentNode.removeChild(summaryItems[id]);
        delete summaryItems[id];
      } else {
        kept.push(id);
      }
    }
    if (kept.length === errored.length) return;
    errored = kept;
    if (!errored.length) clearErrors();
  }
  function showErrors(problems) {
    var summary = $("error-summary"), list = el("ul", {}), n;
    summary.appendChild(el("h2", {}, "There is a problem"));
    for (n = 0; n < problems.length; n++) {
      var p = problems[n];
      var link = el("a", { href: "#" + target(p.id) }, p.message);
      link.addEventListener("click", (function (id) { return function (e) { e.preventDefault(); focus(id); }; })(p.id));
      var li = el("li", {});
      li.appendChild(link);
      list.appendChild(li);
      summaryItems[p.id] = li;
      $(p.id + "-error-text").textContent = p.message;
      $(p.id + "-error").hidden = false;
      $(p.id + "-field").classList.add("has-error");
      $(p.id).setAttribute("aria-describedby", (described[p.id] ? described[p.id] + " " : "") + p.id + "-error");
      if (items[p.id].control !== "radio") $(p.id).setAttribute("aria-invalid", "true");
      errored.push(p.id);
    }
    summary.appendChild(list);
    summary.hidden = false;
    document.title = "Error: " + baseTitle;
    summary.focus();
  }
  function showReview(a) {
    var list = $("review-list"), all = app.rows(a), n;
    clear(list);
    for (n = 0; n < all.length; n++) {
      var row = el("div", { "class": "review-row" });
      row.appendChild(el("dt", {}, all[n].label));
      row.appendChild(el("dd", { "class": "answer" }, all[n].answer));
      var change = el("a", { href: "#" + target(all[n].id) }, "Change");
      change.appendChild(el("span", { "class": "visually-hidden" }, " " + all[n].label));
      change.addEventListener("click", (function (id) { return function (e) { e.preventDefault(); focus(id); }; })(all[n].id));
      var cell = el("dd", { "class": "change" });
      cell.appendChild(change);
      row.appendChild(cell);
      list.appendChild(row);
    }
    reviewed = app.download(a);
    $("file").textContent = reviewed;
    $("review").hidden = false;
    $("status").textContent = "";
    $("review").focus();
  }
  $("questions").addEventListener("input", sync);
  $("questions").addEventListener("change", sync);
  $("f-type").addEventListener("focusout", function (e) {
    if (!e.relatedTarget || !$("f-type").contains(e.relatedTarget)) announceType();
  });
  // Going back to the page restores its answers without an input event.
  window.addEventListener("pageshow", sync);
  $("check").addEventListener("click", function () {
    sync();
    announceType();
    var a = answers(), problems = app.check(a);
    clearErrors();
    if (problems.length) { $("review").hidden = true; reviewed = null; showErrors(problems); return; }
    showReview(a);
  });
  $("save").addEventListener("click", function () {
    var a = answers();
    if (reviewed === null || app.download(a) !== reviewed) { sync(); return; }
    var file = app.name(a);
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(new Blob([reviewed], { type: "application/json" }));
    var link = el("a", { href: objectUrl, download: file });
    link.hidden = true;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    say("Your browser is saving " + file + " to this device. Nothing was sent. Give the file to legal yourself; a person in legal reviews every request.");
  });
  sync();
})();
"""
