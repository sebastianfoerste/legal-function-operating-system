# Contributing

A personal, public-safe prototype. Issues and corrections welcome — especially on the rule thresholds (value bands, SLA targets, approval tiers), which are illustrative defaults.

## Ground rules

1. **Synthetic data only.** Never add real requests, client data, or personal data.
2. **Deterministic.** Same input, same output. No network or model calls in the rules or board pack.
3. **Legible rules.** Each rule stays a short, readable function with an explained decision.
4. **Human in the loop.** Every approval chain must end with a human tier.
5. **Not legal advice.** Keep the framing as an operations/triage artifact.

## Working on it

```bash
make install   # standard library only
make test      # must pass before any PR
make demo      # regenerate examples/board-pack.* if rule output changed, and commit it
```

## Adding or changing a rule

1. Edit the relevant function in `src/legal_function_os/rules.py` (or aggregation in `board_pack.py`).
2. Add a test in `tests/test_rules.py` covering the new behaviour.
3. Run `make test` and `make demo`; commit the regenerated `examples/`.
