"""Deterministic, supervised matter agent runs."""

from __future__ import annotations

from typing import Any

from legal_function_os.rules import decide


def _step(key: str, label: str, status: str, evidence: str, next_action: str) -> dict[str, Any]:
    return {"key": key, "label": label, "status": status, "evidence": evidence, "next_action": next_action}


def _run_for(request: dict[str, Any]) -> dict[str, Any]:
    decision = decide(request)
    request_id = str(request.get("id", "REQ-?"))
    provenance = f"synthetic-request:{request_id}"
    facts = list(request.get("facts", []))
    intake_ok = bool(str(request.get("title", "")).strip()) and bool(str(request.get("type", "")).strip())
    p1 = decision.priority == "P1_blocker"
    sla_breached = bool(request.get("sla_breached"))
    steps = [
        _step("intake", "Validate request intake", "complete" if intake_ok else "blocked", provenance,
              "Keep the structured request as the source of truth." if intake_ok else "Complete title and request type before the run can proceed."),
        _step("risk_triage", "Apply risk and priority rules", "blocked" if p1 else "complete",
              f"risk:{decision.risk};priority:{decision.priority}", "Escalate immediately." if p1 else "Confirm the deterministic result."),
        _step("routing", "Assign owner queue and SLA", "blocked" if sla_breached else "complete",
              f"queue:{decision.queue};response_hours:{decision.sla_response_hours}",
              "Open SLA remediation." if sla_breached else "Notify the internal owner after review."),
        _step("evidence", "Collect supporting facts", "complete" if facts else "review_required",
              f"facts:{len(facts)};{provenance}", "Confirm the recorded facts." if facts else "Request facts from the business owner."),
        _step("response_plan", "Draft the response plan", "complete", f"approval-tier:{decision.approval_chain[-1]}",
              "Review the planned actions before any of them is executed."),
        _step("human_approval", "Record binding approval", "review_required", f"approval-tier:{decision.approval_chain[-1]}",
              f"Obtain documented approval from {decision.approval_chain[-1]}."),
    ]
    planned_actions = [
        f"Confirm queue: {decision.queue}",
        f"Respond within {decision.sla_response_hours} business hours",
        f"Obtain approval: {decision.approval_chain[-1]}",
    ]
    if decision.external_counsel != "in-house":
        planned_actions.append(f"Refer externally: {decision.external_counsel}")
    return {
        "request_id": request_id,
        "title": decision.title,
        "status": "blocked" if any(step["status"] == "blocked" for step in steps) else "review_required",
        "steps": steps,
        "response_plan": {
            "owner_queue": decision.queue,
            "sla": {"response_hours": decision.sla_response_hours, "resolution_days": decision.sla_resolution_days},
            "approval_tier": decision.approval_chain[-1],
            "planned_actions": planned_actions,
        },
        "external_action_allowed": False,
    }


def build_agent_runs(requests: list[dict[str, Any]], *, period: str = "current period") -> dict[str, Any]:
    runs = [_run_for(request) for request in requests]
    return {
        "schema": "legal-function-os.agent-runs.v1",
        "period": period,
        "runs": runs,
        "summary": {
            "total": len(runs),
            "blocked": sum(run["status"] == "blocked" for run in runs),
            "review_required": sum(run["status"] == "review_required" for run in runs),
        },
        "review_gate": "Every planned action requires documented human approval before execution.",
        "external_action_allowed": False,
    }
