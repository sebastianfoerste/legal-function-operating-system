# Legal function and supervised agent consolidation

This repository is the canonical working repository for the deterministic legal function operating model and the supervised legal-operations agent.

The base application remains a standard-library Python package under `src/legal_function_os`. The agent remains an independently testable Python 3.13 component under `supervised-agent`, with its Pydantic models, local MCP-style tools, command line interface and test suite unchanged.

The shared JSON Schema normalizes four boundaries:

1. Review state.
2. Human approval and export gates.
3. Synthetic and approved-public source boundaries.
4. Audit events and optional hash-chain integrity.

The public `legal-ops-agent` repository is archived and points here. It remains readable as a dated snapshot and receives no fixes. `make agent-export` prepares a local path-export branch and does not push it.
