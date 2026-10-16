# Shared workflow control contract

`legal-workflow-controls.v1` is the stable interoperability boundary between the legal function operating system and the supervised agent.

## Local state mappings

| Component | Local value | Shared value |
| --- | --- | --- |
| Legal function OS | `review_required` | `pending_review` |
| Legal function OS | `blocked` | `blocked` |
| Supervised agent | `needs_review` | `pending_review` |
| Supervised agent | `approved`, `rejected`, `revision_requested`, `escalated` | Same value |
| Supervised-agent pilot | `intake`, `triage`, `assignment`, `review`, `revised` | `pending_review` |
| Supervised-agent pilot | `revision_requested` | `revision_requested` |
| Supervised-agent pilot | `approved`, `ready_for_delivery`, `closed` | `approved` |
| Supervised-agent pilot | any state while a charter exclusion or blocked source holds the matter | `blocked` |

The contract keeps external actions disabled. Export can become allowed only after an approved human decision, a documented review note and any component-specific integrity checks. Source references remain synthetic or explicitly approved public sources. Audit events may use the supervised agent's hash chain, while the base legal function workflow can emit unhashed events until it adopts the same integrity mechanism.

The contract does not create legal conclusions and does not authorize publication, filing, delivery or outreach.

The pilot workflow in `supervised-agent/src/pilot` consumes this repository's own contracts instead of defining new ones. It takes queue, service levels and the approval tier from `legal_function_os.rules.decide`, exports its events in `legal-function-os.service-event-ledger.v1` for the outcome control tower, and exports each matter in this shared contract.

## Request input contract

[`legal-request.v1.schema.json`](legal-request.v1.schema.json) is the JSON Schema for one
legal request as the CLI reads it. It is generated from the same constants the
validator and the rules use (`python scripts/build_contracts.py`), and a test fails if
the committed file drifts. The human-readable version is
[`docs/INPUT_FORMAT.md`](../docs/INPUT_FORMAT.md).

## Policy contract

[`legal-function-policy.v1.schema.json`](legal-function-policy.v1.schema.json) is the
JSON Schema for a policy file: the value bands, queues, service levels and thresholds
the rules apply. It is generated from the policy checks in
`src/legal_function_os/policy.py` by the same script, and a test fails if the
committed file drifts. The checks a schema cannot express, such as a threshold
naming one of the file's own value bands, are described in
[`docs/CUSTOMIZE.md`](../docs/CUSTOMIZE.md).
