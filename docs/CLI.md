# Command-line reference

Three entry points ship with the package. All of them read synthetic or your own
JSON and write files locally. They make no network or model calls.

| Command | What it does |
| --- | --- |
| `legal-function-os` | Request triage, board pack, DPA review, capacity, control tower, approval matrix and policy interview |
| `raas-deal-desk` | The industrial RaaS deal decision pack |
| `legal-function-os-mcp` | The same rules as a local stdio MCP server (optional `mcp` extra) |

`python -m legal_function_os` runs the same commands as `legal-function-os`.

## legal-function-os

```text
legal-function-os [--version] COMMAND [options]
```

Each command prints Markdown, or JSON with `--format json`. With `--out DIR` it writes the
same artifacts as files instead. `--policy PATH` applies your own value bands, queues,
service levels and thresholds instead of the bundled illustrative policy
([docs/CUSTOMIZE.md](CUSTOMIZE.md)). `--input PATH` takes a JSON array, a `.csv` file with
one request per row, or `-` for JSON on standard input ([docs/INPUT_FORMAT.md](INPUT_FORMAT.md)).
Without `--input`, the bundled synthetic requests are used.

| Command | Purpose | Options beyond `--input`, `--policy` and `--format` |
| --- | --- | --- |
| `triage` | Risk, priority, queue, SLA, approval chain and external counsel per request, with the reasons | `--id ID` (repeatable) shows only those requests |
| `board-pack` | Roll the decisions up into a board operations pack | `--period LABEL`, `--out DIR`, `--fail-on-breach` |
| `validate` | Check requests against the request contract without deciding anything | none |
| `dpa-review` | Check data processing agreements for the Art. 28(3) GDPR (DSGVO) clauses | `--out DIR`; `--input` takes agreements, not requests; no `--policy` |
| `capacity` | Compare capacity scenarios and name the binding constraint | `--scenarios PATH` (required with `--input`), `--out DIR` |
| `control-tower` | Business-time SLAs, waiting time and value from a service-event ledger | `--events PATH` and `--config PATH` (both required with `--input`), `--out DIR` |
| `approval-matrix` | Who must sign off for each value band and risk level, from the rules and the policy, with each request placed in its cell | `--out DIR` (writes `approval-matrix.md`, `.json` and `.html`) |
| `init` | Write a policy file from a short interview | `--out PATH` (default `policy.json`), `--defaults`, `--force`; no `--input` |

Examples:

```bash
legal-function-os triage --input examples/requests-template.csv
legal-function-os validate --input requests.csv --format json
legal-function-os board-pack --input requests.json --out reports --fail-on-breach
legal-function-os init --defaults --out policy.json
legal-function-os approval-matrix --policy policy.json --out reports
legal-function-os triage --policy policy.json --input requests.csv --id REQ-1001
```

### All-in-one mode

Without a command, `legal-function-os` prints the board pack for the bundled requests. The
original flags still work in that mode and are what `make demo` uses:

| Flag | Writes |
| --- | --- |
| `--input PATH`, `--policy PATH`, `--period LABEL`, `--out DIR`, `--quiet` | Board pack (`--quiet` suppresses the printed pack) |
| `--capacity-scenarios PATH` with `--capacity-output DIR` | Capacity simulation |
| `--events-input PATH`, `--outcome-config PATH` with `--outcome-output DIR` | Outcome control tower (Markdown, JSON, HTML) |
| `--dpa-input PATH` with `--dpa-output PATH` | DPA review JSON; each needs the other |
| `--workspace-output PATH` | Request vault, triage workflows and GC command centre JSON |
| `--collaboration-output-dir DIR` | Operational lists, workflow runs and the local knowledge portal |
| `--approval-matrix-output DIR` | Approval matrix (Markdown, JSON, HTML) |
| `--agent-runs-output PATH` | Supervised matter agent runs JSON |
| `--shared-space-output PATH` with optional `--approvals PATH` | Approval-gated requester status JSON |
| `--fail-on-breach` | Exit status 1 when an SLA is breached |

### Exit status

| Status | Meaning |
| --- | --- |
| 0 | Done. Board-attention items are reported, not treated as failures. |
| 1 | `--fail-on-breach` was given and at least one request breached its SLA. |
| 2 | Invalid input or an invalid combination of flags. The message names the problem. |

## raas-deal-desk

```text
raas-deal-desk [--input PATH] [--out DIR] [--quiet] [--fail-on-blocker]
```

Builds the review-gated RaaS deal decision pack from one synthetic deal object (default: the
bundled deal). `--fail-on-blocker` exits non-zero while the signing gate is blocked. Every
external action stays blocked until a named human approval is recorded.

## legal-function-os-mcp

```text
legal-function-os-mcp [--policy PATH]
```

A local stdio MCP server with four read-only tools: `triage_requests`, `board_pack`,
`dpa_review` and `legal_request_schema`. Input that breaks the request contract is rejected
rather than decided. The tools take data, never file paths: the model calling the server
does not choose what the process reads. Your own policy applies either to every call, with
`--policy PATH` read once at start, or per call as an inline `policy` object in the format
`legal-function-os init` writes; an inline policy wins, and one that cannot be applied is
rejected like any other bad input. It needs the optional extra
(`pip install "legal-function-os[mcp]"`), which is pinned to `mcp>=1.30,<2`;
[ADR 0002](adr/0002-mcp-2x-path.md) records why.

## Related

- [Request input format](INPUT_FORMAT.md) and the generated contract in `contracts/`
- [Customising the policy](CUSTOMIZE.md)
- [Modules](MODULES.md)
