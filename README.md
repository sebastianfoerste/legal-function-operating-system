# legal-function-operating-system

A deterministic legal function operating system for consistent intake, risk,
priority, routing, service levels, approvals, external-counsel decisions,
escalation, and board reporting.

![Legal function operating system](docs/demo.svg)

The system answers the operating questions a first legal hire or General Counsel
faces as a company scales:

1. Which matters require attention first?
2. Who owns the next step?
3. Which approval tier applies?
4. When should specialist counsel or the board become involved?

All bundled data is synthetic. Every consequential decision requires human review.
The repository does not provide legal or accounting advice.

The supervised legal-operations agent is maintained in `supervised-agent`. Both components retain their own Python runtime and test gate. Their interoperability boundary is `contracts/legal-workflow-controls.v1.schema.json`, which normalizes review state, approval gates, source boundaries and audit events without changing either component's public interfaces. Run `make contract-check` for the shared contract, `make agent-check` for the agent and `make check` for the combined gate.

## Two-minute reviewer path

**[Read the artifacts in a browser](https://sebastianfoerste.github.io/legal-function-operating-system/)** —
the deal room, outcome control tower, decision cockpit and architecture flow are
published from this repository. No clone required.

Or run it in one command, also without cloning:

```bash
uvx --from git+https://github.com/sebastianfoerste/legal-function-operating-system legal-function-os
```

That prints the board operations pack from the bundled synthetic requests.
`raas-deal-desk` is the second entry point and prints the deal decision pack.
Both accept `--input` to run against your own JSON instead.

Locally:

1. Read the [general legal-function case study](CASE_STUDY.md).
2. Open the generated [board operations pack](examples/board-pack.md).
3. Inspect the [outcome control tower](examples/legal-outcome-control-tower.md)
   or its [local HTML view](examples/legal-outcome-control-tower.html).
4. Review the [architecture flow](docs/architecture.svg).
5. Run `make check`.

The machine-readable verification manifest is available at
[`docs/verification-manifest.json`](docs/verification-manifest.json). It records
every artifact a reviewer can inspect and the commands that validate them.

The [legal capacity simulation](examples/legal-capacity-simulation.md) replays the
same synthetic portfolio across alternative queue, GC-approval, and
external-counsel assumptions. It makes backlog and constraint trade-offs visible
without executing a staffing decision or external instruction. Its decision brief
identifies each binding queue, approval, or coordination constraint and the minimum
illustrative uplift required to clear it.

The [outcome control tower](examples/legal-outcome-control-tower.md) adds observed
service-delivery evidence to the forecast. A versioned synthetic event ledger
reconciles gross cycle time, business-wait time, legal-controlled time, approval
dwell, SLA attainment, queue age, effort, reopenings, and stalled work. It
calibrates forecast points against observed minutes and keeps every monetary figure
inside an explicit assumption-based proxy.

This capability responds to a measurable operating gap. The
[2025 Thomson Reuters Legal Department Operations Index](https://legal.thomsonreuters.com/en/insights/reports/legal-department-operations-index)
reports under-resourcing, growing in-house workloads, and constrained budgets.
[Axiom's July 2026 research](https://www.axiomlaw.com/resources/press-releases/legal-ai-is-everywhere-but-only-7-of-legal-teams-have-made-it-work?hs_amp=true)
reports that most surveyed legal teams could not demonstrate AI return on
investment. The control tower therefore makes service outcomes and value
assumptions inspectable before a staffing, technology, or external-counsel
decision.

## Operating model

Each incoming legal request moves through a deterministic pipeline:

`intake -> risk -> priority -> routing -> SLA -> approval matrix -> external-counsel decision -> escalation -> board reporting`

The synthetic request set produces:

- a risk and priority decision for every matter;
- an owning legal queue;
- response and resolution service levels;
- a binding human approval tier;
- an external-counsel decision;
- board-attention and SLA escalation flags;
- a request vault and guided workflow set; and
- a board operations pack.

The generated board pack surfaces three board-attention items, one SLA breach, and
three external-counsel referrals across eight synthetic requests.

## Core capabilities

| Capability | Deterministic output | Implementation |
| --- | --- | --- |
| Risk assessment | HIGH, MEDIUM, or LOW based on structured facts | `rules.assess_risk` |
| Priority | P1 to P4 from urgency and risk | `rules.assess_priority` |
| Routing | Owning legal queue by request type | `rules.route` |
| SLA model | Response and resolution targets | `rules.SLA` |
| Approval matrix | Human sign-off tier by value and risk | `rules.approval_chain` |
| External counsel | In-house or scoped specialist referral | `rules.external_counsel` |
| Escalation | SLA, value, dispute, and blocker flags | `rules.escalations` |
| Board reporting | Executive roll-up and request register | `board_pack.py` |
| Capacity simulation | Queue demand, binding constraints, minimum uplift, approval overflow, and scenario delta | `capacity_simulator.py` |
| Outcome control tower | Business-time SLAs, wait-state reconciliation, effort calibration, stalled-work queue, and value proxies | `outcome_control_tower.py` |
| Supervised agent runs | Step-by-step matter runs with evidence and a binding approval step | `agent_run.py` |
| Requester shared space | Status sharing behind a documented approval gate | `shared_space.py` |
| DPA clause review | Art. 28 Abs. 3 lit. a–h DSGVO coverage per document | `contract_intelligence.py` |

The workspace outputs add a deterministic request vault, guided workflows, a GC
command center, operational lists, and a local knowledge portal. Portal answers
cite approved local resources or return an insufficient-evidence result.

### DPA clause review

The clause playbook checks a processing agreement against each requirement of
Article 28(3) GDPR and returns `pass`, `review`, or `missing` per requirement,
with the pinpoint citation and the matched clause excerpt. A `missing`
requirement counts as a blocker.

```bash
PYTHONPATH=src python -m legal_function_os.cli --quiet \
  --dpa-input src/legal_function_os/data/dpa_documents.json \
  --dpa-output examples/dpa-review.json
```

The two synthetic agreements in [`src/legal_function_os/data/dpa_documents.json`](src/legal_function_os/data/dpa_documents.json)
produce fourteen `pass` rows, one `review` row where a security clause never
references Art. 32 DSGVO or technical and organisational measures, and one
`missing` row where the Art. 28 Abs. 3 lit. h audit and inspection right is absent.
The review states a coverage result. It does not state that an agreement is lawful.

## Specialist deal-desk case studies

### Industrial robotics and Robotics-as-a-Service

The repository includes a specialist deal-desk workflow for a synthetic 36-month,
multi-site industrial robotics transaction covering Germany and the United States.
It demonstrates how the general operating model can support a complex combination
of hardware, software, AI, deployment services, telemetry, maintenance, and
recurring service fees.

Start with:

1. the [industrial RaaS case study](RAAS_CASE_STUDY.md);
2. the generated [deal decision pack](examples/raas-deal-pack.md);
3. the dated [primary-source manifest](examples/raas-source-manifest.json); and
4. the generated [decision cockpit](examples/raas-deal-desk.svg).

The generated HTML deal room is published at
[sebastianfoerste.github.io/legal-function-operating-system/raas-deal-room.html](https://sebastianfoerste.github.io/legal-function-operating-system/raas-deal-room.html)
and committed as an offline artifact at [`examples/raas-deal-room.html`](examples/raas-deal-room.html).
A concise walkthrough is available in the [reviewer script](docs/RAAS_REVIEWER_SCRIPT.md).

The specialist workflow preserves:

- clause-level playbook reviews and negotiation guardrails;
- signing blockers, escalation triggers, and named approvers;
- Finance review questions for IFRS 15, ASC 606, IFRS 16, and ASC 842;
- a regulatory readiness matrix with dated primary-source provenance;
- scoped external-counsel instruction packs; and
- a first 100-day legal-function implementation plan.

The signing answer for the bundled synthetic draft is explicit: **do not sign**.
Finance remains accountable for accounting conclusions, qualified external counsel
owns referred jurisdiction-specific advice, and the business retains every approval.

## Run it

```bash
git clone https://github.com/sebastianfoerste/legal-function-operating-system
cd legal-function-operating-system
make install
make test
make demo
make check
```

The project uses Python 3.10 or later and the standard library only. Execution is
offline and deterministic.

`make demo` regenerates:

- [`examples/board-pack.md`](examples/board-pack.md)
- [`examples/board-pack.json`](examples/board-pack.json)
- [`examples/legal-capacity-simulation.md`](examples/legal-capacity-simulation.md)
- [`examples/legal-capacity-simulation.json`](examples/legal-capacity-simulation.json)
- [`examples/legal-outcome-control-tower.md`](examples/legal-outcome-control-tower.md)
- [`examples/legal-outcome-control-tower.json`](examples/legal-outcome-control-tower.json)
- [`examples/legal-outcome-control-tower.html`](examples/legal-outcome-control-tower.html)
- [`examples/raas-deal-pack.md`](examples/raas-deal-pack.md)
- [`examples/raas-deal-pack.json`](examples/raas-deal-pack.json)
- [`examples/raas-deal-room.html`](examples/raas-deal-room.html)
- [`examples/raas-deal-desk.svg`](examples/raas-deal-desk.svg)
- [`examples/raas-source-manifest.json`](examples/raas-source-manifest.json)

The specialist signing gate can be used in a pipeline:

```bash
PYTHONPATH=src python -m legal_function_os.raas_cli \
  --input src/legal_function_os/data/raas_deal.json \
  --out examples \
  --fail-on-blocker
```

Ordinary generation exits with status `0`. A blocked signing gate exits with
status `1`. Invalid input exits with status `2`.

## Repository structure

```text
src/legal_function_os/
  rules.py                 general request routing and approval rules
  board_pack.py            board operations pack
  outcome_control_tower.py observed service outcomes and value proxies
  workspace.py             request vault and GC command center
  collaboration_workspace.py
                           approved local knowledge and supervised workflows
  raas_deal_desk.py        stable specialist deal-desk facade
  raas_models.py           versioned input contract and validation
  raas_rules.py            playbook, Finance, regulation, counsel, and plan rules
  raas_sources.py          dated primary-source registry
  raas_renderers.py        Markdown, HTML, SVG, and JSON outputs
  raas_cli.py              artifact generation and blocker gate
  bundled.py               locates the synthetic data shipped in the wheel
  data/                    synthetic data, packaged so the demo runs uninstalled
    sample_requests.json   synthetic general legal requests
    service_events.json    versioned synthetic request lifecycle
    outcome_config.json    business calendar and value assumptions
    capacity_scenarios.json  illustrative capacity constraints
    dpa_documents.json     synthetic Art. 28 GDPR processing agreements
    raas_deal.json         synthetic specialist transaction
examples/                  committed reviewer and machine-readable outputs
site/                      generated Pages site (not committed)
tests/                     deterministic standard-library tests
scripts/                   artifact, site, and contract verification
```

## Controls

- Synthetic inputs only.
- Deterministic offline execution.
- Human approval for every consequential position.
- Primary-source provenance for regulatory controls.
- Explicit Finance and external-counsel review boundaries.
- No external communication.
- No contract signature or self-approval.
- No client or customer data.
- No automated legal or accounting conclusion.

## Known limitations

1. Thresholds and fallback positions are illustrative internal guardrails.
2. The system operates over structured JSON instead of a live CLM or CRM.
3. Approval roles are modelled and are not connected to an identity provider.
4. US-law issues are routed to qualified US counsel.
5. Product classification requires verified intended-purpose, architecture,
   safety, conformity, and deployment facts.
6. Regulatory dates and requirements require confirmation at the actual review date.
7. Event completeness, effort records, working calendars, and value assumptions
   require validation before management use.

## Human-authored judgment

AI tools assisted implementation. The operating model, issue selection, rule
structure, escalation logic, approval design, regulatory framing, and review
boundaries carry the substantive value. The objective is to make legal judgment
structured, testable, and reviewable.

## License

MIT. See [`LICENSE`](LICENSE).
