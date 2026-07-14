"""Requester-safe status sharing behind a documented approval gate."""

from __future__ import annotations

from typing import Any

from legal_function_os.rules import decide

_MIN_NOTE_LENGTH = 20


def _documented(approval: dict[str, Any] | None) -> bool:
    if not approval:
        return False
    approved_by = str(approval.get("approved_by", "")).strip()
    note = " ".join(str(approval.get("note", "")).split())
    return bool(approved_by) and len(note) >= _MIN_NOTE_LENGTH


def build_shared_space(
    requests: list[dict[str, Any]],
    approvals: dict[str, dict[str, Any]],
    *,
    period: str = "current period",
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for request in requests:
        request_id = str(request.get("id", "REQ-?"))
        decision = decide(request)
        shared = _documented(approvals.get(request_id))
        blocked = decision.priority == "P1_blocker" or bool(request.get("sla_breached"))
        entries.append({
            "request_id": request_id,
            "title": decision.title,
            "shared": shared,
            "status": ("blocked" if blocked else "in_review") if shared else None,
            "owner_queue": decision.queue if shared else None,
            "sla_response_hours": decision.sla_response_hours if shared else None,
            "next_update_due": request.get("deadline") if shared else None,
            "requester_action": (
                "Bitte offene Informationen nachreichen."
                if shared and request.get("awaiting_business_input")
                else ("Keine Aktion erforderlich." if shared else None)
            ),
        })
    return {
        "schema": "legal-function-os.shared-space.v1",
        "period": period,
        "entries": entries,
        "summary": {
            "total": len(entries),
            "shared": sum(entry["shared"] for entry in entries),
            "withheld": sum(not entry["shared"] for entry in entries),
        },
        "share_gate": "Documented approval (name + note >= 20 chars) required per request.",
        "external_action_allowed": False,
    }
