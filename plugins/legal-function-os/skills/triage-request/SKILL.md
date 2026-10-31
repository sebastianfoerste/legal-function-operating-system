---
name: triage-request
description: Triage one or more in-house legal requests (risk, priority, queue, SLA, escalations) with the deterministic rules.
---

Collect each request as JSON matching `legal_request_schema`, then call `triage_requests`. Present one line per request: id, risk, priority, queue, SLA, then escalations.

Rules for every answer:
- Call the `legal-function-os` MCP tool `triage_requests`. Do not work out risk, routing, SLAs or approvers yourself.
- If the tool rejects the input, show the problems and ask for corrected fields. Never guess a value band or request type.
- Report the tool's rationale lines verbatim. The output supports a lawyer's decision; it is not legal advice.
