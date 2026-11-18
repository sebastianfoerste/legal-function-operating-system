# Architecture decision records

One file per decision, numbered in order. Status is Proposed, Accepted, Superseded or
Rejected. A Proposed record names a choice the maintainer still has to make.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-design-tokens.md) | One token set for generated pages, copied into the agent | Accepted |
| [0002](0002-mcp-2x-path.md) | Keep `mcp>=1.9,<2` for now; the path to 2.x | Accepted |
| [0003](0003-intake-facts-and-requester-status.md) | Required facts and requester status are derived views, not new state | Accepted |
| [0004](0004-docx-tracked-changes-engine.md) | Word tracked changes stay in the stdlib writer; Python-Redlines not adopted | Accepted |
| [0005](0005-presence-in-memory.md) | Presence is held in memory only and is never an audit event | Accepted |
| [0006](0006-intake-question-files.md) | Intake questions live in one file per policy, keyed by request type | Accepted |
| [0007](0007-mcp-local-stdio-only.md) | MCP server stays a local stdio process | Accepted |
| [0008](0008-pilot-local-hardening.md) | Pilot server local hardening, not authentication | Accepted |
