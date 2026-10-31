"""Deterministic DPA clause playbook for Art. 28(3) GDPR.

Each requirement of Article 28(3) GDPR is split into the statutory elements a
clause has to cover. A clause passes only when every element is found. A clause
that covers some elements is marked for review, with the missing elements listed.
A clause that is absent is missing, which counts as a blocker. A matched term that
is preceded by a negation ("no audits", "keine Überprüfung") is never read as
coverage; the row is marked for review and the element is reported as negated.

The check reads words, not meaning. It states coverage of the statutory wording.
It does not state that an agreement is lawful or that a clause works, and it
cannot see a clause that was stored under the wrong key. Human review is required.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

# Patterns are regular expressions, matched case-insensitively against the clause
# text. English terms carry word boundaries, so "return" no longer matches inside
# unrelated words. German terms are substrings on purpose: compounds and inflected
# forms ("Unterauftragsverarbeitern", "Löschungsfrist") would otherwise be missed.


def _element(key: str, label: str, label_en: str, quote: str, patterns: tuple[str, ...]) -> dict[str, Any]:
    return {"key": key, "label": label, "label_en": label_en, "quote": quote, "patterns": patterns}


_ARTICLE = r"\bart(?:\.|ikel|icles?|s\.?)?\s?"

DPA_PLAYBOOK: tuple[dict[str, Any], ...] = (
    {
        "key": "documented_instructions",
        "label": "Verarbeitung nur auf dokumentierte Weisung",
        "label_en": "Processing only on documented instructions",
        "citation": "Art. 28 Abs. 3 lit. a DSGVO",
        "required": True,
        "statute": (
            "processes the personal data only on documented instructions from the "
            "controller, including with regard to transfers of personal data to a third "
            "country or an international organisation"
        ),
        "elements": (
            _element(
                "documented_instructions",
                "Dokumentierte Weisung des Verantwortlichen",
                "Documented instructions from the controller",
                "only on documented instructions from the controller",
                (
                    r"dokumentierte[nr]?\s+weisung",
                    r"weisung(?:en)?\s+des\s+verantwortlichen",
                    r"\bdocumented\s+instructions?\b",
                    r"\binstructions?\s+(?:of|from)\s+the\s+controller\b",
                ),
            ),
            _element(
                "third_country_transfers",
                "Einschließlich Übermittlungen in Drittländer oder an internationale Organisationen",
                "Including transfers to a third country or an international organisation",
                "including with regard to transfers of personal data to a third country or an international organisation",
                (
                    r"drittl[aä]nd",
                    r"drittstaat",
                    r"internationale[n]?\s+organisation",
                    r"\bthird\s+countr(?:y|ies)\b",
                    r"\binternational\s+organi[sz]ations?\b",
                ),
            ),
        ),
    },
    {
        "key": "confidentiality_commitment",
        "label": "Vertraulichkeitsverpflichtung der Beschäftigten",
        "label_en": "Confidentiality commitment of authorised persons",
        "citation": "Art. 28 Abs. 3 lit. b DSGVO",
        "required": True,
        "statute": (
            "ensures that persons authorised to process the personal data have committed "
            "themselves to confidentiality or are under an appropriate statutory obligation "
            "of confidentiality"
        ),
        "elements": (
            _element(
                "confidentiality",
                "Verpflichtung zur Vertraulichkeit oder gesetzliche Verschwiegenheitspflicht",
                "Commitment to confidentiality or statutory obligation of confidentiality",
                "committed themselves to confidentiality or are under an appropriate statutory obligation of confidentiality",
                (
                    r"vertraulichkeit",
                    r"verschwiegenheit",
                    r"geheimhaltung",
                    r"\bconfidentialit(?:y|ies)\b",
                    r"\bconfidential\b",
                    r"\bsecrecy\b",
                ),
            ),
        ),
    },
    {
        "key": "security_measures",
        "label": "Technische und organisatorische Maßnahmen",
        "label_en": "Security of processing (Art. 32)",
        "citation": "Art. 28 Abs. 3 lit. c DSGVO",
        "required": True,
        "statute": "takes all measures required pursuant to Article 32",
        "elements": (
            _element(
                "article_32_measures",
                "Maßnahmen nach Art. 32 DSGVO (technische und organisatorische Maßnahmen)",
                "Measures required pursuant to Article 32 (technical and organisational measures)",
                "takes all measures required pursuant to Article 32",
                (
                    _ARTICLE + r"32\b",
                    r"technische[nr]?\s+und\s+organisatorische",
                    r"sicherheit\s+der\s+verarbeitung",
                    r"\btechnical\s+and\s+organi[sz]ational\s+measures\b",
                    r"\bsecurity\s+measures\b",
                    r"\bsecurity\s+of\s+(?:the\s+)?processing\b",
                ),
            ),
        ),
    },
    {
        "key": "subprocessor_authorization",
        "label": "Genehmigung von Unterauftragsverarbeitern",
        "label_en": "Authorisation of sub-processors",
        "citation": "Art. 28 Abs. 3 lit. d DSGVO",
        "required": True,
        "statute": "respects the conditions referred to in paragraphs 2 and 4 for engaging another processor",
        "elements": (
            _element(
                "subprocessor_authorization",
                "Vorherige Genehmigung weiterer Auftragsverarbeiter",
                "Prior authorisation for engaging another processor",
                "respects the conditions referred to in paragraphs 2 and 4 for engaging another processor",
                (
                    r"unterauftragsverarbeiter",
                    r"unterauftragnehmer",
                    r"weitere[rn]?\s+auftragsverarbeiter",
                    r"subunternehmer",
                    r"\bsub-?processors?\b",
                    r"\banother\s+processor\b",
                    r"\bsub-?contractors?\b",
                ),
            ),
        ),
    },
    {
        "key": "data_subject_rights_assistance",
        "label": "Unterstützung bei Betroffenenrechten",
        "label_en": "Assistance with data subject rights",
        "citation": "Art. 28 Abs. 3 lit. e DSGVO",
        "required": True,
        "statute": (
            "assists the controller by appropriate technical and organisational measures "
            "for the fulfilment of the controller's obligation to respond to requests for "
            "exercising the data subject's rights laid down in Chapter III"
        ),
        "elements": (
            _element(
                "data_subject_rights",
                "Unterstützung bei Anfragen zu Betroffenenrechten (Kapitel III)",
                "Assistance with requests for exercising data subject rights (Chapter III)",
                "requests for exercising the data subject's rights laid down in Chapter III",
                (
                    r"betroffenenrechte",
                    r"rechte\s+der\s+betroffenen",
                    r"betroffenenanfragen",
                    r"betroffene[nr]?\s+person",
                    r"kapitel\s+iii\b",
                    r"\bdata\s+subjects?\b",
                    r"\bchapter\s+iii\b",
                ),
            ),
        ),
    },
    {
        "key": "breach_and_dpia_assistance",
        "label": "Unterstützung bei den Pflichten nach Art. 32 bis 36 DSGVO",
        "label_en": "Assistance with the obligations under Articles 32 to 36",
        "citation": "Art. 28 Abs. 3 lit. f DSGVO",
        "required": True,
        "statute": (
            "assists the controller in ensuring compliance with the obligations pursuant "
            "to Articles 32 to 36 taking into account the nature of processing and the "
            "information available to the processor"
        ),
        # A clause that refers to the whole range satisfies every element below.
        "blanket_patterns": (_ARTICLE + r"32\s?(?:bis|to|-|–|—)\s?36\b",),
        "elements": (
            _element(
                "breach_notification",
                "Meldung und Benachrichtigung bei Verletzungen des Schutzes personenbezogener Daten (Art. 33, 34)",
                "Notification and communication of a personal data breach (Articles 33 and 34)",
                "Articles 33 and 34: notification of a personal data breach to the supervisory authority and communication to the data subject",
                (
                    r"verletzung(?:en)?\s+des\s+schutzes",
                    r"datenschutzverletzung",
                    r"datenpanne",
                    _ARTICLE + r"3[34]\b",
                    r"\bpersonal\s+data\s+breach(?:es)?\b",
                    r"\bdata\s+breach(?:es)?\b",
                    r"\bbreach(?:es)?\s+of\s+(?:security|personal\s+data)\b",
                ),
            ),
            _element(
                "dpia_and_prior_consultation",
                "Datenschutz-Folgenabschätzung und vorherige Konsultation (Art. 35, 36)",
                "Data protection impact assessment and prior consultation (Articles 35 and 36)",
                "Articles 35 and 36: data protection impact assessment and prior consultation of the supervisory authority",
                (
                    r"datenschutz-?folgenabsch[aä]tzung",
                    r"\bdsfa\b",
                    r"vorherige[n]?\s+konsultation",
                    _ARTICLE + r"3[56]\b",
                    r"\bdata\s+protection\s+impact\s+assessments?\b",
                    r"\bimpact\s+assessments?\b",
                    r"\bdpias?\b",
                    r"\bprior\s+consultation\b",
                ),
            ),
        ),
    },
    {
        "key": "deletion_return",
        "label": "Löschung oder Rückgabe nach Auftragsende",
        "label_en": "Deletion or return after the end of the services",
        "citation": "Art. 28 Abs. 3 lit. g DSGVO",
        "required": True,
        "statute": (
            "at the choice of the controller, deletes or returns all the personal data to "
            "the controller after the end of the provision of services relating to "
            "processing, and deletes existing copies"
        ),
        "elements": (
            _element(
                "deletion_or_return",
                "Löschung oder Rückgabe aller personenbezogenen Daten nach Wahl des Verantwortlichen",
                "Deletion or return of all personal data at the choice of the controller",
                "at the choice of the controller, deletes or returns all the personal data to the controller after the end of the provision of services",
                (
                    r"l[oö]sch",
                    r"gel[oö]scht",
                    r"r[uü]ckgabe",
                    r"zur[uü]ck(?:zu)?(?:geben|gibt|gegeben)",
                    r"herausgabe",
                    r"\bdelet(?:e|es|ed|ion|ing)\b",
                    r"\beras(?:e|es|ed|ure)\b",
                    r"\breturn(?:s|ed|ing)?\b",
                ),
            ),
        ),
    },
    {
        "key": "audit_rights",
        "label": "Nachweis- und Kontrollrechte",
        "label_en": "Information to demonstrate compliance, audits and inspections",
        "citation": "Art. 28 Abs. 3 lit. h DSGVO",
        "required": True,
        "statute": (
            "makes available to the controller all information necessary to demonstrate "
            "compliance with the obligations laid down in this Article and allow for and "
            "contribute to audits, including inspections, conducted by the controller or "
            "another auditor mandated by the controller"
        ),
        "elements": (
            _element(
                "information_to_demonstrate_compliance",
                "Informationen zum Nachweis der Einhaltung",
                "All information necessary to demonstrate compliance",
                "makes available to the controller all information necessary to demonstrate compliance with the obligations laid down in this Article",
                (
                    r"nachweis",
                    r"erforderlichen\s+informationen",
                    r"notwendigen\s+informationen",
                    r"\binformation\s+necessary\b",
                    r"\bnecessary\s+information\b",
                    r"\bdemonstrate\s+compliance\b",
                    r"\ball\s+(?:the\s+)?information\b",
                ),
            ),
            _element(
                "audits_and_inspections",
                "Überprüfungen einschließlich Inspektionen",
                "Audits, including inspections",
                "allow for and contribute to audits, including inspections, conducted by the controller or another auditor mandated by the controller",
                (
                    r"[uü]berpr[uü]fung",
                    r"inspektion",
                    r"kontroll",
                    r"\baudits?\b",
                    r"\binspections?\b",
                ),
            ),
        ),
    },
    {
        # Art. 28(3), second subparagraph. Absent, it yields review, not missing:
        # whether it should block is a decision for the maintainer.
        "key": "unlawful_instruction_notice",
        "label": "Hinweispflicht bei rechtswidriger Weisung",
        "label_en": "Duty to flag an instruction that infringes data protection law",
        "citation": "Art. 28 Abs. 3 UAbs. 2 DSGVO",
        "required": False,
        "statute": (
            "the processor shall immediately inform the controller if, in its opinion, an "
            "instruction infringes this Regulation or other Union or Member State data "
            "protection provisions"
        ),
        "elements": (
            _element(
                "informs_of_infringing_instruction",
                "Unverzügliche Information des Verantwortlichen über eine rechtswidrige Weisung",
                "Immediately informs the controller of an instruction that infringes data protection law",
                "immediately inform the controller if, in its opinion, an instruction infringes this Regulation or other Union or Member State data protection provisions",
                (
                    r"weisung[^.]{0,120}(?:verst[oö][ßs]|rechtswidrig|widerspricht|verletzt)",
                    r"(?:rechtswidrig|verst[oö][ßs])[^.]{0,120}weisung",
                    r"\binstructions?\b[^.]{0,120}\b(?:infring\w*|violat\w*|unlawful|contraven\w*)\b",
                    r"\b(?:infring\w*|violat\w*|unlawful|contraven\w*)\b[^.]{0,120}\binstructions?\b",
                ),
            ),
        ),
    },
)


CLAUSE_KEYS = tuple(requirement["key"] for requirement in DPA_PLAYBOOK)

# A matched term that one of these precedes, within the same sentence and a few
# words, is read as negated. English: no, not, never, without, n't. German: nicht,
# ohne, kein and its inflections.
_NEGATION = re.compile(
    r"\b(?:no|not|never|without|nicht|ohne|kein(?:e|en|er|es|em)?)\b|\w+n't\b",
    re.IGNORECASE,
)
# A deadline, not a negation of what follows it.
_NOT_A_NEGATION = re.compile(r"\bwithout\s+(?:undue\s+)?delay\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.;:!?]")
_NEGATION_WINDOW_WORDS = 4


def _negated(text: str, start: int) -> bool:
    """Whether a negation precedes position ``start`` within a few words of the same sentence."""

    before = text[:start]
    sentence_breaks = [match.end() for match in _SENTENCE_END.finditer(before)]
    if sentence_breaks:
        before = before[sentence_breaks[-1] :]
    before = _NOT_A_NEGATION.sub(" ", before)
    words = before.split()[-_NEGATION_WINDOW_WORDS:]
    return any(_NEGATION.search(word) for word in words)


def _find(text: str, patterns: tuple[str, ...]) -> str:
    """``found`` when a pattern matches without a preceding negation, ``negated`` when
    every match is negated, ``missing`` when nothing matches."""

    negated = False
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if _negated(text, match.start()):
                negated = True
            else:
                return "found"
    return "negated" if negated else "missing"


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


def _review_clause(requirement: dict[str, Any], clause_text: str | None) -> dict[str, Any]:
    """Status and per-element findings of one clause against one requirement."""

    elements = requirement["elements"]
    if clause_text is None:
        element_status = {element["key"]: "missing" for element in elements}
        status = "missing" if requirement["required"] else "review"
    else:
        blanket = _find(clause_text, requirement.get("blanket_patterns", ()))
        if blanket == "found":
            element_status = {element["key"]: "found" for element in elements}
        else:
            element_status = {
                element["key"]: _find(clause_text, element["patterns"]) for element in elements
            }
        status = "pass" if all(value == "found" for value in element_status.values()) else "review"
    return {
        "status": status,
        "elements": [
            {"key": element["key"], "label": element["label"], "status": element_status[element["key"]]}
            for element in elements
        ],
        "missing_elements": [key for key, value in element_status.items() if value == "missing"],
        "negated_elements": [key for key, value in element_status.items() if value == "negated"],
    }


def build_dpa_review(documents: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        document_id = str(document.get("id", "dpa-?"))
        clauses: dict[str, str] = dict(document.get("clauses", {}))
        for requirement in DPA_PLAYBOOK:
            clause_text = clauses.get(requirement["key"])
            finding = _review_clause(requirement, clause_text)
            rows.append({
                "document_id": document_id,
                "document_title": str(document.get("title", "")),
                "requirement_key": requirement["key"],
                "label": requirement["label"],
                "label_en": requirement["label_en"],
                "citation": requirement["citation"],
                "required": requirement["required"],
                "statute": requirement["statute"],
                "status": finding["status"],
                "elements": finding["elements"],
                "missing_elements": finding["missing_elements"],
                "negated_elements": finding["negated_elements"],
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


def _gaps(row: dict[str, Any]) -> str:
    """The elements a clause does not cover, for the Markdown table."""

    parts = [
        element["label"] + (" (negated)" if element["status"] == "negated" else "")
        for element in row["elements"]
        if element["status"] != "found"
    ]
    return "; ".join(parts) if parts else "—"


def render_dpa_markdown(review: dict[str, Any]) -> str:
    """Render a DPA review as one requirement table per document."""

    lines = [
        "# DPA clause review (Art. 28(3) GDPR / DSGVO)",
        "",
        f"- **{review['document_count']}** document{'' if review['document_count'] == 1 else 's'}"
        f" · **{review['blocker_count']}** blocker{'' if review['blocker_count'] == 1 else 's'}"
        " (missing requirements)",
        "- `pass`: every statutory element of the requirement was found. `review`: an element "
        "is missing, or its wording is negated; the column lists which. `missing`: no clause. "
        "Art. 28 Abs. 3 lit. a to h block when missing; the UAbs. 2 row is marked for review instead.",
        "- The review states coverage of the statutory wording, not that an agreement is lawful. "
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
        lines.append("| Requirement | Citation | Status | Missing elements | Clause excerpt |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in rows:
            status = row["status"].upper() if row["status"] != "pass" else "pass"
            lines.append(
                f"| {_cell(row['label'])} | {_cell(row['citation'])} | {status} | "
                f"{_cell(_gaps(row))} | {_cell(row['clause_excerpt']) or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)
