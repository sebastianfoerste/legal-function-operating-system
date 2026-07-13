"""Request workspace, guided triage workflows and GC operations command center."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from legal_function_os.board_pack import BoardPack, build_board_pack


@dataclass(frozen=True)
class RequestVaultRecord:
    request_id: str
    title: str
    request_type: str
    provenance_ref: str
    risk: str
    priority: str
    queue: str
    approval_tier: str
    external_action_allowed: bool = False


@dataclass(frozen=True)
class TriageWorkflowStep:
    key: str
    label: str
    status: Literal["complete", "review_required", "blocked"]
    evidence: str
    next_action: str


@dataclass(frozen=True)
class TriageWorkflow:
    request_id: str
    owner_queue: str
    status: Literal["review_required", "blocked"]
    steps: list[TriageWorkflowStep]
    external_action_allowed: bool = False


def build_legal_function_workspace(
    requests: list[dict[str, Any]],
    *,
    period: str = "current period",
) -> dict[str, Any]:
    pack = build_board_pack(requests, period=period)
    request_by_id = {str(request.get("id", "REQ-?")): request for request in requests}
    records = [
        RequestVaultRecord(
            request_id=decision.request_id,
            title=decision.title,
            request_type=decision.type,
            provenance_ref=f"synthetic-request:{decision.request_id}",
            risk=decision.risk,
            priority=decision.priority,
            queue=decision.queue,
            approval_tier=decision.approval_chain[-1],
        )
        for decision in pack.decisions
    ]
    workflows = [
        _triage_workflow(decision, request_by_id.get(decision.request_id, {}))
        for decision in pack.decisions
    ]
    return {
        "schema": "legal-function-os.workspace.v1",
        "request_vault": {
            "schema": "legal-function-os.request-vault.v1",
            "source_mode": "synthetic_local_json",
            "records": [asdict(record) for record in records],
            "external_action_allowed": False,
        },
        "triage_workflows": {
            "schema": "legal-function-os.triage-workflows.v1",
            "workflows": [
                {
                    **asdict(workflow),
                    "steps": [asdict(step) for step in workflow.steps],
                }
                for workflow in workflows
            ],
            "execution_mode": "deterministic_supervised",
            "external_action_allowed": False,
        },
        "command_center": _command_center(pack, workflows),
        "review_gate": "Human approval remains required for every consequential decision.",
        "external_action_allowed": False,
    }


def _triage_workflow(decision, request: dict[str, Any]) -> TriageWorkflow:
    sla_breached = bool(request.get("sla_breached"))
    blocked = decision.priority == "P1_blocker" or sla_breached
    status: Literal["review_required", "blocked"] = "blocked" if blocked else "review_required"
    steps = [
        TriageWorkflowStep(
            key="intake",
            label="Validate request intake",
            status="complete",
            evidence=f"synthetic-request:{decision.request_id}",
            next_action="Keep the structured request as the source of truth.",
        ),
        TriageWorkflowStep(
            key="risk",
            label="Apply risk and priority rules",
            status="blocked" if decision.priority == "P1_blocker" else "complete",
            evidence=f"risk:{decision.risk};priority:{decision.priority}",
            next_action="Escalate immediately." if decision.priority == "P1_blocker" else "Confirm the deterministic result.",
        ),
        TriageWorkflowStep(
            key="routing",
            label="Assign owner queue and SLA",
            status="blocked" if sla_breached else "complete",
            evidence=(
                f"queue:{decision.queue};response_hours:{decision.sla_response_hours};"
                f"resolution_days:{decision.sla_resolution_days}"
            ),
            next_action="Open SLA remediation." if sla_breached else "Notify the internal owner after review.",
        ),
        TriageWorkflowStep(
            key="approval",
            label="Record binding approval",
            status="review_required",
            evidence=f"approval-tier:{decision.approval_chain[-1]}",
            next_action=f"Obtain documented approval from {decision.approval_chain[-1]}.",
        ),
    ]
    return TriageWorkflow(
        request_id=decision.request_id,
        owner_queue=decision.queue,
        status=status,
        steps=steps,
    )


def _command_center(pack: BoardPack, workflows: list[TriageWorkflow]) -> dict[str, Any]:
    status_by_request_id = {workflow.request_id: workflow.status for workflow in workflows}
    rows = [
        {
            "request_id": decision.request_id,
            "title": decision.title,
            "risk": decision.risk,
            "priority": decision.priority,
            "queue": decision.queue,
            "approval_tier": decision.approval_chain[-1],
            "external_counsel": decision.external_counsel,
            "status": status_by_request_id.get(decision.request_id, "review_required"),
        }
        for decision in pack.decisions
    ]
    rows.sort(
        key=lambda row: (
            {"blocked": 0, "review_required": 1}[row["status"]],
            {"P1_blocker": 0, "P2_high": 1, "P3_standard": 2, "P4_low": 3}.get(
                row["priority"], 4
            ),
            row["request_id"],
        )
    )
    return {
        "schema": "legal-function-os.gc-command-center.v1",
        "period": pack.period,
        "summary": {
            **pack.totals,
            "blocked_workflows": sum(workflow.status == "blocked" for workflow in workflows),
            "review_required_workflows": sum(
                workflow.status == "review_required" for workflow in workflows
            ),
        },
        "rows": rows,
        "next_actions": [
            "Resolve SLA breaches and P1 blockers first.",
            "Record binding approvals for high-risk and high-value matters.",
            "Review external-counsel referrals and confirm scope before instruction.",
        ],
        "external_action_allowed": False,
    }
