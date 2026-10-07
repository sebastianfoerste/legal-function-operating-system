# Legal function and supervised agent consolidation

This repository is the canonical working repository for the deterministic legal function operating model and the supervised legal-operations agent.

The base application remains a standard-library Python package under `src/legal_function_os`. The agent remains an independently testable Python 3.13 component under `supervised-agent`, with its Pydantic models, local MCP-style tools, command line interface and test suite unchanged.

The shared JSON Schema normalizes four boundaries:

1. Review state.
2. Human approval and export gates.
3. Synthetic and approved-public source boundaries.
4. Audit events and optional hash-chain integrity.

The public `legal-ops-agent` repository is archived and points here. It remains readable as a dated snapshot and receives no fixes. `make agent-export` prepares a local path-export branch and does not push it.

## Pilot workflow

The supervised pilot workflow under `supervised-agent/src/pilot` is the first place where the agent calls the base application at run time. It imports `legal_function_os.rules` for routing, service levels and the approval tier, and `legal_function_os.outcome_control_tower` to read its own events in the base application's ledger schema. The import is resolved from this repository's `src` directory, so the pilot runs in the consolidated repository only. A standalone path export of `supervised-agent` keeps every earlier capability but cannot run the pilot; `parent_bridge.ParentSystemUnavailable` says so. The base application is unchanged and still has no third-party dependency.
