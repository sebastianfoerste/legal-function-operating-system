"""Typed contracts and input validation for the synthetic RaaS deal desk."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Literal

RAAS_INPUT_SCHEMA = "legal-function-os.raas-deal-input.v1"

ClauseSeverity = Literal["negotiable", "requires_approval", "nonstarter"]
FinanceStatus = Literal["review_required", "blocked"]
RegulatoryStatus = Literal[
    "classification_open",
    "contract_update_required",
    "evidence_required",
    "transition_plan_required",
]
GateEffect = Literal[
    "signing_blocker",
    "deployment_blocker",
    "transition_follow_up",
]


@dataclass(frozen=True)
class ClauseReview:
    rule_id: str
    category: str
    severity: ClauseSeverity
    issue: str
    requested_position: str
    standard_position: str
    fallback_position: str
    escalation_trigger: str
    required_approvals: tuple[str, ...]
    rationale: str
    evidence_ref: str


@dataclass(frozen=True)
class FinanceIssue:
    issue_id: str
    topic: str
    status: FinanceStatus
    question: str
    contract_evidence: str
    finance_owner: str
    legal_action: str
    framework: str


@dataclass(frozen=True)
class RegulatoryItem:
    control_id: str
    regime: str
    actor: str
    obligation_or_question: str
    deal_relevance: str
    status: RegulatoryStatus
    gate_effect: GateEffect
    owner: str
    target_date: str
    evidence_required: tuple[str, ...]
    source_id: str
    source_url: str


@dataclass(frozen=True)
class CounselBrief:
    brief_id: str
    workstream: str
    jurisdiction: str
    question: str
    facts: tuple[str, ...]
    assumptions: tuple[str, ...]
    deliverable: str
    deadline: str
    budget_ceiling: str
    internal_owner: str
    approval_required: str
    external_action_allowed: bool = False


@dataclass(frozen=True)
class HundredDayPhase:
    phase: str
    objective: str
    deliverables: tuple[str, ...]
    proof_metric: str


@dataclass(frozen=True)
class RaaSDealPack:
    schema: str
    input_schema: str
    generated_from: str
    verified_on: str
    title: str
    deal_id: str
    deal_facts: dict[str, Any]
    signing_gate: dict[str, Any]
    clause_reviews: tuple[ClauseReview, ...]
    finance_handoff: tuple[FinanceIssue, ...]
    regulatory_readiness: tuple[RegulatoryItem, ...]
    external_counsel_briefs: tuple[CounselBrief, ...]
    hundred_day_plan: tuple[HundredDayPhase, ...]
    source_manifest: tuple[dict[str, str], ...]
    source_digest: str
    disclaimer: str
    external_action_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "input_schema": self.input_schema,
            "generated_from": self.generated_from,
            "verified_on": self.verified_on,
            "title": self.title,
            "deal_id": self.deal_id,
            "deal_facts": self.deal_facts,
            "signing_gate": self.signing_gate,
            "clause_reviews": [asdict(item) for item in self.clause_reviews],
            "finance_handoff": [asdict(item) for item in self.finance_handoff],
            "regulatory_readiness": [
                asdict(item) for item in self.regulatory_readiness
            ],
            "external_counsel_briefs": [
                asdict(item) for item in self.external_counsel_briefs
            ],
            "hundred_day_plan": [asdict(item) for item in self.hundred_day_plan],
            "source_manifest": list(self.source_manifest),
            "source_digest": self.source_digest,
            "disclaimer": self.disclaimer,
            "external_action_allowed": self.external_action_allowed,
        }


def validate_raas_deal(deal: dict[str, Any]) -> dict[str, Any]:
    """Validate the public v1 input contract with field-specific errors."""
    if not isinstance(deal, dict):
        raise ValueError("RaaS deal input must be one JSON object")

    schema = deal.get("schema")
    if schema != RAAS_INPUT_SCHEMA:
        raise ValueError(
            f"schema must equal '{RAAS_INPUT_SCHEMA}', received {schema!r}"
        )

    required = {
        "schema",
        "deal_id",
        "title",
        "provider",
        "customer",
        "sites",
        "commercial_model",
        "product",
        "requested_terms",
        "finance",
    }
    missing = sorted(required - set(deal))
    if missing:
        raise ValueError(f"RaaS deal is missing required fields: {missing}")

    for field in ("deal_id", "title", "provider", "customer"):
        _require_string(deal, field)
    for field in (
        "provider_affiliate",
        "customer_affiliate",
        "stage",
        "business_owner",
    ):
        _optional_string(deal, field)
    _optional_date(deal, "requested_signing_date")
    _require_string_list(deal, "sites")

    commercial = _require_object(deal, "commercial_model")
    for field in ("model", "currency"):
        _require_string(commercial, field, prefix="commercial_model.")
    _require_positive_integer(commercial, "term_months", prefix="commercial_model.")
    _require_non_negative_number(
        commercial, "annual_contract_value", prefix="commercial_model."
    )
    _require_string_list(commercial, "components", prefix="commercial_model.")

    product = _require_object(deal, "product")
    _require_string(product, "robot_type", prefix="product.")
    for field in (
        "connected_product",
        "remote_access",
        "ai_vision",
        "ai_path_planning",
        "ai_safety_component_classification_open",
        "provider_retains_hardware_title",
    ):
        _require_boolean(product, field, prefix="product.")

    terms = _require_object(deal, "requested_terms")
    string_terms = (
        "governing_law",
        "liability_cap",
        "acceptance",
        "ip_ownership",
        "telemetry_and_model_training",
        "site_safety_responsibilities",
        "service_credits",
        "exclusivity",
        "hardware_title",
        "risk_of_loss",
        "removal_cost_owner",
    )
    for field in string_terms:
        _require_string(terms, field, prefix="requested_terms.")
    for field in (
        "termination_for_convenience",
        "personal_data",
        "non_eea_transfer",
    ):
        _require_boolean(terms, field, prefix="requested_terms.")
    _require_non_negative_number(
        terms, "uptime_commitment_percent", prefix="requested_terms."
    )
    _require_non_negative_integer(
        terms, "termination_charge_months", prefix="requested_terms."
    )
    _require_positive_integer(
        terms, "security_incident_notice_hours", prefix="requested_terms."
    )

    finance = _require_object(deal, "finance")
    _require_boolean(finance, "non_binding_loi", prefix="finance.")
    _require_string(finance, "expansion_option", prefix="finance.")
    _require_string_list(finance, "contracting_entities", prefix="finance.")
    return deal


def _require_object(
    value: dict[str, Any], field: str, *, prefix: str = ""
) -> dict[str, Any]:
    item = value.get(field)
    if not isinstance(item, dict):
        raise ValueError(f"{prefix}{field} must be an object")
    return item


def _require_string(
    value: dict[str, Any], field: str, *, prefix: str = ""
) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{prefix}{field} must be a non-empty string")
    return item


def _optional_string(value: dict[str, Any], field: str) -> None:
    if field in value and value[field] is not None:
        _require_string(value, field)


def _optional_date(value: dict[str, Any], field: str) -> None:
    if field not in value or value[field] is None:
        return
    raw = _require_string(value, field)
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format") from exc


def _require_boolean(
    value: dict[str, Any], field: str, *, prefix: str = ""
) -> bool:
    item = value.get(field)
    if not isinstance(item, bool):
        raise ValueError(f"{prefix}{field} must be a boolean")
    return item


def _require_positive_integer(
    value: dict[str, Any], field: str, *, prefix: str = ""
) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
        raise ValueError(f"{prefix}{field} must be a positive integer")
    return item


def _require_non_negative_integer(
    value: dict[str, Any], field: str, *, prefix: str = ""
) -> int:
    item = value.get(field)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise ValueError(f"{prefix}{field} must be a non-negative integer")
    return item


def _require_non_negative_number(
    value: dict[str, Any], field: str, *, prefix: str = ""
) -> int | float:
    item = value.get(field)
    if (
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or item < 0
    ):
        raise ValueError(f"{prefix}{field} must be a non-negative number")
    return item


def _require_string_list(
    value: dict[str, Any], field: str, *, prefix: str = ""
) -> list[str]:
    item = value.get(field)
    if (
        not isinstance(item, list)
        or not item
        or not all(isinstance(entry, str) and entry.strip() for entry in item)
    ):
        raise ValueError(f"{prefix}{field} must be a non-empty list of strings")
    return item
