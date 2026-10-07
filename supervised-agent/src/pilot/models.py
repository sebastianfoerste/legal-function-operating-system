"""Typed records for the pilot workflow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models import MatterIntake

Role = Literal["business_requester", "matter_owner", "specialist_reviewer", "final_approver"]
State = Literal[
    "intake",
    "triage",
    "assignment",
    "review",
    "revision_requested",
    "revised",
    "approved",
    "ready_for_delivery",
    "closed",
]
ValueBand = Literal["none", "<50k", "50k-250k", "250k-1m", ">1m"]
CommentSeverity = Literal["note", "major", "critical"]
CommentKind = Literal["comment", "clarification", "coverage_gap"]
AnchorKind = Literal["finding", "source_span", "change", "deliverable_section"]

# Ascending authority. The parent approval matrix names these tiers.
APPROVAL_TIERS = ("Reviewer", "Legal Ops Lead", "General Counsel")
REQUIRED_FACTS = (
    "counterparty",
    "annual_contract_value_eur",
    "signature_target_date",
    "requested_deviations",
    "business_owner",
)
DELIVERABLE_SECTIONS = (
    "executive_summary",
    "issue_and_deviation_list",
    "reviewed_document",
    "accepted_exceptions",
    "outstanding_obligations",
    "approval_record",
)
SYSTEM_ACTOR_ID = "system:supervised-agent"


class Actor(BaseModel):
    """A simulated local participant. Selecting an actor is not authentication."""

    actor_id: str = Field(..., pattern=r"^syn-[a-z0-9-]+$")
    display_name: str = Field(..., min_length=3)
    role: Role
    specialty: str | None = None
    approval_tier: str | None = None
    onboarded: bool = False
    available: bool = True
    synthetic: Literal[True] = True


class PilotIntake(BaseModel):
    """Intake for one customer-side SaaS contract-deviation matter."""

    matter: MatterIntake
    request_type: Literal["commercial_contract"] = "commercial_contract"
    value_band: ValueBand
    personal_data: bool = False
    non_eea_transfer: bool = False
    uncapped_liability: bool = False
    facts: dict[str, str] = Field(default_factory=dict)
    instructions: str = ""
    # The approval tier the sponsor agreed may accept exceptions for this matter.
    decision_authority: str = ""
    synthetic: Literal[True] = True


class ParentRouting(BaseModel):
    """Decision returned by the parent operating system's rules."""

    request: dict[str, Any]
    risk: str
    priority: str
    queue: str
    sla_response_hours: int
    sla_resolution_days: int
    approval_chain: list[str]
    external_counsel: str
    escalations: list[str]
    board_attention: bool
    rationale: list[str]


class Finding(BaseModel):
    key: str
    origin: Literal["assessment", "playbook"]
    category: str
    severity: str
    summary: str
    evidence: str
    recommended_action: str
    locator: str | None = None
    change_id: str | None = None
    specialist_role: str | None = None


class CommentResponse(BaseModel):
    author_id: str
    author_role: str
    body: str
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str


class Comment(BaseModel):
    comment_id: str
    matter_id: str
    kind: CommentKind = "comment"
    anchor_kind: AnchorKind
    anchor_id: str
    anchor_excerpt: str = ""
    anchor_status: Literal["current", "orphaned"] = "current"
    created_on_version: int
    author_id: str
    author_role: str
    addressed_to: Role | None = None
    severity: CommentSeverity = "note"
    body: str
    state: Literal["open", "resolved"] = "open"
    responses: list[CommentResponse] = Field(default_factory=list)
    resolution: str | None = None
    resolution_evidence: list[str] = Field(default_factory=list)
    resolved_by: str | None = None
    resolved_at: str | None = None
    reopen_count: int = 0
    created_at: str

    @property
    def blocking(self) -> bool:
        return self.state == "open" and (
            self.severity == "critical" or self.kind in {"clarification", "coverage_gap"}
        )
