"""Deterministic capacity scenarios for a synthetic legal-matter portfolio."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from legal_function_os.rules import Decision, decide

SCHEMA = "legal-function-os.capacity-simulation.v1"

_PRIORITY_EFFORT = {
    "P1_blocker": 8,
    "P2_high": 5,
    "P3_standard": 3,
    "P4_low": 1,
}


@dataclass(frozen=True)
class CapacityScenario:
    name: str
    label: str
    queue_capacity_points: dict[str, int]
    gc_approval_slots: int
    external_counsel_slots: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CapacityScenario":
        capacities = {
            str(queue): int(points)
            for queue, points in payload.get("queue_capacity_points", {}).items()
        }
        if not capacities or any(points < 0 for points in capacities.values()):
            raise ValueError("queue_capacity_points must contain non-negative capacities")
        return cls(
            name=str(payload["name"]),
            label=str(payload.get("label", payload["name"])),
            queue_capacity_points=capacities,
            gc_approval_slots=max(0, int(payload.get("gc_approval_slots", 0))),
            external_counsel_slots=max(0, int(payload.get("external_counsel_slots", 0))),
        )


def _effort_points(decision: Decision, request: dict[str, Any]) -> int:
    """Return transparent illustrative work points for one request."""

    points = _PRIORITY_EFFORT[decision.priority]
    points += 2 if decision.risk == "HIGH" else 0
    points += 1 if decision.board_attention else 0
    points += 1 if decision.external_counsel != "in-house" else 0
    points += 1 if "General Counsel" in decision.approval_chain else 0
    points += 1 if request.get("sla_breached") else 0
    return points


def _scenario_result(
    requests: list[dict[str, Any]],
    decisions: list[Decision],
    scenario: CapacityScenario,
) -> dict[str, Any]:
    queue_rows: dict[str, dict[str, Any]] = {}
    request_rows: list[dict[str, Any]] = []
    for request, decision in zip(requests, decisions, strict=True):
        points = _effort_points(decision, request)
        request_rows.append(
            {
                "request_id": decision.request_id,
                "title": decision.title,
                "queue": decision.queue,
                "priority": decision.priority,
                "risk": decision.risk,
                "effort_points": points,
                "requires_gc_approval": "General Counsel" in decision.approval_chain,
                "requires_external_counsel": decision.external_counsel != "in-house",
            }
        )
        row = queue_rows.setdefault(
            decision.queue,
            {"queue": decision.queue, "demand_points": 0, "request_count": 0},
        )
        row["demand_points"] += points
        row["request_count"] += 1

    all_queues = sorted(set(queue_rows) | set(scenario.queue_capacity_points))
    queue_capacity = []
    for queue in all_queues:
        demand = int(queue_rows.get(queue, {}).get("demand_points", 0))
        request_count = int(queue_rows.get(queue, {}).get("request_count", 0))
        capacity = int(scenario.queue_capacity_points.get(queue, 0))
        backlog = max(0, demand - capacity)
        queue_capacity.append(
            {
                "queue": queue,
                "request_count": request_count,
                "demand_points": demand,
                "capacity_points": capacity,
                "backlog_points": backlog,
                "utilization": round(demand / capacity, 3) if capacity else None,
                "status": "constrained" if backlog else "within_assumption",
            }
        )

    gc_demand = sum("General Counsel" in decision.approval_chain for decision in decisions)
    counsel_demand = sum(decision.external_counsel != "in-house" for decision in decisions)
    backlog_points = sum(row["backlog_points"] for row in queue_capacity)
    gc_overflow = max(0, gc_demand - scenario.gc_approval_slots)
    counsel_overflow = max(0, counsel_demand - scenario.external_counsel_slots)
    constrained = bool(backlog_points or gc_overflow or counsel_overflow)
    binding_constraints = [
        {
            "constraint_id": f"queue:{row['queue']}",
            "constraint_type": "queue_capacity",
            "label": row["queue"],
            "demand": row["demand_points"],
            "capacity": row["capacity_points"],
            "minimum_uplift": row["backlog_points"],
            "review_owner": "Legal Operations",
        }
        for row in queue_capacity
        if row["backlog_points"]
    ]
    if gc_overflow:
        binding_constraints.append(
            {
                "constraint_id": "approval:general-counsel",
                "constraint_type": "approval_capacity",
                "label": "General Counsel approvals",
                "demand": gc_demand,
                "capacity": scenario.gc_approval_slots,
                "minimum_uplift": gc_overflow,
                "review_owner": "General Counsel",
            }
        )
    if counsel_overflow:
        binding_constraints.append(
            {
                "constraint_id": "coordination:external-counsel",
                "constraint_type": "external_counsel_capacity",
                "label": "External-counsel coordination",
                "demand": counsel_demand,
                "capacity": scenario.external_counsel_slots,
                "minimum_uplift": counsel_overflow,
                "review_owner": "General Counsel",
            }
        )
    binding_constraints.sort(
        key=lambda row: (
            -int(row["minimum_uplift"]),
            str(row["constraint_id"]),
        )
    )

    ranked_requests = sorted(
        request_rows,
        key=lambda row: (
            {"P1_blocker": 0, "P2_high": 1, "P3_standard": 2, "P4_low": 3}[row["priority"]],
            -row["effort_points"],
            row["request_id"],
        ),
    )
    return {
        "scenario": asdict(scenario),
        "status": "CONSTRAINED" if constrained else "WITHIN_ASSUMPTIONS",
        "summary": {
            "requests": len(decisions),
            "demand_points": sum(row["effort_points"] for row in request_rows),
            "capacity_points": sum(scenario.queue_capacity_points.values()),
            "backlog_points": backlog_points,
            "constrained_queues": sum(row["status"] == "constrained" for row in queue_capacity),
            "gc_approval_demand": gc_demand,
            "gc_approval_capacity": scenario.gc_approval_slots,
            "gc_approval_overflow": gc_overflow,
            "external_counsel_demand": counsel_demand,
            "external_counsel_capacity": scenario.external_counsel_slots,
            "external_counsel_overflow": counsel_overflow,
            "binding_constraints": len(binding_constraints),
        },
        "queue_capacity": queue_capacity,
        "binding_constraints": binding_constraints,
        "priority_review_queue": ranked_requests,
        "external_action_allowed": False,
    }


def build_capacity_simulation(
    requests: list[dict[str, Any]],
    scenario_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run the same synthetic request portfolio through multiple capacity assumptions."""

    if not requests:
        raise ValueError("capacity simulation requires at least one request")
    if not isinstance(scenario_payloads, list) or any(
        not isinstance(payload, dict) for payload in scenario_payloads
    ):
        raise ValueError("capacity scenarios must be a JSON array of objects")
    scenarios = [CapacityScenario.from_dict(payload) for payload in scenario_payloads]
    if len(scenarios) < 2:
        raise ValueError("capacity simulation requires at least two scenarios")

    decisions = [decide(request) for request in requests]
    results = [_scenario_result(requests, decisions, scenario) for scenario in scenarios]
    baseline = results[0]["summary"]
    comparisons = [
        {
            "scenario": result["scenario"]["name"],
            "backlog_points_delta": result["summary"]["backlog_points"]
            - baseline["backlog_points"],
            "constrained_queues_delta": result["summary"]["constrained_queues"]
            - baseline["constrained_queues"],
            "gc_approval_overflow_delta": result["summary"]["gc_approval_overflow"]
            - baseline["gc_approval_overflow"],
            "external_counsel_overflow_delta": result["summary"][
                "external_counsel_overflow"
            ]
            - baseline["external_counsel_overflow"],
        }
        for result in results
    ]
    return {
        "schema": SCHEMA,
        "assumption_notice": (
            "Capacity points and slots are illustrative management assumptions over "
            "synthetic requests. They are planning inputs, not time estimates or legal advice."
        ),
        "scenarios": results,
        "comparison_to_first_scenario": comparisons,
        "decision_brief": {
            "baseline_scenario": results[0]["scenario"]["name"],
            "baseline_binding_constraints": results[0]["binding_constraints"],
            "scenarios_within_assumptions": [
                result["scenario"]["name"]
                for result in results
                if result["status"] == "WITHIN_ASSUMPTIONS"
            ],
            "decision_status": (
                "HUMAN_REVIEW_REQUIRED"
                if results[0]["binding_constraints"]
                else "NO_BINDING_CONSTRAINTS_IN_BASELINE"
            ),
        },
        "review_gate": (
            "A human owner must validate effort assumptions, staffing availability, "
            "approval capacity, and any external-counsel instruction."
        ),
        "external_action_allowed": False,
    }


def render_capacity_markdown(simulation: dict[str, Any]) -> str:
    lines = [
        "# Legal Function Capacity Simulation",
        "",
        simulation["assumption_notice"],
        "",
    ]
    for result in simulation["scenarios"]:
        summary = result["summary"]
        lines.extend(
            [
                f"## {result['scenario']['label']}",
                "",
                f"**Status: {result['status']}**",
                "",
                "| Queue | Requests | Demand | Capacity | Backlog | Utilization |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in result["queue_capacity"]:
            utilization = (
                "n/a"
                if row["utilization"] is None
                else f"{row['utilization'] * 100:.1f}%"
            )
            lines.append(
                f"| {row['queue']} | {row['request_count']} | {row['demand_points']} "
                f"| {row['capacity_points']} | {row['backlog_points']} | {utilization} |"
            )
        lines.extend(
            [
                "",
                f"- GC approval demand/capacity: {summary['gc_approval_demand']}/"
                f"{summary['gc_approval_capacity']}",
                f"- External-counsel coordination demand/capacity: "
                f"{summary['external_counsel_demand']}/"
                f"{summary['external_counsel_capacity']}",
                "",
                "### Binding constraints",
                "",
                "| Constraint | Type | Demand | Capacity | Minimum uplift | Review owner |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        if result["binding_constraints"]:
            for constraint in result["binding_constraints"]:
                lines.append(
                    f"| {constraint['label']} | {constraint['constraint_type']} "
                    f"| {constraint['demand']} | {constraint['capacity']} "
                    f"| {constraint['minimum_uplift']} | {constraint['review_owner']} |"
                )
        else:
            lines.append("| none | n/a | 0 | 0 | 0 | n/a |")
        lines.extend(
            [
                "",
                "### Priority review queue",
                "",
                "| ID | Priority | Risk | Queue | Work points |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for row in result["priority_review_queue"]:
            lines.append(
                f"| {row['request_id']} | {row['priority']} | {row['risk']} "
                f"| {row['queue']} | {row['effort_points']} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Review gate",
            "",
            simulation["review_gate"],
            "",
            "No staffing change, instruction, approval, or external communication is executed.",
            "",
        ]
    )
    return "\n".join(lines)
