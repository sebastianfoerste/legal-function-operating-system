# Testing: LegalOps Agent

## Full Gate

```bash
make check
```

This runs Ruff, Black, MyPy, Pytest and compile checks through the repo Makefile.

## Focused MCP And Source Checks

```bash
python -m pytest -q tests/test_mcp_tools.py tests/test_source_verification.py
```

## CLI Artifact Check

```bash
python -m pytest -q tests/test_cli.py tests/test_review_packet.py
```

## Runtime Check

```bash
python -m pytest -q tests/test_runtime_agent.py
```

## Pilot Workflow Checks

```bash
python -m pytest -q tests/test_export_gate.py tests/test_docx_redline.py
python -m pytest -q tests/test_pilot_workflow.py tests/test_pilot_api.py tests/test_pilot_rehearsal.py
python -m src.pilot.cli rehearse --db /tmp/pilot-rehearsal/pilot.sqlite3 --out /tmp/pilot-rehearsal/out
```

These cover persistence and restart recovery, unauthorised decisions, stale approvals,
cross-matter access, source and playbook changes, direct export bypasses, conflicting
edits, unresolved blockers and document integrity. `test_runtime_server_serves_the_review_room`
needs permission to bind a local port and is skipped where that is refused.

## Quality Expectations

1. Export remains blocked until a documented human review decision permits it and blocker findings are resolved.
2. Source-boundary behavior remains deterministic and local.
3. Generated packets stay review drafts.
4. Tests use synthetic fixtures only.
5. Every reviewed document and delivery package passes `src/export_gate.py`; no other code decides an export.
6. An approval covers one matter version and one reviewed state.
