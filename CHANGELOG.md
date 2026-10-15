# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A published request format: [`contracts/legal-request.v1.schema.json`](contracts/legal-request.v1.schema.json) and [`docs/INPUT_FORMAT.md`](docs/INPUT_FORMAT.md).
- `--version` on `legal-function-os`.
- CI runs the core on Python 3.10 to 3.13, lints it with Ruff and mypy, and checks that the built wheel installs and runs (`make lint`, `make package-check`).
- An offline link check for the Pages site and the Markdown docs (`make site-check`).
- A code of conduct, a root security policy, issue and pull request templates, CODEOWNERS, Dependabot, this changelog and `CITATION.cff`.
- A verification manifest in place of the portfolio proof (#11).
- The supervised agent's pilot workflow and reviewer evidence track (#13).

### Changed

- Input is checked before any decision. An unknown `value_band` or `urgency`, a quoted boolean, a duplicate id or a misspelled field name stops the run with exit status 2 and one line per problem. An unknown `type` still goes to the General queue, with a warning and a "needs manual triage" line in the rationale.
- `pyproject.toml` carries classifiers, project URLs and keywords, and reads the version from the package.
- The README was rewritten (#16) and the case study refreshed (#12).

### Fixed

- A mistyped value band such as `">1M"` was read as "no value", which turned a board-attention matter into a low-risk, reviewer-only one. It is now rejected with a suggestion.
- The README's DPA command printed no DPA rows; it now names the output file.
- The Pages site's "DPA clause review" card linked to a missing file.
- The CLI docstring promised a non-zero exit for board-attention items.
- `legal_function_os.__version__` said 0.2.0 in the 0.3.0 release.

## [0.3.0] - 2026-08-28

### Added

- The synthetic data ships inside the package, so the demo runs without cloning: `uvx --from git+https://github.com/sebastianfoerste/legal-function-operating-system legal-function-os` (#10).
- The reviewer artifacts are published to GitHub Pages.
- A weekly snapshot of repository traffic.

## [0.2.0] - 2026-08-28

### Added

- Supervised agent runs, an approval-gated requester shared space and the Art. 28(3) GDPR DPA clause review (#9).
- The legal capacity simulation and the outcome control tower (#8).
- The supervised legal-operations agent, consolidated into `supervised-agent/` (#7).
- The industrial robotics RaaS deal desk case study (#5).
- The GC command center, operational lists and a local knowledge portal (#1, #2).

### Changed

- Relicensed under MIT.

### Fixed

- Request collections that are `null` no longer break the workspace outputs (#3).

## [0.1.0] - 2026-07-03

### Added

- The deterministic pipeline: intake, risk, priority, routing, SLA, approval matrix, external-counsel decision, escalation and board-pack export.

[Unreleased]: https://github.com/sebastianfoerste/legal-function-operating-system/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/sebastianfoerste/legal-function-operating-system/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/sebastianfoerste/legal-function-operating-system/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sebastianfoerste/legal-function-operating-system/releases/tag/v0.1.0
