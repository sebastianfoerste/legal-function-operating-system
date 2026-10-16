# Security Policy

## Scope

This policy covers the whole repository:

- the `legal-function-os` package in `src/legal_function_os` and its console scripts;
- the scripts in `scripts/` and the GitHub Actions workflows in `.github/workflows`;
- the published GitHub Pages site built by `scripts/build_site.py`;
- the supervised agent in `supervised-agent/`, which also has its own [security policy](supervised-agent/SECURITY.md);
- the supply chain: GitHub Actions and the agent's locked dependencies.

Disagreeing with a rule threshold, a routing decision or a legal citation is not a security issue. Please use the rule change issue template.

## Reporting a vulnerability

Report suspected vulnerabilities privately through the maintainer's GitHub profile contact details. Do not open a public issue.

1. Describe the issue, its impact and the steps to reproduce it.
2. Name the affected paths, commands or versions (`legal-function-os --version`) and include any proof-of-concept details.
3. Allow reasonable time for triage and remediation before public disclosure.

Only the `main` branch and the latest release are supported.

## Local execution and data boundary

The package runs locally and offline. The rules make no network or model calls, and the command-line tools write only to the paths you pass them.

Run it with synthetic or approved public data only. The bundled requests, events, agreements and deal under `src/legal_function_os/data/` are synthetic and safe for public evaluation.

Do not process client documents, privileged advice, personal data, confidential commercial material or production matter files through this repository, its issue tracker or its pull requests.

Generated board packs, reviews and registers are draft management artifacts. They are not legal advice, legal opinions, signatures or external communications, and every consequential decision requires human review.
