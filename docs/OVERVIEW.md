# Overview

Sections moved out of the README. All bundled data is synthetic; every consequential
decision requires human review; nothing here is legal or accounting advice.

## What's inside

Built for the questions a first legal hire or General Counsel faces as a company
scales: which matters come first, who owns the next step, which approval tier
applies, and when specialist counsel or the board must be involved.

Pipeline: `intake -> risk -> priority -> routing -> SLA -> approval matrix -> external-counsel decision -> escalation -> board reporting`.
Modules (capacity simulation, outcome control tower, DPA review, RaaS deal desk, supervised agent) are described in [MODULES.md](MODULES.md).

`legal-function-os` also reads a request log saved from a spreadsheet as CSV
([template](../examples/requests-template.csv)): see the [request input format](INPUT_FORMAT.md).

## Cited DPA clause review (AVV, Art. 28 GDPR / DSGVO)

From a clone, this prints the review of the two bundled synthetic agreements, or writes
it to `dpa-review.md` and `dpa-review.json` with `--out DIR`:

```bash
PYTHONPATH=src python -m legal_function_os.cli dpa-review --format json
```

Real rows from that output (synthetic agreement DPA-002):

```json
{ "citation": "Art. 28 Abs. 3 lit. c DSGVO", "status": "review",
  "label": "Technische und organisatorische Maßnahmen",
  "clause_excerpt": "The processor maintains an information security programme reviewed annually by management." }
{ "citation": "Art. 28 Abs. 3 lit. h DSGVO", "status": "missing",
  "label": "Nachweis- und Kontrollrechte", "clause_excerpt": "" }
```

A `missing` requirement is a blocker. The review states coverage, not that an agreement is lawful.
Details: [MODULES.md](MODULES.md#dpa-clause-review-avv--auftragsverarbeitungsvertrag-art-28-gdpr--dsgvo).

## How is this different from LLM legal skills?

The rules are code, tests gate them, and the output is the same every run. The
supervised agent sits behind review gates and takes routing, SLAs and approval
tiers from these rules rather than guessing them.

## MCP server and Claude Code plugin

LLM legal skills describe escalation and approval rules in prose. This repo ships the same decisions as tested code, and an MCP server lets an agent call them:

```bash
# Claude Code: add the plugin marketplace from this repo, then install the plugin
/plugin marketplace add sebastianfoerste/legal-function-operating-system
/plugin install legal-function-os@legal-function-os

# Any MCP client (stdio). The plugin's .mcp.json pins Python 3.13; the extra itself
# runs on Python 3.10 to 3.15 (tested with mcp 1.30.0).
uvx --python 3.13 --from "legal-function-os[mcp] @ git+https://github.com/sebastianfoerste/legal-function-operating-system" legal-function-os-mcp
```

Tools (all read-only): `triage_requests`, `board_pack`, `dpa_review`, `legal_request_schema`. Input that breaks the request contract is rejected rather than decided. The core package stays standard-library-only; `mcp` is an optional extra (`mcp>=1.30,<2`, [ADR 0002](adr/0002-mcp-2x-path.md)). The approval chain comes from `triage_requests`; there is no separate approval-matrix tool. When an agent prepares the `dpa_review` input, it maps the agreement's clauses to the playbook keys first, and the result depends on that mapping, which a human has to check. The [CLI reference](CLI.md#legal-function-os-mcp) has the command.

## Part of the EU regulation as code suite

By [@sebastianfoerste](https://github.com/sebastianfoerste):

- [awesome-eu-fintech-regulation](https://github.com/sebastianfoerste/awesome-eu-fintech-regulation)
- [contract-review-eval-harness](https://github.com/sebastianfoerste/contract-review-eval-harness)
- **legal-function-operating-system** (this repo)
- [eu-ai-act-classifier](https://github.com/sebastianfoerste/eu-ai-act-classifier)
- [micar-whitepaper-linter](https://github.com/sebastianfoerste/micar-whitepaper-linter)
- [eu-reg-mcp](https://github.com/sebastianfoerste/eu-reg-mcp)
- [micar-register-observatory](https://github.com/sebastianfoerste/micar-register-observatory)

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
8. The transfer rule treats any transfer of personal data outside the EEA as HIGH
   risk. It does not distinguish destinations covered by an adequacy decision
   (Art. 45 GDPR) from those that need Art. 46 safeguards; that distinction is left
   to the reviewer.

Controls (synthetic inputs only, no external communication, no self-approval) are listed in [MODULES.md](MODULES.md#controls).

## Human-authored judgment

AI tools assisted implementation. The operating model, issue selection, rule
structure, escalation logic, approval design, regulatory framing, and review
boundaries carry the substantive value. The objective is to make legal judgment
structured, testable, and reviewable.

## More

- [Competitive research, October 2026](research/2026-10-competitive-landscape.md) and the [adaptation plan](research/adaptation-plan.md)
- [Reviewer script](RAAS_REVIEWER_SCRIPT.md) · [Collaboration programme](COLLABORATION_PROGRAMME.md) · [Consolidation](CONSOLIDATION.md)
- [Supervised agent](../supervised-agent/) and its [pilot case study](../supervised-agent/docs/pilot/CASE_STUDY.md); shared contract: [`contracts/legal-workflow-controls.v1.schema.json`](../contracts/legal-workflow-controls.v1.schema.json)
- [Board pack](../examples/board-pack.md) · [Outcome control tower](../examples/legal-outcome-control-tower.md) · [Capacity simulation](../examples/legal-capacity-simulation.md) · [Approval matrix](../examples/approval-matrix.md) · [Architecture](architecture.svg)
