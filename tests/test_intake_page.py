"""Intake page (F9): question files, the request it saves, and the page that saves it.

The page script and ``intake_page`` implement the same rules. These tests check the
Python side against the request contract on every answer the page can accept, run the
page's own script in Node on the same answers, and check the page markup. The browser
test is in ``test_intake_page_browser``.
"""

from __future__ import annotations

import ast
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from itertools import product
from pathlib import Path
from typing import Any
from unittest import mock

import legal_function_os.intake_page as intake_module
from legal_function_os.cli import main as cli_main
from legal_function_os.design_tokens import TOKENS_CSS
from legal_function_os.intake_page import (
    ALWAYS_ASKED,
    DRAFT_ID,
    NOT_ASKED,
    OPTIONAL_FIELDS,
    QUESTIONS_SCHEMA,
    SET_BY_PAGE,
    WHITESPACE,
    IntakeQuestionsError,
    build_intake_form,
    check_answers,
    clean_text,
    download_name,
    evaluate,
    load_intake_questions,
    page_script,
    page_style,
    render_download,
    render_intake_html,
    render_intake_markdown,
    request_from_answers,
    review_rows,
    write_intake_page,
)
from legal_function_os.policy import PolicyError, default_policy, parse_policy
from legal_function_os.rules import URGENCIES
from legal_function_os.validation import request_schema, validate_requests

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "intake-page.html"
PILOT_MODELS = ROOT / "supervised-agent" / "src" / "pilot" / "models.py"
REQUIRE_JS_TESTS = "REQUIRE_JS_TESTS"

# Text a requester can type that trips naive trimming, escaping or encoding.
TEXTS = (
    "",
    "  ",
    "\x1c",
    "\x85",
    "\ufeff",
    WHITESPACE + "x" + WHITESPACE,
    " padded ",
    "x</script><b>&amp;",
    "a\ud800b",
    "line\nbreak",
    "\u2028",
    "\U0001f600",
    "\x00",
    "\xa0x\xa0",
    "a\udfffb",
    "x\ud800",
    "a\ud800\ue000",
    "\U00010000 \U0010ffff \udbff \udc00 \ud800\ud800",
    "a" * 49 + " b" + "c" * 20,
    "A" * 60,
    "\u00dcber " * 20,
    "NDA_v2 - Example (synthetic)",
)
# Radio values the page never writes; each must count as no answer.
BAD_INDEXES = ("-1", "01", "99", "1.0", " 0", "0 ", "true")


def bundled() -> dict[str, Any]:
    questions, _ = load_intake_questions()
    return copy.deepcopy(questions)


def keys_questions() -> dict[str, Any]:
    """The bundled questions plus what the bundled file lacks: two keys where sorting the text
    and sorting the key differ, a key every JavaScript object already has, a question shown
    on a No, and a type that makes two optional fields required."""

    questions = bundled()
    questions["types"]["dpa"]["also_required"].append("deadline")
    questions["types"]["dpa"]["questions"] += [
        {"key": "item1", "label": "Item one", "kind": "text", "required": False},
        {"key": "item", "label": "Item", "kind": "text", "required": False},
        # Every JavaScript object inherits a "constructor" property.
        {"key": "constructor", "label": "Constructor", "kind": "text"},
    ]
    # A question shown when the answer is No, which is falsy in JavaScript.
    questions["types"]["vendor_review"]["questions"].append(
        {"key": "why_no_data", "label": "Why no personal data?", "kind": "text",
         "show_if": {"field": "personal_data", "in": [False]}}
    )
    return questions


def form_for(questions: dict[str, Any] | None = None, policy: Any = None) -> dict[str, Any]:
    return build_intake_form(bundled() if questions is None else questions, policy)


def problems(questions: Any, policy: Any = None) -> list[str]:
    try:
        build_intake_form(questions, policy)
    except (IntakeQuestionsError, PolicyError) as exc:
        return exc.problems
    return []


def custom_policy() -> Any:
    """The default policy with other band names, a new type and one type removed."""

    names = {"<50k": "small", "50k-250k": "medium", "250k-1m": "large", ">1m": "huge"}
    text = json.dumps(default_policy().to_dict())
    for old, new in names.items():
        text = text.replace(json.dumps(old), json.dumps(new))
    data = json.loads(text)
    data["name"] = "Custom test policy"
    del data["routing"]["by_type"]["ip"]
    data["routing"]["by_type"]["regulatory"] = "General"
    return parse_policy(data, "custom test policy")


def complete(form: dict[str, Any], type_key: str | None) -> dict[str, Any]:
    """Answers with every question answered, for ``type_key`` (None: not sure)."""

    fields: dict[str, str] = {}
    for item in form["fields"]:
        if item["control"] != "radio":
            fields[item["name"]] = f"{item['name']} text"
        elif item["name"] == "type":
            values = [o["value"] for o in item["options"]]
            fields["type"] = str(values.index(type_key))
        else:
            fields[item["name"]] = "0"
    questions: dict[str, str] = {}
    for form_type in form["types"]:
        if form_type["key"] == type_key:
            for q in form_type["questions"]:
                questions[q["name"]] = "0" if q["control"] == "radio" else f"{q['name']} answer"
    return {"fields": fields, "questions": questions}


def answer_vectors(form: dict[str, Any]) -> list[dict[str, Any]]:
    """Every answer combination the page's choices allow, plus hostile text and values."""

    radios = [f for f in form["fields"] if f["control"] == "radio"]
    texts = [f for f in form["fields"] if f["control"] != "radio"]
    vectors: list[dict[str, Any]] = []
    # 1. Every combination of the request-field choices, unanswered included.
    choices = [["", *map(str, range(len(f["options"])))] for f in radios]
    for n, combo in enumerate(product(*choices)):
        fields = dict(zip([f["name"] for f in radios], combo, strict=True))
        if n % 2 == 0:
            fields.update({f["name"]: f"{f['name']} text" for f in texts})
        questions: dict[str, str] = {}
        type_index = int(combo[0]) if combo[0] else None
        if type_index is not None and type_index < len(form["types"]) and n % 3:
            for q in form["types"][type_index]["questions"]:
                questions[q["name"]] = str(n % len(q["options"])) if q["control"] == "radio" else "answer"
        vectors.append({"fields": fields, "questions": questions})
    flags = [f["name"] for f in radios if f["name"] in ("personal_data", "non_eea_transfer", "uncapped_liability")]
    for form_type in form["types"]:
        base = complete(form, form_type["key"])
        qs = form_type["questions"]
        # 2. For each type, every combination of its choices with the flags varied.
        q_radios = [q for q in qs if q["control"] == "radio"]
        q_texts = [q for q in qs if q["control"] != "radio"]
        q_choices = [["", *map(str, range(len(q["options"])))] for q in q_radios]
        for combo in product(*q_choices):
            for flag_values in product("01", repeat=len(flags)):
                for answered in (True, False):
                    answers = copy.deepcopy(base)
                    answers["fields"].update(dict(zip(flags, flag_values, strict=True)))
                    answers["questions"] = dict(zip([q["name"] for q in q_radios], combo, strict=True))
                    if answered:
                        answers["questions"].update({q["name"]: "answer" for q in q_texts})
                    vectors.append(answers)
        # 3. Hostile text in every text question, and radio values the page never writes.
        for q in qs:
            for value in TEXTS if q["control"] != "radio" else BAD_INDEXES:
                answers = copy.deepcopy(base)
                answers["questions"][q["name"]] = value
                vectors.append(answers)
    base = complete(form, form["types"][0]["key"])
    for item in form["fields"]:
        for value in TEXTS if item["control"] != "radio" else BAD_INDEXES:
            answers = copy.deepcopy(base)
            answers["fields"][item["name"]] = value
            vectors.append(answers)
    return vectors


def expected_problems(form: dict[str, Any], answers: dict[str, Any]) -> list[str]:
    """An independent statement of what the page must ask for, by item id."""

    fields, questions = answers["fields"], answers.get("questions", {})

    def given(item: dict[str, Any], raw: str) -> Any:
        if item["control"] == "radio":
            index = {str(i): o["value"] for i, o in enumerate(item["options"])}
            return ("answered", index[raw]) if raw in index else None
        return ("answered", clean_text(raw)) if clean_text(raw) else None

    base = {f["name"]: given(f, fields.get(f["name"], "")) for f in form["fields"]}
    chosen = base["type"][1] if base["type"] else None
    form_type = next((t for t in form["types"] if t["key"] == chosen), None)
    missing = []
    for f in form["fields"]:
        required = f["required"] or (form_type is not None and f["name"] in form_type["also_required"])
        if required and base[f["name"]] is None:
            missing.append(f["id"])
    if form_type is None:
        return missing
    by_name = {q["name"]: q for q in form_type["questions"]}

    def shown(q: dict[str, Any]) -> bool:
        cond = q.get("show_if")
        if cond is None:
            return True
        if cond["field"] in base:
            answer = base[cond["field"]]
        else:
            controller = by_name[cond["field"]]
            if not shown(controller):
                return False
            answer = given(controller, questions.get(controller["name"], ""))
        return answer is not None and any(type(answer[1]) is type(v) and answer[1] == v for v in cond["in"])

    for q in form_type["questions"]:
        if shown(q) and q["required"] and given(q, questions.get(q["name"], "")) is None:
            missing.append(q["id"])
    return missing


class _Page(HTMLParser):
    """Elements, attributes, scripts and visible text of a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.scripts: list[tuple[dict[str, str | None], str]] = []
        self.style = ""
        self.text: list[str] = []
        self._in: str | None = None
        self._attrs: dict[str, str | None] = {}
        self._buffer = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))
        if tag in ("script", "style"):
            self._in, self._attrs, self._buffer = tag, dict(attrs), ""

    def handle_endtag(self, tag: str) -> None:
        if tag == self._in:
            if tag == "script":
                self.scripts.append((self._attrs, self._buffer))
            else:
                self.style = self._buffer
            self._in = None

    def handle_data(self, data: str) -> None:
        if self._in:
            self._buffer += data
        else:
            self.text.append(data)


def parse(page: str) -> _Page:
    parser = _Page()
    parser.feed(page)
    return parser


def node_available() -> bool:
    return shutil.which("node") is not None


class QuestionFileTests(unittest.TestCase):
    def test_the_bundled_questions_build_with_no_problems_or_notes(self) -> None:
        form = form_for()
        self.assertEqual(form["notes"], [])
        self.assertEqual([t["key"] for t in form["types"]], list(default_policy().routing))
        for form_type in form["types"]:
            self.assertNotEqual(form_type["label"], form_type["key"])
        # The bundled file has no value-band condition, so it builds under any policy.
        conditions = [q["show_if"]["field"] for t in form["types"] for q in t["questions"] if "show_if" in q]
        self.assertNotIn("value_band", conditions)
        self.assertEqual(form_for(policy=custom_policy())["policy"], "Custom test policy")
        # The policy, not the file, orders and numbers the types and their questions.
        reordered = bundled()
        reordered["types"] = dict(reversed(list(reordered["types"].items())))
        self.assertEqual(form_for(reordered), form)

    def test_every_request_field_has_a_place(self) -> None:
        groups = (ALWAYS_ASKED, OPTIONAL_FIELDS, NOT_ASKED, SET_BY_PAGE)
        names = [name for group in groups for name in group]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(request_schema()["properties"]))
        self.assertLessEqual(set(request_schema()["required"]), {*ALWAYS_ASKED, "id"})

    def test_fields_follow_the_contract_order_and_types(self) -> None:
        form = form_for()
        properties = request_schema()["properties"]
        self.assertEqual(
            [f["name"] for f in form["fields"]],
            [p for p in properties if p in (*ALWAYS_ASKED, *OPTIONAL_FIELDS)],
        )
        self.assertEqual(form["order"], list(properties))
        controls = {f["name"]: f["control"] for f in form["fields"]}
        self.assertEqual(controls["description"], "textarea")
        for name in ("title", "counterparty", "requested_by", "deadline"):
            self.assertEqual(controls[name], "text")
        for name in ("type", "value_band", "personal_data", "non_eea_transfer", "uncapped_liability", "urgency"):
            self.assertEqual(controls[name], "radio")
        for name in ALWAYS_ASKED:
            self.assertTrue(next(f for f in form["fields"] if f["name"] == name)["required"], name)
        # The not-sure label is the type's last answer, not a key of its own.
        self.assertNotIn("not_sure", next(f for f in form["fields"] if f["name"] == "type"))

    def test_options_come_from_the_contract_and_the_policy(self) -> None:
        schema = request_schema()["properties"]
        form = form_for()
        options = {f["name"]: [o["value"] for o in f.get("options", [])] for f in form["fields"]}
        self.assertEqual(options["value_band"], [v for v in schema["value_band"]["enum"] if v is not None])
        self.assertEqual(options["urgency"], [v for v in schema["urgency"]["enum"] if v is not None])
        self.assertEqual(options["urgency"], list(URGENCIES))
        self.assertEqual(options["type"], [*schema["type"]["examples"], None])
        for name in ("personal_data", "non_eea_transfer", "uncapped_liability"):
            self.assertEqual(options[name], [True, False])

        policy = custom_policy()
        form = form_for(policy=policy)
        options = {f["name"]: f["options"] for f in form["fields"] if "options" in f}
        self.assertEqual([o["value"] for o in options["value_band"]], list(policy.value_bands))
        # A band the question file does not label shows its own name.
        self.assertEqual(options["value_band"][1], {"label": "small", "value": "small"})
        self.assertEqual([o["value"] for o in options["type"]], [*policy.routing, None])
        self.assertEqual(
            form["notes"],
            [
                "fields.value_band.options.<50k: the policy has no value band '<50k'; label ignored",
                "fields.value_band.options.50k-250k: the policy has no value band '50k-250k'; label ignored",
                "fields.value_band.options.250k-1m: the policy has no value band '250k-1m'; label ignored",
                "fields.value_band.options.>1m: the policy has no value band '>1m'; label ignored",
                'intake questions for "ip" are not used: the policy has no request type "ip"',
                'request type "regulatory" has no intake questions; the page offers it as "regulatory"',
            ],
        )

    def test_conditions_can_only_look_back(self) -> None:
        def with_dpa(change: Any) -> list[str]:
            questions = bundled()
            change(questions["types"]["dpa"]["questions"])
            return problems(questions)

        where = "types.dpa.questions"
        cases = {
            # A missing key is reported once, not again as a null value.
            "a condition without a field": (
                lambda qs: qs[2].update(show_if={"in": [True]}),
                f"{where}[2].show_if.field: missing",
            ),
            "a condition without its answers": (
                lambda qs: qs[2].update(show_if={"field": "non_eea_transfer"}),
                f"{where}[2].show_if.in: missing",
            ),
            "a later question": (
                lambda qs: qs[1].update(show_if={"field": "sub_processors", "in": [True]}),
                f'{where}[1].show_if.field: "sub_processors" is asked later (questions[3]); '
                "a condition can only name an answer given above it (forward-only)",
            ),
            "itself": (
                lambda qs: qs[3].update(show_if={"field": "sub_processors", "in": [True]}),
                f"{where}[3].show_if.field: names its own question; a condition can only name an answer given above it",
            ),
            "an unknown name": (
                lambda qs: qs[4].update(show_if={"field": "sub_processor", "in": [True]}),
                f"{where}[4].show_if.field: \"sub_processor\" is not asked before this question (did you mean 'sub_processors'?)",
            ),
            "a misspelled request field": (
                lambda qs: qs[4].update(show_if={"field": "personal_dta", "in": [True]}),
                f"{where}[4].show_if.field: \"personal_dta\" is not asked before this question (did you mean 'personal_data'?)",
            ),
            "type": (
                lambda qs: qs[0].update(show_if={"field": "type", "in": ["dpa"]}),
                f'{where}[0].show_if.field: "type" cannot be a condition; put the question under types.<type> instead',
            ),
            "a free-text request field": (
                lambda qs: qs[0].update(show_if={"field": "counterparty", "in": ["x"]}),
                f'{where}[0].show_if.field: "counterparty" is free text and cannot control a question; use yes_no or choice',
            ),
            "a free-text question": (
                lambda qs: qs[2].update(show_if={"field": "processing_purpose", "in": ["x"]}),
                f'{where}[2].show_if.field: "processing_purpose" is free text and cannot control a question; use yes_no or choice',
            ),
            "a string for a yes or no": (
                lambda qs: qs[4].update(show_if={"field": "sub_processors", "in": ["yes"]}),
                f"{where}[4].show_if.in[0]: \"yes\" is not an answer to 'sub_processors'; use one of true, false",
            ),
            "a choice that is not offered": (
                lambda qs: qs[1].update(show_if={"field": "processing_role", "in": ["Maybe"]}),
                f"{where}[1].show_if.in[0]: \"Maybe\" is not an answer to 'processing_role'; use one of "
                '"We decide (we are the controller)", "The other party decides (we are the processor)", "Not sure"',
            ),
            "a band the policy lacks": (
                lambda qs: qs[0].update(show_if={"field": "value_band", "in": [">1M"]}),
                f"{where}[0].show_if.in[0]: \">1M\" is not an answer to 'value_band'; use one of "
                '"none", "<50k", "50k-250k", "250k-1m", ">1m"',
            ),
            "an empty list": (
                lambda qs: qs[4].update(show_if={"field": "sub_processors", "in": []}),
                f"{where}[4].show_if.in: expected a non-empty list of answers, got a list",
            ),
            "answers that are not a list": (
                lambda qs: qs[4].update(show_if={"field": "sub_processors", "in": True}),
                f"{where}[4].show_if.in: expected a non-empty list of answers, got a boolean",
            ),
            "a value listed twice": (
                lambda qs: qs[4].update(show_if={"field": "sub_processors", "in": [True, True]}),
                f"{where}[4].show_if.in[1]: True is listed twice",
            ),
            "a number after its boolean": (
                lambda qs: qs[4].update(show_if={"field": "sub_processors", "in": [True, 1]}),
                f"{where}[4].show_if.in[1]: 1 is not an answer to 'sub_processors'; use one of true, false",
            ),
            "an extra key": (
                lambda qs: qs[4]["show_if"].update(when="now"),
                f"{where}[4].show_if.when: unknown key; prefix your own keys with x_",
            ),
            "a null condition": (
                lambda qs: qs[4].update(show_if=None),
                f"{where}[4].show_if: expected an object, got null",
            ),
            "a field that is not a name": (
                lambda qs: qs[4].update(show_if={"field": 3, "in": [True]}),
                f"{where}[4].show_if.field: expected the name of an earlier answer, got a number",
            ),
            "another type's question": (
                lambda qs: qs[1].update(show_if={"field": "security_review_done", "in": [True]}),
                f'{where}[1].show_if.field: "security_review_done" is not asked before this question',
            ),
            "a number for a yes or no": (
                lambda qs: qs[4].update(show_if={"field": "sub_processors", "in": [1]}),
                f"{where}[4].show_if.in[0]: 1 is not an answer to 'sub_processors'; use one of true, false",
            ),
            # A question that takes a controller's name does not change that controller's answers.
            "a question named like a request field": (
                lambda qs: qs[3].update(key="urgency") or qs[4].update(show_if={"field": "urgency", "in": ["high"]}),
                f'{where}[3].key: "urgency" is a request field; choose another key',
            ),
            # The controller's own problem is reported once, not again at what depends on it.
            # Its own key is the problem, reported there; it is not "free text".
            "a controller whose own key is wrong": (
                lambda qs: qs[3].update(key="Sub_Processors") or qs[4].update(show_if={"field": "Sub_Processors", "in": [True]}),
                f"{where}[3].key: expected lower-case letters, digits and _, starting with a letter, up to 40 characters",
            ),
            "a controller with a wrong kind": (
                lambda qs: qs[3].update(kind="yesno"),
                f"{where}[3].kind: expected one of text, textarea, yes_no, choice, got 'yesno'",
            ),
            # Answers that are not known yet: a condition below adds no second problem,
            # even one that names no answer at all.
            "a controller with one option": (
                lambda qs: qs[0].update(options=["Only"]) or qs[1].update(show_if={"field": "processing_role", "in": ["Nope"]}),
                f"{where}[0].options: expected a list of 2 to 20 answers, got a list",
            ),
            "a controller with too many options": (
                lambda qs: qs[0].update(options=[f"Option {n}" for n in range(21)])
                or qs[1].update(show_if={"field": "processing_role", "in": ["Nope"]}),
                f"{where}[0].options: expected a list of 2 to 20 answers, got a list",
            ),
            "a controller with an option that is not text": (
                lambda qs: qs[0]["options"].__setitem__(2, {"label": "Not sure"})
                or qs[1].update(show_if={"field": "processing_role", "in": ["Not sure"]}),
                f"{where}[0].options[2]: expected non-empty text, got an object",
            ),
            "a controller with a blank option": (
                lambda qs: qs[0].update(options=["A", " ", "B"]) or qs[1].update(show_if={"field": "processing_role", "in": ["Nope"]}),
                f"{where}[0].options[1]: expected non-empty text, got text",
            ),
            "a controller with an unpaired surrogate": (
                lambda qs: qs[0].update(options=["A", "B\ud800", "C"]) or qs[1].update(show_if={"field": "processing_role", "in": ["Nope"]}),
                f"{where}[0].options[1]: contains an unpaired surrogate; the page could not save it",
            ),
            "a controller with a wrong kind and a typo below it": (
                lambda qs: qs[0].update(kind="Choice") or qs[1].update(show_if={"field": "processing_role", "in": ["Nope"]}),
                f"{where}[0].kind: expected one of text, textarea, yes_no, choice, got 'Choice'",
            ),
            # A padded answer has one reading, so naming it is not a second problem.
            "a controller with a padded option": (
                lambda qs: qs[0]["options"].__setitem__(2, " Not sure")
                or qs[1].update(show_if={"field": "processing_role", "in": ["Not sure"]}),
                f"{where}[0].options[2]: has spaces at the start or end",
            ),
        }
        for name, (change, message) in cases.items():
            with self.subTest(name):
                self.assertEqual(with_dpa(change), [message])
        # A condition's own problem is still reported when its controller has one.
        self.assertEqual(
            with_dpa(lambda qs: qs[0].update(options=["Only"]) or qs[1].update(show_if={"field": "processing_role", "in": []})),
            [
                f"{where}[0].options: expected a list of 2 to 20 answers, got a list",
                f"{where}[1].show_if.in: expected a non-empty list of answers, got a list",
            ],
        )
        # A typo in a condition is still reported when a controller's answer is only padded
        # or repeated, and each answer is offered once.
        self.assertEqual(
            with_dpa(
                lambda qs: qs[0].update(options=["A", " B", "C"])
                or qs[1].update(show_if={"field": "processing_role", "in": ["B", "Nope"]})
            ),
            [
                f"{where}[0].options[1]: has spaces at the start or end",
                f'{where}[1].show_if.in[1]: "Nope" is not an answer to \'processing_role\'; use one of "A", "B", "C"',
            ],
        )
        self.assertEqual(
            with_dpa(
                lambda qs: qs[0].update(options=["A", "A", "B"])
                or qs[1].update(show_if={"field": "processing_role", "in": ["Nope"]})
            ),
            [
                f"{where}[0].options[1]: 'A' is listed twice",
                f'{where}[1].show_if.in[0]: "Nope" is not an answer to \'processing_role\'; use one of "A", "B"',
            ],
        )

    def test_a_condition_on_a_request_field_or_an_earlier_answer_is_accepted(self) -> None:
        questions = bundled()
        dpa = questions["types"]["dpa"]["questions"]
        dpa[1]["show_if"] = {"field": "value_band", "in": ["250k-1m", ">1m"]}
        dpa[2]["show_if"] = {"field": "processing_role", "in": ["Not sure"]}
        dpa[0]["show_if"] = {"field": "urgency", "in": ["blocker"]}
        form = form_for(questions)
        shown = {q["name"]: q.get("show_if") for q in form["types"][2]["questions"]}
        self.assertEqual(shown["processing_purpose"], {"field": "value_band", "in": ["250k-1m", ">1m"]})
        self.assertEqual(shown["processing_role"], {"field": "urgency", "in": ["blocker"]})

    def test_every_problem_is_reported_at_once(self) -> None:
        questions = bundled()
        questions["fields"]["title"]["label"] = " "
        questions["types"]["dpa"]["questions"][1]["kind"] = "number"
        questions["types"]["ip"]["questions"][2]["show_if"]["field"] = "later"
        self.assertEqual(
            problems(questions),
            [
                "fields.title.label: expected non-empty text, got text",
                "types.dpa.questions[1].kind: expected one of text, textarea, yes_no, choice, got 'number'",
                "types.ip.questions[2].show_if.field: \"later\" is not asked before this question",
            ],
        )

    def test_another_type_can_ask_the_same_key(self) -> None:
        # A key is unique within its type; another type may ask the same thing.
        questions = bundled()
        questions["types"]["vendor_review"]["questions"][0]["key"] = "processing_role"
        form = form_for(questions)
        self.assertEqual(
            [q["id"] for t in form["types"] for q in t["questions"] if q["name"] == "processing_role"],
            ["q1-processing_role", "q2-processing_role"],
        )

    def test_questions_are_checked(self) -> None:
        def first_dpa(update: dict[str, Any], remove: tuple[str, ...] = ()) -> list[str]:
            questions = bundled()
            question = questions["types"]["dpa"]["questions"][0]
            question.update(update)
            for key in remove:
                del question[key]
            return problems(questions)

        where = "types.dpa.questions[0]"
        key_rule = "expected lower-case letters, digits and _, starting with a letter, up to 40 characters"
        cases = {
            "a key with capitals": ({"key": "Role"}, (), [f"{where}.key: {key_rule}"]),
            "a key that is too long": ({"key": "a" * 41}, (), [f"{where}.key: {key_rule}"]),
            "a key starting with _": ({"key": "_role"}, (), [f"{where}.key: {key_rule}"]),
            "a key that is a request field": (
                {"key": "counterparty"}, (), [f'{where}.key: "counterparty" is a request field; choose another key'],
            ),
            "a key that is legal's own field": (
                {"key": "summary"}, (), [f'{where}.key: "summary" is a request field; choose another key'],
            ),
            "a key used twice": (
                {"key": "processing_purpose"}, (), ['types.dpa.questions[1].key: "processing_purpose" is used twice in this type'],
            ),
            "a key with a line break at the end": ({"key": "role\n"}, (), [f"{where}.key: {key_rule}"]),
            "no kind": ({}, ("kind",), [f"{where}.kind: missing"]),
            "one option": ({"options": ["Only"]}, (), [f"{where}.options: expected a list of 2 to 20 answers, got a list"]),
            "21 options": (
                {"options": [f"Answer {n}" for n in range(21)]}, (),
                [f"{where}.options: expected a list of 2 to 20 answers, got a list"],
            ),
            "20 options": ({"options": [f"Answer {n}" for n in range(20)]}, (), []),
            "a blank option": ({"options": ["A", " "]}, (), [f"{where}.options[1]: expected non-empty text, got text"]),
            "a label that is only a byte order mark": ({"label": "\ufeff"}, (), [f"{where}.label: expected non-empty text, got text"]),
            "an option with spaces": ({"options": ["A", " B"]}, (), [f"{where}.options[1]: has spaces at the start or end"]),
            "an option twice": ({"options": ["A", "A"]}, (), [f"{where}.options[1]: 'A' is listed twice"]),
            "an option ending in U+FEFF": ({"options": ["A", "B\ufeff"]}, (), [f"{where}.options[1]: has spaces at the start or end"]),
            "an option with a link": (
                {"options": ["A", "See https://example.org"]}, (),
                [f"{where}.options[1]: must not contain a link (http:// or https://); the page is self-contained"],
            ),
            "options that are not a list": (
                {"options": "Yes or no"}, (), [f"{where}.options: expected a list of 2 to 20 answers, got text"],
            ),
            "options on a text question": (
                {"kind": "text"}, (), [f"{where}.options: only a choice question has options"],
            ),
            "options on a yes or no question": (
                {"kind": "yes_no"}, (), [f"{where}.options: only a choice question has options"],
            ),
            "a label with a link": (
                {"label": "See HTTP://example.org"}, (),
                [f"{where}.label: must not contain a link (http:// or https://); the page is self-contained"],
            ),
            "a hint with a secure link in capitals": (
                {"hint": "See HTTPS://example.org"}, (),
                [f"{where}.hint: must not contain a link (http:// or https://); the page is self-contained"],
            ),
            "an unpaired surrogate": (
                {"hint": "a\ud800b"}, (), [f"{where}.hint: contains an unpaired surrogate; the page could not save it"],
            ),
            "required that is not a boolean": ({"required": "yes"}, (), [f"{where}.required: expected true or false, got text"]),
            "required as a number": ({"required": 1}, (), [f"{where}.required: expected true or false, got a number"]),
            "a misspelled key": ({"lable": "x"}, (), [f"{where}.lable: unknown key (did you mean 'label'?); prefix your own keys with x_"]),
        }
        for name, (update, remove, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(first_dpa(update, remove), expected)
        self.assertEqual(first_dpa({"x_note": "kept for reviewers", "_comment": "also ignored"}), [])
        # A question without its own error gets one that fits its control.
        questions = bundled()
        for question in questions["types"]["dpa"]["questions"][:4]:
            del question["error"]
        self.assertEqual(
            [q["error"] for q in form_for(questions)["types"][2]["questions"][:4]],
            [
                "Choose an answer to: Who decides how the data is used?",
                "Enter an answer to: What is the data used for?",
                "Enter an answer to: Which countries outside the EEA?",
                "Choose an answer to: Will sub-processors be involved?",
            ],
        )

    def test_fields_are_checked(self) -> None:
        def change(edit: Any) -> list[str]:
            questions = bundled()
            edit(questions["fields"])
            return problems(questions)

        cases = {
            "id": (lambda f: f.update(id={"label": "Ref"}), ["fields.id: the page sets id to REQ-DRAFT; legal gives the register number"]),
            "facts": (lambda f: f.update(facts={"label": "Facts"}), ["fields.facts: facts are filled from the type questions; ask them under types"]),
            "a comment among the fields": (lambda f: f.update(_comment="reviewed in October"), []),
            "legal's own field": (lambda f: f.update(sla_breached={"label": "Late?"}), ["fields.sla_breached: legal's own field; the page never asks it"]),
            "an unknown field": (lambda f: f.update(titel={"label": "x"}), ["fields.titel: not a request field the page asks (did you mean 'title'?)"]),
            "a missing decision field": (lambda f: f.pop("urgency"), ["fields.urgency: missing; the page always asks it"]),
            "a missing title": (lambda f: f.pop("title"), ["fields.title: missing; the page always asks it"]),
            "a condition on a field": (
                lambda f: f["personal_data"].update(show_if={"field": "urgency", "in": ["high"]}),
                ["fields.personal_data.show_if: only a type question can have a condition; a request field is always asked"],
            ),
            "not sure on a band": (
                lambda f: f["value_band"].update(not_sure="Not sure"),
                ["fields.value_band.not_sure: unknown key; prefix your own keys with x_"],
            ),
            "required on a decision field": (
                lambda f: f["personal_data"].update(required=False),
                ["fields.personal_data.required: unknown key; prefix your own keys with x_"],
            ),
            "a misspelled hint": (
                lambda f: f["title"].update(hnt="One line"),
                ["fields.title.hnt: unknown key (did you mean 'hint'?); prefix your own keys with x_"],
            ),
            "options on a yes or no": (
                lambda f: f["personal_data"].update(options={"true": "Yes"}),
                ["fields.personal_data.options: unknown key; prefix your own keys with x_"],
            ),
            "options on the type": (
                lambda f: f["type"].update(options={"dpa": "DPA"}),
                ["fields.type.options: unknown key; prefix your own keys with x_"],
            ),
            "an urgency left unlabelled": (
                lambda f: f["urgency"]["options"].pop("low"), ["fields.urgency.options.low: missing; label every urgency"],
            ),
            "an unknown urgency": (
                lambda f: f["urgency"]["options"].update(urgent="Now"),
                ["fields.urgency.options.urgent: not one of blocker, high, standard, low"],
            ),
            "a misspelled urgency": (
                lambda f: f["urgency"]["options"].update(hihg="Soon"),
                ["fields.urgency.options.hihg: not one of blocker, high, standard, low (did you mean 'high'?)"],
            ),
            "options that are not an object": (
                lambda f: f["value_band"].update(options=["a"]),
                ["fields.value_band.options: expected an object of value to label, got a list"],
            ),
            "type without a not-sure label": (lambda f: f["type"].pop("not_sure"), ["fields.type.not_sure: missing"]),
            "a blank not-sure label": (lambda f: f["type"].update(not_sure=" "), ["fields.type.not_sure: expected non-empty text, got text"]),
            "a field that is not an object": (lambda f: f.update(title="Title"), ["fields.title: expected an object, got text"]),
            "two bands with one label": (
                lambda f: f["value_band"]["options"].update({"250k-1m": "Over EUR 1 million"}),
                ["fields.value_band: 'Over EUR 1 million' labels both '250k-1m' and '>1m'; give each answer its own label"],
            ),
            "two bands whose labels differ only in spaces": (
                lambda f: f["value_band"]["options"].update({"250k-1m": "Over\u00a0 EUR 1 million "}),
                ["fields.value_band: 'Over EUR 1 million' labels both '250k-1m' and '>1m'; give each answer its own label"],
            ),
            "a label for a band the policy does not have": (lambda f: f["value_band"]["options"].update(huge=None), []),
            "two urgencies with one label": (
                lambda f: f["urgency"]["options"].update(low="Within a few days"),
                ["fields.urgency: 'Within a few days' labels both 'high' and 'low'; give each answer its own label"],
            ),
            "not sure labelled like a type": (
                lambda f: f["type"].update(not_sure="A dispute or claim"),
                ["fields.type: 'A dispute or claim' labels both 'dispute' and not_sure; give each answer its own label"],
            ),
        }
        for name, (edit, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(change(edit), expected)

    def test_odd_values_are_named_and_extensions_are_skipped(self) -> None:
        questions = bundled()
        questions["fields"]["title"]["label"] = True
        questions["fields"]["title"]["hint"] = None
        questions["types"]["dpa"]["questions"][0] = "Who decides?"
        questions["types"]["dpa"]["questions"][2]["show_if"] = "when it leaves the EEA"
        self.assertEqual(
            problems(questions),
            [
                "fields.title.label: expected non-empty text, got a boolean",
                "fields.title.hint: expected non-empty text, got null",
                "types.dpa.questions[0]: expected an object, got text",
                "types.dpa.questions[2].show_if: expected an object, got text",
            ],
        )
        questions = bundled()
        questions["fields"]["x_note"] = {"anything": True}
        questions["types"]["_draft"] = {"label": "Not yet"}
        questions["fields"]["urgency"]["options"]["x_note"] = "labels reviewed in October"
        questions["fields"]["value_band"]["options"]["_comment"] = "kept for reviewers"
        self.assertEqual(form_for(questions)["notes"], [])
        del questions["fields"]["value_band"]["options"]
        form = form_for(questions)
        band = next(f for f in form["fields"] if f["name"] == "value_band")
        self.assertEqual([o["label"] for o in band["options"]], list(default_policy().value_bands))
        self.assertEqual(form["notes"], [])
        # A radio answer always matches an option; anything else reads as not given.
        self.assertEqual(intake_module._answer_text(band, {"value_band": "nope"}, "Not given"), "Not given")
        # Urgencies keep the contract's order whatever order the file labels them in,
        # and show their own names when it labels none.
        urgency = questions["fields"]["urgency"]
        urgency["options"] = dict(reversed(list(urgency["options"].items())))
        options = next(f for f in form_for(questions)["fields"] if f["name"] == "urgency")["options"]
        self.assertEqual([o["value"] for o in options], list(URGENCIES))
        del urgency["options"]
        options = next(f for f in form_for(questions)["fields"] if f["name"] == "urgency")["options"]
        self.assertEqual(options, [{"label": u, "value": u} for u in URGENCIES])

    def test_a_contract_change_stops_the_build(self) -> None:
        schema = request_schema()
        schema["properties"]["deadline"] = {"type": ["integer", "null"]}
        with mock.patch.object(intake_module, "request_schema", return_value=schema):
            with self.assertRaisesRegex(RuntimeError, "the request contract changed: no page control for deadline"):
                form_for()

    def test_an_optional_field_left_out_is_not_asked(self) -> None:
        questions = bundled()
        del questions["fields"]["deadline"]
        form = form_for(questions)
        self.assertNotIn("deadline", [f["name"] for f in form["fields"]])
        self.assertEqual(form["notes"], ["the question file does not word deadline, so the page does not ask it"])
        questions["types"]["dpa"]["also_required"] = ["deadline"]
        self.assertEqual(problems(questions), ['types.dpa.also_required[0]: "deadline" is not asked: word it under fields first'])

    def test_an_answer_without_an_error_message_is_asked_for_by_its_label(self) -> None:
        questions = bundled()
        del questions["fields"]["title"]["error"]
        del questions["fields"]["urgency"]["error"]
        del questions["types"]["dpa"]["questions"][0]["error"]
        form = form_for(questions)
        answers = complete(form, "dpa")
        answers["fields"].update(title="", urgency="")
        answers["questions"]["processing_role"] = ""
        self.assertEqual(
            [p["message"] for p in check_answers(form, answers)],
            [
                "Enter an answer to: Short title",
                "Choose an answer to: How soon do you need an answer?",
                "Choose an answer to: Who decides how the data is used?",
            ],
        )

    def test_types_are_checked(self) -> None:
        def change(edit: Any) -> list[str]:
            questions = bundled()
            edit(questions["types"])
            return problems(questions)

        cases = {
            "a type without a label": (lambda t: t["dpa"].pop("label"), ["types.dpa.label: missing"]),
            "an unknown also-required field": (
                lambda t: t["dpa"].update(also_required=["value_band"]),
                ["types.dpa.also_required[0]: expected one of counterparty, requested_by, description, deadline, got 'value_band'"],
            ),
            "a field listed twice": (
                lambda t: t["dpa"].update(also_required=["counterparty", "counterparty"]),
                ['types.dpa.also_required[1]: "counterparty" is listed twice'],
            ),
            "a type hint with an unpaired surrogate": (
                lambda t: t["dpa"].update(hint="a\ud800b"),
                ["types.dpa.hint: contains an unpaired surrogate; the page could not save it"],
            ),
            "also-required that is not a list": (
                lambda t: t["dpa"].update(also_required="counterparty"),
                ["types.dpa.also_required: expected a list of fields, got text"],
            ),
            "questions that are not a list": (
                lambda t: t["dpa"].update(questions={}), ["types.dpa.questions: expected a list of questions, got an object"],
            ),
            "two types with blank labels": (
                lambda t: t["dpa"].update(label=" ") or t["ip"].update(label=" "),
                ["types.dpa.label: expected non-empty text, got text", "types.ip.label: expected non-empty text, got text"],
            ),
            "a type without questions": (lambda t: t["dpa"].pop("questions"), ["types.dpa.questions: missing"]),
            "a type that is not an object": (
                lambda t: t.update(dpa=[]),
                ["types.dpa: expected an object, got a list"],
            ),
            "a type label with a link": (
                lambda t: t["dpa"].update(label="DPA, see https://example.org"),
                ["types.dpa.label: must not contain a link (http:// or https://); the page is self-contained"],
            ),
        }
        for name, (edit, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(change(edit), expected)
        # A type the policy lacks is still checked, so the file stays fit for another policy.
        questions = bundled()
        questions["types"]["ip"]["questions"][0]["kind"] = "number"
        self.assertEqual(
            problems(questions, custom_policy()),
            ["types.ip.questions[0].kind: expected one of text, textarea, yes_no, choice, got 'number'"],
        )

    def test_the_top_level_is_checked(self) -> None:
        self.assertEqual(problems([]), ["expected an object, got a list"])
        questions = bundled()
        questions["schema"] = "legal-function-os.intake-questions.v2"
        questions["x_owner"] = "legal ops"
        self.assertEqual(
            problems(questions),
            [f"schema: expected {QUESTIONS_SCHEMA!r}, got 'legal-function-os.intake-questions.v2'"],
        )
        questions = bundled()
        questions["fields"] = []
        questions["types"] = "none"
        self.assertEqual(
            problems(questions),
            ["fields: expected an object, got a list", "types: expected an object, got text"]
            + [f"fields.{name}: missing; the page always asks it" for name in ()],
        )
        self.assertEqual(problems({"schema": QUESTIONS_SCHEMA}), ["name: missing", "fields: missing", "types: missing"])
        # null is a wrong type, not a missing key: a page with no fields or no types is refused.
        questions = bundled()
        questions["fields"] = None
        questions["types"] = None
        self.assertEqual(problems(questions), ["fields: expected an object, got null", "types: expected an object, got null"])

    def test_policy_text_the_page_carries_is_checked(self) -> None:
        policy = default_policy()
        cases = {
            "a link in the name": (
                {"name": "ACME policy, see https://wiki.example"},
                ["policy name 'ACME policy, see https://wiki.example': must not contain a link (http:// or https://); the page is self-contained"],
            ),
            "a surrogate in a type": (
                {"routing": {**policy.routing, "x\ud800": "General"}},
                ["policy request type 'x\\ud800': contains an unpaired surrogate; the page could not save it"],
            ),
            "a link in a band": (
                {"value_bands": (*policy.value_bands, "see http://x")},
                ["policy value band 'see http://x': must not contain a link (http:// or https://); the page is self-contained"],
            ),
            "a link in capitals": (
                {"name": "ACME policy, see HTTPS://wiki.example"},
                ["policy name 'ACME policy, see HTTPS://wiki.example': must not contain a link (http:// or https://); the page is self-contained"],
            ),
            "a link in a name with accents": (
                {"name": "Richtlinie für Verträge, https://wiki.example"},
                ["policy name 'Richtlinie für Verträge, https://wiki.example': must not contain a link (http:// or https://); the page is self-contained"],
            ),
            "a link in the name and in a band": (
                {"name": "see https://wiki.example", "value_bands": (*policy.value_bands, "see http://x")},
                [
                    "policy name 'see https://wiki.example': must not contain a link (http:// or https://); the page is self-contained",
                    "policy value band 'see http://x': must not contain a link (http:// or https://); the page is self-contained",
                ],
            ),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(problems(bundled(), replace(policy, **change)), expected)
        # The policy is blamed, not the question file, and nothing else is checked first.
        with self.assertRaises(PolicyError) as caught:
            build_intake_form(None, replace(policy, name="see https://wiki.example", source="team-policy.json"))
        self.assertEqual(caught.exception.source, "team-policy.json")
        self.assertEqual(len(caught.exception.problems), 1)
    def test_unreadable_files_are_reported(self) -> None:
        # Messages name the bundled file by what it is, not by where it is installed.
        self.assertEqual(load_intake_questions()[1], "bundled intake questions")
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "questions.json"
            bad.write_text("{", encoding="utf-8")
            with self.assertRaises(IntakeQuestionsError) as caught:
                load_intake_questions(str(bad))
            self.assertTrue(caught.exception.problems[0].startswith("not valid JSON: "))
            # A file an editor saved with a byte order mark still loads.
            marked = Path(tmp) / "marked.json"
            marked.write_text(json.dumps(bundled()), encoding="utf-8-sig")
            self.assertEqual(load_intake_questions(str(marked)), (bundled(), str(marked)))
            with self.assertRaises(IntakeQuestionsError) as caught:
                load_intake_questions(str(Path(tmp) / "missing.json"))
            self.assertTrue(caught.exception.problems[0].startswith("cannot read the file: "))
            self.assertIn("missing.json: cannot read the file", str(caught.exception))
            with self.assertRaises(IntakeQuestionsError) as caught:
                load_intake_questions(tmp)  # a folder, not a file
            self.assertTrue(caught.exception.problems[0].startswith("cannot read the file: "))


class AnswerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.form = form_for()

    def test_every_answer_the_page_accepts_passes_validation(self) -> None:
        properties = list(request_schema()["properties"])
        # The keys form has fact keys whose text order and key order differ.
        for policy, questions in ((default_policy(), None), (custom_policy(), None), (default_policy(), keys_questions())):
            form = form_for(questions, policy=policy)
            vectors = answer_vectors(form)
            self.assertGreater(len(vectors), 5000)
            accepted = 0
            for answers in vectors:
                found = check_answers(form, answers)
                self.assertEqual([p["id"] for p in found], expected_problems(form, answers), answers)
                request = request_from_answers(form, answers)
                self.assertEqual(request["id"], DRAFT_ID)
                self.assertEqual(list(request), [p for p in properties if p in request], answers)
                for key, value in request.items():
                    self.assertNotIn(value, (None, "", []), (key, answers))
                if "facts" in request:
                    keys = [fact.split(": ", 1)[0] for fact in request["facts"]]
                    self.assertEqual(keys, sorted(keys), answers)
                self.assertEqual(json.loads(render_download(request)), [request])
                if found:
                    continue
                accepted += 1
                report = validate_requests([request], policy)
                self.assertTrue(report.ok, (report.lines(), answers))
                warnings = [issue.field for issue in report.issues if issue.severity == "warning"]
                self.assertEqual(warnings, [] if "type" in request else ["type"], answers)
            self.assertGreater(accepted, 1000)

    def test_hidden_answers_are_never_saved(self) -> None:
        answers = complete(self.form, "ip")
        answers["questions"] = {"ip_kind": "0", "open_source": "0", "open_source_licences": "MIT"}
        self.assertEqual(request_from_answers(self.form, answers)["facts"], ["ip_kind: A brand or trademark"])
        answers["questions"]["ip_kind"] = "2"
        self.assertEqual(
            request_from_answers(self.form, answers)["facts"],
            ["ip_kind: Software or copyright", "open_source: yes", "open_source_licences: MIT"],
        )
        # A question whose controller is hidden is hidden too.
        answers["questions"]["ip_kind"] = "1"
        state = evaluate(self.form, answers)
        self.assertEqual(state["visible"], [True, False, False])
        self.assertEqual([r["label"] for r in review_rows(self.form, answers)][-1], "What is it about?")

    def test_a_type_can_make_an_optional_field_required(self) -> None:
        answers = complete(self.form, "commercial_contract")
        answers["fields"]["counterparty"] = " "
        self.assertEqual(check_answers(self.form, answers), [{"id": "f-counterparty", "message": "Enter the other party"}])
        answers = complete(self.form, "ip")
        answers["fields"]["counterparty"] = ""
        self.assertEqual(check_answers(self.form, answers), [])
        self.assertNotIn("counterparty", request_from_answers(self.form, answers))

    def test_not_sure_leaves_the_type_out(self) -> None:
        answers = complete(self.form, None)
        request = request_from_answers(self.form, answers)
        self.assertNotIn("type", request)
        self.assertNotIn("facts", request)
        self.assertEqual(review_rows(self.form, answers)[1]["answer"], "Something else, or not sure")

    def test_the_review_lists_every_question_with_its_answer(self) -> None:
        answers = complete(self.form, "dpa")
        answers["fields"]["deadline"] = ""
        rows = review_rows(self.form, answers)
        self.assertEqual(
            [(r["label"], r["answer"]) for r in rows][:5],
            [
                ("Short title", "title text"),
                ("What do you need help with?", "Data processing agreement (DPA)"),
                ("Other party", "counterparty text"),
                ("Value of the contract or claim", "No money involved"),
                ("Does it involve personal data?", "Yes"),
            ],
        )
        self.assertIn(("Date you need an answer by", "Not given"), [(r["label"], r["answer"]) for r in rows])
        self.assertEqual(rows[-1], {"id": "q2-sub_processor_list", "label": "Which sub-processors?", "answer": "sub_processor_list answer"})

    def test_text_is_trimmed_like_validation_and_kept_encodable(self) -> None:
        self.assertEqual(
            set(WHITESPACE), {chr(c) for c in range(sys.maxunicode + 1) if chr(c).isspace()} | {"\ufeff"}
        )
        self.assertEqual(clean_text("\x1c\x85 title \u3000\ufeff"), "title")
        self.assertEqual(clean_text("a\ud800b\udfff"), "a\ufffdb\ufffd")
        self.assertEqual(clean_text(None), "")
        answers = complete(self.form, "dpa")
        answers["fields"]["title"] = "a\ud800b"
        request = request_from_answers(self.form, answers)
        self.assertEqual(request["title"], "a\ufffdb")
        render_download(request).encode("utf-8")  # the file is always valid UTF-8

    def test_facts_are_sorted_by_key_like_the_bridge(self) -> None:
        form = form_for(keys_questions())
        answers = complete(form, "dpa")
        answers["questions"].update(item="x", item1="y")
        facts = request_from_answers(form, answers)["facts"]
        # Text order would put "item1: y" first, because a digit sorts before ":".
        self.assertLess(facts.index("item: x"), facts.index("item1: y"))
        given = {f.split(": ", 1)[0]: f.split(": ", 1)[1] for f in facts}
        self.assertEqual(facts, [f"{key}: {value}" for key, value in sorted(given.items()) if value])

    def test_question_keys_and_hints_at_their_limits(self) -> None:
        questions = bundled()
        questions["types"]["dpa"]["questions"][1]["key"] = "a" * 40
        questions["types"]["dpa"]["hint"] = "Have the agreement at hand."
        form = form_for(questions)
        self.assertEqual(form["types"][2]["questions"][1]["name"], "a" * 40)
        self.assertIn('<p class="hint">Have the agreement at hand.</p>', render_intake_html(form))

    def test_the_facts_match_the_pilot_bridge(self) -> None:
        tree = ast.parse(PILOT_MODELS.read_text(encoding="utf-8"))
        values = {
            target.id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name) and target.id in ("REQUIRED_FACTS", "REQUIRED_FACT_LABELS")
        }
        facts, labels = values["REQUIRED_FACTS"], values["REQUIRED_FACT_LABELS"]
        contract = next(t for t in self.form["types"] if t["key"] == "commercial_contract")
        asked = [q for q in contract["questions"]][: len(facts) - 1]
        self.assertEqual(facts[0], "counterparty")
        self.assertEqual(contract["also_required"], ["counterparty"])
        self.assertEqual([q["name"] for q in asked], list(facts[1:]))
        self.assertEqual([q["label"] for q in asked], [labels[k] for k in facts[1:]])
        # The pilot writes facts as "key: value" sorted by key, dropping blank ones.
        answers = complete(self.form, "commercial_contract")
        given = {q["name"]: f"{q['name']} answer" for q in asked}
        answers["questions"] = dict(given)
        self.assertEqual(
            request_from_answers(self.form, answers)["facts"],
            [f"{key}: {value}" for key, value in sorted(given.items()) if value],
        )

    def test_the_download_round_trips_through_the_cli(self) -> None:
        for type_key in ("dpa", None):
            request = request_from_answers(self.form, complete(self.form, type_key))
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / download_name(request)
                path.write_text(render_download(request), encoding="utf-8")
                code, out, err = run_cli(["validate", "--input", str(path), "--format", "json"])
                self.assertEqual(code, 0, err)
                warnings = [i["field"] for i in json.loads(out)["issues"] if i["severity"] == "warning"]
                self.assertEqual(warnings, [] if type_key else ["type"])
                code, out, err = run_cli(["triage", "--input", str(path), "--format", "json"])
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(out)["decisions"][0]["request_id"], DRAFT_ID)

    def test_download_names(self) -> None:
        self.assertEqual(download_name({"title": "NDA with Example GmbH (synthetic)"}), "legal-request-nda-with-example-gmbh-synthetic.json")
        self.assertEqual(download_name({"title": "Ärger / 2026"}), "legal-request-rger-2026.json")
        self.assertEqual(download_name({"title": "§§§"}), "legal-request.json")
        self.assertEqual(download_name({}), "legal-request.json")
        long = download_name({"title": "a" * 49 + " b" + "c" * 20})
        self.assertEqual(long, "legal-request-" + "a" * 49 + ".json")


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(argv)
    return code, out.getvalue(), err.getvalue()


class PageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.form = form_for()
        self.page = render_intake_html(self.form)
        self.parsed = parse(self.page)

    def test_the_page_carries_its_form_and_one_pinned_script(self) -> None:
        data = [s for a, s in self.parsed.scripts if a.get("type") == "application/json"]
        code = [(a, s) for a, s in self.parsed.scripts if a.get("type") != "application/json"]
        self.assertEqual(len(data), 1)
        # The whole form but its notes, which the script never reads.
        self.assertEqual(json.loads(data[0]), {k: v for k, v in self.form.items() if k != "notes"})
        self.assertEqual(len(code), 1)
        self.assertEqual(code[0][0], {})
        self.assertEqual(code[0][1], page_script())
        self.assertEqual(self.parsed.style, page_style())
        self.assertTrue(self.parsed.style.startswith(TOKENS_CSS))
        csp = next(a["content"] for t, a in self.parsed.elements if t == "meta" and a.get("http-equiv") == "Content-Security-Policy")

        def digest(text: str) -> str:
            return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")

        self.assertEqual(
            csp,
            f"default-src 'none'; script-src 'sha256-{digest(page_script())}'; "
            f"style-src 'sha256-{digest(page_style())}'; img-src 'none'; connect-src 'none'; "
            "form-action 'none'; base-uri 'none'",
        )

    def test_the_page_can_send_nothing(self) -> None:
        lowered = self.page.lower()
        for forbidden in ("http://", "https://", "<link", "<form", "<iframe", "<img", "<object", "<embed"):
            self.assertNotIn(forbidden, lowered)
        for forbidden in ("url(", "@import", "@font-face"):
            self.assertNotIn(forbidden, self.parsed.style)
        for tag, attrs in self.parsed.elements:
            for name in attrs:
                self.assertFalse(name.startswith("on"), (tag, name))
                self.assertNotIn(name, ("style", "action", "method", "formaction", "src"), (tag, name))
            if tag == "button":
                self.assertEqual(attrs.get("type"), "button")
        script = page_script()
        for forbidden in (
            "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "Function(",
            "fetch", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "localStorage",
            "sessionStorage", "indexedDB", "Date", "Math.random", "crypto", "window.open",
            "setInterval", "setTimeout", "postMessage", "location", "mailto:", ".style", "submit",
        ):
            self.assertNotIn(forbidden, script)
        # The script is generic: every field, option and wording comes from the data block.
        for word in ("value_band", "personal_data", "non_eea_transfer", "uncapped_liability", "urgency",
                     "counterparty", "requested_by", "sla_breached", "commercial_contract", "dpa", "<50k"):
            self.assertNotIn(word, script)
        with self.assertRaises(ValueError):
            render_intake_html({**self.form, "policy": "Policy at HTTPS://example.org"})
        with self.assertRaises(ValueError):
            render_intake_html({**self.form, "questions": "Questions at http://example.org"})

    def test_a_slot_name_in_the_text_stays_text(self) -> None:
        questions = bundled()
        questions["fields"]["title"]["hint"] = "Not __SCRIPT__ or __SPEC__ or __TYPES__"
        questions["name"] = "Questions __POLICY__"
        form = form_for(questions)
        page = render_intake_html(form)
        parsed = parse(page)
        data = next(s for a, s in parsed.scripts if a.get("type") == "application/json")
        self.assertEqual(json.loads(data), {k: v for k, v in form.items() if k != "notes"})
        self.assertEqual([s for a, s in parsed.scripts if not a], [page_script()])
        self.assertIn("Not __SCRIPT__ or __SPEC__ or __TYPES__", "".join(parsed.text))
        self.assertIn("Questions: Questions __POLICY__.", " ".join(" ".join(parsed.text).split()))

    def test_text_cannot_break_out_of_the_page(self) -> None:
        questions = bundled()
        questions["fields"]["title"]["label"] = "Title </script><b>bold</b> & \u2028 \"quoted\""
        questions["types"]["dpa"]["questions"][0]["options"][0] = "<i>We</i>"
        # Hints, a type's label and hint, and both names in the footer are escaped too.
        questions["fields"]["title"]["hint"] = "<b>hint</b>"
        questions["types"]["dpa"].update(label="<i>DPA</i>", hint="<b>Have it at hand</b>")
        questions["name"] = "<b>Questions</b>"
        page = render_intake_html(form_for(questions, replace(default_policy(), name="<i>Policy</i>")))
        parsed = parse(page)
        data = next(s for a, s in parsed.scripts if a.get("type") == "application/json")
        for raw in ("<", ">", "&", "\u2028"):
            self.assertNotIn(raw, data)
        self.assertNotIn("b", [t for t, _ in parsed.elements])
        self.assertNotIn("i", [t for t, _ in parsed.elements])
        self.assertIn("Title &lt;/script&gt;&lt;b&gt;bold&lt;/b&gt; &amp;", page)
        self.assertIn("Title </script><b>bold</b> &", "".join(parsed.text))

    def test_every_control_is_labelled_and_described(self) -> None:
        ids = {a["id"] for _, a in self.parsed.elements if a.get("id")}
        labels = {a["for"] for t, a in self.parsed.elements if t == "label" and a.get("for")}
        self.assertEqual(len([a["id"] for _, a in self.parsed.elements if a.get("id")]), len(ids))
        for tag, attrs in self.parsed.elements:
            if tag in ("input", "textarea"):
                self.assertIn(attrs["id"], labels, attrs)
            for ref in (attrs.get("aria-describedby") or "").split() + (attrs.get("aria-labelledby") or "").split():
                self.assertIn(ref, ids)
            if tag == "fieldset":
                self.assertIn(f"{attrs['id']}-0", ids)
        radios = [a for t, a in self.parsed.elements if t == "input" and a.get("type") == "radio"]
        self.assertFalse([a for a in radios if "checked" in a])  # nothing is preselected
        counts = {}
        for tag, _ in self.parsed.elements:
            counts[tag] = counts.get(tag, 0) + 1
        self.assertEqual(counts["fieldset"], counts["legend"])
        sections = {a["id"]: a for t, a in self.parsed.elements if t == "section" and a.get("id", "").startswith("type-")}
        self.assertEqual(sorted(sections), sorted(t["id"] for t in self.form["types"]))
        self.assertTrue(all("hidden" in a for a in sections.values()))
        summary = next(a for _, a in self.parsed.elements if a.get("id") == "error-summary")
        self.assertEqual((summary["role"], summary["tabindex"], "hidden" in summary), ("alert", "-1", True))
        status = next(a for _, a in self.parsed.elements if a.get("id") == "status")
        self.assertEqual(status["role"], "status")
        # The type announcement has a region of its own that takes no space on the page.
        type_status = next(a for _, a in self.parsed.elements if a.get("id") == "type-status")
        self.assertEqual((type_status["role"], type_status["class"]), ("status", "visually-hidden"))
        conditional = {q["id"] for t in self.form["types"] for q in t["questions"] if "show_if" in q}
        hidden = {a["id"][: -len("-field")] for _, a in self.parsed.elements if a.get("id", "").endswith("-field") and "hidden" in a}
        self.assertEqual(hidden, conditional)
        self.assertIn("@media (max-width:640px)", self.parsed.style)
        self.assertIn("[hidden] { display:none !important; }", self.parsed.style)
        # Each hint is linked to its control, and each error starts hidden.
        attrs = {a["id"]: a for _, a in self.parsed.elements if a.get("id")}
        items = [*self.form["fields"], *(q for t in self.form["types"] for q in t["questions"])]
        for item in items:
            expected = f"{item['id']}-hint" if item["hint"] else None
            self.assertEqual(attrs[item["id"]].get("aria-describedby"), expected, item["id"])
            self.assertIn("hidden", attrs[f"{item['id']}-error"])
            self.assertIn(f"{item['id']}-error-text", attrs)
            # A screen reader hears "Error:" before each message.
            self.assertIn(f'id="{item["id"]}-error" hidden><span class="visually-hidden">Error: </span>', self.page)
            # The label says "(optional)" exactly when the answer may be left out.
            label = re.search(
                rf'(?:<label for="{item["id"]}">|<fieldset id="{item["id"]}"[^>]*><legend>)(.*?)</(?:label|legend)>',
                self.page,
            )
            self.assertEqual('<span class="optional"' in label.group(1), not item["required"], item["id"])
        # Every question that may be left out says so, the type questions too.
        marks = [a for t, a in self.parsed.elements if t == "span" and a.get("class") == "optional"]
        self.assertEqual(len(marks), len([item for item in items if not item["required"]]))
        # Each question's control follows its kind.
        tags = {a["id"]: t for t, a in self.parsed.elements if a.get("id")}
        element = {"text": "input", "textarea": "textarea", "yes_no": "fieldset", "choice": "fieldset"}
        for question in (q for t in self.form["types"] for q in t["questions"]):
            self.assertEqual(tags[question["id"]], element[question["kind"]], question["id"])

    def test_a_type_with_no_questions_says_so(self) -> None:
        form = form_for(policy=custom_policy())
        empty = next(t for t in form["types"] if not t["questions"])
        self.assertIn(
            f'<h2 id="{empty["id"]}-h">{empty["label"]}: a few more questions</h2>'
            '<p class="muted">No further questions for this type.</p></section>',
            render_intake_html(form),
        )

    def test_the_words_never_claim_to_send_or_decide(self) -> None:
        text = " ".join(" ".join(self.parsed.text).split())
        for sentence in (
            "This page sends nothing.",
            "A person in legal reviews every request and makes every decision.",
            "Nothing here is legal advice.",
            "Demonstration only: use made-up details, never real client, customer or personal data.",
            "Saves the file on this device. Nothing is sent.",
            "Its reference is REQ-DRAFT until legal gives it a register number.",
        ):
            self.assertIn(sentence, text)
        words = text + " " + " ".join(
            str(v) for item in (*self.form["fields"], *(q for t in self.form["types"] for q in t["questions"]))
            for k, v in item.items() if k in ("label", "hint", "error")
        ) + " " + " ".join(t["label"] for t in self.form["types"])
        policy = default_policy()
        queues = {*policy.routing.values(), policy.unknown_type_queue, policy.non_eea_transfer_queue}
        banned = [*queues, "submit", "send", "approve", "approved", "approval", "queue", "priority", "risk",
                  "Reviewer", "Legal Ops Lead", "General Counsel", "Board note", "SLA"]
        for word in banned:
            self.assertIsNone(re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", words, re.IGNORECASE), word)
        self.assertNotIn("✓", self.page)

    def test_rendering_is_deterministic_and_matches_the_committed_example(self) -> None:
        self.assertEqual(self.page, render_intake_html(form_for()))
        self.assertEqual(self.page, EXAMPLE.read_text(encoding="utf-8"))

    def test_the_question_sheet_says_what_the_page_asks(self) -> None:
        sheet = render_intake_markdown(self.form)
        self.assertIn(
            f"Questions: {self.form['questions']}. Value bands and request types follow the "
            f"policy: {self.form['policy']}.",
            sheet,
        )
        self.assertIn("- **Short title** (`title`), required.", sheet)
        self.assertIn(
            "- **Value of the contract or claim** (`value_band`), required. Choices: No money involved; "
            "Under EUR 50,000; EUR 50,000 to EUR 250,000; EUR 250,000 to EUR 1 million; Over EUR 1 million.",
            sheet,
        )
        self.assertIn("- **Other party** (`counterparty`), optional. Hint: The company or person on the other side, if there is one.\n", sheet)
        self.assertIn("## Data processing agreement (DPA) (`dpa`)", sheet)
        self.assertIn("Also required for this type: Other party.", sheet)
        self.assertIn(
            "1. **Who decides how the data is used?** (`processing_role`, choice), required. Choices: "
            "We decide (we are the controller); The other party decides (we are the processor); Not sure.\n",
            sheet,
        )
        self.assertIn(
            '3. **Which countries outside the EEA?** (`transfer_countries`, text), required. Shown when '
            '"Does it involve any data sent to or accessed from outside the EEA?" is Yes. '
            "Hint: If you do not know, write not sure.\n",
            sheet,
        )
        self.assertIn(
            '2. **When is a reply due?** (`reply_due`, text), required. Shown when "Where does it stand?" is '
            "A formal letter or claim has arrived or Court or arbitration proceedings have started.",
            sheet,
        )
        self.assertNotIn("## Notes", sheet)
        custom = render_intake_markdown(form_for(policy=custom_policy()))
        self.assertIn("## Notes", custom)
        for note in form_for(policy=custom_policy())["notes"]:
            self.assertIn(f"\n- {note}\n", custom)
        self.assertIn("## regulatory (`regulatory`)\n\nNo further questions.", custom)
        # A line break in a label stays inside its bullet.
        questions = bundled()
        questions["fields"]["title"]["label"] = "Short\ntitle"
        self.assertIn("\n- **Short title** (`title`), required.", render_intake_markdown(form_for(questions)))


class CliTests(unittest.TestCase):
    def test_out_writes_the_committed_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli(["intake-page", "--out", tmp])
            self.assertEqual((code, out), (0, ""))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["intake-page.html"])
            self.assertEqual((Path(tmp) / "intake-page.html").read_bytes(), EXAMPLE.read_bytes())
            self.assertIn("wrote ", err)

    def test_prints_the_sheet_or_the_form(self) -> None:
        code, out, _ = run_cli(["intake-page", "--format", "json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), form_for())
        code, out, _ = run_cli(["intake-page"])
        self.assertEqual(code, 0)
        self.assertEqual(out, render_intake_markdown(form_for()))

    def test_bad_questions_stop_before_anything_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            questions = bundled()
            questions["types"]["dpa"]["questions"][1]["show_if"] = {"field": "sub_processors", "in": [True]}
            questions["fields"]["title"]["label"] = " "
            path = Path(tmp) / "questions.json"
            path.write_text(json.dumps(questions), encoding="utf-8")
            out_dir = Path(tmp) / "out"
            code, out, err = run_cli(["intake-page", "--questions", str(path), "--out", str(out_dir)])
            self.assertEqual((code, out), (2, ""))
            # One line for each problem, each naming the file.
            self.assertIn(f"error: {path}: fields.title.label: expected non-empty text, got text\n", err)
            self.assertIn(f"error: {path}: types.dpa.questions[1].show_if.field:", err)
            self.assertTrue(err.endswith("The intake questions cannot be used. Nothing was written.\n"))
            self.assertFalse(out_dir.exists())
            code, _, err = run_cli(["intake-page", "--questions", str(Path(tmp) / "nope.json")])
            self.assertEqual(code, 2)
            self.assertIn("cannot read the file", err)
            # A file saved in another encoding is reported, not a traceback.
            latin = Path(tmp) / "latin.json"
            latin.write_bytes('{"name": "Fragen f\u00fcr Vertr\u00e4ge"}'.encode("latin-1"))
            code, out, err = run_cli(["intake-page", "--questions", str(latin)])
            self.assertEqual((code, out), (2, ""))
            self.assertIn(f"error: {latin}: cannot read the file: it is not UTF-8 text (byte 0xfc at position 18); save it as UTF-8\n", err)

    def test_policy_text_with_a_link_stops_before_anything_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            data = default_policy().to_dict()
            data["name"] = "ACME policy, see https://wiki.example"
            path.write_text(json.dumps(data), encoding="utf-8")
            out_dir = Path(tmp) / "out"
            code, out, err = run_cli(["intake-page", "--policy", str(path), "--out", str(out_dir)])
            self.assertEqual((code, out), (2, ""))
            self.assertIn(f"error: {path}: policy name 'ACME policy, see https://wiki.example': must not contain a link", err)
            self.assertTrue(err.endswith("The policy cannot be used for the intake page. Nothing was written.\n"), err)
            self.assertFalse(out_dir.exists())

    def test_unused_keys_with_a_link_are_noted_and_kept_off_the_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            questions = bundled()
            questions["types"]["see https://wiki.example"] = {"label": "Wiki", "questions": []}
            questions["fields"]["value_band"]["options"]["http://x"] = "A band the policy lacks"
            path = Path(tmp) / "questions.json"
            path.write_text(json.dumps(questions), encoding="utf-8")
            code, out, err = run_cli(["intake-page", "--questions", str(path), "--out", tmp])
            self.assertEqual((code, out), (0, ""), err)
            self.assertIn('note: intake questions for "see https://wiki.example" are not used', err)
            self.assertIn("note: fields.value_band.options.http://x: the policy has no value band", err)
            page = (Path(tmp) / "intake-page.html").read_text(encoding="utf-8")
            self.assertNotIn("http", page.lower().replace("http-equiv", ""))

    def test_a_page_that_cannot_be_rendered_leaves_no_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            with self.assertRaises(ValueError):
                write_intake_page({**form_for(), "policy": "see https://wiki.example"}, out_dir)
            self.assertFalse(out_dir.exists())

    def test_a_policy_sets_the_bands_and_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(custom_policy().to_dict()), encoding="utf-8")
            code, out, err = run_cli(["intake-page", "--policy", str(path), "--format", "json"])
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["policy"], "Custom test policy")
            self.assertIn('note: request type "regulatory" has no intake questions', err)
            # The notes are printed with --out too.
            code, _, err = run_cli(["intake-page", "--policy", str(path), "--out", str(Path(tmp) / "out")])
            self.assertEqual(code, 0, err)
            self.assertIn('note: request type "regulatory" has no intake questions', err)


@unittest.skipUnless(node_available() or os.environ.get(REQUIRE_JS_TESTS) == "1", "node is not installed")
class ScriptTests(unittest.TestCase):
    """The page's own script, run in Node without a document, against this module."""

    HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const [scriptPath, formPath, vectorsPath, outPath, names] = process.argv.slice(2);
const context = {};
vm.createContext(context);
vm.runInContext(fs.readFileSync(scriptPath, "utf8"), context);
if (typeof context.intakeCore !== "function") { process.exit(4); }
const results = {};
for (const name of names.split(",")) {
  const core = context.intakeCore(JSON.parse(fs.readFileSync(formPath + "." + name, "utf8")));
  results[name] = JSON.parse(fs.readFileSync(vectorsPath + "." + name, "utf8")).map((a) => ({
    download: core.download(a), check: core.check(a), name: core.name(a), rows: core.rows(a),
  }));
}
fs.writeFileSync(outPath, JSON.stringify(results));
"""

    def setUp(self) -> None:
        if not node_available():
            self.fail("REQUIRE_JS_TESTS=1 but node is not installed")

    def test_the_script_parses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.js"
            path.write_text(page_script(), encoding="utf-8")
            result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_script_saves_what_this_module_saves(self) -> None:
        forms = {"form": form_for(), "custom": form_for(policy=custom_policy()), "keys": form_for(keys_questions())}
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "page.js").write_text(page_script(), encoding="utf-8")
            (base / "harness.cjs").write_text(self.HARNESS, encoding="utf-8")
            vectors = {}
            for name, form in forms.items():
                (base / f"form.json.{name}").write_text(json.dumps(form), encoding="utf-8")
                vectors[name] = answer_vectors(form)
                (base / f"vectors.json.{name}").write_text(json.dumps(vectors[name]), encoding="utf-8")
            result = subprocess.run(
                ["node", str(base / "harness.cjs"), str(base / "page.js"), str(base / "form.json"),
                 str(base / "vectors.json"), str(base / "out.json"), ",".join(forms)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            results = json.loads((base / "out.json").read_text(encoding="utf-8"))
        for name, form in forms.items():
            self.assertEqual(len(results[name]), len(vectors[name]))
            for answers, got in zip(vectors[name], results[name], strict=True):
                request = request_from_answers(form, answers)
                expected = {
                    "download": render_download(request),
                    "check": check_answers(form, answers),
                    "name": download_name(request),
                    "rows": review_rows(form, answers),
                }
                self.assertEqual(got, expected, answers)

    def test_the_script_only_exports_its_rules_without_a_document(self) -> None:
        harness = (
            "const vm = require('vm'); const fs = require('fs');"
            "const c = { document: { getElementById: () => { throw new Error('dom used'); } } };"
            "vm.createContext(c);"
            "try { vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), c); } catch (e) { console.log(e.message); }"
            "console.log(typeof c.intakeCore);"
        )
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "page.js").write_text(page_script(), encoding="utf-8")
            result = subprocess.run(["node", "-e", harness, str(Path(tmp) / "page.js")], capture_output=True, text=True)
        self.assertEqual(result.stdout.split("\n")[:2], ["dom used", "undefined"])


if __name__ == "__main__":
    unittest.main()
