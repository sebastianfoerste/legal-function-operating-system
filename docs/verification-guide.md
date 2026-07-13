# Verification guide

This repository implements a supervised legal-operations workflow. It does not provide legal advice.

## Fast verification path

1. Read the 90-second verification path in `README.md`.
2. Open `examples/matters/saas_msa_deviation.json`, `examples/matters/dpa_subprocessors_review.json`, and `examples/matters/ai_vendor_model_training_review.json`.
3. Run one fixture through `python -m src.cli --input <fixture>`.
4. Confirm that the first assessment is blocked for export.
5. Apply an approval note with `--approve-note` and inspect the review packet.
6. Run `make check`.

## Files to inspect

- `models.py`: typed Pydantic contracts for every workflow handoff.
- `src/legal_ops.py`: deterministic risk findings, reviewer routing, and the export gate.
- `src/source_verification.py`: source-prefix and public-regulatory boundary checks.
- `src/mcp_tools.py`: local MCP-style tools with schema-bound inputs.
- `tests/`: export-gate, source-boundary, runtime, and packet tests.

## Verification standard

The relevant behavior is control discipline. The system accepts synthetic matter facts, turns them into structured risk decisions, routes review, records a human decision, and blocks export until the approval conditions are satisfied.

All examples are synthetic and public-safe. Do not use client, privileged, confidential, or personal data when running this repository.
