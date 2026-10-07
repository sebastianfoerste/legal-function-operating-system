"""Recommendations put to a reviewer, and what the reviewer decided on each.

This is the reviewer-evidence track's own model. It shares no code with the document
change sets of the review workspace: a recommendation here is a rule finding or a
finding of a captured model review, and neither has a location in a DOCX.
"""

from __future__ import annotations

import hashlib
import json
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models import LegalOpsAssessment
from src.legal_ops import all_source_refs

SET_SCHEMA: Final = "legal-ops-agent.recommendation-set.v1"

RecommendationDecision = Literal["pending", "accepted", "corrected", "rejected"]
DECIDED: frozenset[str] = frozenset({"accepted", "corrected", "rejected"})


class Recommendation(BaseModel):
    id: str
    locator: str
    original_text: str
    proposed_text: str
    rationale: str
    source_refs: list[str]
    decision: RecommendationDecision = "pending"
    reviewer: str | None = None
    reason: str = ""
    corrected_text: str | None = None
    usefulness: int | None = Field(default=None, ge=1, le=4)
    decided_at: str | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "Recommendation":
        if self.decision == "pending":
            return self
        if not (self.reviewer or "").strip():
            raise ValueError(f"{self.id}: a decided recommendation names its reviewer")
        if self.usefulness is None:
            raise ValueError(f"{self.id}: a decided recommendation carries a usefulness score")
        # An acceptance needs no explanation. A rejection or correction without one
        # loses the half of the record that could change the system.
        if self.decision != "accepted" and not self.reason.strip():
            raise ValueError(f"{self.id}: a {self.decision} recommendation needs a written reason")
        if (self.decision == "corrected") != bool((self.corrected_text or "").strip()):
            raise ValueError(
                f"{self.id}: corrected text belongs to a corrected recommendation, and only there"
            )
        return self

    def reviewed_text(self) -> str | None:
        """The wording that survives review, or None when the reviewer rejected it."""

        if self.decision == "accepted":
            return self.proposed_text
        if self.decision == "corrected":
            return self.corrected_text
        return None


class RecommendationSet(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_id: Literal["legal-ops-agent.recommendation-set.v1"] = Field(SET_SCHEMA, alias="schema")
    source_digest: str = Field(..., min_length=64, max_length=64)
    recommendations: list[Recommendation]

    def all_decided(self) -> bool:
        return bool(self.recommendations) and all(
            item.decision in DECIDED for item in self.recommendations
        )


def decide_recommendation(
    recommendation_set: RecommendationSet,
    recommendation_id: str,
    decision: str,
    *,
    reviewer: str,
    usefulness: int,
    reason: str = "",
    corrected_text: str | None = None,
    decided_at: str | None = None,
) -> RecommendationSet:
    if decision not in DECIDED:
        raise ValueError("a decision is accepted, corrected or rejected")
    index = next(
        (
            position
            for position, item in enumerate(recommendation_set.recommendations)
            if item.id == recommendation_id
        ),
        None,
    )
    if index is None:
        raise ValueError(f"unknown recommendation: {recommendation_id}")
    decided = recommendation_set.recommendations[index].model_dump()
    decided.update(
        decision=decision,
        reviewer=reviewer,
        reason=reason.strip(),
        corrected_text=corrected_text,
        usefulness=usefulness,
        decided_at=decided_at,
    )
    updated = recommendation_set.model_copy(deep=True)
    # Rebuilt through validation: assigning to the fields would skip the reason rule.
    updated.recommendations[index] = Recommendation.model_validate(decided)
    return updated


def recommendations_from_assessment(assessment: LegalOpsAssessment) -> RecommendationSet:
    """One recommendation per rule finding: the action the rules recommend for it."""

    matter = assessment.matter
    return RecommendationSet(
        schema=SET_SCHEMA,
        source_digest=hashlib.sha256(
            json.dumps(matter.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        recommendations=[
            Recommendation(
                id=f"finding-{index}",
                locator=f"finding {index} | {finding.category} | severity {finding.severity}",
                original_text=finding.evidence,
                proposed_text=finding.recommended_action,
                rationale=finding.summary,
                source_refs=all_source_refs(matter),
            )
            for index, finding in enumerate(assessment.findings, start=1)
        ],
    )
