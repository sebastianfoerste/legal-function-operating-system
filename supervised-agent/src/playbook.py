"""Versioned playbooks that propose document-specific changes.

A playbook rule locates one clause in the indexed document, checks whether the
wording deviates from the standard position and, if so, proposes a change at a
stable locator. The engine is deterministic: no model call, no network access.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.docx_redline import DocumentIndex, Operation, Paragraph, RedlineEdit

DEFAULT_PLAYBOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "pilot"
    / "playbook"
    / "saas-msa-deviation-playbook.v1.json"
)

ChangeDecision = Literal["pending", "accepted", "rejected", "amended", "clarification_requested"]
RuleKind = Literal["replace_phrase", "delete_paragraph", "insert_after"]


class ChangeAnchor(BaseModel):
    """Stable locator: the paragraph is identified by a hash of its text, the
    position is a tie-breaker only, and the span addresses characters inside it."""

    paragraph_index: int
    paragraph_hash: str
    clause_ref: str | None = None
    start: int | None = None
    end: int | None = None

    def label(self) -> str:
        span = f"[{self.start}:{self.end}]" if self.start is not None else ""
        clause = f"clause {self.clause_ref} " if self.clause_ref else ""
        return f"{clause}para:{self.paragraph_index}@{self.paragraph_hash}{span}"


class DocumentChange(BaseModel):
    id: str
    locator: str
    original_text: str
    proposed_text: str
    rationale: str
    source_refs: list[str]
    decision: ChangeDecision = "pending"
    anchor: ChangeAnchor | None = None
    operation: Operation = "replace_span"
    rule_id: str | None = None
    amended_text: str | None = None
    decision_reason: str | None = None

    @property
    def final_text(self) -> str:
        return (
            self.amended_text
            if self.decision == "amended" and self.amended_text
            else (self.proposed_text)
        )

    def to_edit(self) -> RedlineEdit:
        if self.anchor is None:
            raise ValueError(f"{self.id}: change has no document locator")
        return RedlineEdit(
            change_id=self.id,
            operation=self.operation,
            paragraph_index=self.anchor.paragraph_index,
            paragraph_hash=self.anchor.paragraph_hash,
            original_text=self.original_text,
            new_text=self.final_text,
            start=self.anchor.start,
            end=self.anchor.end,
        )


class DocumentChangeSet(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_id: str = Field("document.change-set.v2", alias="schema")
    assessment_id: str
    source_digest: str
    playbook_id: str
    playbook_version: int
    changes: list[DocumentChange]
    coverage_problems: list[str] = Field(default_factory=list, alias="coverageProblems")
    source_preserved: bool = Field(True, alias="sourcePreserved")
    all_changes_decided: bool = Field(False, alias="allChangesDecided")


class PlaybookRule(BaseModel):
    rule_id: str
    topic: str
    category: str
    severity: Literal["low", "medium", "high"]
    kind: RuleKind
    clause_pattern: str
    deviation_pattern: str | None = None
    max_value: int | None = None
    unless_pattern: str | None = None
    standard_text: str = ""
    standard_position: str
    fallback_position: str
    rationale: str
    specialist_role: str | None = None
    exception_obligation: str | None = None
    obligation_owner_role: str = "Commercial Counsel"
    obligation_due_days_before_signature: int = 0


class Playbook(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_id: Literal["legal-ops-agent.playbook.v1"] = Field(alias="schema")
    playbook_id: str
    version: int
    label: str
    matter_type: str
    synthetic: Literal[True]
    rules: list[PlaybookRule]

    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json", by_alias=True), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def rule(self, rule_id: str) -> PlaybookRule | None:
        return next((rule for rule in self.rules if rule.rule_id == rule_id), None)

    def rule_ref(self, rule_id: str) -> str:
        return f"{self.playbook_id}@v{self.version}#{rule_id}"


class Deviation(BaseModel):
    """A playbook deviation found in the document."""

    key: str
    rule_id: str
    topic: str
    category: str
    severity: str
    summary: str
    evidence: str
    locator: str
    standard_position: str
    fallback_position: str
    specialist_role: str | None = None
    change_id: str | None = None


class Proposal(BaseModel):
    changes: list[DocumentChange]
    deviations: list[Deviation]
    problems: list[str]


def load_playbook(path: Path | None = None) -> Playbook:
    return Playbook.model_validate_json((path or DEFAULT_PLAYBOOK_PATH).read_text("utf-8"))


def document_source_ref(index: DocumentIndex, paragraph: Paragraph) -> str:
    return f"synthetic:matter-document:{index.sha256[:12]}#para:{paragraph.index}"


def _deviating_span(rule: PlaybookRule, paragraph: Paragraph) -> tuple[int, int] | None:
    if rule.kind != "replace_phrase":
        return (0, len(paragraph.text))
    match = re.search(rule.deviation_pattern or "", paragraph.text)
    if match is None:
        return None
    if rule.max_value is not None and int(match.group("value")) <= rule.max_value:
        return None
    return match.span("span") if "span" in match.groupdict() else match.span()


def propose_changes(index: DocumentIndex, playbook: Playbook) -> Proposal:
    """Match every playbook rule against the document and propose located changes."""

    changes: list[DocumentChange] = []
    deviations: list[Deviation] = []
    problems: list[str] = []
    for rule in playbook.rules:
        if rule.unless_pattern and any(
            re.search(rule.unless_pattern, p.text) for p in index.paragraphs if p.supported
        ):
            continue
        clause = re.compile(rule.clause_pattern)
        matches = [p for p in index.paragraphs if p.supported and clause.search(p.text)]
        if not matches:
            continue
        if len(matches) > 1:
            problems.append(
                f"rule {rule.rule_id}: ambiguous target, {len(matches)} paragraphs match "
                f"(paragraphs {', '.join(str(p.index) for p in matches)})"
            )
            continue
        paragraph = matches[0]
        span = _deviating_span(rule, paragraph)
        if span is None:
            continue
        start, end = span
        operation: Operation
        if rule.kind == "insert_after":
            operation, original, anchor_span = "insert_paragraph_after", "", (None, None)
        elif rule.kind == "delete_paragraph":
            operation, original, anchor_span = "delete_paragraph", paragraph.text, (None, None)
        else:
            operation, original = "replace_span", paragraph.text[start:end]
            anchor_span = (start, end)
        anchor = ChangeAnchor(
            paragraph_index=paragraph.index,
            paragraph_hash=paragraph.text_hash,
            clause_ref=paragraph.clause_ref,
            start=anchor_span[0],
            end=anchor_span[1],
        )
        change_id = f"chg-{rule.rule_id}-{paragraph.text_hash[:8]}"
        changes.append(
            DocumentChange(
                id=change_id,
                locator=anchor.label(),
                anchor=anchor,
                operation=operation,
                original_text=original,
                proposed_text=rule.standard_text,
                rationale=rule.rationale,
                source_refs=[
                    playbook.rule_ref(rule.rule_id),
                    document_source_ref(index, paragraph),
                ],
                rule_id=rule.rule_id,
            )
        )
        deviations.append(
            Deviation(
                key=f"dev-{rule.rule_id}-{paragraph.text_hash[:8]}",
                rule_id=rule.rule_id,
                topic=rule.topic,
                category=rule.category,
                severity=rule.severity,
                summary=f"{rule.topic}: the draft departs from the playbook position.",
                evidence=paragraph.text if operation != "replace_span" else original,
                locator=anchor.label(),
                standard_position=rule.standard_position,
                fallback_position=rule.fallback_position,
                specialist_role=rule.specialist_role,
                change_id=change_id,
            )
        )
    # Content the engine cannot read is reported, never silently passed.
    for name, digest in index.unexamined:
        kind = "paragraph with unsupported content" if name == "p" else f"w:{name} element"
        problems.append(
            f"coverage gap {digest}: a body-level {kind} was not examined against the playbook"
        )
    return Proposal(changes=changes, deviations=deviations, problems=problems)
