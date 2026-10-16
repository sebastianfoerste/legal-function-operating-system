## What and why

<!-- What does this change, and why? Link the issue if there is one. -->

## Checklist

- [ ] Synthetic data only: no real requests, client matters, contracts or personal data in code, fixtures, tests, examples or this description.
- [ ] `make check` passes (tests, regenerated artifacts, manifest, contracts, site links and the agent gate).
- [ ] `make demo` was run and the regenerated `examples/` are committed.
- [ ] A rule change comes with a test and an updated `docs/INPUT_FORMAT.md`; a changed request field also needs `make contracts`.
- [ ] Every approval chain still ends with a human tier, and nothing calls a network service or a model from the rules.
- [ ] Public claims changed (README, case studies, legal citations or DPA wording)? Then this needs the maintainer's legal review before merge.
