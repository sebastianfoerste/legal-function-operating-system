"""Deterministic rules for a legal function operating system.

Each function takes a single legal request (a dict) and returns a small, explained
decision: how it is routed, its SLA, who must approve it, whether it escalates, and
whether external counsel is indicated. The rules are intentionally legible — a lawyer
should be able to read them and agree or disagree. Nothing here is legal advice;
all bundled data is synthetic.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

# --- Reference data ----------------------------------------------------------

VALUE_BANDS = ["none", "<50k", "50k-250k", "250k-1m", ">1m"]

# Which internal queue owns each request type.
ROUTING = {
    "commercial_contract": "Commercial",
    "vendor_review": "Commercial",
    "dpa": "Privacy",
    "privacy_query": "Privacy",
    "ai_governance": "Legal Ops (AI)",
    "corporate": "Corporate / GC",
    "fundraising": "Corporate / GC",
    "employment": "Employment",
    "dispute": "Litigation",
    "ip": "Commercial",
}

# Response / resolution targets by priority (business hours / business days).
SLA = {
    "P1_blocker": {"response_hours": 4, "resolution_days": 1},
    "P2_high": {"response_hours": 8, "resolution_days": 3},
    "P3_standard": {"response_hours": 16, "resolution_days": 5},
    "P4_low": {"response_hours": 40, "resolution_days": 10},
}


@dataclass
class Decision:
    request_id: str
    title: str
    type: str
    risk: str                  # HIGH | MEDIUM | LOW
    priority: str              # P1_blocker .. P4_low
    queue: str
    sla_response_hours: int
    sla_resolution_days: int
    approval_chain: list[str]
    external_counsel: str      # "in-house" or a referral label
    escalations: list[str]
    board_attention: bool
    rationale: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value_index(band: str) -> int:
    try:
        return VALUE_BANDS.index(band)
    except ValueError:
        return 0


# --- Risk -------------------------------------------------------------------

def assess_risk(req: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    value_idx = _value_index(req.get("value_band", "none"))
    personal_data = bool(req.get("personal_data", False))
    non_eea = bool(req.get("non_eea_transfer", False))
    uncapped = bool(req.get("uncapped_liability", False))
    rtype = req.get("type", "")

    high = False
    if non_eea and personal_data:
        high = True
        reasons.append("Personal data transferred outside the EEA.")
    if value_idx >= VALUE_BANDS.index(">1m"):
        high = True
        reasons.append("Contract value above €1m.")
    if uncapped:
        high = True
        reasons.append("Uncapped liability exposure.")
    if rtype == "dispute" and value_idx >= VALUE_BANDS.index("250k-1m"):
        high = True
        reasons.append("Dispute above €250k.")
    if high:
        return "HIGH", reasons

    medium = False
    if value_idx == VALUE_BANDS.index("250k-1m"):
        medium = True
        reasons.append("Contract value €250k–€1m.")
    if personal_data:
        medium = True
        reasons.append("Personal data processed.")
    if rtype in {"corporate", "fundraising", "ai_governance"}:
        medium = True
        reasons.append(f"Type '{rtype}' carries elevated baseline risk.")
    if medium:
        return "MEDIUM", reasons

    reasons.append("No elevated-risk signals detected.")
    return "LOW", reasons


# --- Priority ---------------------------------------------------------------

def assess_priority(req: dict, risk: str) -> str:
    urgency = (req.get("urgency", "standard") or "standard").lower()
    if urgency == "blocker":
        return "P1_blocker"
    if urgency == "high" or risk == "HIGH":
        return "P2_high"
    if urgency == "low" and risk == "LOW":
        return "P4_low"
    return "P3_standard"


# --- Routing ----------------------------------------------------------------

def route(req: dict) -> str:
    # Privacy concerns override the default type routing.
    if req.get("non_eea_transfer") or req.get("personal_data") and req.get("type") == "privacy_query":
        return "Privacy"
    return ROUTING.get(req.get("type", ""), "General")


# --- Approval matrix --------------------------------------------------------

def approval_chain(req: dict, risk: str) -> list[str]:
    """Who must sign off before the request can close. Always ends with a human."""
    value_idx = _value_index(req.get("value_band", "none"))
    chain: list[str] = ["Reviewer"]

    if value_idx >= VALUE_BANDS.index("50k-250k"):
        chain.append("Legal Ops Lead")
    if value_idx >= VALUE_BANDS.index("250k-1m") or risk == "HIGH":
        chain.append("General Counsel")
    if value_idx >= VALUE_BANDS.index(">1m"):
        chain.append("Board note")
    # De-duplicate while preserving order.
    seen: set[str] = set()
    return [c for c in chain if not (c in seen or seen.add(c))]


# --- External counsel decision tree -----------------------------------------

def external_counsel(req: dict, risk: str) -> str:
    rtype = req.get("type", "")
    value_idx = _value_index(req.get("value_band", "none"))
    if rtype == "dispute" and value_idx >= VALUE_BANDS.index("250k-1m"):
        # Material disputes need litigation capacity and procedural expertise.
        return "External: litigation counsel"
    if rtype in {"corporate", "fundraising"}:
        # Corporate events are episodic and specialist-heavy for a lean legal function.
        return "External: corporate counsel"
    if rtype == "ai_governance" and req.get("non_eea_transfer"):
        # Cross-border AI governance needs combined AI, privacy and transfer analysis.
        return "External: cross-border AI/privacy specialist"
    return "in-house"


# --- Escalation rules -------------------------------------------------------

def escalations(req: dict, risk: str, priority: str) -> tuple[list[str], bool]:
    items: list[str] = []
    board_attention = False

    if req.get("sla_breached"):
        items.append("SLA breached — escalate to Legal Ops Lead.")
    if risk == "HIGH" and priority == "P1_blocker":
        items.append("High-risk blocker — escalate to General Counsel immediately.")
    if _value_index(req.get("value_band", "none")) >= VALUE_BANDS.index(">1m"):
        items.append("Value above €1m — add to board awareness list.")
        board_attention = True
    if req.get("type") == "dispute":
        items.append("Active dispute — notify General Counsel.")
        if _value_index(req.get("value_band", "none")) >= VALUE_BANDS.index("250k-1m"):
            board_attention = True
    return items, board_attention


# --- Top-level decision ------------------------------------------------------

def decide(req: dict) -> Decision:
    risk, risk_reasons = assess_risk(req)
    priority = assess_priority(req, risk)
    queue = route(req)
    sla = SLA[priority]
    chain = approval_chain(req, risk)
    counsel = external_counsel(req, risk)
    esc, board = escalations(req, risk, priority)

    rationale = list(risk_reasons)
    rationale.append(f"Priority {priority} from urgency '{req.get('urgency', 'standard')}' and risk {risk}.")
    rationale.append(f"Routed to {queue}; approval chain: {' -> '.join(chain)}.")
    if counsel != "in-house":
        rationale.append(counsel + " indicated.")

    return Decision(
        request_id=req.get("id", "REQ-?"),
        title=req.get("title", "Untitled request"),
        type=req.get("type", "unknown"),
        risk=risk,
        priority=priority,
        queue=queue,
        sla_response_hours=sla["response_hours"],
        sla_resolution_days=sla["resolution_days"],
        approval_chain=chain,
        external_counsel=counsel,
        escalations=esc,
        board_attention=board,
        rationale=rationale,
    )
