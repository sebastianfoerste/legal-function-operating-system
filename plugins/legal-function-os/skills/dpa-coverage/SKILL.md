---
name: dpa-coverage
description: Check which Art. 28(3) GDPR clauses a data processing agreement covers against the bundled playbook.
---

Put each agreement into the input shape (id, title, and clause texts keyed by playbook key: `documented_instructions`, `confidentiality_commitment`, `security_measures`, `subprocessor_authorization`, `data_subject_rights_assistance`, `breach_and_dpia_assistance`, `deletion_return`, `audit_rights`, `unlawful_instruction_notice`), call `dpa_review`, and list per document the rows that are `missing` (blockers) or `review`, with their `missing_elements` and `negated_elements`.

Rules for every answer:
- Call the `legal-function-os` MCP tool `dpa_review`. Do not judge coverage yourself.
- You map clauses to playbook keys before the tool runs, and the result depends on that mapping. Say so, show which clause text you put under each key, and ask the reader to check the mapping; a clause under the wrong key is reported as missing.
- If the tool rejects the input, show the problems and ask for corrected clause keys or texts.
- Report each row's `status`, `citation` and `missing_elements` as the tool returns them. The tool reads words, not meaning: it states coverage of the statutory wording, not that an agreement is lawful. The output supports a lawyer's decision; it is not legal advice.
