---
name: dpa-coverage
description: Check which DPA clauses a data processing agreement covers against the bundled playbook.
---

Put each agreement into the input shape (id plus clause texts keyed by playbook key), call `dpa_review`, and list the missing or thin clauses per document.

Rules for every answer:
- Call the `legal-function-os` MCP tool named below. Do not work out risk, routing, SLAs or approvers yourself.
- If the tool rejects the input, show the problems and ask for corrected fields. Never guess a value band or request type.
- Report the tool's rationale lines verbatim. The output supports a lawyer's decision; it is not legal advice.
