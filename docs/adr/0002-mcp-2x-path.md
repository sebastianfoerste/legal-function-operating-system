# 0002. Keep `mcp>=1.9,<2` for now; the path to 2.x

- Status: Accepted
- Date: 2026-10-20

## Context

The optional MCP server (`legal-function-os-mcp`) is built on the 1.x Python SDK with
`mcp.server.fastmcp.FastMCP` and four read-only tools. `pyproject.toml` pins
`mcp>=1.9,<2` and Dependabot ignores major updates.

State of the SDK on 2026-10-20, Observed on PyPI (<https://pypi.org/pypi/mcp/json>)
and in the SDK's migration guide
(<https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md>):

- 2.0.0 was released on 2026-07-28; 2.3.0 (2026-10-02) is current.
- The 1.x line is still released in parallel; 1.30.0 came out on 2026-09-07.
- 2.x renames `FastMCP` to `MCPServer` (`mcp.server.mcpserver`), so the current import
  fails with `ModuleNotFoundError`. A global 2.x install already breaks
  `tests.test_mcp_server` outside the project's virtual environment.
- Tool decorators and structured-output rules are unchanged. Raising `MCPError` now
  becomes a JSON-RPC error rather than an `isError` result, and execution failures the
  model should see are meant to raise `ToolError`. Python field names become
  snake_case. Protocol 2026-07-28 drops the initialize handshake and sessions.

## Decision

Keep the pin. The 1.x line is maintained and still released, and this server needs
nothing from 2.x: it is a local stdio server with four read-only tools.

The path to 2.x, to be taken as one change when the 1.x line stops getting releases or
a client requires protocol 2026-07-28:

1. Import `MCPServer` from `mcp.server.mcpserver`; keep the read-only annotations.
2. Make `InputRejected` surface as a tool error the model can read, either by raising
   `ToolError` or by returning `CallToolResult(is_error=True)`, and add a test that a
   rejected input is not reported as a protocol failure.
3. Widen the extra to `mcp>=2.3,<3`, drop the Dependabot ignore, and run the CI `mcp`
   job on the lowest and highest supported versions.
4. Keep the server local over stdio. Remote HTTP transport and authentication are out
   of scope (owner decision; see `docs/research/adaptation-plan.md`).

## Consequences

- No behaviour changes now. Users with a global 2.x install keep getting a clear
  import error from the extra's pin instead of a broken server.
- The migration is small and mapped. Its main risk is the error shape, which step 2
  tests.
