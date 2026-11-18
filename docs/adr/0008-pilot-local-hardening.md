# 0008. Pilot server local hardening, not authentication

- Status: Accepted
- Date: 2026-11-18
- Answers owner decision 1 in `docs/research/adaptation-plan.md` (authentication and the
  11 controls in
  [`IDENTITY_CONTROLS.md`](../../supervised-agent/docs/pilot/IDENTITY_CONTROLS.md)).

## Context

The supervised agent's pilot lets a caller choose a simulated local role: a drop-down in
the review room, the `X-Pilot-Actor` header over HTTP. Selecting an actor is not
authentication. `IDENTITY_CONTROLS.md` lists 11 controls that must exist before
practitioners rely on the pilot, and none is built. Items 1 to 6 (sign-in against the
organisation's identity provider, server-side sessions, administered provisioning,
person-level separation of duties, step-up confirmation for approvals, ethical walls) are
the precondition for practitioner work product. Presence (F4, ADR 0005) makes the gap more
visible, because it shows who has a matter open under a chosen role.

The core package has no network server; its MCP server runs over stdio (ADR 0007). The
only HTTP server is the agent runtime, `supervised-agent/runtime_agent/app.py`, a standard
library `ThreadingHTTPServer` that `pilot serve` starts. Before this decision it already
answered only its own `Host` names (against DNS rebinding), accepted only JSON POSTs of at
most 1 MiB, and sent no `Access-Control-*` header. Observed while deciding:

- The listening address was not enforced. `HOST` was read unchecked, so `HOST=0.0.0.0`
  would listen on every interface. Only the docs said to stay on `127.0.0.1`.
- `Origin` was never checked. A POST carrying `Origin: http://evil.example` was accepted
  (201); protection against cross-site requests rested on the browser's preflight alone.
- Responses carried no framing policy. In Chromium, a page on another origin framed the
  live review room, which loaded and fetched actors and matters.
- The three refusals of a final approval (tier too low, approver is also requester or
  matter owner, approver decided a change) were enforced in `_ev_approver_authorised` but
  no test reached them.
- The access log of `BaseHTTPRequestHandler` printed every request line to standard
  error, including each presence check-in with its matter ID and time, although presence
  is never logged (owner decision 7, ADR 0005).

Sign-in through OIDC or SAML needs the organisation's identity provider, network access
and real credentials, and probably a new dependency. None of these exists in this
repository, so it cannot be built or tested here.

## Decision

1. Authentication is not built here. Controls 1 to 11 stay preconditions for practitioner
   use. The review room, the actor listing and the delivery manifests keep saying that
   roles are simulated local roles and not authentication.
2. The pilot server gets local hardening, which is not authentication:
   - `build_server` resolves `HOST` and refuses to start unless every address is loopback,
     then checks the bound address again before it listens. There is no switch to listen
     elsewhere; that is control 7 (TLS behind the organisation's access proxy).
   - It answers only its own `Host` names, as before.
   - A request with an `Origin` header is refused (403 `origin_not_allowed`) unless the
     origin is `http://` with the host and port of the `Host` header. A request without
     one (scripts, `curl`, same-origin page loads) is served.
   - Every response sends `X-Frame-Options: DENY` and
     `Content-Security-Policy: frame-ancestors 'none'; base-uri 'none'; object-src 'none'`,
     with `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and
     `Cross-Origin-Resource-Policy: same-origin`. The policy does not restrict scripts or
     styles, which the review room sets inline. No `Access-Control-*` header is sent and
     no `OPTIONS` handler exists.
   - The request log leaves out a presence check-in that reaches the review-room API; other
     requests, including one to a presence path that is refused before it gets there, are
     logged as before.
3. Tests prove that a final approval is refused when the approver holds too low a tier, is
   also the requester or matter owner, or decided a change, and that no HTTP route
   registers an actor or changes a role or tier. These rules compare actor IDs, not
   people. No command can make the matter owner the final approver, so the owner case is
   defence in depth: its test reaches it only by writing the assignment directly into the
   store.

## Consequences

- `HOST=0.0.0.0`, or any address that is not loopback, now stops the server with a message
  that names control 7. No tracked file sets `HOST`.
- A page on another origin can no longer frame the review room, and a browser request that
  carries a foreign `Origin` (every cross-origin POST and every CORS-mode fetch) is refused
  on the server, not only by the browser's preflight. A cross-origin GET that sends no
  `Origin` (a navigation, an image or script load) is still answered, but the other origin
  can neither read nor embed the response (same-origin policy,
  `Cross-Origin-Resource-Policy`, no framing), and a data route also needs `X-Pilot-Actor`,
  a custom header that only an answered preflight could allow. The room's own package view
  still works: the room fetches the package and shows it in a sandboxed `srcdoc` frame, so
  no server response is framed (checked in Chromium).
- A TLS-terminating proxy that sends an `https://` origin would be refused. That
  deployment is control 7 and unsupported today; revisit the rule with control 7.
- `ALLOWED_HOSTS` can still name a host that resolves elsewhere and reopen DNS rebinding;
  `SETUP.md` says to name only hosts that resolve to this machine.
- Anyone who can use the machine can still act as any role, and any process running as the
  same user can still write the SQLite store (control 10). The requester and change-decider
  refusals are tested through `register_actor`, which replaces an actor without writing an
  event: a control 3 gap that these tests show but do not close. The matter-owner refusal
  is tested through such a direct write to the store.
- The `approver_authorised` requirement text now names all three rules, as the check
  already enforced, in `state_machine.py` and `RUNBOOK.md`.
- Tests, all under `supervised-agent/tests/`: `test_runtime_agent.py` (listening address,
  `Origin`, headers on every response, request log), `test_review_room_browser.py` (the
  package frame still renders; another page cannot frame the room),
  `test_pilot_workflow.py` and `test_pilot_api.py` (approval refusals; no actor route).

## Alternatives rejected

- **Sign-in through OIDC or SAML, with server-side sessions and step-up, built now.** It
  would start to close controls 1, 2 and 5, but it cannot be built or tested without the
  organisation's identity provider and network access, it probably needs a new
  dependency, and it would move the server off loopback.
- **A per-start local secret, printed at start and sent as a header.** It would stop other
  users of a shared machine from driving the API, but it does not address who is at the
  keyboard: anyone at the machine could still read it and choose any role. It would also
  look like a sign-in, which works against "Selecting an actor is not authentication".
- **Record the decision and build nothing.** It would leave the listening address, framing
  and `Origin` gaps open, and the approval refusals untested, although closing them is
  cheap, local and testable.
