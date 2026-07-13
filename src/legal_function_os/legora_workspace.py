"""Deterministic Lists, workflow definitions and local knowledge portal."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from legal_function_os.board_pack import build_board_pack

ALLOWED_STEPS = {"validate_intake", "risk_triage", "assign_owner", "check_sla", "collect_evidence", "human_approval", "board_pack"}


def build_operational_list(requests: list[dict[str, Any]], period: str) -> dict[str, Any]:
    pack = build_board_pack(requests, period=period)
    by_id = {str(item.get("id")): item for item in requests}
    rows = []
    for decision in pack.decisions:
        source = by_id.get(decision.request_id, {})
        rows.append({"id": f"list:{decision.request_id}", "request_id": decision.request_id, "kind": "legal_request", "title": decision.title, "owner": decision.queue, "priority": decision.priority, "risk": decision.risk, "sla_response_hours": decision.sla_response_hours, "sla_resolution_days": decision.sla_resolution_days, "deadline": source.get("deadline"), "dependencies": list(source.get("dependencies", [])), "source_refs": [f"synthetic-request:{decision.request_id}"], "status": "blocked" if decision.priority == "P1_blocker" or source.get("sla_breached") else "review_required", "evidence_refs": []})
    rows.sort(key=lambda row: ({"blocked": 0, "review_required": 1}[row["status"]], {"P1_blocker": 0, "P2_high": 1, "P3_standard": 2, "P4_low": 3}.get(row["priority"], 4), row["request_id"]))
    return {"schema": "legal-function-os.operational-list.v1", "period": period, "rows": rows, "filters": {"blocked": sum(row["status"] == "blocked" for row in rows), "overdue": sum(bool(by_id.get(row["request_id"], {}).get("sla_breached")) for row in rows), "awaiting_business_input": sum(bool(by_id.get(row["request_id"], {}).get("awaiting_business_input")) for row in rows), "ready_for_approval": sum(row["status"] == "review_required" for row in rows)}, "external_action_allowed": False}


def validate_workflow_definition(definition: dict[str, Any]) -> dict[str, Any]:
    required = {"id", "name", "version", "status", "steps"}
    if not required.issubset(definition):
        raise ValueError(f"workflow definition is missing fields: {sorted(required - set(definition))}")
    if definition["status"] not in {"draft", "active", "retired"} or int(definition["version"]) < 1:
        raise ValueError("workflow status or version is invalid")
    invalid = [step for step in definition["steps"] if step.get("type") not in ALLOWED_STEPS]
    if invalid:
        raise ValueError(f"unsupported workflow step: {invalid[0].get('type')}")
    if not any(step["type"] == "human_approval" for step in definition["steps"]):
        raise ValueError("workflow requires a human approval step")
    return {"schema": "workflow.definition.v1", **definition, "external_action_allowed": False}


def build_workflow_library() -> list[dict[str, Any]]:
    return [validate_workflow_definition({"id": "workflow:legal-request", "name": "Legal request triage and approval", "version": 1, "status": "active", "steps": [{"id": "intake", "type": "validate_intake"}, {"id": "risk", "type": "risk_triage"}, {"id": "owner", "type": "assign_owner"}, {"id": "sla", "type": "check_sla"}, {"id": "evidence", "type": "collect_evidence"}, {"id": "approval", "type": "human_approval"}, {"id": "report", "type": "board_pack"}]})]


def dry_run_workflow(definition: dict[str, Any], operational_list: dict[str, Any]) -> dict[str, Any]:
    definition = validate_workflow_definition(definition)
    blocked = sum(row["status"] == "blocked" for row in operational_list["rows"])
    return {"schema": "workflow.run.v1", "id": f"run:{definition['id']}:v{definition['version']}", "definition_id": definition["id"], "definition_version": definition["version"], "status": "blocked" if blocked else "review_required", "step_results": [{"step_id": step["id"], "status": "blocked" if blocked and step["type"] in {"risk_triage", "human_approval", "board_pack"} else "complete"} for step in definition["steps"]], "external_action_allowed": False}


def build_knowledge_portal(requests: list[dict[str, Any]], workflows: list[dict[str, Any]]) -> dict[str, Any]:
    resources = [{"id": f"resource:{item.get('id', index)}", "title": str(item.get("title", "Synthetic request precedent")), "passage": str(item.get("description") or item.get("summary") or "Synthetic legal request precedent for local review."), "source_ref": f"synthetic-request:{item.get('id', index)}", "approved": True} for index, item in enumerate(requests, start=1)]
    resources.extend({"id": f"resource:{workflow['id']}", "title": workflow["name"], "passage": "The workflow validates intake, applies deterministic risk triage, collects evidence and requires human approval.", "source_ref": f"workflow:{workflow['id']}:v{workflow['version']}", "approved": True} for workflow in workflows)
    digest = hashlib.sha256(json.dumps(resources, sort_keys=True).encode()).hexdigest()
    return {"schema": "portal.share.v1", "local_only": True, "approved": True, "resource_digest": digest, "resources": resources, "internal_prompts_exposed": False, "external_action_allowed": False}


def answer_portal(portal: dict[str, Any], query: str) -> dict[str, Any]:
    terms = [term for term in query.lower().split() if len(term) > 3]
    match = next((resource for resource in portal["resources"] if any(term in (resource["title"] + " " + resource["passage"]).lower() for term in terms)), None)
    if match is None:
        return {"status": "insufficient_evidence", "answer": "The approved local resources do not support an answer.", "citations": []}
    return {"status": "grounded", "answer": match["passage"], "citations": [{"resource_id": match["id"], "source_ref": match["source_ref"]}]}


def render_portal(portal: dict[str, Any], output: Path) -> Path:
    cards = "".join(f"<article><h2>{html.escape(item['title'])}</h2><p>{html.escape(item['passage'])}</p><code>{html.escape(item['source_ref'])}</code></article>" for item in portal["resources"])
    document = f"<!doctype html><html><head><meta charset='utf-8'><title>Legal Function Knowledge Portal</title><style>body{{font:15px system-ui;max-width:1000px;margin:40px auto;color:#172033}}article{{border:1px solid #d9dee8;border-radius:10px;padding:16px;margin:12px 0}}code{{font-size:12px}}</style></head><body><h1>Legal Function Knowledge Portal</h1><p>Local approved knowledge only. Human review remains required.</p>{cards}</body></html>"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


def build_legora_workspace(requests: list[dict[str, Any]], period: str) -> dict[str, Any]:
    operational_list = build_operational_list(requests, period)
    workflows = build_workflow_library()
    portal = build_knowledge_portal(requests, workflows)
    return {"schema": "legal-function-os.legora-workspace.v1", "operational_list": operational_list, "workflow_definitions": workflows, "workflow_runs": [dry_run_workflow(workflows[0], operational_list)], "knowledge_portal": portal, "portal_answer": answer_portal(portal, "Which workflow requires human approval?"), "external_action_allowed": False}
