# Industrial Robotics RaaS Deal Decision Pack

**Deal:** RAAS-2026-001
**Input contract:** `legal-function-os.raas-deal-input.v1`
**Verified legal-source snapshot:** 2026-07-16
**Signing decision:** Do not sign the current draft.

## Executive signing gate

- Status: **BLOCKED**
- Core blocking items: **7**
- Signing-blocker regulatory controls: **2**
- Deployment-blocker regulatory controls: **2**
- Required approvers: **16**
- Ready for human approval: **false**
- Signature action allowed: **false**

### Core blocking items

- **RAAS-ACCEPTANCE-001:** Acceptance depends on the customer's subjective satisfaction.
- **RAAS-DATA-001:** The proposed data clause permits unrestricted telemetry and model-training use.
- **RAAS-EXCLUSIVITY-001:** The customer requests broad global industry exclusivity.
- **RAAS-IP-001:** The customer claims ownership of site-specific and platform improvements.
- **RAAS-LIABILITY-001:** The customer requests uncapped liability across broad claim categories.
- **RAAS-SAFETY-001:** Robot, integration, and customer site-safety responsibilities remain undocumented.
- **FIN-002:** Do objective acceptance criteria, operational use, deemed acceptance, and cure rights support the intended revenue-recognition point?

### Regulatory signing blockers

- **REG-004:** EU Data Act. Owner: Product counsel, Data owner, and Product. Define product data, user access, permitted use, third-party sharing, trade-secret safeguards, and contract terms for connected-product data.
- **REG-007:** GDPR and international transfers. Owner: DPO or privacy owner, Security, and Legal. Identify personal data in video, access logs, support records, and telemetry, then document roles, purposes, security, retention, transparency, and transfers.

### Deployment blockers

- **REG-001:** EU machinery framework. Owner: Product safety lead and Legal. Confirm the current conformity path, technical file, instructions, declaration, risk assessment, substantial-modification controls, and site integration allocation.
- **REG-003:** EU Artificial Intelligence Act. Owner: AI governance owner, Product safety lead, and Legal. Record intended purpose and determine whether vision or path-planning AI is a safety component or otherwise falls within a regulated high-risk use case.

### Transition follow-up

- **REG-002:** Machinery Regulation transition. Owner: Product safety lead, Engineering, and Legal. Map the 2027 transition for products, software changes, instructions, technical documentation, and AI-enabled safety components.
- **REG-005:** Cyber Resilience Act. Owner: CISO, Product Security, and Legal. Confirm product-with-digital-elements scope, vulnerability handling, support period, security updates, reporting workflow, and contractual evidence.
- **REG-006:** Product Liability Directive transition. Owner: Product counsel, Product Safety, Insurance, and Engineering. Map national implementation and responsibility for hardware, software, AI, updates, remote services, components, technical evidence, and post-market control.

### Required approvals

- AI governance owner
- CEO
- CFO
- CRO
- CTO
- Commercial owner
- Customer data owner
- DPO or privacy owner
- Finance owner
- General Counsel
- Insurance owner
- Product owner
- Product safety lead
- Security owner
- Service operations owner
- VP Operations

### What could delay deployment

- Objective acceptance and commissioning criteria remain open.
- The site-safety responsibility matrix is unsigned.
- AI safety-component classification is unresolved.
- Connected-product data and remote-access controls require evidence.

### What could delay revenue

- Subjective acceptance may delay the transfer-of-control assessment.
- Uncapped service credits create variable-consideration uncertainty.
- Termination rights may reduce the enforceable contract term.
- The lease assessment and contracting-entity model remain open.

## Deal facts

- Provider: ModuBot Automation GmbH (synthetic)
- Provider affiliate: ModuBot Inc., Delaware (synthetic)
- Customer: Atlas Components SE (synthetic)
- Customer affiliate: Atlas Components USA, Inc. (synthetic)
- Sites: Augsburg, Germany, Austin, Texas, United States
- Commercial model: Robotics-as-a-Service
- Annual contract value: 1800000 EUR
- Term: 36 months
- Requested governing law: Texas law for the global framework
- Requested signing date: 2026-08-14

## Negotiation playbook

| Rule | Category | Severity | Issue | Standard position | Fallback | Approvals |
| --- | --- | --- | --- | --- | --- | --- |
| RAAS-ACCEPTANCE-001 | acceptance | nonstarter | Acceptance depends on the customer's subjective satisfaction. | Use objective site acceptance tests, measurable criteria, a fixed test window, a cure process, and deemed acceptance for operational use. | Permit one documented retest cycle against agreed criteria before deemed acceptance. | General Counsel, CFO, VP Operations |
| RAAS-DATA-001 | data and model improvement | nonstarter | The proposed data clause permits unrestricted telemetry and model-training use. | Define product-data categories, user access, permitted service purposes, retention, security, trade-secret controls, and separate rules for model improvement. | Use aggregated or de-identified operational data for reliability improvement, subject to documented exclusions and customer access rights. | General Counsel, DPO or privacy owner, CTO, Customer data owner |
| RAAS-EXCLUSIVITY-001 | commercial scope | nonstarter | The customer requests broad global industry exclusivity. | No customer exclusivity over the provider's modular robotics platform or roadmap. | Consider a narrow, paid, time-limited site or use-case restriction with named competitors and minimum commercial commitments. | CEO, CRO, General Counsel |
| RAAS-IP-001 | IP ownership | nonstarter | The customer claims ownership of site-specific and platform improvements. | The provider retains platform, robot, software, model, workflow, and generalised improvement IP. The customer retains its pre-existing IP and receives agreed use rights. | Grant a site-use licence for customer-funded deliverables while preserving provider ownership of reusable technology and de-identified know-how. | General Counsel, CTO, Product owner |
| RAAS-LIABILITY-001 | liability | nonstarter | The customer requests uncapped liability across broad claim categories. | Use an aggregate cap linked to fees under the affected order form, with narrow exclusions supported by insurance and applicable law. | Offer a separately capped super-cap for defined privacy, security, confidentiality, or IP claims after Finance, Insurance, and General Counsel review. | General Counsel, CFO, Insurance owner |
| RAAS-SAFETY-001 | product and site safety | nonstarter | Robot, integration, and customer site-safety responsibilities remain undocumented. | Allocate machinery conformity, integration, guarding, site preparation, risk assessment, operating instructions, training, change control, and incident duties. | Use a signed responsibility matrix and site acceptance protocol before commissioning. | Product safety lead, VP Operations, General Counsel |
| RAAS-AI-SAFETY-001 | AI and safety classification | requires_approval | The role of AI vision and path planning in safety functions remains open. | Document intended purpose, safety functions, failure effects, conformity path, human oversight, validation, change control, and technical-file ownership. | Block safety-relevant autonomous behaviour until accountable technical owners approve the classification and evidence set. | Product safety lead, AI governance owner, General Counsel |
| RAAS-SECURITY-001 | cybersecurity and remote access | requires_approval | The proposed incident-notification period may not support contractual or regulatory escalation. | Require prompt internal escalation and a contract notice window aligned with incident severity, legal duties, and verified information. | Use an initial material-incident notice followed by staged factual updates. | Security owner, DPO or privacy owner, General Counsel |
| RAAS-SLA-001 | service levels | requires_approval | Service credits are uncapped and can accumulate outside the liability structure. | Use tiered service credits with a monthly cap, defined exclusions, measurement rules, and an agreed relationship to other remedies. | Increase the monthly credit cap for repeated failures while preserving an aggregate contractual ceiling. | General Counsel, CFO, Service operations owner |
| RAAS-TERM-001 | term and termination | requires_approval | The customer can terminate for convenience without recovery of deployment costs. | Protect committed hardware, integration, installation, removal, and minimum-term costs. | Use a declining early-termination schedule tied to unrecovered deployment costs. | CFO, General Counsel, Commercial owner |
| RAAS-HARDWARE-001 | hardware ownership and risk | negotiable | The provider retains title while risk of loss shifts to the customer after delivery. | Align title, custody, insurance, maintenance access, damage responsibility, and removal rights across the RaaS term. | Customer bears site-custody risk after installation, subject to provider maintenance obligations and agreed insurance evidence. | Finance owner, Insurance owner, General Counsel |

## Finance handoff

Every item requires Finance validation. The output makes no accounting conclusion.

| ID | Topic | Status | Finance question | Legal action | Framework |
| --- | --- | --- | --- | --- | --- |
| FIN-001 | Performance obligations | review_required | Are robot access, installation, integration, software, support, updates, and optimisation distinct promises or one combined performance obligation? | Keep the statement of work, order form, and service description factually aligned. | IFRS 15 / ASC 606; Finance must determine the accounting treatment |
| FIN-002 | Acceptance and transfer of control | blocked | Do objective acceptance criteria, operational use, deemed acceptance, and cure rights support the intended revenue-recognition point? | Replace subjective acceptance with measurable site acceptance tests. | IFRS 15 / ASC 606; Finance must determine the accounting treatment |
| FIN-003 | Variable consideration | review_required | How should uptime credits, implementation remedies, bonuses, and penalties be reflected in transaction price and constraint analysis? | Cap and define credits, measurement periods, exclusions, and remedy interaction. | IFRS 15 / ASC 606; Finance must determine the accounting treatment |
| FIN-004 | Contract term and termination | review_required | What enforceable term remains after termination-for-convenience rights, renewal options, and early-termination payments? | Document enforceable minimum commitments and recovery of deployment costs. | IFRS 15 / ASC 606; Finance must determine the accounting treatment |
| FIN-005 | Lease assessment | review_required | Does the arrangement contain a lease because the customer controls the use of an identified robot during the contract term? | Clarify substitution rights, operating control, identified assets, site access, and deployment flexibility. | IFRS 16 / ASC 842 assessment before IFRS 15 / ASC 606 allocation |
| FIN-006 | Options, expansions, and modifications | review_required | Do the US rollout option, additional robot orders, price protection, and change orders create material rights or contract modifications? | Use an explicit change-control and pricing mechanism for future sites and modules. | IFRS 15 / ASC 606; Finance must determine the accounting treatment |
| FIN-007 | Letter of intent and side commitments | review_required | Are commercial promises outside the signed agreement enforceable or relevant to the accounting contract and transaction price? | Inventory side letters, emails, pilots, rebates, and oral commitments before close. | IFRS 15 / ASC 606; Finance must determine the accounting treatment |
| FIN-008 | Contracting entity and intercompany support | review_required | Which entity contracts, invoices, holds inventory, provides support, owns IP, and bears warranty or product-liability exposure for each site? | Align customer contracts with the approved Germany-US intercompany model. | Entity, tax, transfer-pricing, and accounting review required |

## Regulatory readiness matrix

| Control | Regime | Actor | Status | Gate effect | Deal question | Owner | Target | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REG-001 | EU machinery framework | Manufacturer, authorised representative, importer, or system integrator as applicable | evidence_required | deployment_blocker | Confirm the current conformity path, technical file, instructions, declaration, risk assessment, substantial-modification controls, and site integration allocation. | Product safety lead and Legal | 2026-08-14 | [EU-MACHINERY-DIRECTIVE](https://eur-lex.europa.eu/eli/dir/2006/42/oj/eng) |
| REG-002 | Machinery Regulation transition | Manufacturer and other relevant economic operators | transition_plan_required | transition_follow_up | Map the 2027 transition for products, software changes, instructions, technical documentation, and AI-enabled safety components. | Product safety lead, Engineering, and Legal | 2026-10-31 | [EU-MACHINERY-REGULATION](https://eur-lex.europa.eu/eli/reg/2023/1230/oj/eng) |
| REG-003 | EU Artificial Intelligence Act | Provider, product manufacturer, deployer, importer, or distributor as applicable | classification_open | deployment_blocker | Record intended purpose and determine whether vision or path-planning AI is a safety component or otherwise falls within a regulated high-risk use case. | AI governance owner, Product safety lead, and Legal | 2026-08-14 | [EU-AI-ACT](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng) |
| REG-004 | EU Data Act | Manufacturer, related-service provider, data holder, and user as applicable | contract_update_required | signing_blocker | Define product data, user access, permitted use, third-party sharing, trade-secret safeguards, and contract terms for connected-product data. | Product counsel, Data owner, and Product | 2026-08-14 | [EU-DATA-ACT](https://eur-lex.europa.eu/eli/reg/2023/2854/oj/eng) |
| REG-005 | Cyber Resilience Act | Manufacturer and other relevant economic operators | transition_plan_required | transition_follow_up | Confirm product-with-digital-elements scope, vulnerability handling, support period, security updates, reporting workflow, and contractual evidence. | CISO, Product Security, and Legal | 2026-08-31 | [EU-CRA](https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng) |
| REG-006 | Product Liability Directive transition | Manufacturer, component manufacturer, importer, authorised representative, or fulfilment provider | transition_plan_required | transition_follow_up | Map national implementation and responsibility for hardware, software, AI, updates, remote services, components, technical evidence, and post-market control. | Product counsel, Product Safety, Insurance, and Engineering | 2026-10-31 | [EU-PRODUCT-LIABILITY](https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng) |
| REG-007 | GDPR and international transfers | Controller, joint controller, or processor as established by facts | evidence_required | signing_blocker | Identify personal data in video, access logs, support records, and telemetry, then document roles, purposes, security, retention, transparency, and transfers. | DPO or privacy owner, Security, and Legal | 2026-08-14 | [EU-GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng) |

## External-counsel instruction packs

### EXT-001: EU product safety and AI classification

- Jurisdiction: Germany and European Union
- Question: Confirm the conformity and classification path for the modular robot, AI vision, path planning, system integration, and planned 2027 deployments.
- Deliverable: Five-page decision memo, responsibility-matrix comments, and an evidence list required before commissioning.
- Deadline: 2026-08-14
- Budget ceiling: EUR 12,000, approval required for any expansion
- Internal owner: General Counsel and Product Safety Lead
- Approval required: General Counsel
- External action allowed: false

Facts:

- Synthetic framework covers a German site and a later US site.
- AI vision and path planning are included.
- Safety-component classification remains open.
- Customer and provider site responsibilities are undocumented.

Assumptions:

- No bespoke hazardous-environment use is currently planned.
- The technical file and risk assessment can be made available under NDA.

### EXT-002: US RaaS commercial and product exposure

- Jurisdiction: United States, with Texas deployment focus
- Question: Review the US order-form structure, governing law, hardware custody, UCC or lease issues, warranties, indemnities, limitation of liability, service credits, product exposure, and removal rights.
- Deliverable: Annotated issues list and approved US fallback positions for the order form.
- Deadline: 2026-08-14
- Budget ceiling: USD 15,000, fixed-fee proposal requested
- Internal owner: General Counsel and CFO
- Approval required: General Counsel
- External action allowed: false

Facts:

- The provider retains robot title.
- The customer requests Texas law and uncapped liability.
- The later deployment is planned for Austin.
- Remote support may be provided from the EU.

Assumptions:

- No consumer deployment is contemplated.
- The US sales affiliate will participate in contracting or support.

### EXT-003: Germany-US entity, tax, and intercompany model

- Jurisdiction: Germany and United States
- Question: Confirm the contracting, invoicing, inventory, IP licence, warranty, support, and risk allocation between the German parent and US affiliate.
- Deliverable: Entity-responsibility chart, required intercompany documents, and a list of customer-contract clauses that must match the approved model.
- Deadline: 2026-09-15
- Budget ceiling: EUR 18,000 combined legal and tax scope
- Internal owner: CFO and General Counsel
- Approval required: CFO
- External action allowed: false

Facts:

- The product IP is held by the German provider in the synthetic scenario.
- The framework contemplates German and US deployments.
- Customer-facing support may be delivered by both entities.

Assumptions:

- Existing intercompany agreements can be reviewed.
- Finance will provide the intended transfer-pricing policy and revenue flows.

### EXT-004: IP and trade-secret protection

- Jurisdiction: Germany, European Union, and United States
- Question: Protect reusable robotics, software, model, workflow, and improvement IP while defining customer rights in site-specific deliverables and production data.
- Deliverable: IP clause mark-up, invention and trade-secret control checklist, and filing recommendations.
- Deadline: 2026-08-14
- Budget ceiling: EUR 10,000 for contract and portfolio review
- Internal owner: General Counsel and CTO
- Approval required: General Counsel
- External action allowed: false

Facts:

- The customer requests ownership of all site-specific improvements.
- The product uses telemetry and AI-enabled optimisation.
- The deployment exposes personnel to customer manufacturing information.

Assumptions:

- Patent, trademark, and invention-assignment records are available.
- Commercial teams can identify customer-funded development.

## Founding General Counsel 100-day plan

### Days 1 to 30: establish control

Create a verified legal baseline and decision authority for the first legal function.

- Legal request intake, risk tiers, SLAs, and escalation matrix
- Contract, entity, signatory authority, litigation, employment, privacy, and IP inventories
- Top 20 customer and supplier contract review
- External-counsel panel with scopes, rates, conflicts, and instruction template
- Immediate product safety, AI, cybersecurity, and data-law issue register

**Proof metric:** All material matters have an owner, deadline, evidence reference, and approval tier.

### Days 31 to 60: build the operating model

Turn repeat legal work into controlled deal and governance workflows.

- RaaS MSA, pilot, order form, DPA, NDA, supplier, and employment template set
- Negotiation playbook with fallback positions and authority limits
- Deal-desk cadence with Sales, Finance, Security, Product, and Operations
- IFRS 15 and ASC 606 contract-structuring checklist with Finance
- Board legal-risk pack and corporate-housekeeping calendar

**Proof metric:** Standard deals follow the playbook, and deviations reach the correct approver.

### Days 61 to 100: scale and evidence

Prepare the legal function for cross-border growth and repeatable diligence.

- Germany-US entity and intercompany responsibility model
- Regulatory readiness programme for machinery, AI, data, cybersecurity, and product liability
- Product and data responsibility matrices embedded in deployment workflows
- IP lifecycle covering inventions, open source, trade secrets, trademarks, and patents
- Legal metrics for cycle time, deviation rate, outside-counsel spend, disputes, and open controls

**Proof metric:** Management can see signing blockers, deployment risks, spend, and readiness from one evidence-backed pack.

## Primary-source manifest

- **[EU-DATA-ACT](https://eur-lex.europa.eu/eli/reg/2023/2854/oj/eng):** Regulation (EU) 2023/2854, Data Act, Articles 3 to 5, 13, and 50. Legal effect: `directly_applicable_regulation`. Generally applies from 12 September 2025. Article 3(1) applies to connected products and related services placed on the market after 12 September 2026.
- **[EU-MACHINERY-DIRECTIVE](https://eur-lex.europa.eu/eli/dir/2006/42/oj/eng):** Directive 2006/42/EC, Machinery Directive, Articles 5 and 12, Annex I. Legal effect: `directive_implemented_in_national_law`. Current EU machinery framework during the synthetic 2026 review, implemented through national law.
- **[EU-MACHINERY-REGULATION](https://eur-lex.europa.eu/eli/reg/2023/1230/oj/eng):** Regulation (EU) 2023/1230, Machinery Regulation, Articles 10 to 18 and 54, Annex III. Legal effect: `directly_applicable_regulation`. Generally applies from 20 January 2027.
- **[EU-AI-ACT](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng):** Regulation (EU) 2024/1689, Artificial Intelligence Act, Articles 6, 9 to 15, 17, 43, and 113. Legal effect: `directly_applicable_regulation`. Generally applies from 2 August 2026. Article 6(1) and the corresponding product-linked high-risk obligations apply from 2 August 2027. Earlier phases under Article 113 must be checked separately.
- **[EU-CRA](https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng):** Regulation (EU) 2024/2847, Cyber Resilience Act, Articles 13, 14, 32, and 71. Legal effect: `directly_applicable_regulation`. Chapter IV applies from 11 June 2026. Article 14 applies from 11 September 2026. The Regulation generally applies from 11 December 2027.
- **[EU-PRODUCT-LIABILITY](https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng):** Directive (EU) 2024/2853, Product Liability Directive, Articles 2, 4, 7 to 11, 21, and 22. Legal effect: `directive_requires_national_implementation`. Member States must transpose the Directive by 9 December 2026. The resulting national rules apply to products placed on the market or put into service after 9 December 2026.
- **[EU-GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng):** Regulation (EU) 2016/679, General Data Protection Regulation, Articles 5, 6, 13, 28, 32, 35, and 44 to 49. Legal effect: `directly_applicable_regulation`. In force and directly applicable. The concrete obligations depend on the roles, data, purposes, and transfer path.

Source digest: `776adbd1b46a33879ee4cb4f93538d9893e2d171c6f5b27af9f7305c7578c881`

_This public-safe demonstration uses synthetic facts and illustrative internal guardrails. It is legal-operations and deal-structuring support. It is not legal or accounting advice. Qualified Legal, Finance, Tax, Security, Product, and Safety reviewers must validate the analysis before any external use._
