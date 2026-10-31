---
name: approval-tier
description: Answer who must approve a matter, from the tested approval matrix.
---

Build the request, call `triage_requests`, and answer with `approval_chain` (the last entry is the binding approver) plus any `external_counsel` referral.

Rules for every answer:
- Call the `legal-function-os` MCP tool `triage_requests`. Do not work out risk, routing, SLAs or approvers yourself.
- If the tool rejects the input, show the problems and ask for corrected fields. Never guess a value band or request type.
- Report the tool's rationale lines verbatim. The output supports a lawyer's decision; it is not legal advice.
