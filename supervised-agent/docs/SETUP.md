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

The runtime listens only on a loopback address: `HOST` is `127.0.0.1` by default and may
be `localhost`, and any address that is not loopback (`0.0.0.0`, a network address) stops it
before it listens. It answers only requests whose `Host` header names `127.0.0.1`,
`localhost` or `[::1]` (with the bound port or none); `ALLOWED_HOSTS=name1,name2` replaces
that list and should name only hosts that resolve to this machine. A browser request whose
`Origin` is not the server's own (`http://` with the host and port of the `Host` header) is
refused with 403 `origin_not_allowed`; requests without an `Origin`, such as `curl`, are
served. POST bodies must be `application/json` and at most 1 MiB. No page may frame the
runtime: every response sends `X-Frame-Options: DENY` and
`Content-Security-Policy: frame-ancestors 'none'`, with `nosniff`, `no-referrer` and a
same-origin resource policy. This is local hardening, not authentication: anyone at this
machine can still act as any role ([IDENTITY_CONTROLS.md](pilot/IDENTITY_CONTROLS.md)).

Then inspect:

```bash
curl -fsS http://127.0.0.1:18085/health
curl -fsS http://127.0.0.1:18085/mcp/manifest
```

## Data Boundary

Use synthetic or approved public data only. Source references beginning with `client:`, `candidate:`, `privileged:` or `confidential:` are blocker inputs.
