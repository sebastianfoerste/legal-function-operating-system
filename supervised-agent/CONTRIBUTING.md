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
make demo     # regenerate examples/ if output changed, and commit it
```

## Reporting an issue

Be specific: the rule or step, what you expected, and — for regulatory checks — the corrected citation. Citation fixes are the most valuable contribution.
