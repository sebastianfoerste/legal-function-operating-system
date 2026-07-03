# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities privately and do not open public issues.

1. Email the maintainer with a clear description, impact, and reproduction steps.
2. Include affected versions/paths and any proof-of-concept details.
3. Allow reasonable time for triage and remediation before public disclosure.

## Scope

This policy covers application code, CI/CD workflows, and dependency supply chain risks
present in this repository.

## Local execution and data boundary

Run this project locally with synthetic or approved public data only. The sample
matters under `examples/` are synthetic and safe for public evaluation.

Do not process client documents, privileged advice, candidate data, confidential
commercial material, personal data or production matter files through this
repository. Source references that begin with `client:`, `candidate:`,
`privileged:` or `confidential:` are deliberately treated as blockers.

External model processing is disabled by default. Do not add API keys or route
matter facts to external systems unless a separate, explicit review decision has
approved that use for non-sensitive data.

Generated packets, manifests and registers are draft reviewer artifacts. They
are not legal advice, legal opinions, signatures or external communications.
