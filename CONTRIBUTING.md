# Contributing

A personal, public-safe prototype. Issues and corrections are welcome, especially on
the rule thresholds (value bands, SLA targets, approval tiers), which are illustrative
defaults.

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md). Report
security issues privately, as described in [SECURITY.md](SECURITY.md). The issue
forms cover bugs, rule changes and new request types.

## Ground rules

1. **Synthetic data only.** Never add real requests, client data, or personal data.
2. **Deterministic.** Same input, same output. No network or model calls in the rules or board pack.
3. **Legible rules.** Each rule stays a short, readable function with an explained decision.
4. **Human in the loop.** Every approval chain must end with a human tier.
5. **Not legal advice.** Keep the framing as an operations/triage artifact.

## Working on it

```bash
make install         # standard library only
make test            # must pass before any PR
make demo            # regenerate the committed artifacts in examples/
make lint            # Ruff and mypy on the core; needs the pinned tools (below)
make package-check   # build the wheel, install it in a clean environment and run it
make check           # the full gate: tests, regenerated artifacts, manifest, contracts,
                     # site links, the supervised agent's gate, and patch hygiene
```

`make install`, `make test` and `make demo` need nothing beyond Python. `make lint` and
`make check` need pinned third-party tools, which `make install-dev` installs into the
current environment (use a virtual environment):

```bash
python3 -m venv .venv && . .venv/bin/activate
make install-dev     # requirements-dev.txt (ruff, mypy) and, for make agent-check,
                     # supervised-agent/requirements.txt and supervised-agent/requirements-dev.txt
make check
```

`make agent-check` (part of `make check`) runs `make -C supervised-agent check`, which
needs Python 3.13 or later and the agent's runtime and dev dependencies. CI runs all of
these: the core tests on Python 3.10 to 3.15, the `mcp` extra, lint, the wheel and the
agent gate. Record user-facing changes under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).

## Adding or changing a rule

1. Edit the relevant function in `src/legal_function_os/rules.py` (or aggregation in `board_pack.py`).
2. Add a test in `tests/test_rules.py` covering the new behaviour.
3. Run `make test` and `make demo`; commit the regenerated `examples/`.

For the industrial robotics deal desk, keep the public facade stable in
`src/legal_function_os/raas_deal_desk.py`. Add domain logic to the relevant RaaS
module, add coverage in `tests/test_raas_deal_desk.py`, and keep every external
action blocked until a named human approval is recorded.
