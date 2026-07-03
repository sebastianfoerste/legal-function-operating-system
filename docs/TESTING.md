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

## Quality Expectations

1. Export remains blocked until a documented human review decision permits it and blocker findings are resolved.
2. Source-boundary behavior remains deterministic and local.
3. Generated packets stay review drafts.
4. Tests use synthetic fixtures only.
