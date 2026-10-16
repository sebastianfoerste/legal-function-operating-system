"""Deterministic rules for a legal function operating system.

Each function takes a single legal request (a dict) and returns a small, explained
decision: how it is routed, its SLA, who must approve it, whether it escalates, and
whether external counsel is indicated. The rules are intentionally legible. A lawyer
should be able to read them and agree or disagree. Nothing here is legal advice;
all bundled data is synthetic.

The value bands, queues, SLAs and thresholds come from a policy (see policy.py).
Every function takes an optional ``policy``; without one it applies the bundled
default policy, which holds the values these rules have always used.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from legal_function_os.policy import Policy, default_policy

# --- Reference data ----------------------------------------------------------

# Requester urgency, most urgent first. A request without one is "standard".
URGENCIES = ("blocker", "high", "standard", "low")

# The default policy's values, kept under their old names for existing imports.
VALUE_BANDS = list(default_policy().value_bands)
# Which internal queue owns each request type.
ROUTING = dict(default_policy().routing)
# Response / resolution targets by priority (business hours / business days).
SLA = {
    priority: {"response_hours": target.response_hours, "resolution_days": target.resolution_days}
    for priority, target in default_policy().sla.items()
}


def _policy(policy: Policy | None) -> Policy:
    return policy if policy is not None else default_policy()


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


def _value_index(band: str | None, policy: Policy | None = None) -> int:
    """Position of a value band. A missing band is the lowest; an unknown one is an error.

    Unknown bands used to count as "none", so a typo such as ">1M" silently turned a
    board-level matter into a low-risk one. Validate input first for a friendly message.
    """
    return _policy(policy).band_index(band)


# --- Risk -------------------------------------------------------------------

def assess_risk(req: dict, policy: Policy | None = None) -> tuple[str, list[str]]:
    rules = _policy(policy)
    reasons: list[str] = []
    band = req.get("value_band")
    personal_data = bool(req.get("personal_data", False))
    non_eea = bool(req.get("non_eea_transfer", False))
    uncapped = bool(req.get("uncapped_liability", False))
    rtype = req.get("type", "")

    high = False
    if non_eea and personal_data:
        high = True
        reasons.append("Personal data transferred outside the EEA.")
    if rules.reaches(band, rules.high_risk_from.value_band):
        high = True
        reasons.append(rules.high_risk_from.text)
    if uncapped:
        high = True
        reasons.append("Uncapped liability exposure.")
    if rtype == "dispute" and rules.reaches(band, rules.dispute_high_risk_from.value_band):
        high = True
        reasons.append(rules.dispute_high_risk_from.text)
    if high:
        return "HIGH", reasons

    medium = False
    if rules.reaches(band, rules.medium_risk_from.value_band):
        medium = True
        reasons.append(rules.medium_risk_from.text)
    if personal_data:
        medium = True
        reasons.append("Personal data processed.")
    if rtype in rules.elevated_types:
        medium = True
        reasons.append(f"Type '{rtype}' carries elevated baseline risk.")
    if medium:
        return "MEDIUM", reasons

    reasons.append("No elevated-risk signals detected.")
    return "LOW", reasons


# --- Priority ---------------------------------------------------------------

def assess_priority(req: dict, risk: str) -> str:
    urgency = (req.get("urgency", "standard") or "standard").lower()
    if urgency not in URGENCIES:
        # Unknown urgencies used to fall through to P3 without a word.
        raise ValueError(
            f"unknown urgency {req.get('urgency')!r}; expected one of {', '.join(URGENCIES)}"
        )
    if urgency == "blocker":
        return "P1_blocker"
    if urgency == "high" or risk == "HIGH":
        return "P2_high"
    if urgency == "low" and risk == "LOW":
        return "P4_low"
    return "P3_standard"


# --- Routing ----------------------------------------------------------------

def route(req: dict, policy: Policy | None = None) -> str:
    rules = _policy(policy)
    # A cross-border transfer overrides the default type routing.
    if req.get("non_eea_transfer"):
        return rules.non_eea_transfer_queue
    return rules.routing.get(req.get("type", ""), rules.unknown_type_queue)


# --- Approval matrix --------------------------------------------------------

def approval_chain(req: dict, risk: str, policy: Policy | None = None) -> list[str]:
    """Who must sign off before the request can close. Always ends with a human."""
    rules = _policy(policy)
    band = req.get("value_band")
    rules.band_index(band)  # an unknown band is an error, even below every threshold
    chain: list[str] = ["Reviewer"]

    if rules.reaches(band, rules.legal_ops_lead_from):
        chain.append("Legal Ops Lead")
    if rules.reaches(band, rules.general_counsel_from) or risk == "HIGH":
        chain.append("General Counsel")
    if rules.reaches(band, rules.board_note_from):
        chain.append("Board note")
    # De-duplicate while preserving order.
    return list(dict.fromkeys(chain))


# --- External counsel decision tree -----------------------------------------

def external_counsel(req: dict, risk: str, policy: Policy | None = None) -> str:
    rules = _policy(policy)
    rtype = req.get("type", "")
    if rtype == "dispute" and rules.reaches(req.get("value_band"), rules.dispute_counsel_from):
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

def escalations(
    req: dict, risk: str, priority: str, policy: Policy | None = None
) -> tuple[list[str], bool]:
    rules = _policy(policy)
    band = req.get("value_band")
    items: list[str] = []
    board_attention = False

    if req.get("sla_breached"):
        items.append("SLA breached: escalate to Legal Ops Lead.")
    if risk == "HIGH" and priority == "P1_blocker":
        items.append("High-risk blocker: escalate to General Counsel immediately.")
    if rules.reaches(band, rules.board_awareness_from.value_band):
        items.append(rules.board_awareness_from.text)
        board_attention = True
    if req.get("type") == "dispute":
        items.append("Active dispute: notify General Counsel.")
        if rules.reaches(band, rules.dispute_board_attention_from):
            board_attention = True
    return items, board_attention


# --- Top-level decision ------------------------------------------------------

def decide(req: dict, policy: Policy | None = None) -> Decision:
    rules = _policy(policy)
    risk, risk_reasons = assess_risk(req, rules)
    priority = assess_priority(req, risk)
    queue = route(req, rules)
    sla = rules.sla[priority]
    chain = approval_chain(req, risk, rules)
    counsel = external_counsel(req, risk, rules)
    esc, board = escalations(req, risk, priority, rules)

    rationale = list(risk_reasons)
    rationale.append(f"Priority {priority} from urgency '{req.get('urgency', 'standard')}' and risk {risk}.")
    rationale.append(f"Routed to {queue}; approval chain: {' -> '.join(chain)}.")
    rtype = req.get("type")
    if not rtype:
        rationale.append("No request type given: needs manual triage.")
    elif rtype not in rules.routing:
        rationale.append(f"Request type '{rtype}' is not in the routing table: needs manual triage.")
    if counsel != "in-house":
        rationale.append(counsel + " indicated.")

    return Decision(
        request_id=req.get("id", "REQ-?"),
        title=req.get("title", "Untitled request"),
        type=req.get("type", "unknown"),
        risk=risk,
        priority=priority,
        queue=queue,
        sla_response_hours=sla.response_hours,
        sla_resolution_days=sla.resolution_days,
        approval_chain=chain,
        external_counsel=counsel,
        escalations=esc,
        board_attention=board,
        rationale=rationale,
    )
