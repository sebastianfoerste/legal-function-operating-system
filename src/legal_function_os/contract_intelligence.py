"""Deterministic DPA clause playbook for Art. 28(3) GDPR."""

from __future__ import annotations

import difflib
from typing import Any

DPA_PLAYBOOK: tuple[dict[str, Any], ...] = (
    {"key": "documented_instructions", "label": "Verarbeitung nur auf dokumentierte Weisung", "citation": "Art. 28 Abs. 3 lit. a DSGVO", "required": True, "patterns": ("dokumentierte weisung", "documented instructions")},
    {"key": "confidentiality_commitment", "label": "Vertraulichkeitsverpflichtung der Beschäftigten", "citation": "Art. 28 Abs. 3 lit. b DSGVO", "required": True, "patterns": ("vertraulichkeit", "confidentiality")},
    {"key": "security_measures", "label": "Technische und organisatorische Maßnahmen", "citation": "Art. 28 Abs. 3 lit. c DSGVO", "required": True, "patterns": ("art. 32", "technische und organisatorische", "security measures")},
    {"key": "subprocessor_authorization", "label": "Genehmigung von Unterauftragsverarbeitern", "citation": "Art. 28 Abs. 3 lit. d DSGVO", "required": True, "patterns": ("unterauftragsverarbeiter", "subprocessor", "sub-processor")},
    {"key": "data_subject_rights_assistance", "label": "Unterstützung bei Betroffenenrechten", "citation": "Art. 28 Abs. 3 lit. e DSGVO", "required": True, "patterns": ("betroffenenrechte", "data subject")},
    {"key": "breach_and_dpia_assistance", "label": "Unterstützung bei Meldepflichten und DSFA", "citation": "Art. 28 Abs. 3 lit. f DSGVO", "required": True, "patterns": ("verletzung des schutzes", "breach", "datenschutz-folgenabschätzung", "dpia")},
    {"key": "deletion_return", "label": "Löschung oder Rückgabe nach Auftragsende", "citation": "Art. 28 Abs. 3 lit. g DSGVO", "required": True, "patterns": ("löschung", "rückgabe", "deletion", "return")},
    {"key": "audit_rights", "label": "Nachweis- und Kontrollrechte", "citation": "Art. 28 Abs. 3 lit. h DSGVO", "required": True, "patterns": ("überprüfung", "audit", "inspektion")},
)


CLAUSE_KEYS = tuple(requirement["key"] for requirement in DPA_PLAYBOOK)


def check_dpa_documents(documents: Any) -> list[str]:
    """Return what stops ``documents`` from being reviewed, one line per problem.

    A clause stored under a misspelled key would be ignored and its requirement
    reported missing, so a key close to a playbook key is a problem. Other keys are
    clauses the Art. 28(3) checklist does not cover, and are left alone.
    """

    if not isinstance(documents, list):
        return [f"expected a JSON array of agreements, got {type(documents).__name__}"]
    problems: list[str] = []
    seen: set[str] = set()
    for position, document in enumerate(documents, start=1):
        if not isinstance(document, dict):
            problems.append(f"agreement {position}: expected an object, got {type(document).__name__}")
            continue
        document_id = document.get("id")
        label = f"agreement {position}"
        if not isinstance(document_id, str) or not document_id.strip():
            problems.append(f"{label}: id is missing; every agreement needs one")
        else:
            label = f"{label} ({document_id})"
            if document_id in seen:
                problems.append(f"{label}: id is used twice; ids must be unique")
            seen.add(document_id)
        title = document.get("title")
        if title is not None and not isinstance(title, str):
            problems.append(f"{label}: title must be a string")
        clauses = document.get("clauses", {})
        if not isinstance(clauses, dict):
            problems.append(f"{label}: clauses must be an object of clause key to clause text")
            continue
        for key, text in clauses.items():
            if key not in CLAUSE_KEYS:
                close = difflib.get_close_matches(key, CLAUSE_KEYS, n=1, cutoff=0.8)
                if close:
                    problems.append(
                        f"{label}: clause {key!r} is not a playbook key (did you mean "
                        f"{close[0]!r}?); its text would be ignored"
                    )
            elif text is not None and not isinstance(text, str):
                problems.append(f"{label}: clause {key!r} must be text")
    return problems


def build_dpa_review(documents: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        document_id = str(document.get("id", "dpa-?"))
        clauses: dict[str, str] = dict(document.get("clauses", {}))
        for requirement in DPA_PLAYBOOK:
            clause_text = clauses.get(requirement["key"])
            if clause_text is None:
                status = "missing"
            elif any(pattern in clause_text.lower() for pattern in requirement["patterns"]):
                status = "pass"
            else:
                status = "review"
            rows.append({
                "document_id": document_id,
                "document_title": str(document.get("title", "")),
                "requirement_key": requirement["key"],
                "label": requirement["label"],
                "citation": requirement["citation"],
                "status": status,
                "clause_excerpt": (clause_text or "")[:240],
                "source_ref": f"synthetic-dpa:{document_id}",
                "reviewer_note": None,
            })
    return {
        "schema": "legal-function-os.dpa-review.v1",
        "document_count": len(documents),
        "rows": rows,
        "blocker_count": sum(row["status"] == "missing" for row in rows),
        "requires_human_review": True,
        "external_action_allowed": False,
    }


def _cell(text: Any) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render_dpa_markdown(review: dict[str, Any]) -> str:
    """Render a DPA review as one requirement table per document."""

    lines = [
        "# DPA clause review (Art. 28(3) GDPR / DSGVO)",
        "",
        f"- **{review['document_count']}** document{'' if review['document_count'] == 1 else 's'}"
        f" · **{review['blocker_count']}** blocker{'' if review['blocker_count'] == 1 else 's'}"
        " (missing requirements)",
        "- The review states coverage, not that an agreement is lawful. "
        "Human review is required.",
        "",
    ]
    documents: dict[str, list[dict[str, Any]]] = {}
    for row in review["rows"]:
        documents.setdefault(row["document_id"], []).append(row)
    for document_id, rows in documents.items():
        title = rows[0]["document_title"]
        lines.append(f"## {document_id}: {title}" if title else f"## {document_id}")
        lines.append("")
        lines.append("| Requirement | Citation | Status | Clause excerpt |")
        lines.append("| --- | --- | --- | --- |")
        for row in rows:
            status = row["status"].upper() if row["status"] != "pass" else "pass"
            lines.append(
                f"| {_cell(row['label'])} | {_cell(row['citation'])} | {status} | "
                f"{_cell(row['clause_excerpt']) or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)
