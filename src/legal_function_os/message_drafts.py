"""Turn a synthetic message export into request drafts for legal to complete.

A team that takes requests in a chat channel or a shared mailbox can save the messages
as JSON lines, one message per line, and pass the file to ``legal-function-os
message-drafts``. Each message becomes one ``legal-request.v1`` draft:

- Values are copied only from labelled lines such as ``Value band: <50k``. A label is
  matched the way a CSV header is ("Value band", "value-band" and "valueBand" all mean
  ``value_band``), and a yes/no answer is read with the same words. A value is copied
  as written, so ``>1M`` stays ``>1M`` and validation names it. Nothing is read from the
  rest of the text: the subject becomes the title, and the whole text the description.
- Every field the intake page always asks is in every draft. A field the message does
  not state is left blank (``""``) and named. Every blank but ``type`` is an error, so
  ``validate`` and ``triage`` refuse the draft until a person in legal fills it; left
  out, the field would take its default (false or none), which can lower the risk. A
  blank ``type`` is only a warning: the draft validates, and ``triage`` decides it,
  marked for manual triage, without the type's own rules, which can also lower the
  risk. Legal fills it before triage.
- Fields legal sets (the id, the service-level flag, ``facts`` and the rest) are never
  copied. Drafts are numbered ``REQ-DRAFT-1``, ``REQ-DRAFT-2`` and so on in message
  order, keep their message id in ``x_message_id``, and legal renumbers them.

Every sender must be a synthetic ``syn-`` handle, the pilot's pattern for synthetic
actors. That marks the export as synthetic data; it says nothing about who sent a
message, and senders are not verified. The command reads one local file. It connects to
no chat or mail service, captures nothing live, replies to no one and decides nothing.
It is a CLI command and not an MCP tool, so no model feeds it messages or fills its
blanks (ADR 0009). Deterministic: nothing reads a clock.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legal_function_os.bundled import bundled_path, not_utf8, read_utf8
from legal_function_os.intake_csv import HEADER_ALIASES
from legal_function_os.intake_page import ALWAYS_ASKED, NOT_ASKED, clean_text
from legal_function_os.policy import Policy, default_policy
from legal_function_os.validation import (
    AUXILIARY_FIELDS,
    BOOLEAN_FIELDS,
    BOOLEAN_WORDS,
    EXTENSION_PREFIXES,
    REQUEST_FIELDS,
    misspelled_field,
    normalise_field_name,
    validate_requests,
)

EXPORT_FILE = "sample_messages.jsonl"
BUNDLED_SOURCE = "bundled synthetic message export"
JSON_FILE = "message-drafts.json"
MARKDOWN_FILE = "message-drafts.md"
DRAFT_PREFIX = "REQ-DRAFT-"
# The pilot's pattern for synthetic actor ids (supervised-agent/src/pilot/models.py).
SENDER = re.compile(r"syn-[a-z0-9-]+\Z")
MESSAGE_KEYS = ("message_id", "sender", "channel", "sent_at", "subject", "text")
REQUIRED_KEYS = ("message_id", "sender", "text")
# Fields a labelled line can fill. The rest of the text is the description.
COPIED = (*ALWAYS_ASKED, "counterparty", "requested_by", "deadline")
# Legal's own fields: a labelled line naming one is noted and not copied.
LEGAL_SETS = ("id", *NOT_ASKED, "facts")
# Draft keys follow the request contract, as the intake page writes them.
FIELD_ORDER = (*REQUEST_FIELDS, *AUXILIARY_FIELDS)
# A label starts the line: letters, then letters, spaces, dots, hyphens or underscores,
# then a colon. A quoted reply ("> Value band: ...") or a list item is not a label.
# The value is everything after the colon, trimmed by clean_text: a lazy value followed by
# trailing blanks would backtrack quadratically on a long run of spaces.
LABEL = re.compile(r"[ \t]*([A-Za-z][A-Za-z _.\-]{0,39}?)[ \t]*:(.*)\Z")


class MessageExportError(ValueError):
    """A message export that cannot be read; ``problems`` lists every reason."""

    def __init__(self, source: str, problems: list[str]) -> None:
        super().__init__(f"{source}: " + "; ".join(problems))
        self.source = source
        self.problems = problems


@dataclass(frozen=True)
class Message:
    """One message of the export, its text cleaned as the intake page cleans an answer."""

    line: int
    message_id: str
    sender: str
    channel: str
    sent_at: str
    subject: str
    text: str


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    return "an array" if isinstance(value, list) else "an object"


def load_message_export(path: str | None = None) -> tuple[str, str]:
    """The export's text (the bundled one without ``path``) and its name for messages."""

    if path == "-":
        raise MessageExportError(
            "standard input",
            ["standard input is not read; save the export as a file and pass its path"],
        )
    source = BUNDLED_SOURCE if path is None else path
    try:
        text = read_utf8(bundled_path(EXPORT_FILE) if path is None else Path(path))
    except OSError as exc:
        raise MessageExportError(source, [f"cannot read the file: {exc.strerror or exc}"]) from None
    except UnicodeDecodeError as exc:
        raise MessageExportError(source, [f"cannot read the file: {not_utf8(exc)}"]) from None
    return text, source


def _unknown_key(key: str) -> str:
    name = normalise_field_name(key)
    close = [name] if name in MESSAGE_KEYS else difflib.get_close_matches(name, MESSAGE_KEYS, n=1)
    hint = f" (did you mean {close[0]!r}?)" if close else ""
    return f"unknown key {key!r}{hint}; prefix your own keys with x_"


def _line_problems(item: dict[str, Any]) -> list[str]:
    problems = [
        _unknown_key(key)
        for key in item
        if key not in MESSAGE_KEYS and not key.startswith(EXTENSION_PREFIXES)
    ]
    for key in MESSAGE_KEYS:
        value = item.get(key)
        if value is not None and not isinstance(value, str):
            problems.append(f"{key}: expected a string, got {_kind(value)}")
        elif key in REQUIRED_KEYS and not clean_text(value):
            problems.append(f"{key}: missing; every message needs one")
    sender = item.get("sender")
    if isinstance(sender, str) and clean_text(sender) and not SENDER.match(sender):
        problems.append(
            f"sender: {sender!r} is not a synthetic sender (syn- followed by lower-case "
            "letters, digits or hyphens); this command reads synthetic exports only"
        )
    return problems


def read_messages(text: str, source: str) -> list[Message]:
    """The messages of a JSON-lines export, or every problem with its line number.

    Lines are numbered as an editor shows them, and blank lines are skipped. Keys that
    start with ``x_`` or ``_`` are ignored.
    """

    if text.lstrip().startswith("["):
        raise MessageExportError(
            source,
            [
                "this is a JSON array, not JSON lines (one message object per line); "
                "a JSON array of requests goes to validate or triage, not here"
            ],
        )
    problems: list[str] = []
    messages: list[Message] = []
    seen: dict[str, int] = {}
    for number, raw in enumerate(text.split("\n"), start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            problems.append(f"line {number}: not valid JSON: {exc.msg} (column {exc.colno})")
            continue
        except RecursionError:
            problems.append(f"line {number}: nested too deeply to read")
            continue
        if not isinstance(item, dict):
            problems.append(f"line {number}: expected a JSON object (one message per line), got {_kind(item)}")
            continue
        found = _line_problems(item)
        problems += [f"line {number}: {problem}" for problem in found]
        message_id = clean_text(item.get("message_id"))
        if message_id in seen:
            problems.append(f"line {number}: message_id: {message_id!r} repeats line {seen[message_id]}")
        elif message_id:
            seen[message_id] = number
        if not found:
            messages.append(
                Message(
                    line=number,
                    message_id=message_id,
                    sender=item["sender"],
                    channel=clean_text(item.get("channel")),
                    sent_at=clean_text(item.get("sent_at")),
                    subject=clean_text(item.get("subject")),
                    text=clean_text(item["text"]),
                )
            )
    if problems:
        raise MessageExportError(source, problems)
    return messages


def _value(name: str, text: str) -> Any:
    return BOOLEAN_WORDS.get(text.lower(), text) if name in BOOLEAN_FIELDS else text


def labelled_values(text: str) -> tuple[dict[str, Any], list[str]]:
    """The values a message's labelled lines state, and notes on the labels not copied.

    A label naming a field legal sets, or one that looks like a misspelled request
    field, is noted. Any other label is ignored: the whole text is the description. An
    empty value is not given, and a field given two different ways is not copied.
    """

    found: dict[str, list[Any]] = {}
    notes: list[str] = []
    for raw in text.splitlines():
        match = LABEL.match(raw)
        if not match:
            continue
        label, value = match.group(1).strip(), clean_text(match.group(2))
        name = normalise_field_name(label)
        name = HEADER_ALIASES.get(name, name)
        if name in COPIED:
            if value:
                found.setdefault(name, []).append(_value(name, value))
        elif name in LEGAL_SETS:
            notes.append(f"{label!r} is set by legal; not copied")
        else:
            meant = misspelled_field(name)
            if meant:
                notes.append(f"{label!r} looks like {meant!r}; not copied")
    values: dict[str, Any] = {}
    for name, given in found.items():
        distinct = list(dict.fromkeys(given))
        if len(distinct) > 1:
            notes.append(f"{name} is given {len(distinct)} different ways; not copied")
        else:
            values[name] = distinct[0]
    return values, list(dict.fromkeys(notes))


def draft_request(position: int, message: Message) -> tuple[dict[str, Any], dict[str, Any]]:
    """The draft for one message, numbered by its position, and what was done with it."""

    values, notes = labelled_values(message.text)
    subject = " ".join(message.subject.split())
    title_from = "subject" if subject else "Title line" if "title" in values else None
    if subject and values.get("title", subject) != subject:
        notes.append("the subject and the Title line differ; the subject is used")
    if subject:
        values["title"] = subject
    draft_id = f"{DRAFT_PREFIX}{position}"
    request: dict[str, Any] = {}
    copied: list[str] = []
    blank: list[str] = []
    not_given: list[str] = []
    for name in FIELD_ORDER:
        if name == "id":
            request["id"] = draft_id
        elif name == "description":
            request["description"] = message.text
        elif name in values:
            request[name] = values[name]
            copied.append(name)
        elif name in ALWAYS_ASKED:
            request[name] = ""
            blank.append(name)
        elif name in COPIED:
            not_given.append(name)
    request["x_message_id"] = message.message_id
    entry = {
        "line": message.line,
        "message_id": message.message_id,
        "sender": message.sender,
        "channel": message.channel,
        "sent_at": message.sent_at,
        "text": message.text,
        "draft_id": draft_id,
        "title_from": title_from,
        "copied": copied,
        "blank": blank,
        "not_given": not_given,
        "notes": notes,
    }
    return request, entry


def build_message_drafts(
    messages: list[Message], policy: Policy | None = None, source: str = BUNDLED_SOURCE
) -> dict[str, Any]:
    """Drafts for every message, and per message what was copied, left blank and noted.

    ``check`` holds what validation says about the values that were copied, checked
    against ``policy``; the blanks are left out of it, because legal fills them.
    """

    rules = policy if policy is not None else default_policy()
    pairs = [draft_request(position, message) for position, message in enumerate(messages, start=1)]
    drafts = [draft for draft, _entry in pairs]
    entries = [entry for _draft, entry in pairs]
    report = validate_requests(drafts, rules)
    for index, entry in enumerate(entries):
        entry["check"] = [
            {"severity": issue.severity, "field": issue.field, "message": issue.message}
            for issue in report.issues
            if issue.index == index and issue.field not in entry["blank"]
        ]
    notes = [] if messages else ["the export holds no messages"]
    return {"source": source, "policy": rules.name, "drafts": drafts, "messages": entries, "notes": notes}


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def summary_line(result: dict[str, Any]) -> str:
    """How many drafts there are, and how many legal must fill before validate and triage."""

    drafts, messages = len(result["drafts"]), len(result["messages"])
    head = f"{_plural(drafts, 'draft')} from {_plural(messages, 'message')}"
    if not messages:
        return f"{head}."
    open_drafts = sum(1 for entry in result["messages"] if entry["blank"])
    if not open_drafts:
        return f"{head}; no draft has blanks."
    verb = "has" if open_drafts == 1 else "have"
    return f"{head}; {open_drafts} {verb} blanks for legal to fill before validate and triage."


def render_message_drafts_json(result: dict[str, Any]) -> str:
    """The drafts file: a JSON array of ``legal-request.v1`` drafts, which ``validate`` reads."""

    return json.dumps(result["drafts"], indent=2, ensure_ascii=False) + "\n"


def _md_line(value: Any) -> str:
    return " ".join(str(value).split())


def _names(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names) if names else "none"


def _message_line(entry: dict[str, Any]) -> str:
    parts = [f"Message {_md_line(entry['message_id'])} (line {entry['line']}) from {entry['sender']}"]
    if entry["channel"]:
        parts.append(f"in {_md_line(entry['channel'])}")
    if entry["sent_at"]:
        parts.append(f"sent {_md_line(entry['sent_at'])}")
    return ", ".join(parts) + "."


def _copied_line(name: str, value: Any, title_from: str | None) -> str:
    shown = str(value).lower() if isinstance(value, bool) else _md_line(value)
    where = f" (from the {title_from})" if name == "title" else ""
    return f"- `{name}`: {shown}{where}"


def _draft_section(draft: dict[str, Any], entry: dict[str, Any]) -> list[str]:
    title = _md_line(draft["title"]) or "(no title)"
    lines = [f"## {entry['draft_id']}: {title}", "", _message_line(entry), ""]
    lines += [f"    {text}".rstrip() for text in entry["text"].splitlines()]
    lines += ["", "Copied:", ""]
    lines += [_copied_line(name, draft[name], entry["title_from"]) for name in entry["copied"]] or ["- none"]
    lines += ["", f"Blank for legal to fill: {_names(entry['blank'])}.", ""]
    lines += [f"Not given: {_names(entry['not_given'])}."]
    if entry["check"]:
        lines += ["", "Check:", ""]
        lines += [
            f"- {issue['severity']}: `{issue['field']}`: {_md_line(issue['message'])}"
            for issue in entry["check"]
        ]
    if entry["notes"]:
        lines += ["", "Notes:", ""]
        lines += [f"- {_md_line(note)}" for note in entry["notes"]]
    return [*lines, ""]


def render_message_drafts_markdown(result: dict[str, Any]) -> str:
    """The drafts for a reviewer in legal: each message, what was copied, what is blank."""

    lines = [
        "# Message drafts",
        "",
        f"Source: {_md_line(result['source'])}. Policy: {_md_line(result['policy'])}. "
        f"{summary_line(result)}",
        "",
        "Drafts for legal to complete. Nothing was sent and nothing was decided: no risk, "
        "priority, queue, service level or approval chain. Values were copied only from "
        "labelled lines such as `Value band: <50k`; nothing was read from the rest of a "
        "message. Senders are copied as written in the export and are not verified: a "
        "`syn-` sender marks the export as synthetic, and it says nothing about who sent a "
        "message. Not legal advice.",
        "",
    ]
    if not result["messages"]:
        lines += ["No messages in the export.", ""]
    for draft, entry in zip(result["drafts"], result["messages"], strict=True):
        lines += _draft_section(draft, entry)
    lines += [
        "## Before triage",
        "",
        "1. Fill every blank from the message, or by asking its sender. Do not delete a "
        "blank field: a field left out takes its default (false or none), which can lower "
        "the risk. `validate` only warns about a blank `type`, and `triage` then decides "
        "the draft without the type's own rules, which can lower the risk: fill `type` "
        "before triage.",
        "2. Give each draft a register number in place of its `REQ-DRAFT-` id.",
        "3. Run `legal-function-os validate` on the drafts file, then `triage`.",
    ]
    return "\n".join(lines) + "\n"


def write_message_drafts(result: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    """Write message-drafts.json and message-drafts.md, both rendered before either is written."""

    files = {
        "json": (JSON_FILE, render_message_drafts_json(result).encode("utf-8")),
        "md": (MARKDOWN_FILE, render_message_drafts_markdown(result).encode("utf-8")),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, (name, data) in files.items():
        path = output_dir / name
        path.write_bytes(data)
        paths[key] = path
    return paths
