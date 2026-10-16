# legal-function-operating-system

[![ci](https://github.com/sebastianfoerste/legal-function-operating-system/actions/workflows/ci.yml/badge.svg)](https://github.com/sebastianfoerste/legal-function-operating-system/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Legal requests in → risk, owner, SLA, approval tier and a board pack out — deterministic rules, no LLM in the decision path.**

![Legal function operating system](docs/demo.svg)

Built for the questions a first legal hire or General Counsel faces as a company
scales: which matters come first, who owns the next step, which approval tier
applies, and when specialist counsel or the board must be involved.

> All bundled data is synthetic. Every consequential decision requires human review.
> This repository does not provide legal or accounting advice.

## Try it in one command

No clone needed (Python 3.10+, standard library only):

```bash
uvx --from git+https://github.com/sebastianfoerste/legal-function-operating-system legal-function-os
```

A PyPI package (`legal-function-os`) is coming; it is not published yet, so use the git form above.
`raas-deal-desk` is the second entry point (deal decision pack). Both accept `--input` for your own JSON, and `legal-function-os` also reads a request log saved from a spreadsheet as CSV ([template](examples/requests-template.csv)): see the [request input format](docs/INPUT_FORMAT.md).

## Example output

Real output of the command above (first lines, synthetic requests):

```text
# Legal Function: Board Operations Pack

## Executive summary

- **8** legal requests handled · **5** high-risk
- **5** require GC sign-off · **3** flagged for board attention
- **3** external-counsel referrals · **1** SLA breaches

## Board attention

| ID | Title | Risk | Type |
| --- | --- | --- | --- |
| REQ-1001 | Enterprise MSA: Globex (synthetic) | HIGH | commercial_contract |
| REQ-1005 | Series B financing: term sheet (synthetic) | HIGH | fundraising |
| REQ-1007 | Customer dispute: SLA credits claim (synthetic) | HIGH | dispute |

## SLA breaches

- REQ-1006: Vendor security questionnaire: analytics tool (synthetic)
```

Full pack: [`examples/board-pack.md`](examples/board-pack.md).

### Cited DPA clause review (AVV, Art. 28 GDPR / DSGVO)

From a clone, this writes the review to `dpa-review.json`:

```bash
PYTHONPATH=src python -m legal_function_os.cli --quiet \
  --dpa-input src/legal_function_os/data/dpa_documents.json \
  --dpa-output dpa-review.json
```

Real rows from that file (synthetic agreement DPA-002):

```json
{ "citation": "Art. 28 Abs. 3 lit. c DSGVO", "status": "review",
  "label": "Technische und organisatorische Maßnahmen",
  "clause_excerpt": "The processor maintains an information security programme reviewed annually by management." }
{ "citation": "Art. 28 Abs. 3 lit. h DSGVO", "status": "missing",
  "label": "Nachweis- und Kontrollrechte", "clause_excerpt": "" }
```

A `missing` requirement is a blocker. The review states coverage, not that an agreement is lawful.
Details: [docs/MODULES.md](docs/MODULES.md#dpa-clause-review-avv--auftragsverarbeitungsvertrag-art-28-gdpr--dsgvo).

## How is this different from LLM legal skills?

The rules are code, tests gate them, and the output is the same every run. The
supervised agent sits behind review gates and takes routing, SLAs and approval
tiers from these rules rather than guessing them.

## Use it next to claude-for-legal (MCP server and Claude Code plugin)

LLM legal skills describe escalation and approval rules in prose. This repo ships the same decisions as tested code, and an MCP server lets an agent call them:

```bash
# Claude Code: add the plugin marketplace from this repo, then install the plugin
/plugin marketplace add sebastianfoerste/legal-function-operating-system
/plugin install legal-function-os@legal-function-os

# Any MCP client (stdio). The extra needs Python 3.13 when run with uvx:
uvx --python 3.13 --from "legal-function-os[mcp] @ git+https://github.com/sebastianfoerste/legal-function-operating-system" legal-function-os-mcp
```

Tools (all read-only): `triage_requests`, `board_pack`, `dpa_review`, `legal_request_schema`. Input that breaks the request contract is rejected rather than decided. The core package stays standard-library-only; `mcp` is an optional extra.

## Demo and links

- [Artifacts in a browser](https://sebastianfoerste.github.io/legal-function-operating-system/): deal room, outcome control tower, decision cockpit, architecture flow
- [General case study](CASE_STUDY.md) · [Industrial RaaS case study](RAAS_CASE_STUDY.md) ("do not sign" deal-room demo: [`raas-deal-room.html`](https://sebastianfoerste.github.io/legal-function-operating-system/raas-deal-room.html))
- [Board pack](examples/board-pack.md) · [Outcome control tower](examples/legal-outcome-control-tower.md) · [Capacity simulation](examples/legal-capacity-simulation.md) · [Architecture](docs/architecture.svg)
- [Verification manifest](docs/verification-manifest.json): every inspectable artifact and the commands that validate it
- [Supervised agent](supervised-agent/) and its [pilot case study](supervised-agent/docs/pilot/CASE_STUDY.md); shared contract: [`contracts/legal-workflow-controls.v1.schema.json`](contracts/legal-workflow-controls.v1.schema.json)
- Detail: [Modules, capabilities, layout](docs/MODULES.md) · [Reviewer script](docs/RAAS_REVIEWER_SCRIPT.md) · [Collaboration programme](docs/COLLABORATION_PROGRAMME.md) · [Consolidation](docs/CONSOLIDATION.md) · [Contributing](CONTRIBUTING.md)

## Run from a clone

```bash
git clone https://github.com/sebastianfoerste/legal-function-operating-system
cd legal-function-operating-system
make install && make test && make demo && make check
```

## What's inside

Pipeline: `intake -> risk -> priority -> routing -> SLA -> approval matrix -> external-counsel decision -> escalation -> board reporting`.
Modules (capacity simulation, outcome control tower, DPA review, RaaS deal desk, supervised agent) are described in [docs/MODULES.md](docs/MODULES.md).

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

Controls (synthetic inputs only, no external communication, no self-approval) are listed in [docs/MODULES.md](docs/MODULES.md#controls).

## Human-authored judgment

AI tools assisted implementation. The operating model, issue selection, rule
structure, escalation logic, approval design, regulatory framing, and review
boundaries carry the substantive value. The objective is to make legal judgment
structured, testable, and reviewable.

## License

MIT. See [`LICENSE`](LICENSE).
