"""Local deliverables: internal review exports and the approved delivery package.

The two are deliberately different artifacts in different folders. An internal
review export is a working draft and says so on every file. A delivery package is
only ever written by ``PilotService.prepare_delivery`` after the export gate has
passed. Nothing here sends, files or publishes anything.
"""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.docx_redline import RevisionMark, apply_tracked_changes, list_tracked_changes
from src.export_gate import ExportBlockedError, ExportEligibility
from src.pilot.models import Comment, Finding, ParentRouting, PilotIntake
from src.playbook import DocumentChange

MANIFEST_SCHEMA = "legal-ops-agent.deliverable-manifest.v1"
SYNTHETIC_NOTICE = (
    "Synthetic data. Prepared for local handover inside the pilot. Not sent, filed or "
    "published. Not legal advice."
)
DRAFT_NOTICE = (
    "INTERNAL REVIEW DRAFT. Not approved. Not a delivery package. Do not pass on outside "
    "the review team."
)
Block = tuple[Any, ...]


@dataclass(frozen=True)
class PackageData:
    matter_id: str
    title: str
    state: str
    version: int
    content_hash: str
    review_hash: str
    document_name: str
    document: bytes
    intake: PilotIntake
    routing: ParentRouting
    playbook_ref: str
    playbook_hash: str
    findings: list[Finding]
    changes: list[Any]
    comments: list[Comment]
    decisions: list[dict[str, Any]]
    obligations: list[dict[str, str]]
    source_support: list[dict[str, Any]]
    eligibility: ExportEligibility
    chain_root: str
    actor_names: dict[str, str]
    generated_at: str


_OUTCOME = {
    "accepted": "Reverted to the standard position",
    "amended": "Fallback wording agreed",
    "rejected": "Exception accepted: counterparty wording stays",
    "pending": "Not yet decided",
    "clarification_requested": "Waiting for clarification",
}


def _final_wording(change: DocumentChange) -> str:
    if change.decision == "rejected":
        return change.original_text
    if change.operation == "delete_paragraph" and change.decision != "pending":
        return "(clause deleted)"
    return change.final_text or "(clause deleted)"


def _topic(data: PackageData, change: DocumentChange) -> str:
    finding = next((f for f in data.findings if f.change_id == change.id), None)
    return finding.summary.split(":", 1)[0] if finding else (change.rule_id or change.id)


def _issue_rows(data: PackageData) -> list[dict[str, str]]:
    return [
        {
            "change_id": change.id,
            "locator": ("after " if change.operation == "insert_paragraph_after" else "")
            + change.locator,
            "topic": _topic(data, change),
            "severity": next(
                (f.severity for f in data.findings if f.change_id == change.id), "medium"
            ),
            "counterparty_wording": change.original_text or "(no clause in the draft)",
            "playbook_wording": change.proposed_text or "(delete clause)",
            "outcome": _OUTCOME[change.decision],
            "final_wording": _final_wording(change),
            "reason": change.decision_reason or change.rationale,
            "decided_by": data.actor_names.get(
                getattr(change, "decided_by", "") or "", "undecided"
            ),
        }
        for change in data.changes
    ]


def _valid_decisions(data: PackageData, kinds: set[str]) -> list[dict[str, Any]]:
    return [
        d
        for d in data.decisions
        if d["kind"] in kinds and d["invalidated_at"] is None and d["version"] == data.version
    ]


def _sections(data: PackageData, *, draft: bool) -> list[tuple[str, list[Block]]]:
    issues = _issue_rows(data)
    counts = {key: sum(c.decision == key for c in data.changes) for key in _OUTCOME}
    exceptions = [
        row for row in issues if row["outcome"] in {_OUTCOME["rejected"], _OUTCOME["amended"]}
    ]
    approvals = _valid_decisions(data, {"specialist_signoff", "final_approval"})
    final = next((d for d in approvals if d["kind"] == "final_approval"), None)
    facts = data.intake.facts
    summary: list[Block] = [
        (
            "p",
            f'The customer draft "{data.document_name}" from {facts.get("counterparty", "the counterparty")} '
            f"was reviewed against {data.playbook_ref}. {len(issues)} deviation(s) from the playbook "
            f"were found. Reverted to the standard position: {counts['accepted']}. Settled on "
            f"fallback wording: {counts['amended']}. Accepted as an exception: {counts['rejected']}."
            + (
                f" {counts['pending'] + counts['clarification_requested']} are still open."
                if draft
                else ""
            ),
        ),
        (
            "p",
            f"The parent operating system rates the matter {data.routing.risk} risk, priority "
            f"{data.routing.priority}, queue {data.routing.queue}. The approval tier it requires is "
            f"{data.routing.approval_chain[-1]}."
            + (
                f" Final approval was recorded by {data.actor_names.get(final['actor_id'], final['actor_id'])}."
                if final
                else " No final approval is recorded for this version."
            ),
        ),
        (
            "p",
            f"{len(data.obligations)} obligation(s) remain open and each has an owner and a deadline "
            f"below. Signature target date: {facts.get('signature_target_date', 'not set')}.",
        ),
    ]
    support_rows = [
        [
            item["change_id"],
            "; ".join(
                f"{s['source_ref']}: {s['allowlist_check']['status']}" for s in item["sources"]
            ),
            "; ".join(s["quote_check"]["status"] for s in item["sources"]),
            item["human_review"]["status"]
            + (
                f" by {data.actor_names.get(item['human_review']['confirmed_by'], '')}"
                if item["human_review"]["confirmed_by"]
                else ""
            ),
        ]
        for item in data.source_support
    ]
    return [
        ("1. Executive summary", summary),
        (
            "2. Issue and deviation list",
            [
                (
                    "table",
                    [
                        "Clause",
                        "Topic",
                        "Severity",
                        "Counterparty wording",
                        "Outcome",
                        "Final wording",
                        "Reason",
                    ],
                    [
                        [
                            r["locator"].split(" para:")[0],
                            r["topic"],
                            r["severity"],
                            r["counterparty_wording"],
                            r["outcome"],
                            r["final_wording"],
                            r["reason"],
                        ]
                        for r in issues
                    ],
                )
            ],
        ),
        (
            "3. Reviewed document",
            [
                (
                    "p",
                    ("draft-redline.docx" if draft else "reviewed-document.docx")
                    + " carries every "
                    + ("proposed" if draft else "approved")
                    + " change as a tracked change against the unmodified customer draft "
                    f"(SHA-256 {hashlib.sha256(data.document).hexdigest()}). Rejecting all tracked "
                    "changes in Word restores the customer draft exactly.",
                )
            ],
        ),
        (
            "4. Accepted exceptions",
            [
                (
                    (
                        "table",
                        ["Topic", "What was accepted", "Wording", "Reason", "Decided by"],
                        [
                            [
                                r["topic"],
                                r["outcome"],
                                r["final_wording"],
                                r["reason"],
                                r["decided_by"],
                            ]
                            for r in exceptions
                        ],
                    )
                    if exceptions
                    else ("p", "No exception to the playbook was accepted.")
                )
            ],
        ),
        (
            "5. Outstanding obligations",
            [
                (
                    (
                        "table",
                        ["Obligation", "Arises from", "Owner", "Deadline"],
                        [
                            [
                                o["obligation"],
                                o["arises_from"],
                                f"{o['owner_role']}: {o['owner']}",
                                o["due"],
                            ]
                            for o in data.obligations
                        ],
                    )
                    if data.obligations
                    else ("p", "No outstanding obligation.")
                )
            ],
        ),
        (
            "6. Approval record",
            [
                (
                    (
                        "table",
                        [
                            "Decision",
                            "By (simulated local role)",
                            "Version",
                            "Recorded (UTC)",
                            "Note",
                        ],
                        [
                            [
                                d["kind"].replace("_", " "),
                                data.actor_names.get(d["actor_id"], d["actor_id"]),
                                str(d["version"]),
                                d["created_at"],
                                d["note"],
                            ]
                            for d in approvals
                        ],
                    )
                    if approvals
                    else ("p", "No approval is recorded for this version.")
                ),
                (
                    "list",
                    [
                        f"Matter version: {data.version}",
                        f"Content hash: {data.content_hash}",
                        f"Reviewed-state hash: {data.review_hash}",
                        f"Event chain root: {data.chain_root}",
                        "Approvers are simulated local roles, not authenticated identities.",
                    ],
                ),
                (
                    "table",
                    ["Export check", "Result", "Detail"],
                    [[c.check_id, c.status, c.detail] for c in data.eligibility.checks],
                ),
            ],
        ),
        (
            "Verification performed and remaining human review",
            [
                (
                    "p",
                    "Three different things were checked for each change. The allowlist check "
                    "only establishes that a reference uses a permitted source prefix. The quote "
                    "check establishes that the quoted wording is present at the stated place in "
                    "the stated source version. Whether the source supports the wording for this "
                    "matter was confirmed by a reviewer, not by software.",
                ),
                (
                    "table",
                    ["Change", "Allowlist check", "Quote check", "Human confirmation"],
                    support_rows,
                ),
            ],
        ),
    ]


def _header(data: PackageData, *, draft: bool) -> list[str]:
    return [
        DRAFT_NOTICE if draft else SYNTHETIC_NOTICE,
        f"Matter {data.matter_id}, version {data.version}, state {data.state}",
        f"Requester: {data.intake.matter.requester}, {data.intake.matter.business_unit}",
        f"Generated (UTC): {data.generated_at}",
    ]


def _cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(data: PackageData, *, draft: bool) -> str:
    title = ("Internal review export: " if draft else "Customer package: ") + data.title
    lines = [f"# {title}", "", *[f"> {line}" for line in _header(data, draft=draft)], ""]
    for heading, blocks in _sections(data, draft=draft):
        lines += [f"## {heading}", ""]
        for block in blocks:
            if block[0] == "p":
                lines += [block[1], ""]
            elif block[0] == "list":
                lines += [f"- {item}" for item in block[1]] + [""]
            else:
                lines.append("| " + " | ".join(block[1]) + " |")
                lines.append("| " + " | ".join("---" for _ in block[1]) + " |")
                lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in block[2]]
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(data: PackageData, *, draft: bool) -> str:
    esc = html.escape
    title = ("Internal review export: " if draft else "Customer package: ") + data.title
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>{esc(title)}</title>",
        "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:1080px;margin:32px auto;padding:0 20px;color:#172033}"
        "h1{font-size:26px}h2{font-size:19px;margin-top:32px;border-bottom:1px solid #d9dee8;padding-bottom:6px}"
        "table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.5px}"
        "th,td{border:1px solid #d9dee8;padding:7px 9px;text-align:left;vertical-align:top}th{background:#f3f5f9}"
        ".notice{border-left:4px solid #9a3412;background:#fff7ed;padding:10px 14px;margin:16px 0}"
        ".notice p{margin:2px 0}@media print{body{margin:0}}</style></head><body>",
        f"<h1>{esc(title)}</h1><div class='notice'>",
        *[f"<p>{esc(line)}</p>" for line in _header(data, draft=draft)],
        "</div>",
    ]
    for heading, blocks in _sections(data, draft=draft):
        parts.append(f"<section><h2>{esc(heading)}</h2>")
        for block in blocks:
            if block[0] == "p":
                parts.append(f"<p>{esc(block[1])}</p>")
            elif block[0] == "list":
                parts.append("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in block[1]) + "</ul>")
            else:
                head = "".join(f"<th>{esc(h)}</th>" for h in block[1])
                rows = "".join(
                    "<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in row) + "</tr>"
                    for row in block[2]
                )
                parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts) + "\n"


def _redline(data: PackageData, *, draft: bool) -> bytes:
    """Apply the decided wording. A rejected change leaves the counterparty text alone."""

    applicable = [
        change
        for change in data.changes
        if change.decision
        in (
            {"accepted", "amended", "pending", "clarification_requested"}
            if draft
            else {"accepted", "amended"}
        )
    ]
    mark = RevisionMark(
        author="DRAFT proposal, not approved" if draft else "Approved review (synthetic pilot)",
        date=data.generated_at[:19] + "Z",
    )
    reviewed, _ = apply_tracked_changes(data.document, [c.to_edit() for c in applicable], mark)
    return reviewed


def _write(folder: Path, files: dict[str, bytes], data: PackageData, kind: str) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, payload in files.items():
        (folder / name).write_bytes(payload)
        entries.append(
            {"name": name, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        )
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "kind": kind,
        "matter_id": data.matter_id,
        "matter_version": data.version,
        "content_hash": data.content_hash,
        "review_hash": data.review_hash,
        "source_document": {
            "name": data.document_name,
            "sha256": hashlib.sha256(data.document).hexdigest(),
        },
        "playbook": {"ref": data.playbook_ref, "sha256": data.playbook_hash},
        "eligibility": data.eligibility.model_dump(by_alias=True),
        "event_chain_root": data.chain_root,
        "generated_at_utc": data.generated_at,
        "folder": "/".join(folder.parts[-3:]),
        "files": entries,
        "external_delivery": "disabled",
        "identity": "simulated local roles, not authenticated",
        "synthetic": True,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_internal_review_export(data: PackageData, folder: Path) -> dict[str, Any]:
    files = {
        "internal-review.md": render_markdown(data, draft=True).encode("utf-8"),
        "draft-redline.docx": _redline(data, draft=True),
    }
    return _write(folder, files, data, "internal_review")


def write_delivery_package(data: PackageData, folder: Path) -> dict[str, Any]:
    # Defence in depth: the service evaluates the gate, this refuses anything else.
    if data.eligibility.kind != "delivery_package" or not data.eligibility.eligible:
        raise ExportBlockedError(data.eligibility)
    reviewed = _redline(data, draft=False)
    issue_list = {
        "matter_id": data.matter_id,
        "matter_version": data.version,
        "issues": _issue_rows(data),
        "obligations": data.obligations,
        "tracked_changes": len(list_tracked_changes(reviewed)),
    }
    files = {
        "customer-package.md": render_markdown(data, draft=False).encode("utf-8"),
        "customer-package.html": render_html(data, draft=False).encode("utf-8"),
        "reviewed-document.docx": reviewed,
        "issue-list.json": (json.dumps(issue_list, indent=2) + "\n").encode("utf-8"),
    }
    return _write(folder, files, data, "delivery_package")
