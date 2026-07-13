"""Local playbooks, matter Lists, change sets and review-room rendering."""

from __future__ import annotations

import hashlib
import html
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field

from models import LegalOpsAssessment, compute_audit_event_hash
from src.source_verification import verify_source_ref


class DocumentChange(BaseModel):
    id: str
    locator: str
    original_text: str
    proposed_text: str
    rationale: str
    source_refs: list[str]
    decision: str = "pending"


class DocumentChangeSet(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_id: str = Field("document.change-set.v1", alias="schema")
    source_digest: str
    playbook_version: int
    changes: list[DocumentChange]
    source_preserved: bool = Field(True, alias="sourcePreserved")
    export_allowed: bool = Field(False, alias="exportAllowed")


class MatterListItem(BaseModel):
    id: str
    kind: str
    title: str
    owner: str
    due_at: str
    source_refs: list[str]
    dependencies: list[str]
    evidence_refs: list[str] = Field(default_factory=list)
    status: str = "review_required"


class MatterList(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_id: str = Field("legal-ops-agent.matter-list.v1", alias="schema")
    items: list[MatterListItem]
    external_action_allowed: bool = Field(False, alias="externalActionAllowed")


class TimelineEvent(BaseModel):
    seq: int
    event_type: str
    actor: str
    target_id: str
    occurred_at: str
    previous_hash: str | None
    event_hash: str


class Playbook(TypedDict):
    version: int
    position: str
    fallback: str
    source: str


PLAYBOOKS: dict[str, Playbook] = {
    "contract": {
        "version": 1,
        "position": "Consequential commitments require written approval and source-bound review.",
        "fallback": "Escalate the clause with a time-limited exception.",
        "source": "synthetic:contract-playbook-v1",
    },
    "privacy": {
        "version": 1,
        "position": "Processing purpose, retention and approved subprocessors must be explicit.",
        "fallback": "Record a documented remediation plan before signature.",
        "source": "synthetic:dpa-playbook-v1",
    },
    "regulatory_monitoring": {
        "version": 1,
        "position": "Legal conclusions require current primary-source verification.",
        "fallback": "Label the conclusion provisional and assign legal review.",
        "source": "synthetic:regulatory-response-playbook-v1",
    },
}


def build_change_set(assessment: LegalOpsAssessment) -> DocumentChangeSet:
    blocked = [
        source.source_ref
        for source in assessment.source_verifications
        if source.status == "blocker"
    ]
    if blocked:
        raise ValueError(
            f"blocked source references prevent document processing: {', '.join(blocked)}"
        )
    playbook = PLAYBOOKS.get(assessment.matter.matter_type, PLAYBOOKS["contract"])
    source = json.dumps(assessment.matter.model_dump(mode="json"), sort_keys=True)
    changes = [
        DocumentChange(
            id=f"change-{index}",
            locator=f"finding:{index}",
            original_text=finding.evidence,
            proposed_text=playbook["position"],
            rationale=finding.recommended_action,
            source_refs=[playbook["source"], *assessment.matter.source_refs],
        )
        for index, finding in enumerate(assessment.findings, start=1)
    ]
    return DocumentChangeSet(
        schema="document.change-set.v1",
        source_digest=hashlib.sha256(source.encode()).hexdigest(),
        playbook_version=playbook["version"],
        changes=changes,
        sourcePreserved=True,
        exportAllowed=False,
    )


def decide_change(
    change_set: DocumentChangeSet, change_id: str, decision: str
) -> DocumentChangeSet:
    if decision not in {"accepted", "rejected"}:
        raise ValueError("change decision must be accepted or rejected")
    updated = change_set.model_copy(deep=True)
    change = next((candidate for candidate in updated.changes if candidate.id == change_id), None)
    if change is None:
        raise ValueError(f"unknown change: {change_id}")
    change.decision = decision
    updated.export_allowed = bool(updated.changes) and all(
        item.decision == "accepted" for item in updated.changes
    )
    return updated


def build_matter_list(assessment: LegalOpsAssessment) -> MatterList:
    created = datetime.fromisoformat(assessment.created_at_utc.replace("Z", "+00:00"))
    items: list[MatterListItem] = []
    for index, commitment in enumerate(assessment.customer_commitments, start=1):
        items.append(
            MatterListItem(
                id=f"commitment-{index}",
                kind="commitment",
                title=commitment.commitment,
                owner=commitment.owner_role,
                due_at=(created + timedelta(days=14)).isoformat(),
                source_refs=[commitment.source],
                dependencies=["legal-review"],
            )
        )
    for index, finding in enumerate(assessment.findings, start=1):
        items.append(
            MatterListItem(
                id=f"finding-{index}",
                kind="finding",
                title=finding.summary,
                owner=assessment.routing.owner_role,
                due_at=(created + timedelta(hours=assessment.routing.sla_hours)).isoformat(),
                source_refs=list(assessment.matter.source_refs),
                dependencies=[] if finding.severity == "blocker" else ["source-review"],
                status="blocked" if finding.severity == "blocker" else "review_required",
            )
        )
    return MatterList(
        schema="legal-ops-agent.matter-list.v1",
        items=items,
        externalActionAllowed=False,
    )


def resolve_list_item(
    matter_list: MatterList, item_id: str, evidence_refs: list[str]
) -> MatterList:
    if not evidence_refs:
        raise ValueError("resolution evidence is required")
    updated = matter_list.model_copy(deep=True)
    item = next((candidate for candidate in updated.items if candidate.id == item_id), None)
    if item is None:
        raise ValueError(f"unknown matter List item: {item_id}")
    for source_ref in evidence_refs:
        if verify_source_ref(source_ref).status == "blocker":
            raise ValueError("blocked evidence reference cannot resolve a task")
    item.evidence_refs = evidence_refs
    item.status = "resolved"
    return updated


def build_timeline(matter_list: MatterList, actor: str = "Legal reviewer") -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    previous = None
    for seq, item in enumerate(matter_list.items):
        occurred_at = datetime(2026, 7, 13, tzinfo=UTC).isoformat()
        event_hash = compute_audit_event_hash(
            seq, previous, "matter_list_item_created", actor, item.id, occurred_at
        )
        events.append(
            TimelineEvent(
                seq=seq,
                event_type="matter_list_item_created",
                actor=actor,
                target_id=item.id,
                occurred_at=occurred_at,
                previous_hash=previous,
                event_hash=event_hash,
            )
        )
        previous = event_hash
    return events


def render_review_room(
    assessment: LegalOpsAssessment,
    change_set: DocumentChangeSet,
    matter_list: MatterList,
    output: Path,
) -> Path:
    sources = "".join(
        f"<li>{html.escape(source.source_ref)}: {source.status}</li>"
        for source in assessment.source_verifications
    )
    changes = "".join(
        f"<tr><td>{html.escape(change.locator)}</td><td>{html.escape(change.proposed_text)}</td><td>{change.decision}</td></tr>"
        for change in change_set.changes
    )
    tasks = "".join(
        f"<li><strong>{html.escape(item.title)}</strong>, {html.escape(item.owner)}, {item.status}</li>"
        for item in matter_list.items
    )
    document = f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(assessment.matter.title)}</title><style>body{{font:15px system-ui;max-width:1100px;margin:40px auto;color:#172033}}section{{border:1px solid #d9dee8;border-radius:10px;padding:18px;margin:16px 0}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #d9dee8;padding:8px;text-align:left}}.gate{{color:#9a3412}}</style></head><body><h1>{html.escape(assessment.matter.title)}</h1><p class='gate'>Local review only. External access and delivery are disabled.</p><section><h2>Source verification</h2><ul>{sources}</ul></section><section><h2>Document changes</h2><table><tr><th>Locator</th><th>Proposed text</th><th>Decision</th></tr>{changes}</table></section><section><h2>Matter List</h2><ul>{tasks}</ul></section></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


def render_annotated_docx(change_set: DocumentChangeSet, output: Path) -> Path:
    if not change_set.export_allowed:
        raise ValueError("DOCX export requires every proposed change to be accepted")
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{escape(change.proposed_text)}</w:t></w:r></w:p>"
        for change in change_set.changes
        if change.decision == "accepted"
    )
    content_types = "<?xml version='1.0' encoding='UTF-8'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>"
    rels = "<?xml version='1.0' encoding='UTF-8'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/></Relationships>"
    document = f"<?xml version='1.0' encoding='UTF-8'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>{paragraphs}<w:sectPr/></w:body></w:document>"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", rels)
        package.writestr("word/document.xml", document)
    return output
