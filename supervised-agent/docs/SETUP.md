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

The runtime answers only requests whose `Host` header names `127.0.0.1`, `localhost` or
`[::1]` (with the bound port or none); `ALLOWED_HOSTS=name1,name2` replaces that list.
POST bodies must be `application/json` and at most 1 MiB.

Then inspect:

```bash
curl -fsS http://127.0.0.1:18085/health
curl -fsS http://127.0.0.1:18085/mcp/manifest
```

## Data Boundary

Use synthetic or approved public data only. Source references beginning with `client:`, `candidate:`, `privileged:` or `confidential:` are blocker inputs.
