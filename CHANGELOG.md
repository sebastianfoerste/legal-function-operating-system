# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Review room: an "Also open" line shows which other simulated reviewer roles have the matter open and on which revision, and warns with a reload button when the matter has moved on. Presence is held in server memory for two minutes; it is never stored, logged, exported or shown to requesters (ADR 0005).
- A published request format: [`contracts/legal-request.v1.schema.json`](contracts/legal-request.v1.schema.json) and [`docs/INPUT_FORMAT.md`](docs/INPUT_FORMAT.md).
- CSV intake: `--input requests.csv` reads a request log saved from a spreadsheet, one request per row. Headers are matched loosely, yes/no answers become booleans, and Excel's comma, semicolon, tab, UTF-16 and Windows-1252 exports all work. [`examples/requests-template.csv`](examples/requests-template.csv) is a template.
- `--version` on `legal-function-os`.
- CI runs the core on Python 3.10 to 3.13, lints it with Ruff and mypy, and checks that the built wheel installs and runs (`make lint`, `make package-check`).
- A release workflow for PyPI trusted publishing. It stays inactive until the repository variable `PYPI_PUBLISH` is `true`.
- An offline link check for the Pages site and the Markdown docs (`make site-check`).
- A code of conduct, a root security policy, issue and pull request templates, CODEOWNERS, Dependabot, this changelog and `CITATION.cff`.
- A verification manifest in place of the portfolio proof (#11).
- The supervised agent's pilot workflow and reviewer evidence track (#13).
- Review room: inline decision forms with an error summary replace the browser prompt and confirm dialogs; resolving a comment shows the evidence cited in its thread.
- Review room: opening a synthetic matter shows the five required facts, pre-filled from the scenario, and opens the matter only when all are filled, so the first version can be submitted.
- Review room: requesters see a plain-language stage, their next step and what is withheld; reviewers see the playbook's standard and fallback position beside each change.
- One design token set (`design_tokens.py`, light and dark, contrast-tested), used by the Pages index and the review room.
- `docs/CLI.md`, the command reference the CLI help already pointed to.
- Competitive research and an adaptation plan in `docs/research/`, Round 3 of the agent's competitive research, and architecture decision records in `docs/adr/`.

### Changed

- Input is checked before any decision. An unknown `value_band` or `urgency`, a quoted boolean, a duplicate id or a misspelled field name stops the run with exit status 2 and one line per problem. An unknown `type` still goes to the General queue, with a warning and a "needs manual triage" line in the rationale.
- `pyproject.toml` carries classifiers, project URLs and keywords, and reads the version from the package.
- The README was rewritten (#16) and the case study refreshed (#12).

### Fixed

- The knowledge portal and the agent's static review-room snapshot now declare their page language.
- The review room's selects have labels, the matter list marks the open matter, and results are announced to screen readers.
- A mistyped value band such as `">1M"` was read as "no value", which turned a board-attention matter into a low-risk, reviewer-only one. It is now rejected with a suggestion.
- The workspace, agent-run and shared-space outputs counted `"awaiting_business_input": "no"` as true and split a string in `facts` or `dependencies` into characters. These optional fields are now type-checked and listed in the request schema.
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
