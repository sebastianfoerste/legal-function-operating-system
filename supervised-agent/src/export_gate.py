"""The single export-eligibility check for every consequential export.

Both the stateless library path (``render_annotated_docx``) and the store-backed
pilot path build an ``ExportContext`` and call ``evaluate_export_eligibility``.
No other code decides whether a reviewed document or a delivery package may be
written.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from models import AuditChainVerification, LegalOpsAssessment, verify_audit_chain

ExportKind = Literal["internal_review", "reviewed_document", "delivery_package"]
CheckStatus = Literal["pass", "fail", "not_applicable"]

TERMINAL_CHANGE_DECISIONS = frozenset({"accepted", "rejected", "amended"})
DELIVERY_STATES = frozenset({"approved", "ready_for_delivery"})

# An internal review export only needs a clean source boundary and an intact record:
# reviewers must be able to read a draft that still has open findings.
_REQUIRED_CHECKS: dict[str, frozenset[str]] = {
    "internal_review": frozenset(
        {
            "assessment_present",
            "assessment_bound_to_version",
            "source_boundary_clear",
            "document_hash_matches",
            "audit_chain_verified",
        }
    ),
}
_ALL_CHECKS = (
    "assessment_present",
    "assessment_bound_to_version",
    "assessment_approved",
    "source_boundary_clear",
    "no_blocker_findings",
    "document_hash_matches",
    "changes_decided",
    "no_unresolved_blockers",
    "required_reviewer_decisions",
    "audit_chain_verified",
    "matter_state_permits_delivery",
)


class ExportBlockedError(ValueError):
    """Raised when an export is attempted without passing the eligibility check."""

    def __init__(self, eligibility: "ExportEligibility") -> None:
        self.eligibility = eligibility
        super().__init__(f"{eligibility.kind} export blocked: " + "; ".join(eligibility.reasons()))


class GateCheck(BaseModel):
    check_id: str
    status: CheckStatus
    required: bool
    detail: str


class ExportEligibility(BaseModel):
    schema_id: Literal["legal-ops-agent.export-eligibility.v1"] = Field(
        "legal-ops-agent.export-eligibility.v1", alias="schema"
    )
    model_config = {"populate_by_name": True}

    kind: ExportKind
    eligible: bool
    checks: list[GateCheck]
    # No export path in this repository sends, files or publishes anything.
    external_delivery_allowed: Literal[False] = False

    def reasons(self) -> list[str]:
        return [
            f"{check.check_id}: {check.detail}"
            for check in self.checks
            if check.required and check.status != "pass"
        ]


class RequiredDecision(BaseModel):
    """One reviewer decision the matter needs, and the decision record found for it."""

    requirement: str
    binds_review_hash: bool = False
    actor_id: str | None = None
    version: int | None = None
    content_hash: str | None = None
    review_hash: str | None = None
    invalidated: bool = False


class StatefulContext(BaseModel):
    """Facts only a persistent matter record can supply."""

    matter_id: str
    matter_state: str
    current_version: int
    current_content_hash: str
    assessment_version: int
    assessment_content_hash: str
    current_review_hash: str
    open_blocking_items: list[str]
    required_decisions: list[RequiredDecision]
    matter_chain: AuditChainVerification


class ExportContext(BaseModel):
    kind: ExportKind
    assessment: LegalOpsAssessment | None = None
    change_set_assessment_id: str | None = None
    recorded_document_sha256: str | None = None
    actual_document_sha256: str | None = None
    change_decisions: dict[str, str] = Field(default_factory=dict)
    stateful: StatefulContext | None = None


def _check_binding(context: ExportContext) -> tuple[CheckStatus, str]:
    assessment = context.assessment
    if assessment is None:
        return "fail", "no assessment to bind the change set to"
    if context.change_set_assessment_id != assessment.assessment_id:
        return (
            "fail",
            "change set was built for a different assessment "
            f"({context.change_set_assessment_id} != {assessment.assessment_id})",
        )
    stateful = context.stateful
    if stateful is None:
        return "pass", "change set and assessment share one assessment id"
    if stateful.assessment_version != stateful.current_version:
        return (
            "fail",
            f"assessment belongs to version {stateful.assessment_version}, "
            f"current version is {stateful.current_version}",
        )
    if stateful.assessment_content_hash != stateful.current_content_hash:
        return "fail", "assessment was made over different matter content; reassess"
    return "pass", f"assessment is bound to version {stateful.current_version}"


def _check_decisions(stateful: StatefulContext) -> tuple[CheckStatus, str]:
    problems: list[str] = []
    for decision in stateful.required_decisions:
        if decision.actor_id is None:
            problems.append(f"{decision.requirement} is missing")
        elif decision.invalidated:
            problems.append(f"{decision.requirement} was invalidated by a later change")
        elif (
            decision.version != stateful.current_version
            or decision.content_hash != stateful.current_content_hash
        ):
            problems.append(
                f"{decision.requirement} was given on version {decision.version}, "
                f"not the current version {stateful.current_version}"
            )
        elif decision.binds_review_hash and decision.review_hash != stateful.current_review_hash:
            problems.append(
                f"{decision.requirement} predates a later change decision or comment resolution"
            )
    if problems:
        return "fail", "; ".join(problems)
    if not stateful.required_decisions:
        return "fail", "no reviewer decision requirement was derived for this matter"
    return "pass", f"{len(stateful.required_decisions)} required decision(s) bound to this version"


def evaluate_export_eligibility(context: ExportContext) -> ExportEligibility:
    """Evaluate every export condition and report each one, pass or fail."""

    assessment = context.assessment
    stateful = context.stateful
    results: dict[str, tuple[CheckStatus, str]] = {}

    results["assessment_present"] = (
        ("pass", f"assessment {assessment.assessment_id}")
        if assessment is not None
        else ("fail", "no assessment exists for this matter version")
    )
    results["assessment_bound_to_version"] = _check_binding(context)

    if assessment is None:
        missing: tuple[CheckStatus, str] = ("fail", "no assessment")
        for check_id in ("assessment_approved", "source_boundary_clear", "no_blocker_findings"):
            results[check_id] = missing
        results["audit_chain_verified"] = missing
    else:
        approved = assessment.review_state == "approved" and assessment.export_allowed
        results["assessment_approved"] = (
            ("pass", "parent assessment is approved with a documented review note")
            if approved
            else (
                "fail",
                f"parent assessment is {assessment.review_state} and not approved for export",
            )
        )
        blocked_sources = [
            record.source_ref
            for record in assessment.source_verifications
            if record.status == "blocker"
        ]
        results["source_boundary_clear"] = (
            ("fail", f"{len(blocked_sources)} blocked source reference(s) prevent processing")
            if blocked_sources
            else ("pass", "no blocked source prefix")
        )
        blockers = [f.category for f in assessment.findings if f.severity == "blocker"]
        results["no_blocker_findings"] = (
            ("fail", f"blocker finding(s) remain: {', '.join(blockers)}")
            if blockers
            else ("pass", "no blocker finding")
        )
        chain = verify_audit_chain(assessment.audit_events)
        if not chain.verified:
            results["audit_chain_verified"] = ("fail", f"assessment audit chain: {chain.reason}")
        elif stateful is not None and not stateful.matter_chain.verified:
            results["audit_chain_verified"] = (
                "fail",
                f"matter event chain: {stateful.matter_chain.reason}",
            )
        else:
            results["audit_chain_verified"] = ("pass", "audit chain intact")

    if context.recorded_document_sha256 is None or context.actual_document_sha256 is None:
        results["document_hash_matches"] = ("fail", "no document digest to compare")
    elif context.recorded_document_sha256 != context.actual_document_sha256:
        results["document_hash_matches"] = (
            "fail",
            "source DOCX digest does not match the reviewed change set",
        )
    else:
        results["document_hash_matches"] = ("pass", "document digest matches the reviewed version")

    undecided = sorted(
        change_id
        for change_id, decision in context.change_decisions.items()
        if decision not in TERMINAL_CHANGE_DECISIONS
    )
    results["changes_decided"] = (
        (
            "fail",
            "export requires every proposed change to be decided; "
            f"undecided: {', '.join(undecided)}",
        )
        if undecided
        else ("pass", f"{len(context.change_decisions)} proposed change(s) decided")
    )

    if stateful is None:
        not_applicable: tuple[CheckStatus, str] = (
            "not_applicable",
            "stateless library call: no persistent matter record to consult",
        )
        results["no_unresolved_blockers"] = not_applicable
        results["required_reviewer_decisions"] = not_applicable
        results["matter_state_permits_delivery"] = not_applicable
    else:
        results["no_unresolved_blockers"] = (
            ("fail", "unresolved: " + "; ".join(stateful.open_blocking_items))
            if stateful.open_blocking_items
            else ("pass", "no open critical comment, clarification or hold")
        )
        results["required_reviewer_decisions"] = _check_decisions(stateful)
        results["matter_state_permits_delivery"] = (
            ("pass", f"matter state is {stateful.matter_state}")
            if stateful.matter_state in DELIVERY_STATES
            else ("fail", f"matter state {stateful.matter_state} does not permit delivery")
        )

    # A delivery package only exists for a persistent matter; a stateless caller can
    # never satisfy the reviewer-decision requirement, so it must not get one.
    if context.kind == "delivery_package" and stateful is None:
        results["required_reviewer_decisions"] = (
            "fail",
            "a delivery package requires recorded reviewer decisions from the matter store",
        )

    required = _REQUIRED_CHECKS.get(context.kind, frozenset(_ALL_CHECKS))
    checks = [
        GateCheck(
            check_id=check_id,
            status=results[check_id][0],
            required=check_id in required and results[check_id][0] != "not_applicable",
            detail=results[check_id][1],
        )
        for check_id in _ALL_CHECKS
    ]
    eligible = all(check.status == "pass" for check in checks if check.required)
    return ExportEligibility(
        schema="legal-ops-agent.export-eligibility.v1",
        kind=context.kind,
        eligible=eligible,
        checks=checks,
    )


def require_export_eligibility(context: ExportContext) -> ExportEligibility:
    eligibility = evaluate_export_eligibility(context)
    if not eligibility.eligible:
        raise ExportBlockedError(eligibility)
    return eligibility
