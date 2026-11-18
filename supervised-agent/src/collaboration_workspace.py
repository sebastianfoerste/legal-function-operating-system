"""Matter Lists, the stateless change-set path and the static review-room snapshot.

Proposed changes come from the versioned playbook engine in ``src.playbook`` and are
written as tracked changes at verified locators by ``src.docx_redline``. Every
reviewed-document export passes ``src.export_gate``; a decided change set alone
never authorises one.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from models import LegalOpsAssessment, compute_audit_event_hash
from src.docx_redline import RevisionMark, index_docx, write_reviewed_docx
from src.export_gate import ExportContext, require_export_eligibility
from src.pilot.design_tokens import PRINT_CSS, TOKENS_CSS
from src.playbook import DocumentChange, DocumentChangeSet, Playbook, load_playbook, propose_changes
from src.source_verification import verify_source_refs

__all__ = ["DocumentChange", "DocumentChangeSet"]

# The snapshot's look: the shared tokens (the agent's own copy), a stacked table under
# 640px so a phone never scrolls sideways, and the light print block last.
SNAPSHOT_CSS = (
    TOKENS_CSS + "body{font:15px var(--font);margin:0;color:var(--ink);background:var(--bg)}"
    "main{max-width:1100px;margin:40px auto;padding:0 16px}h1{font-family:var(--font-head)}"
    "section{border:1px solid var(--line);border-radius:10px;padding:18px;margin:16px 0;"
    "background:var(--surface);overflow-wrap:break-word}"
    "table{width:100%;border-collapse:collapse}"
    "td,th{border:1px solid var(--line);padding:8px;text-align:left}"
    "th{background:var(--panel)}.gate{color:var(--warn)}\n"
    "@media (max-width:640px){table,tbody,tr,td{display:block;width:100%}thead{display:none}"
    "tr{margin:0 0 12px;border:1px solid var(--line);border-radius:8px;overflow:hidden}"
    "td{border:0;border-top:1px solid var(--line)}td:first-child{border-top:0}"
    "td[data-label]::before{content:attr(data-label);display:block;font-weight:700;"
    "font-size:12px;color:var(--muted)}}\n" + PRINT_CSS
)
SNAPSHOT_COLUMNS = ("Locator", "Original text", "Proposed text", "Decision")


class MatterListItem(BaseModel):
    id: str
    kind: str
    title: str
    owner: str
    due_at: str
    source_refs: list[str]
    dependencies: list[str]
    evidence_refs: list[str] = Field(default_factory=list)
    comments: list[dict[str, str]] = Field(default_factory=list)
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


def _reproducible_now() -> datetime:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH", "0")
    try:
        return datetime.fromtimestamp(int(raw_epoch), UTC)
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError("SOURCE_DATE_EPOCH must be a valid integer Unix timestamp") from error


def build_change_set(
    assessment: LegalOpsAssessment,
    source_document: Path | None = None,
    playbook: Playbook | None = None,
) -> DocumentChangeSet:
    """Propose document-specific changes for a matter.

    Without a source document there is nothing to locate a change in, so the change
    set is empty. Generic wording is never proposed.
    """

    blocked = [
        source.source_ref
        for source in assessment.source_verifications
        if source.status == "blocker"
    ]
    if blocked:
        raise ValueError(
            f"blocked source references prevent document processing: {', '.join(blocked)}"
        )
    playbook = playbook or load_playbook()
    changes: list[DocumentChange] = []
    problems: list[str] = []
    if source_document is None:
        source = json.dumps(assessment.matter.model_dump(mode="json"), sort_keys=True).encode()
    else:
        source = source_document.read_bytes()
        proposal = propose_changes(index_docx(source), playbook)
        changes, problems = proposal.changes, proposal.problems
    return DocumentChangeSet(
        schema="document.change-set.v2",
        assessment_id=assessment.assessment_id,
        source_digest=hashlib.sha256(source).hexdigest(),
        playbook_id=playbook.playbook_id,
        playbook_version=playbook.version,
        changes=changes,
        coverageProblems=problems,
        sourcePreserved=True,
        allChangesDecided=not changes,
    )


def decide_change(
    change_set: DocumentChangeSet, change_id: str, decision: str
) -> DocumentChangeSet:
    """Record one decision. This never makes the change set exportable on its own."""

    if decision not in {"accepted", "rejected"}:
        raise ValueError("change decision must be accepted or rejected")
    updated = change_set.model_copy(deep=True)
    change = next((candidate for candidate in updated.changes if candidate.id == change_id), None)
    if change is None:
        raise ValueError(f"unknown change: {change_id}")
    change.decision = decision  # type: ignore[assignment]
    updated.all_changes_decided = all(
        item.decision in {"accepted", "rejected"} for item in updated.changes
    )
    return updated


def build_matter_list(assessment: LegalOpsAssessment) -> MatterList:
    created = _reproducible_now()
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
    if any(record.status == "blocker" for record in verify_source_refs(evidence_refs)):
        raise ValueError("blocked evidence reference cannot resolve a task")
    item.evidence_refs = evidence_refs
    item.status = "resolved"
    return updated


def comment_on_list_item(
    matter_list: MatterList, item_id: str, author: str, body: str
) -> MatterList:
    if not body.strip():
        raise ValueError("comment body is required")
    updated = matter_list.model_copy(deep=True)
    item = next((candidate for candidate in updated.items if candidate.id == item_id), None)
    if item is None:
        raise ValueError(f"unknown matter List item: {item_id}")
    item.comments.append(
        {
            "id": f"comment-{len(item.comments) + 1}",
            "author": author,
            "body": body.strip(),
            "createdAt": _reproducible_now().isoformat(),
        }
    )
    return updated


def build_timeline(matter_list: MatterList, actor: str = "Legal reviewer") -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    previous = None
    occurred_at = _reproducible_now().isoformat()
    for item in matter_list.items:
        seq = len(events)
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
        if item.status == "resolved":
            seq = len(events)
            event_hash = compute_audit_event_hash(
                seq, previous, "matter_list_item_resolved", actor, item.id, occurred_at
            )
            events.append(
                TimelineEvent(
                    seq=seq,
                    event_type="matter_list_item_resolved",
                    actor=actor,
                    target_id=item.id,
                    occurred_at=occurred_at,
                    previous_hash=previous,
                    event_hash=event_hash,
                )
            )
            previous = event_hash
        for comment in item.comments:
            seq = len(events)
            comment_occurred_at = comment["createdAt"]
            event_hash = compute_audit_event_hash(
                seq,
                previous,
                "matter_list_item_commented",
                comment["author"],
                item.id,
                comment_occurred_at,
            )
            events.append(
                TimelineEvent(
                    seq=seq,
                    event_type="matter_list_item_commented",
                    actor=comment["author"],
                    target_id=item.id,
                    occurred_at=comment_occurred_at,
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
    """Write a static, read-only snapshot. It records nothing.

    Decisions are taken in the pilot review room (``runtime_agent``), which saves
    them through the application layer.
    """

    sources = "".join(
        f"<li>{html.escape(source.source_ref)}: {source.status}</li>"
        for source in assessment.source_verifications
    )
    changes = "".join(
        "<tr>"
        + "".join(
            f"<td data-label='{label}'>{html.escape(value)}</td>"
            for label, value in zip(
                SNAPSHOT_COLUMNS,
                (change.locator, change.original_text, change.proposed_text, change.decision),
                strict=True,
            )
        )
        + "</tr>"
        for change in change_set.changes
    )
    head = "".join(f"<th scope='col'>{label}</th>" for label in SNAPSHOT_COLUMNS)
    tasks = "".join(
        f"<li><strong>{html.escape(item.title)}</strong>, {html.escape(item.owner)}, {item.status}</li>"
        for item in matter_list.items
    )
    document = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{html.escape(assessment.matter.title)}</title><style>{SNAPSHOT_CSS}</style></head><body><main><h1>{html.escape(assessment.matter.title)}</h1><p class='gate'>Static snapshot for reading. Nothing on this page is saved. External access and delivery are disabled.</p><section><h2>Source verification</h2><ul>{sources}</ul></section><section><h2>Document changes</h2><table><thead><tr>{head}</tr></thead><tbody>{changes}</tbody></table></section><section><h2>Matter List</h2><ul>{tasks}</ul></section></main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


def render_annotated_docx(
    change_set: DocumentChangeSet,
    source: Path,
    output: Path,
    *,
    assessment: LegalOpsAssessment,
) -> Path:
    """Write accepted changes as tracked changes, if the export gate allows it.

    The parent assessment is a required argument: a fully decided change set is not
    enough. This is a stateless call, so the reviewer named on the assessment is an
    unauthenticated string; an approved delivery package only comes from the pilot
    service, which checks recorded reviewer decisions.
    """

    if source.resolve() == output.resolve():
        raise ValueError("reviewed DOCX output must not overwrite the source document")
    if not zipfile.is_zipfile(source):
        raise ValueError("source document must be a DOCX package")
    require_export_eligibility(
        ExportContext(
            kind="reviewed_document",
            assessment=assessment,
            change_set_assessment_id=change_set.assessment_id,
            recorded_document_sha256=change_set.source_digest,
            actual_document_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            change_decisions={change.id: change.decision for change in change_set.changes},
        )
    )
    change_timestamp = _reproducible_now().replace(microsecond=0).isoformat().replace("+00:00", "Z")
    edits = [change.to_edit() for change in change_set.changes if change.decision == "accepted"]
    # No reviewer decision is recorded on this path, so the label says who it is not.
    mark = RevisionMark(author="Legal reviewer (not authenticated)", date=change_timestamp)
    return write_reviewed_docx(source, output, edits, mark)
