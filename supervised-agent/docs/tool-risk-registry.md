# Tool Risk Registry

This registry records the local MCP-style tools exposed by `src/mcp_tools.py` and the control expectation for each tool.

## `legal.matter.assess`

Purpose: validate a typed matter intake and return deterministic findings, controls, source verification records, reviewer routing and audit events.

Risk: legal output may look authoritative if removed from its review context.

Controls:

1. Pydantic input validation.
2. Synthetic or approved public data boundary.
3. Export state starts as `needs_review`.
4. Source verification records are attached to the assessment.

## `legal.review.decide`

Purpose: apply a documented human review decision to an assessment.

Risk: an approval could be recorded without meaningful review rationale.

Controls:

1. Review decision schema.
2. Approval, rejection, revision and escalation require a note.
3. Blocker findings continue to prevent export after approval.

## `legal.review.packet`

Purpose: render a Markdown packet for reviewer sign-off.

Risk: a draft packet could be mistaken for final legal advice.

Controls:

1. Packet includes review state and controls.
2. Packet generation writes an audit event.
3. Packet wording remains reviewer-facing.

## `legal.sources.list`

Purpose: show the permitted source and data boundary for the public demo.

Risk: users may assume arbitrary material is acceptable.

Controls:

1. Allowed and blocked categories are explicit.
2. External processing is disabled by default.

## `legal.sources.verify`

Purpose: classify source references without external fetching.

Risk: source status may be confused with legal verification of the source content.

Controls:

1. `synthetic:` references pass for demo use.
2. `public:` references are checked against a regulatory-domain allowlist.
3. `client:`, `candidate:`, `privileged:` and `confidential:` references become blockers.
4. Public references still require human review before reliance.

## Validation

```bash
python -m pytest -q tests/test_mcp_tools.py tests/test_source_verification.py
```
