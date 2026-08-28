# Agent Guide: LegalOps Agent

## Local Rules

1. Use synthetic or explicitly approved public data only.
2. Keep client, candidate, privileged and confidential source prefixes blocked.
3. Do not add external delivery, publication, filing or outreach actions.
4. Keep every consequential output behind human review.
5. Preserve the local MCP-style tool boundary.
6. Add tests for source verification, review gates, manifests or runtime behavior when touching those areas.

## Validation

Run the focused check first, then the full gate when scope permits:

```bash
python -m pytest -q tests/test_mcp_tools.py tests/test_source_verification.py
make check
```
