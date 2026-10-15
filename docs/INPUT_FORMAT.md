# Request input format

`legal-function-os --input requests.json` reads a JSON array of legal requests. Each
request is one object. The machine-readable contract is
[`contracts/legal-request.v1.schema.json`](../contracts/legal-request.v1.schema.json)
(JSON Schema 2020-12). The bundled synthetic set,
[`src/legal_function_os/data/sample_requests.json`](../src/legal_function_os/data/sample_requests.json),
is a complete example.

```json
[
  {
    "id": "REQ-1001",
    "title": "Enterprise MSA: Globex (synthetic)",
    "type": "commercial_contract",
    "counterparty": "Globex Inc. (synthetic)",
    "value_band": ">1m",
    "personal_data": true,
    "non_eea_transfer": false,
    "uncapped_liability": true,
    "urgency": "high",
    "requested_by": "sales"
  }
]
```

Every input is checked before any decision is made. Use `--input -` to read the
array from standard input. A request log kept in a spreadsheet works too: save it
as CSV ([Spreadsheets (CSV)](#spreadsheets-csv)).

## Fields

Only `id` and `title` are required. An omitted optional field, or `null`, takes its
default.

| Field | Type | Default | What it drives |
| --- | --- | --- | --- |
| `id` | string, unique in the file | required | The request register and every cross-reference |
| `title` | string | required | The board pack and register |
| `type` | string | none | Owning queue and type-specific rules (see below) |
| `counterparty` | string | none | Register only; not used in decisions |
| `value_band` | one of `none`, `<50k`, `50k-250k`, `250k-1m`, `>1m` | `none` | Risk, approval chain, litigation referral, board attention |
| `personal_data` | `true` / `false` | `false` | MEDIUM risk; HIGH risk together with `non_eea_transfer` |
| `non_eea_transfer` | `true` / `false` | `false` | Routes to Privacy whatever the type; HIGH risk with `personal_data` |
| `uncapped_liability` | `true` / `false` | `false` | HIGH risk |
| `urgency` | one of `blocker`, `high`, `standard`, `low` | `standard` | Priority and therefore the SLA |
| `requested_by` | string | none | Register only |
| `sla_breached` | `true` / `false` | `false` | SLA escalation; `--fail-on-breach` exits 1 |

Values are matched exactly. `">1m"` is a value band; `">1M"` is rejected with a
suggestion, because it used to be read as "no value" and turned a board-level
matter into a low-risk one. Booleans are JSON `true` and `false`, not the strings
`"yes"` or `"false"`.

The value bands, request types, queues and thresholds below are the bundled
default policy. A policy file can set your own; requests are then checked against
it. See [Make the rules your own](CUSTOMIZE.md).

### Value bands

With the shipped thresholds (illustrative, not a recommendation):

| Band | Effect |
| --- | --- |
| `none`, `<50k` | Reviewer only, unless the risk is HIGH |
| `50k-250k` | Adds Legal Ops Lead to the approval chain |
| `250k-1m` | Adds General Counsel; MEDIUM risk. A dispute at this value or above is HIGH risk, goes to external litigation counsel and gets board attention |
| `>1m` | HIGH risk; adds a Board note; board awareness escalation |

A HIGH-risk request always needs General Counsel, whatever its value.

### Request types and queues

| `type` | Queue | Type-specific rules |
| --- | --- | --- |
| `commercial_contract` | Commercial | |
| `vendor_review` | Commercial | |
| `ip` | Commercial | |
| `dpa` | Privacy | |
| `privacy_query` | Privacy | |
| `ai_governance` | Legal Ops (AI) | MEDIUM baseline risk; with a non-EEA transfer, external cross-border AI/privacy specialist |
| `corporate` | Corporate / GC | MEDIUM baseline risk; external corporate counsel |
| `fundraising` | Corporate / GC | MEDIUM baseline risk; external corporate counsel |
| `employment` | Employment | |
| `dispute` | Litigation | General Counsel is notified; see the value bands above |

A missing or unknown type is not an error. The request goes to the General queue
(or Privacy, for a non-EEA transfer), the run prints a warning, and the decision's
rationale says the request needs manual triage.

### Urgency and priority

| Urgency | Priority |
| --- | --- |
| `blocker` | P1_blocker |
| `high`, or any HIGH-risk request | P2_high |
| `low`, when the risk is LOW | P4_low |
| anything else | P3_standard |

## Other fields

Fields not listed above pass through unchanged. The optional workspace,
agent-run and shared-space outputs read six more, which never change a decision:

| Field | Type |
| --- | --- |
| `description`, `summary` | string |
| `deadline` | string, for example `2026-12-01` |
| `facts` | array of strings |
| `dependencies` | array, for example of request ids |
| `awaiting_business_input` | `true` / `false` |

They are checked like the request fields, because a wrong type would be misread
there: the string `"no"` would count as true, and a single string of facts would be
split into characters.

A field whose name is close to a request field, such as `valueBand` or
`uncapped_liabilty`, is rejected, because its value would otherwise be ignored
without a word. Prefix your own fields with `x_` (for example `x_matter_number`) to
keep them out of that check.

## Spreadsheets (CSV)

Save the sheet as CSV and pass the file: `legal-function-os --input requests.csv`.
A file ending in `.csv` or `.tsv` is read as a table with one request per row.
[`examples/requests-template.csv`](../examples/requests-template.csv) holds the
bundled synthetic requests and gives the same board pack as the JSON set.

| Part of the sheet | How it is read |
| --- | --- |
| Header row | Names the fields. Spelling is relaxed: `Value band`, `value-band` and `valueBand` all mean `value_band`, and `Request ID`, `Request type` and `Requester` mean `id`, `type` and `requested_by` |
| Empty cell | The field was not given, so its default applies |
| Yes/no columns | `personal_data`, `non_eea_transfer`, `uncapped_liability`, `sla_breached` and `awaiting_business_input` accept yes/no, true/false, ja/nein, wahr/falsch, 1/0 and x, in any case |
| `facts`, `dependencies` | One item per line of the cell (Alt+Enter in Excel) |
| Every other cell | Text, checked exactly as in JSON, so `>1M` is still rejected |
| Delimiter | Comma, semicolon or tab, recognised from the header row. Excel in a German locale writes semicolons |
| Encoding | UTF-8 with or without a byte order mark, or UTF-16 with one. Anything else is read as Windows-1252, Excel's plain CSV default, and the run says so |

Problems name the row a spreadsheet shows, counting the header as row 1:

```text
error: row 3 (REQ-2): value_band: '>1M' is not a value band (did you mean '>1m'?); use one of none, <50k, 50k-250k, 250k-1m, >1m
```

A header that looks like a misspelled field, such as `Value bnad`, stops the run
with one message for the column. Any other column, such as `Notes`, is carried
along unused, and the run prints a note naming it, so a column like
`Value band (EUR)` is never ignored without a word. Prefix your own columns with
`x_` to leave them out of the note. Workbooks (`.xlsx`, `.ods`, `.numbers`) are
not read: save the sheet as CSV first (in Excel, *CSV UTF-8*).

## What happens on bad input

Problems are reported together on standard error, one line each, naming the
request, its id and the field. For this input:

```json
[
  {"id": "REQ-1", "title": "Enterprise MSA", "type": "commercial_contract", "value_band": ">1M", "personal_data": "no"},
  {"id": "REQ-2", "title": "New licence question", "type": "regulatory"}
]
```

the run stops with:

```text
error: request 1 (REQ-1): value_band: '>1M' is not a value band (did you mean '>1m'?); use one of none, <50k, 50k-250k, 250k-1m, >1m
error: request 1 (REQ-1): personal_data: expected true or false, got 'no' (write false, without quotes)
warning: request 2 (REQ-2): type: 'regulatory' is not a request type in the routing table; the request needs manual triage
2 errors, 1 warning in 2 requests. Nothing was written. Request format: https://github.com/sebastianfoerste/legal-function-operating-system/blob/main/docs/INPUT_FORMAT.md
```

| Situation | Result |
| --- | --- |
| Any error | Exit status 2; nothing is written |
| Warnings only | Warnings on standard error; the run continues |
| Valid input | Normal output |

Errors are: a missing `id` or `title`, a duplicate `id`, an unknown `value_band` or
`urgency`, a value of the wrong type, and a misspelled field name. Warnings are a
missing or unknown `type` and an empty input.
