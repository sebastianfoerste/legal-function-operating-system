"""A matter review captured by contract-review-eval-harness, as recommendations.

The harness produces and scores a model's review of a matter. This module lets the
supervised workflow put that review to a lawyer: each finding becomes one
recommendation, under the finding's own id, and the draft is bound to the hash by
which the harness identifies the review. A session held on it can therefore be read
by the harness as a reviewer session on that exact output.

The models mirror `contract_eval.matter` field for field. The review hash is taken
over the validated model with its defaults, so a field added here or there changes
the hash; a test compares the two against a harness checkout.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models import MatterIntake
from src.recommendations import SET_SCHEMA, Recommendation, RecommendationSet

REVIEW_SCHEMA: Final = "contract-review-eval.matter-review.v1"
CAPTURE_SCHEMA = "contract-review-eval.matter-capture.v1"
SESSION_SCHEMA = "contract-review-eval.reviewer-session.v1"

# A review is model output. These bounds keep an oversized or malformed one from
# reaching a reviewer; they are far above what a real review of one matter needs.
MAX_FINDINGS = 200
MAX_TEXT = 4000
# Finding ids become command arguments and headings, so they stay plain.
_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

Severity = Literal["low", "medium", "high"]
Action = Literal["accept", "negotiate", "reject", "escalate"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HarnessCitation(_Strict):
    citation_id: str
    document_id: str
    quote: str = Field(..., max_length=MAX_TEXT)


class HarnessConflict(_Strict):
    finding_id: str = Field(..., pattern=_ID)
    summary: str = Field(..., max_length=MAX_TEXT)
    materiality: Severity
    evidence: list[str] = Field(default_factory=list)


class HarnessPosition(_Strict):
    finding_id: str = Field(..., pattern=_ID)
    summary: str = Field(..., max_length=MAX_TEXT)
    action: Action
    materiality: Severity
    playbook_rule: str | None = None
    evidence: list[str] = Field(default_factory=list)


class HarnessEscalation(_Strict):
    finding_id: str = Field(..., pattern=_ID)
    question: str = Field(..., max_length=MAX_TEXT)
    reason: str = Field(..., max_length=MAX_TEXT)
    evidence: list[str] = Field(default_factory=list)


class HarnessMatterReview(_Strict):
    """Mirror of contract_eval.matter.MatterReview."""

    schema_version: Literal["contract-review-eval.matter-review.v1"] = Field(
        default=REVIEW_SCHEMA, alias="schema"
    )
    conflicts: list[HarnessConflict] = Field(default_factory=list)
    positions: list[HarnessPosition] = Field(default_factory=list)
    escalations: list[HarnessEscalation] = Field(default_factory=list)
    citations: list[HarnessCitation] = Field(default_factory=list)

    def findings(self) -> list[HarnessConflict | HarnessPosition | HarnessEscalation]:
        return [*self.conflicts, *self.positions, *self.escalations]

    @model_validator(mode="after")
    def validate_references(self) -> "HarnessMatterReview":
        findings = self.findings()
        if not 0 < len(findings) <= MAX_FINDINGS:
            raise ValueError(f"a review needs between 1 and {MAX_FINDINGS} findings")
        for label, ids in (
            ("citation", [citation.citation_id for citation in self.citations]),
            ("finding", [finding.finding_id for finding in findings]),
        ):
            repeated = sorted({item for item in ids if ids.count(item) > 1})
            if repeated:
                raise ValueError(f"duplicate {label} ids: {repeated}")
        known = {citation.citation_id for citation in self.citations}
        for finding in findings:
            unknown = sorted(set(finding.evidence) - known)
            if unknown:
                raise ValueError(
                    f"finding {finding.finding_id!r} references unknown citation ids: {unknown}"
                )
        return self

    def canonical_sha256(self) -> str:
        """The identity the harness gives this exact output."""

        payload = json.dumps(self.model_dump(by_alias=True), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_harness_review(path: Path) -> HarnessMatterReview:
    """Read a review from a bare output file or from a capture of a live run.

    A capture also names the condition and model that produced the output. Those are
    left behind on purpose: a reviewer rates the output without knowing its origin.
    """

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "raw_text" in data:
        return HarnessMatterReview.model_validate_json(data["raw_text"])
    if isinstance(data, dict) and data.get("schema") == CAPTURE_SCHEMA:
        raise ValueError(f"{path} records a failed attempt; it holds no output to review")
    return HarnessMatterReview.model_validate(data)


def template_differences(
    review: HarnessMatterReview, matter: MatterIntake, template: dict[str, Any]
) -> list[str]:
    """Compare a review and intake with a session template the harness wrote for it."""

    finding_ids = sorted(finding.finding_id for finding in review.findings())
    expected = {
        "matter_id": matter.matter_id,
        "round_id": matter.round_id,
        "review_sha256": review.canonical_sha256(),
    }
    differences = [
        f"{field}: here {value!r}, template {template.get(field)!r}"
        for field, value in expected.items()
        if template.get(field) != value
    ]
    rated = sorted(
        str(item.get("finding_id"))
        for item in template.get("decisions", [])
        if isinstance(item, dict)
    )
    if rated != finding_ids:
        differences.append(f"finding ids: here {finding_ids}, template {rated}")
    return differences


def recommendations_from_harness_review(
    review: HarnessMatterReview, matter: MatterIntake
) -> RecommendationSet:
    """One recommendation per finding, under the finding's id, with its quoted evidence."""

    if not (matter.matter_id and matter.round_id):
        raise ValueError("a harness review needs an intake that names its matter and round")
    citations = {citation.citation_id: citation for citation in review.citations}
    source_refs = {document.document_id: document.source_ref for document in matter.documents}

    def recommendation(
        finding_id: str, kind: str, statement: str, basis: str, evidence: list[str]
    ) -> Recommendation:
        cited = [citations[citation_id] for citation_id in evidence]
        documents = list(dict.fromkeys(citation.document_id for citation in cited))
        # A document the round does not hold is named as such: a reviewer should
        # see that the output cited something that is not on the file.
        labelled = [
            document if document in source_refs else f"{document} (not on the file)"
            for document in documents
        ]
        return Recommendation(
            id=finding_id,
            locator=f"{kind} | documents: {', '.join(labelled) or 'none cited'}",
            original_text="\n".join(
                f"[{citation.document_id}] {citation.quote}" for citation in cited
            ),
            proposed_text=statement,
            rationale=basis,
            source_refs=[
                source_refs[document] for document in documents if document in source_refs
            ],
        )

    recommendations = [
        *(
            recommendation(
                item.finding_id,
                "conflict",
                item.summary,
                f"Conflict between documents. Materiality: {item.materiality}.",
                item.evidence,
            )
            for item in review.conflicts
        ),
        *(
            recommendation(
                item.finding_id,
                "position",
                item.summary,
                f"Recommended action: {item.action}. Materiality: {item.materiality}."
                + (f" Playbook rule: {item.playbook_rule}." if item.playbook_rule else ""),
                item.evidence,
            )
            for item in review.positions
        ),
        *(
            recommendation(item.finding_id, "escalation", item.question, item.reason, item.evidence)
            for item in review.escalations
        ),
    ]
    return RecommendationSet(
        schema=SET_SCHEMA,
        source_digest=review.canonical_sha256(),
        recommendations=recommendations,
    )
