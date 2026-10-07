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

## Document And Pilot Checks

```bash
python -m pytest -q tests/test_matter_documents.py tests/test_pilot_session.py tests/test_pilot_record.py
```

Three of these tests compare the Northwind intakes and the session format with a
`contract-review-eval-harness` checkout. They are skipped unless
`CONTRACT_EVAL_HARNESS_ROOT` names one, so they do not run in CI.

## Runtime Check

```bash
python -m pytest -q tests/test_runtime_agent.py
```

## Quality Expectations

1. Export remains blocked until a documented human review decision permits it and blocker findings are resolved.
2. Source-boundary behavior remains deterministic and local.
3. Generated packets stay review drafts.
4. Tests use synthetic fixtures only.
