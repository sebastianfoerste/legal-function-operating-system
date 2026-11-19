# Contributing

This is a personal, public-safe prototype. Issues and corrections are welcome.

## Ground rules

1. **Synthetic data only.** Never add real client data, privileged material, negotiation history, or personal data.
2. **Deterministic by default.** Same input, same output. No network or model calls in the core checks/evaluation.
3. **Cited / grounded findings.** Every regulatory finding carries a specific, verifiable citation.
4. **Not legal advice.** Keep the framing as a review / evaluation artifact.

## Working on it

```bash
make install
make test     # must pass before any PR
make check    # the full gate: Ruff, Black, mypy, the tests and a compile check
python -m src.pilot.cli scenario-docs   # after changing a scenario in examples/pilot/scenarios/
python -m src.pilot.evidence.example    # after changing src/pilot/evidence/; rewrites examples/pilot/synthetic-worked-example/
```

`scenario-docs` regenerates the facilitator scripts in `docs/pilot/scenarios/` and the
synthetic DOCX fixtures in `examples/pilot/documents/` from the scenario files; commit what
it changes. There is no `make demo` here: `python -m src.pilot.evidence.example` rewrites
the synthetic worked example, which a test checks is current; the other runs under
`examples/` are committed snapshots.

## Reporting an issue

Be specific: the rule or step, what you expected, and — for regulatory checks — the corrected citation. Citation fixes are the most valuable contribution.
