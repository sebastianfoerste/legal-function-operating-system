"""Deterministic DPA clause playbook for Art. 28(3) GDPR."""

from __future__ import annotations

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
