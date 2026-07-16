"""Deterministic legal and operating rules for the synthetic RaaS deal."""

from __future__ import annotations

from typing import Any

from legal_function_os.raas_models import (
    ClauseSeverity,
    ClauseReview,
    CounselBrief,
    FinanceIssue,
    HundredDayPhase,
    RAAS_INPUT_SCHEMA,
    RaaSDealPack,
    RegulatoryItem,
    validate_raas_deal,
)
from legal_function_os.raas_sources import (
    DISCLAIMER,
    SOURCE_MANIFEST,
    VERIFIED_ON,
    source_digest,
    source_url,
)


def build_raas_deal_pack(deal: dict[str, Any]) -> RaaSDealPack:
    deal = validate_raas_deal(deal)
    clause_reviews = tuple(_build_clause_reviews(deal))
    finance_handoff = tuple(_build_finance_handoff(deal))
    regulatory_readiness = tuple(_build_regulatory_readiness(deal))
    counsel_briefs = tuple(_build_external_counsel_briefs(deal))
    hundred_day_plan = tuple(_build_hundred_day_plan())
    signing_gate = _build_signing_gate(
        clause_reviews,
        finance_handoff,
        regulatory_readiness,
    )
    commercial = deal["commercial_model"]
    facts = {
        "provider": deal["provider"],
        "provider_affiliate": deal.get("provider_affiliate"),
        "customer": deal["customer"],
        "customer_affiliate": deal.get("customer_affiliate"),
        "sites": deal["sites"],
        "stage": deal.get("stage", "contract review"),
        "requested_signing_date": deal.get("requested_signing_date"),
        "term_months": commercial["term_months"],
        "annual_contract_value": commercial["annual_contract_value"],
        "currency": commercial["currency"],
        "commercial_model": commercial["model"],
        "governing_law_request": deal["requested_terms"]["governing_law"],
        "business_owner": deal.get("business_owner", "Commercial"),
    }
    return RaaSDealPack(
        schema="legal-function-os.raas-deal-pack.v1",
        input_schema=RAAS_INPUT_SCHEMA,
        generated_from=f"synthetic-deal:{deal['deal_id']}",
        verified_on=VERIFIED_ON,
        title="Industrial Robotics RaaS Deal Decision Pack",
        deal_id=str(deal["deal_id"]),
        deal_facts=facts,
        signing_gate=signing_gate,
        clause_reviews=clause_reviews,
        finance_handoff=finance_handoff,
        regulatory_readiness=regulatory_readiness,
        external_counsel_briefs=counsel_briefs,
        hundred_day_plan=hundred_day_plan,
        source_manifest=SOURCE_MANIFEST,
        source_digest=source_digest(),
        disclaimer=DISCLAIMER,
    )


def _build_clause_reviews(deal: dict[str, Any]) -> list[ClauseReview]:
    terms = deal["requested_terms"]
    product = deal["product"]
    reviews: list[ClauseReview] = []

    def add(
        rule_id: str,
        category: str,
        severity: ClauseSeverity,
        issue: str,
        field: str,
        standard: str,
        fallback: str,
        escalation: str,
        approvals: tuple[str, ...],
        rationale: str,
    ) -> None:
        reviews.append(
            ClauseReview(
                rule_id=rule_id,
                category=category,
                severity=severity,
                issue=issue,
                requested_position=str(terms[field]),
                standard_position=standard,
                fallback_position=fallback,
                escalation_trigger=escalation,
                required_approvals=approvals,
                rationale=rationale,
                evidence_ref=(
                    f"synthetic-deal:{deal['deal_id']}:requested_terms.{field}"
                ),
            )
        )

    if _contains(terms["liability_cap"], "uncapped", "unlimited"):
        add(
            "RAAS-LIABILITY-001",
            "liability",
            "nonstarter",
            "The customer requests uncapped liability across broad claim categories.",
            "liability_cap",
            "Use an aggregate cap linked to fees under the affected order form, with narrow exclusions supported by insurance and applicable law.",
            "Offer a separately capped super-cap for defined privacy, security, confidentiality, or IP claims after Finance, Insurance, and General Counsel review.",
            "Any uncapped exposure or cap above the approved authority matrix.",
            ("General Counsel", "CFO", "Insurance owner"),
            "Hardware, software, remote services, and physical operations can create exposure disproportionate to recurring fees.",
        )
    if _contains(terms["acceptance"], "subjective", "customer discretion"):
        add(
            "RAAS-ACCEPTANCE-001",
            "acceptance",
            "nonstarter",
            "Acceptance depends on the customer's subjective satisfaction.",
            "acceptance",
            "Use objective site acceptance tests, measurable criteria, a fixed test window, a cure process, and deemed acceptance for operational use.",
            "Permit one documented retest cycle against agreed criteria before deemed acceptance.",
            "Acceptance can be delayed without objective failure criteria.",
            ("General Counsel", "CFO", "VP Operations"),
            "Subjective acceptance can delay deployment, billing, and Finance's assessment of transfer of control.",
        )
    if _contains(terms["ip_ownership"], "customer owns all", "all improvements"):
        add(
            "RAAS-IP-001",
            "IP ownership",
            "nonstarter",
            "The customer claims ownership of site-specific and platform improvements.",
            "ip_ownership",
            "The provider retains platform, robot, software, model, workflow, and generalised improvement IP. The customer retains its pre-existing IP and receives agreed use rights.",
            "Grant a site-use licence for customer-funded deliverables while preserving provider ownership of reusable technology and de-identified know-how.",
            "Any assignment of core technology, model behaviour, or reusable improvements.",
            ("General Counsel", "CTO", "Product owner"),
            "Overbroad ownership language can impair the product roadmap and create conflicting rights across deployments.",
        )
    if _contains(
        terms["telemetry_and_model_training"], "unrestricted", "all data"
    ):
        add(
            "RAAS-DATA-001",
            "data and model improvement",
            "nonstarter",
            "The proposed data clause permits unrestricted telemetry and model-training use.",
            "telemetry_and_model_training",
            "Define product-data categories, user access, permitted service purposes, retention, security, trade-secret controls, and separate rules for model improvement.",
            "Use aggregated or de-identified operational data for reliability improvement, subject to documented exclusions and customer access rights.",
            "Training use involving personal data, confidential production data, or undefined purposes.",
            (
                "General Counsel",
                "DPO or privacy owner",
                "CTO",
                "Customer data owner",
            ),
            "Connected-product data, confidential manufacturing information, privacy, and model improvement require distinct legal and technical treatment.",
        )
    if _contains(
        terms["site_safety_responsibilities"], "undocumented", "to be agreed"
    ):
        add(
            "RAAS-SAFETY-001",
            "product and site safety",
            "nonstarter",
            "Robot, integration, and customer site-safety responsibilities remain undocumented.",
            "site_safety_responsibilities",
            "Allocate machinery conformity, integration, guarding, site preparation, risk assessment, operating instructions, training, change control, and incident duties.",
            "Use a signed responsibility matrix and site acceptance protocol before commissioning.",
            "Deployment or production use before the signed safety responsibility matrix.",
            ("Product safety lead", "VP Operations", "General Counsel"),
            "A modular robot deployment crosses product design, system integration, customer-site controls, and operational change management.",
        )
    if _contains(terms["service_credits"], "uncapped"):
        add(
            "RAAS-SLA-001",
            "service levels",
            "requires_approval",
            "Service credits are uncapped and can accumulate outside the liability structure.",
            "service_credits",
            "Use tiered service credits with a monthly cap, defined exclusions, measurement rules, and an agreed relationship to other remedies.",
            "Increase the monthly credit cap for repeated failures while preserving an aggregate contractual ceiling.",
            "Credits exceed the approved percentage of monthly RaaS fees.",
            ("General Counsel", "CFO", "Service operations owner"),
            "Uptime remedies affect variable consideration, margin, operational capacity, and wider liability exposure.",
        )
    if (
        terms["termination_for_convenience"]
        and terms["termination_charge_months"] == 0
    ):
        add(
            "RAAS-TERM-001",
            "term and termination",
            "requires_approval",
            "The customer can terminate for convenience without recovery of deployment costs.",
            "termination_charge_months",
            "Protect committed hardware, integration, installation, removal, and minimum-term costs.",
            "Use a declining early-termination schedule tied to unrecovered deployment costs.",
            "Termination rights undermine the approved deal margin or contract term.",
            ("CFO", "General Counsel", "Commercial owner"),
            "RaaS economics depend on recovering hardware and deployment investment over time.",
        )
    if terms["security_incident_notice_hours"] > 48:
        add(
            "RAAS-SECURITY-001",
            "cybersecurity and remote access",
            "requires_approval",
            "The proposed incident-notification period may not support contractual or regulatory escalation.",
            "security_incident_notice_hours",
            "Require prompt internal escalation and a contract notice window aligned with incident severity, legal duties, and verified information.",
            "Use an initial material-incident notice followed by staged factual updates.",
            "Remote access or product incident without an approved response and notification workflow.",
            ("Security owner", "DPO or privacy owner", "General Counsel"),
            "Remote maintenance and products with digital elements require coordinated security, privacy, product, and customer communications.",
        )
    if _contains(terms["exclusivity"], "global", "industry-wide"):
        add(
            "RAAS-EXCLUSIVITY-001",
            "commercial scope",
            "nonstarter",
            "The customer requests broad global industry exclusivity.",
            "exclusivity",
            "No customer exclusivity over the provider's modular robotics platform or roadmap.",
            "Consider a narrow, paid, time-limited site or use-case restriction with named competitors and minimum commercial commitments.",
            "Any restriction affecting sales outside the named deployment and use case.",
            ("CEO", "CRO", "General Counsel"),
            "Broad exclusivity can constrain a platform business beyond the value of one deal.",
        )
    if (
        _contains(terms["risk_of_loss"], "customer after delivery")
        and terms["hardware_title"].lower() == "provider"
    ):
        add(
            "RAAS-HARDWARE-001",
            "hardware ownership and risk",
            "negotiable",
            "The provider retains title while risk of loss shifts to the customer after delivery.",
            "risk_of_loss",
            "Align title, custody, insurance, maintenance access, damage responsibility, and removal rights across the RaaS term.",
            "Customer bears site-custody risk after installation, subject to provider maintenance obligations and agreed insurance evidence.",
            "The insurance position does not match the title and custody allocation.",
            ("Finance owner", "Insurance owner", "General Counsel"),
            "Retained-title equipment requires a coherent allocation of custody, insurance, damage, access, and end-of-term recovery.",
        )
    if product["ai_safety_component_classification_open"]:
        reviews.append(
            ClauseReview(
                rule_id="RAAS-AI-SAFETY-001",
                category="AI and safety classification",
                severity="requires_approval",
                issue="The role of AI vision and path planning in safety functions remains open.",
                requested_position="Product classification has not been finalised.",
                standard_position="Document intended purpose, safety functions, failure effects, conformity path, human oversight, validation, change control, and technical-file ownership.",
                fallback_position="Block safety-relevant autonomous behaviour until accountable technical owners approve the classification and evidence set.",
                escalation_trigger="Any safety-relevant AI function is deployed without a recorded classification decision.",
                required_approvals=(
                    "Product safety lead",
                    "AI governance owner",
                    "General Counsel",
                ),
                rationale="The regulatory path depends on intended use, safety-component status, and the applicable conformity-assessment route.",
                evidence_ref=f"synthetic-deal:{deal['deal_id']}:product.ai_safety_component_classification_open",
            )
        )

    order = {"nonstarter": 0, "requires_approval": 1, "negotiable": 2}
    return sorted(reviews, key=lambda item: (order[item.severity], item.rule_id))


def _build_finance_handoff(deal: dict[str, Any]) -> list[FinanceIssue]:
    terms = deal["requested_terms"]
    ref = f"synthetic-deal:{deal['deal_id']}"
    revenue_framework = (
        "IFRS 15 / ASC 606; Finance must determine the accounting treatment"
    )
    return [
        FinanceIssue(
            "FIN-001",
            "Performance obligations",
            "review_required",
            "Are robot access, installation, integration, software, support, updates, and optimisation distinct promises or one combined performance obligation?",
            f"{ref}:commercial_model.components",
            "Revenue Accounting",
            "Keep the statement of work, order form, and service description factually aligned.",
            revenue_framework,
        ),
        FinanceIssue(
            "FIN-002",
            "Acceptance and transfer of control",
            (
                "blocked"
                if _contains(terms["acceptance"], "subjective")
                else "review_required"
            ),
            "Do objective acceptance criteria, operational use, deemed acceptance, and cure rights support the intended revenue-recognition point?",
            f"{ref}:requested_terms.acceptance",
            "Revenue Accounting",
            "Replace subjective acceptance with measurable site acceptance tests.",
            revenue_framework,
        ),
        FinanceIssue(
            "FIN-003",
            "Variable consideration",
            "review_required",
            "How should uptime credits, implementation remedies, bonuses, and penalties be reflected in transaction price and constraint analysis?",
            f"{ref}:requested_terms.service_credits",
            "Revenue Accounting",
            "Cap and define credits, measurement periods, exclusions, and remedy interaction.",
            revenue_framework,
        ),
        FinanceIssue(
            "FIN-004",
            "Contract term and termination",
            "review_required",
            "What enforceable term remains after termination-for-convenience rights, renewal options, and early-termination payments?",
            f"{ref}:requested_terms.termination_for_convenience",
            "Controllership",
            "Document enforceable minimum commitments and recovery of deployment costs.",
            revenue_framework,
        ),
        FinanceIssue(
            "FIN-005",
            "Lease assessment",
            "review_required",
            "Does the arrangement contain a lease because the customer controls the use of an identified robot during the contract term?",
            f"{ref}:requested_terms.hardware_title",
            "Technical Accounting",
            "Clarify substitution rights, operating control, identified assets, site access, and deployment flexibility.",
            "IFRS 16 / ASC 842 assessment before IFRS 15 / ASC 606 allocation",
        ),
        FinanceIssue(
            "FIN-006",
            "Options, expansions, and modifications",
            "review_required",
            "Do the US rollout option, additional robot orders, price protection, and change orders create material rights or contract modifications?",
            f"{ref}:finance.expansion_option",
            "Revenue Accounting",
            "Use an explicit change-control and pricing mechanism for future sites and modules.",
            revenue_framework,
        ),
        FinanceIssue(
            "FIN-007",
            "Letter of intent and side commitments",
            "review_required",
            "Are commercial promises outside the signed agreement enforceable or relevant to the accounting contract and transaction price?",
            f"{ref}:finance.non_binding_loi",
            "CFO and Revenue Accounting",
            "Inventory side letters, emails, pilots, rebates, and oral commitments before close.",
            revenue_framework,
        ),
        FinanceIssue(
            "FIN-008",
            "Contracting entity and intercompany support",
            "review_required",
            "Which entity contracts, invoices, holds inventory, provides support, owns IP, and bears warranty or product-liability exposure for each site?",
            f"{ref}:finance.contracting_entities",
            "CFO, Tax, and Controllership",
            "Align customer contracts with the approved Germany-US intercompany model.",
            "Entity, tax, transfer-pricing, and accounting review required",
        ),
    ]


def _build_regulatory_readiness(deal: dict[str, Any]) -> list[RegulatoryItem]:
    signing_date = str(deal.get("requested_signing_date") or "before signing")
    product = deal["product"]
    return [
        RegulatoryItem(
            "REG-001",
            "EU machinery framework",
            "Manufacturer, authorised representative, importer, or system integrator as applicable",
            "Confirm the current conformity path, technical file, instructions, declaration, risk assessment, substantial-modification controls, and site integration allocation.",
            "The agreement covers a modular industrial robot cell and site commissioning.",
            "evidence_required",
            "deployment_blocker",
            "Product safety lead and Legal",
            signing_date,
            (
                "Conformity responsibility matrix",
                "Technical-file index",
                "Site risk assessment",
                "Commissioning and change-control protocol",
            ),
            "EU-MACHINERY-DIRECTIVE",
            source_url("EU-MACHINERY-DIRECTIVE"),
        ),
        RegulatoryItem(
            "REG-002",
            "Machinery Regulation transition",
            "Manufacturer and other relevant economic operators",
            "Map the 2027 transition for products, software changes, instructions, technical documentation, and AI-enabled safety components.",
            "The 36-month framework extends into the Machinery Regulation application period.",
            "transition_plan_required",
            "transition_follow_up",
            "Product safety lead, Engineering, and Legal",
            "2026-10-31",
            (
                "Product transition inventory",
                "Technical-documentation gap assessment",
                "Change-control impact analysis",
            ),
            "EU-MACHINERY-REGULATION",
            source_url("EU-MACHINERY-REGULATION"),
        ),
        RegulatoryItem(
            "REG-003",
            "EU Artificial Intelligence Act",
            "Provider, product manufacturer, deployer, importer, or distributor as applicable",
            "Record intended purpose and determine whether vision or path-planning AI is a safety component or otherwise falls within a regulated high-risk use case.",
            (
                "The product description leaves safety-component classification open."
                if product["ai_safety_component_classification_open"]
                else "The product includes AI-enabled vision and path planning."
            ),
            "classification_open",
            "deployment_blocker",
            "AI governance owner, Product safety lead, and Legal",
            signing_date,
            (
                "Intended-purpose statement",
                "Safety-function map",
                "Classification decision",
                "Validation and human-oversight evidence",
            ),
            "EU-AI-ACT",
            source_url("EU-AI-ACT"),
        ),
        RegulatoryItem(
            "REG-004",
            "EU Data Act",
            "Manufacturer, related-service provider, data holder, and user as applicable",
            "Define product data, user access, permitted use, third-party sharing, trade-secret safeguards, and contract terms for connected-product data.",
            "The framework covers connected robots, telemetry, remote services, and deployments after 12 September 2026.",
            "contract_update_required",
            "signing_blocker",
            "Product counsel, Data owner, and Product",
            signing_date,
            (
                "Product-data inventory",
                "User-access mechanism",
                "Data-use schedule",
                "Trade-secret safeguards",
            ),
            "EU-DATA-ACT",
            source_url("EU-DATA-ACT"),
        ),
        RegulatoryItem(
            "REG-005",
            "Cyber Resilience Act",
            "Manufacturer and other relevant economic operators",
            "Confirm product-with-digital-elements scope, vulnerability handling, support period, security updates, reporting workflow, and contractual evidence.",
            "Remote access, fleet software, AI components, and field updates create a product cybersecurity lifecycle.",
            "transition_plan_required",
            "transition_follow_up",
            "CISO, Product Security, and Legal",
            "2026-08-31",
            (
                "Product security plan",
                "Vulnerability disclosure process",
                "Support-period decision",
                "Incident reporting runbook",
            ),
            "EU-CRA",
            source_url("EU-CRA"),
        ),
        RegulatoryItem(
            "REG-006",
            "Product Liability Directive transition",
            "Manufacturer, component manufacturer, importer, authorised representative, or fulfilment provider",
            "Map national implementation and responsibility for hardware, software, AI, updates, remote services, components, technical evidence, and post-market control.",
            "Later framework deployments may be placed on the market or put into service after 9 December 2026.",
            "transition_plan_required",
            "transition_follow_up",
            "Product counsel, Product Safety, Insurance, and Engineering",
            "2026-10-31",
            (
                "National implementation check",
                "Product and component responsibility map",
                "Update-control record",
                "Insurance and evidence-retention review",
            ),
            "EU-PRODUCT-LIABILITY",
            source_url("EU-PRODUCT-LIABILITY"),
        ),
        RegulatoryItem(
            "REG-007",
            "GDPR and international transfers",
            "Controller, joint controller, or processor as established by facts",
            "Identify personal data in video, access logs, support records, and telemetry, then document roles, purposes, security, retention, transparency, and transfers.",
            "EU and US sites use remote support and cross-border operational access.",
            "evidence_required",
            "signing_blocker",
            "DPO or privacy owner, Security, and Legal",
            signing_date,
            (
                "Data-flow map",
                "Role assessment",
                "DPA and transfer mechanism",
                "DPIA screening",
            ),
            "EU-GDPR",
            source_url("EU-GDPR"),
        ),
    ]


def _build_external_counsel_briefs(deal: dict[str, Any]) -> list[CounselBrief]:
    signing_date = str(deal.get("requested_signing_date") or "before signing")
    return [
        CounselBrief(
            "EXT-001",
            "EU product safety and AI classification",
            "Germany and European Union",
            "Confirm the conformity and classification path for the modular robot, AI vision, path planning, system integration, and planned 2027 deployments.",
            (
                "Synthetic framework covers a German site and a later US site.",
                "AI vision and path planning are included.",
                "Safety-component classification remains open.",
                "Customer and provider site responsibilities are undocumented.",
            ),
            (
                "No bespoke hazardous-environment use is currently planned.",
                "The technical file and risk assessment can be made available under NDA.",
            ),
            "Five-page decision memo, responsibility-matrix comments, and an evidence list required before commissioning.",
            signing_date,
            "EUR 12,000, approval required for any expansion",
            "General Counsel and Product Safety Lead",
            "General Counsel",
        ),
        CounselBrief(
            "EXT-002",
            "US RaaS commercial and product exposure",
            "United States, with Texas deployment focus",
            "Review the US order-form structure, governing law, hardware custody, UCC or lease issues, warranties, indemnities, limitation of liability, service credits, product exposure, and removal rights.",
            (
                "The provider retains robot title.",
                "The customer requests Texas law and uncapped liability.",
                "The later deployment is planned for Austin.",
                "Remote support may be provided from the EU.",
            ),
            (
                "No consumer deployment is contemplated.",
                "The US sales affiliate will participate in contracting or support.",
            ),
            "Annotated issues list and approved US fallback positions for the order form.",
            signing_date,
            "USD 15,000, fixed-fee proposal requested",
            "General Counsel and CFO",
            "General Counsel",
        ),
        CounselBrief(
            "EXT-003",
            "Germany-US entity, tax, and intercompany model",
            "Germany and United States",
            "Confirm the contracting, invoicing, inventory, IP licence, warranty, support, and risk allocation between the German parent and US affiliate.",
            (
                "The product IP is held by the German provider in the synthetic scenario.",
                "The framework contemplates German and US deployments.",
                "Customer-facing support may be delivered by both entities.",
            ),
            (
                "Existing intercompany agreements can be reviewed.",
                "Finance will provide the intended transfer-pricing policy and revenue flows.",
            ),
            "Entity-responsibility chart, required intercompany documents, and a list of customer-contract clauses that must match the approved model.",
            "2026-09-15",
            "EUR 18,000 combined legal and tax scope",
            "CFO and General Counsel",
            "CFO",
        ),
        CounselBrief(
            "EXT-004",
            "IP and trade-secret protection",
            "Germany, European Union, and United States",
            "Protect reusable robotics, software, model, workflow, and improvement IP while defining customer rights in site-specific deliverables and production data.",
            (
                "The customer requests ownership of all site-specific improvements.",
                "The product uses telemetry and AI-enabled optimisation.",
                "The deployment exposes personnel to customer manufacturing information.",
            ),
            (
                "Patent, trademark, and invention-assignment records are available.",
                "Commercial teams can identify customer-funded development.",
            ),
            "IP clause mark-up, invention and trade-secret control checklist, and filing recommendations.",
            signing_date,
            "EUR 10,000 for contract and portfolio review",
            "General Counsel and CTO",
            "General Counsel",
        ),
    ]


def _build_hundred_day_plan() -> list[HundredDayPhase]:
    return [
        HundredDayPhase(
            "Days 1 to 30: establish control",
            "Create a verified legal baseline and decision authority for the first legal function.",
            (
                "Legal request intake, risk tiers, SLAs, and escalation matrix",
                "Contract, entity, signatory authority, litigation, employment, privacy, and IP inventories",
                "Top 20 customer and supplier contract review",
                "External-counsel panel with scopes, rates, conflicts, and instruction template",
                "Immediate product safety, AI, cybersecurity, and data-law issue register",
            ),
            "All material matters have an owner, deadline, evidence reference, and approval tier.",
        ),
        HundredDayPhase(
            "Days 31 to 60: build the operating model",
            "Turn repeat legal work into controlled deal and governance workflows.",
            (
                "RaaS MSA, pilot, order form, DPA, NDA, supplier, and employment template set",
                "Negotiation playbook with fallback positions and authority limits",
                "Deal-desk cadence with Sales, Finance, Security, Product, and Operations",
                "IFRS 15 and ASC 606 contract-structuring checklist with Finance",
                "Board legal-risk pack and corporate-housekeeping calendar",
            ),
            "Standard deals follow the playbook, and deviations reach the correct approver.",
        ),
        HundredDayPhase(
            "Days 61 to 100: scale and evidence",
            "Prepare the legal function for cross-border growth and repeatable diligence.",
            (
                "Germany-US entity and intercompany responsibility model",
                "Regulatory readiness programme for machinery, AI, data, cybersecurity, and product liability",
                "Product and data responsibility matrices embedded in deployment workflows",
                "IP lifecycle covering inventions, open source, trade secrets, trademarks, and patents",
                "Legal metrics for cycle time, deviation rate, outside-counsel spend, disputes, and open controls",
            ),
            "Management can see signing blockers, deployment risks, spend, and readiness from one evidence-backed pack.",
        ),
    ]


def _build_signing_gate(
    clause_reviews: tuple[ClauseReview, ...],
    finance_handoff: tuple[FinanceIssue, ...],
    regulatory_readiness: tuple[RegulatoryItem, ...],
) -> dict[str, Any]:
    contract_blockers = [
        {
            "rule_id": item.rule_id,
            "category": item.category,
            "issue": item.issue,
        }
        for item in clause_reviews
        if item.severity == "nonstarter"
    ]
    finance_blockers = [
        {"issue_id": item.issue_id, "topic": item.topic, "question": item.question}
        for item in finance_handoff
        if item.status == "blocked"
    ]
    signing_regulatory = [
        _regulatory_gate_item(item)
        for item in regulatory_readiness
        if item.gate_effect == "signing_blocker"
    ]
    deployment_blockers = [
        _regulatory_gate_item(item)
        for item in regulatory_readiness
        if item.gate_effect == "deployment_blocker"
    ]
    transition_follow_up = [
        _regulatory_gate_item(item)
        for item in regulatory_readiness
        if item.gate_effect == "transition_follow_up"
    ]
    core_blockers = [*contract_blockers, *finance_blockers]
    blocked = bool(core_blockers or signing_regulatory)
    approvals = sorted(
        {
            approval
            for item in clause_reviews
            for approval in item.required_approvals
        }
    )
    return {
        "status": "blocked" if blocked else "human_approval_required",
        "ready_for_human_approval": not blocked,
        "signature_action_allowed": False,
        "answer": (
            "Do not sign the current draft."
            if blocked
            else "The deterministic checks are clear. Named human approvals remain required."
        ),
        "blocking_items": core_blockers,
        "blocking_contract_items": contract_blockers,
        "blocking_finance_items": finance_blockers,
        "blocking_regulatory_items": signing_regulatory,
        "blocking_deployment_items": deployment_blockers,
        "transition_follow_up_items": transition_follow_up,
        "required_approvals": approvals,
        "open_regulatory_controls": len(regulatory_readiness),
        "deployment_delay_drivers": [
            "Objective acceptance and commissioning criteria remain open.",
            "The site-safety responsibility matrix is unsigned.",
            "AI safety-component classification is unresolved.",
            "Connected-product data and remote-access controls require evidence.",
        ],
        "revenue_delay_drivers": [
            "Subjective acceptance may delay the transfer-of-control assessment.",
            "Uncapped service credits create variable-consideration uncertainty.",
            "Termination rights may reduce the enforceable contract term.",
            "The lease assessment and contracting-entity model remain open.",
        ],
        "review_gate": (
            "A named General Counsel and accountable Finance, Product, Safety, "
            "Security, and Commercial owners must approve consequential positions."
        ),
        "external_action_allowed": False,
    }


def _regulatory_gate_item(item: RegulatoryItem) -> dict[str, str]:
    return {
        "control_id": item.control_id,
        "regime": item.regime,
        "question": item.obligation_or_question,
        "owner": item.owner,
        "gate_effect": item.gate_effect,
    }


def _contains(value: Any, *needles: str) -> bool:
    text = str(value).lower()
    return any(needle.lower() in text for needle in needles)
