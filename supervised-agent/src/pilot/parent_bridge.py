"""Bridge to the parent legal function operating system.

The pilot does not add a second routing or reporting model. Queue, service levels
and the approval tier come from ``legal_function_os.rules``; pilot measurements are
exported in the parent's service-event ledger so its outcome control tower can
read them; control state is exported in the shared ``legal-workflow-controls.v1``
contract.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from src.pilot.models import APPROVAL_TIERS, ParentRouting, PilotIntake

PARENT_SRC = Path(__file__).resolve().parents[3] / "src"
_URGENCY = {"low": "low", "medium": "standard", "high": "high"}

# Pilot state -> shared contract review_state.
CONTRACT_REVIEW_STATE = {
    "intake": "pending_review",
    "triage": "pending_review",
    "assignment": "pending_review",
    "review": "pending_review",
    "revision_requested": "revision_requested",
    "revised": "pending_review",
    "approved": "approved",
    "ready_for_delivery": "approved",
    "closed": "approved",
}


class ParentSystemUnavailable(RuntimeError):
    """The parent package cannot be imported (for example in a standalone export)."""


def parent_module(name: str) -> ModuleType:
    qualified = f"legal_function_os.{name}"
    try:
        return importlib.import_module(qualified)
    except ModuleNotFoundError:
        if not (PARENT_SRC / "legal_function_os").is_dir():
            raise ParentSystemUnavailable(
                "the pilot workflow needs the parent legal_function_os package for routing "
                f"and reporting; it was not found at {PARENT_SRC}"
            ) from None
        sys.path.append(str(PARENT_SRC))
        return importlib.import_module(qualified)


def parent_request(matter_id: str, intake: PilotIntake) -> dict[str, Any]:
    """Express a pilot intake as a parent legal request."""

    return {
        "id": matter_id,
        "title": intake.matter.title,
        "type": intake.request_type,
        "value_band": intake.value_band,
        "urgency": _URGENCY[intake.matter.urgency],
        "personal_data": intake.personal_data,
        "non_eea_transfer": intake.non_eea_transfer,
        "uncapped_liability": intake.uncapped_liability,
        "description": intake.matter.summary,
        "facts": [f"{key}: {value}" for key, value in sorted(intake.facts.items()) if value],
    }


def route(matter_id: str, intake: PilotIntake) -> ParentRouting:
    request = parent_request(matter_id, intake)
    decision = parent_module("rules").decide(request)
    return ParentRouting(
        request=request,
        risk=decision.risk,
        priority=decision.priority,
        queue=decision.queue,
        sla_response_hours=decision.sla_response_hours,
        sla_resolution_days=decision.sla_resolution_days,
        approval_chain=list(decision.approval_chain),
        external_counsel=decision.external_counsel,
        escalations=list(decision.escalations),
        board_attention=decision.board_attention,
        rationale=list(decision.rationale),
    )


def required_approval_tier(routing: ParentRouting) -> str:
    """The highest human tier in the parent approval chain."""

    tiers = [tier for tier in routing.approval_chain if tier in APPROVAL_TIERS]
    return max(tiers, key=APPROVAL_TIERS.index) if tiers else APPROVAL_TIERS[0]


def tier_covers(held: str | None, required: str) -> bool:
    return (
        held in APPROVAL_TIERS
        and required in APPROVAL_TIERS
        and APPROVAL_TIERS.index(held) >= APPROVAL_TIERS.index(required)
    )


def pilot_scope_exclusions(routing: ParentRouting, intake: PilotIntake) -> list[str]:
    """Charter exclusions, derived from the parent decision. Empty means in scope."""

    exclusions: list[str] = []
    if intake.value_band == ">1m" or "Board note" in routing.approval_chain:
        exclusions.append("contract value above EUR 1m needs a board note and is outside the pilot")
    if intake.uncapped_liability:
        exclusions.append("a request for uncapped liability is outside the pilot")
    if intake.non_eea_transfer and intake.personal_data:
        exclusions.append("a transfer of personal data outside the EEA is outside the pilot")
    if routing.external_counsel != "in-house":
        exclusions.append(f"the parent rules refer the matter out ({routing.external_counsel})")
    return exclusions
