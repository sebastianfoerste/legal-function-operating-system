# Setup: LegalOps Agent

## Prerequisites

1. Python 3.13 or newer.
2. `uv` for lockfile maintenance, or `pip` for the locked requirements path.

## Environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
make install
```

## CLI Demo

Run a synthetic matter assessment:

```bash
python -m src.cli --input examples/matters/saas_msa_deviation.json
```

Write reviewer artifacts:

```bash
python -m src.cli \
  --input examples/matters/enterprise_dpa.json \
  --json-output demo_output/assessment.json \
  --packet-output demo_output/review-packet.md \
  --commitments-output demo_output/customer-commitments.json \
  --sources-output demo_output/source-verification.json \
  --manifest-output demo_output/artifact-manifest.json
```

## Runtime Canary

```bash
PORT=18085 python -m runtime_agent.app
```

Then inspect:

```bash
curl -fsS http://127.0.0.1:18085/health
curl -fsS http://127.0.0.1:18085/mcp/manifest
```

## Data Boundary

Use synthetic or approved public data only. Source references beginning with `client:`, `candidate:`, `privileged:` or `confidential:` are blocker inputs.
