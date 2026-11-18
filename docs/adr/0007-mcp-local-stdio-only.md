# 0007. MCP server stays a local stdio process

- Status: Accepted
- Date: 2026-11-18
- Answers owner decision 6 in `docs/research/adaptation-plan.md` (remote MCP and HTTP
  transport), and with it step 4 of the 2.x path in [ADR 0002](0002-mcp-2x-path.md),
  which left the question to that decision.

## Context

`legal-function-os-mcp` is started by the MCP client as a child process and talks to it
over stdio. `main()` calls `FastMCP.run()` with no transport, so the SDK's default,
`"stdio"`, applies. Its only option is `--policy PATH`. The plugin's `.mcp.json` starts
it with `uvx` as a local command.

The 1.x SDK could serve the same tools over a network. Observed in `mcp` 1.30.0:

- `FastMCP.run()` also takes `"sse"` and `"streamable-http"`. Those transports listen on
  `127.0.0.1:8000` by default and turn on DNS-rebinding protection for loopback hosts.
  They need no new dependency: the `mcp` extra already installs Starlette and Uvicorn.
  What they add is a network listener.
- A user of the shipped entry point cannot reach them. No option or environment
  variable selects a transport, and `FASTMCP_HOST` and `FASTMCP_PORT` do not change the
  server's settings, because the server is built with explicit ones.
  `mcp run FILE --transport ...` only starts a server stored at module level as `mcp`,
  `server` or `app`, and `mcp_server.py` builds its server inside a function.

claude-for-legal's `commercial-legal/.mcp.json` connects remote HTTP MCP servers for
Ironclad, DocuSign, iManage, TopCounsel, Definely, Slack and Google Drive (Observed; see
the [landscape](../research/2026-10-competitive-landscape.md)). Hosted MCP clients that
accept only a server URL cannot start a local process (Inferred).

A network transport, or remote connectors, would bring:

- A listener that other processes can reach, so the server would have to know who is
  calling. It has no way to: selecting an actor is not authentication, and
  authentication is owner decision 1, which is not built.
- Requests, agreements and policies sent over a network instead of a pipe.
- Signing, posting and access to document stores (DocuSign, Slack, iManage). These are
  external delivery, publication, filing or outreach actions, which this repository does
  not add, and they would reach client and privileged material, which it does not
  process.

## Decision

1. The server runs only over stdio, as a process the MCP client starts. It offers no
   HTTP or SSE transport and no transport, host or port option. `mcp_server.py` keeps no
   module-level server object that `mcp run` could start with another transport.
2. The plugin's `.mcp.json` starts only this local server, as a command. It has no `url`,
   no transport `type` other than stdio and no remote connector, and neither the plugin
   manifest nor the marketplace declares MCP servers of its own.
3. The server does not authenticate callers. Nothing reaches it over a network: the
   client that starts it owns the pipe, and the server runs as that local user. The tools
   stay read-only and take data, never file paths.
4. Reopening this needs a new ADR that settles authentication (owner decision 1) first.

## Consequences

- Clients run the server as a local subprocess. A hosted client that only accepts a
  remote MCP URL cannot use it (Inferred). A user who wraps it in their own network
  server does so outside this repository's guarantees.
- Tests in `tests/test_mcp_server.py` hold the decision: `main()` calls `run()` with no
  transport and the module has no `mcp`, `server` or `app` object; `--transport`,
  `--host` and `--port` are refused; the SDK's default transport is `"stdio"`; every
  server in a plugin's `.mcp.json` is a local command that starts
  `legal-function-os-mcp`, with no `url` and no other transport type; and no plugin or
  marketplace entry declares servers inline.
- The default-transport test reads `FastMCP.run` from the 1.x SDK on purpose. The 2.x
  migration in ADR 0002 must check `MCPServer.run` the same way, or the CI `mcp` job
  fails.
- `SECURITY.md` ("The package runs locally and offline") and `docs/CLI.md` ("A local
  stdio MCP server") stay true for the MCP server.

## Alternatives rejected

- **An opt-in loopback HTTP transport** (`--transport streamable-http` on 127.0.0.1).
  No new dependency, and the SDK protects loopback hosts against DNS rebinding. But it
  opens a port that any local process can reach, with nothing to tell callers apart, and
  gives local MCP clients nothing that stdio does not.
- **A remote server with authentication, and remote connectors in `.mcp.json`** (the
  claude-for-legal pattern). It would be usable from hosted clients and reach systems of
  record, but it needs identity work the repository does not have (owner decision 1),
  sends request data over a network, and adds signing, posting and filing.
