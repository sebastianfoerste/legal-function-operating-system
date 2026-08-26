# Source-Verified SaaS MSA Run, 2026-06-30

This is a dated proof snapshot for the canonical evaluator path. It uses the
synthetic SaaS MSA deviation fixture and records the source-verified packet runner
output committed in [`source-verified-saas-msa-run-2026-06-30.json`](source-verified-saas-msa-run-2026-06-30.json).

## Metadata

| Field | Value |
|---|---|
| Fixture | `examples/matters/saas_msa_deviation.json` |
| Command | `python -m src.cli --input examples/matters/saas_msa_deviation.json --json-output ... --packet-output ... --sources-output ... --review-runner-output ... --manifest-output ...` |
| Python | `3.13.14` |
| Runner schema | `legal-ops-agent.source-verified-review-packet-run.v1` |
| Assessment ID | `loa_0b5d728ed132582a` |
| Generated at | `2026-06-30T10:54:07Z` |
| Review state | `needs_review` |
| Runner status | `review_required` |
| Export allowed | `false` |
| External actions allowed | `false` |
| Delivery mode | `local_review_only` |
| Source boundary | `verified_demo_or_public_regulatory_sources` |
| Test gate | `python -m pytest -q tests/test_mcp_tools.py tests/test_source_verification.py` passed with 12 tests; `make check` passed with 35 tests |

## Reviewer Signal

The runner proves the public-safe workflow boundary:

- The matter is synthetic and uses `synthetic:saas-msa-deviation-example`.
- Source verification has 1 pass, 0 warnings and 0 blockers.
- The matter routes to Privacy Counsel, Commercial Counsel and General Counsel.
- Export stays blocked because no documented human approval has been recorded.
- The policy envelope blocks `external_delivery`, `publication`, `filing` and `outreach`.
- Generated review artifacts are locally manifestable with SHA-256 digests.

## Captured Result

| Dimension | Value |
|---|---:|
| Highest severity | `high` |
| Findings | 2 |
| Blocker findings | 0 |
| Source passes | 1 |
| Source warnings | 0 |
| Source blockers | 0 |
| Export allowed | `false` |
| Human review required | `true` |

The snapshot is generated from synthetic data only. It is a reviewer evidence
artifact for the control model, not legal advice or a benchmark.
