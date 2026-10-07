"""The matter state machine: allowed transitions, who may trigger them, and the
evidence each one needs. The service evaluates the named evidence items; this
module is the single description of what is allowed."""

from __future__ import annotations

from dataclasses import dataclass

from src.pilot.models import Role, State

STATES: tuple[State, ...] = (
    "intake",
    "triage",
    "assignment",
    "review",
    "revision_requested",
    "revised",
    "approved",
    "ready_for_delivery",
    "closed",
)

EVIDENCE: dict[str, str] = {
    "intake_complete": "Every required fact, the instructions and a readable source document are present.",
    "assessment_current": "The assessment was made over the current matter version.",
    "sources_usable": "Every source reference passes the source boundary without a blocker or warning.",
    "pilot_scope_met": "The parent routing decision places the matter inside the pilot charter.",
    "decision_authority_agreed": "The recorded decision authority covers the approval tier the parent approval matrix requires.",
    "reviewers_available": "An onboarded, available matter owner, final approver and every required specialist are assigned, with duties separated.",
    "revision_reason_recorded": "The request names at least one open comment and gives a reason.",
    "revision_addressed": "Every comment named in the revision request has a response from the matter owner.",
    "changes_decided": "Every proposed change on the current version is accepted, rejected or amended.",
    "no_open_blockers": "No critical comment, clarification request or coverage gap is open.",
    "specialist_signoffs_current": "Every required specialist signed off on the current version.",
    "approver_authorised": "The approver holds the required tier and is neither the requester nor the matter owner.",
    "export_gate_passes": "The single export-eligibility check passes for a delivery package.",
    "delivery_manifest_current": "A delivery manifest exists for the current version and reviewed state.",
    "acceptance_recorded": "The requester recorded an acceptance note.",
    "withdrawal_reason_recorded": "A reason for closing without delivery is recorded.",
}


@dataclass(frozen=True)
class Transition:
    source: State
    target: State
    command: str
    roles: tuple[Role, ...]
    evidence: tuple[str, ...]


_REVIEWERS: tuple[Role, ...] = ("matter_owner", "specialist_reviewer", "final_approver")

TRANSITIONS: tuple[Transition, ...] = (
    Transition("intake", "triage", "submit_intake", ("business_requester",), ("intake_complete",)),
    Transition(
        "triage",
        "assignment",
        "complete_triage",
        ("matter_owner",),
        ("assessment_current", "sources_usable", "pilot_scope_met", "decision_authority_agreed"),
    ),
    Transition("assignment", "review", "start_review", ("matter_owner",), ("reviewers_available",)),
    Transition(
        "review",
        "revision_requested",
        "request_revision",
        _REVIEWERS,
        ("revision_reason_recorded",),
    ),
    Transition(
        "review",
        "approved",
        "approve",
        ("final_approver",),
        (
            "assessment_current",
            "sources_usable",
            "changes_decided",
            "no_open_blockers",
            "specialist_signoffs_current",
            "approver_authorised",
        ),
    ),
    Transition(
        "revision_requested",
        "revised",
        "submit_revision",
        ("matter_owner",),
        ("revision_addressed",),
    ),
    Transition("revised", "review", "resume_review", _REVIEWERS, ("assessment_current",)),
    Transition(
        "approved",
        "revision_requested",
        "request_revision",
        _REVIEWERS,
        ("revision_reason_recorded",),
    ),
    Transition(
        "approved",
        "ready_for_delivery",
        "prepare_delivery",
        ("matter_owner",),
        ("export_gate_passes",),
    ),
    Transition(
        "ready_for_delivery",
        "revision_requested",
        "request_revision",
        _REVIEWERS,
        ("revision_reason_recorded",),
    ),
    Transition(
        "ready_for_delivery",
        "closed",
        "accept_delivery",
        ("business_requester",),
        ("delivery_manifest_current", "acceptance_recorded"),
    ),
)

# A substantive change after triage always returns the matter to "revised": the new
# version is reassessed and every sign-off and approval given earlier is invalidated.
REASSESSMENT_SOURCES: frozenset[State] = frozenset(
    {"assignment", "review", "revision_requested", "revised", "approved", "ready_for_delivery"}
)
WITHDRAWAL_ROLES: tuple[Role, ...] = ("matter_owner", "business_requester")


def find_transition(source: str, command: str) -> Transition | None:
    return next(
        (t for t in TRANSITIONS if t.source == source and t.command == command),
        None,
    )


def allowed_commands(source: str) -> list[Transition]:
    return [t for t in TRANSITIONS if t.source == source]


def describe_transitions() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "from": t.source,
            "to": t.target,
            "command": t.command,
            "roles": list(t.roles),
            "evidence": list(t.evidence),
        }
        for t in TRANSITIONS
    ]
    rows.append(
        {
            "from": "any state after triage",
            "to": "revised",
            "command": "amend_matter",
            "roles": ["business_requester", "matter_owner"],
            "evidence": ["substantive change to document, facts, instructions or playbook"],
        }
    )
    rows.append(
        {
            "from": "any open state",
            "to": "closed",
            "command": "withdraw",
            "roles": list(WITHDRAWAL_ROLES),
            "evidence": ["withdrawal_reason_recorded"],
        }
    )
    return rows
