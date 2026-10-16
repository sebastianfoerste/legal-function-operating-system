"""Command-line entry point.

    legal-function-os                     board pack for the bundled synthetic requests
    legal-function-os triage --input requests.csv
    legal-function-os board-pack --input requests.json --out reports
    legal-function-os validate --input requests.csv --format json
    legal-function-os dpa-review --input agreements.json
    legal-function-os capacity --input requests.json --scenarios scenarios.json
    legal-function-os control-tower --input requests.json --events events.json --config config.json
    legal-function-os init                writes policy.json from a short interview
    legal-function-os triage --policy policy.json --input requests.csv

``python -m legal_function_os`` runs the same commands. Each command prints Markdown,
or JSON with ``--format json``, and ``--out DIR`` writes the same artifacts as files.
``--policy`` applies your own value bands, queues, SLAs and thresholds instead of the
bundled defaults. Without a command, the original all-in-one flags still work unchanged.

Board-attention items are reported, not treated as failures: the exit status is 0
unless --fail-on-breach is given and there are SLA breaches (status 1), or the input
is invalid (status 2).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from legal_function_os import __version__
from legal_function_os.agent_run import build_agent_runs
from legal_function_os.board_pack import build_board_pack, render_markdown, render_triage_markdown
from legal_function_os.bundled import bundled_path
from legal_function_os.capacity_simulator import (
    build_capacity_simulation,
    render_capacity_markdown,
)
from legal_function_os.collaboration_workspace import build_collaboration_workspace, render_portal
from legal_function_os.contract_intelligence import (
    build_dpa_review,
    check_dpa_documents,
    render_dpa_markdown,
)
from legal_function_os.intake import InputError, load_requests
from legal_function_os.outcome_control_tower import (
    build_outcome_control_tower,
    render_outcome_markdown,
    write_outcome_artifacts,
)
from legal_function_os.policy import Policy, PolicyError, load_policy, render_policy_json
from legal_function_os.policy_init import InterviewError, run_interview
from legal_function_os.rules import decide
from legal_function_os.shared_space import build_shared_space
from legal_function_os.validation import ValidationReport, validate_requests
from legal_function_os.workspace import build_legal_function_workspace

PROG = "legal-function-os"
INPUT_FORMAT_URL = (
    "https://github.com/sebastianfoerste/legal-function-operating-system/blob/main/"
    "docs/INPUT_FORMAT.md"
)
POLICY_FORMAT_URL = (
    "https://github.com/sebastianfoerste/legal-function-operating-system/blob/main/"
    "docs/CUSTOMIZE.md"
)
TRIAGE_SCHEMA = "legal-function-os.triage.v1"
POLICY_HELP = (
    "Policy JSON with your value bands, queues, SLAs and thresholds (write one with "
    f"'{PROG} init'; see docs/CUSTOMIZE.md). Default: the bundled illustrative policy."
)
INPUT_HELP = (
    "Requests: a JSON array, or a .csv file with one request per row (see "
    "docs/INPUT_FORMAT.md); - reads JSON from standard input. Default: the bundled "
    "synthetic requests."
)


class _Failure(Exception):
    """Stop a command with an exit status after its message has been printed."""

    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


def _error(message: str) -> _Failure:
    print(f"error: {message}", file=sys.stderr)
    return _Failure(2)


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _read_json(path: str, what: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise _error(f"cannot read {what} {path}: {exc.strerror or exc}") from None
    except json.JSONDecodeError as exc:
        raise _error(f"{what} {path} is not valid JSON: {exc}") from None


def _load_policy(path: str | None) -> Policy:
    """Read and check a policy file, printing every problem; None is the bundled default."""

    try:
        policy = load_policy(path)
    except PolicyError as exc:
        for problem in exc.problems:
            print(f"error: {exc.source}: {problem}", file=sys.stderr)
        print(
            f"The policy cannot be applied. Nothing was written. Policy format: {POLICY_FORMAT_URL}",
            file=sys.stderr,
        )
        raise _Failure(2) from None
    if path is not None:
        print(f"note: applying policy {policy.name!r} from {path}", file=sys.stderr)
    return policy


def _load_valid_requests(
    path: str | None, policy: Policy | None = None
) -> tuple[list[dict[str, Any]], ValidationReport]:
    """Read and validate requests, printing notes and problems to standard error."""

    try:
        loaded = load_requests(path)
    except InputError as exc:
        raise _error(str(exc)) from None
    for note in loaded.notes:
        print(f"note: {note}", file=sys.stderr)
    report = validate_requests(loaded.requests, policy)
    for line in report.lines(loaded.locate):
        print(line, file=sys.stderr)
    if not report.ok:
        print(
            f"{report.summary()}. Nothing was written. Request format: {INPUT_FORMAT_URL}",
            file=sys.stderr,
        )
        raise _Failure(2)
    return loaded.requests, report


def _emit(text: str) -> None:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _write(out_dir: str, files: dict[str, str]) -> None:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
        print(f"wrote {directory / name}", file=sys.stderr)


# --- Commands ----------------------------------------------------------------


def _triage(args: argparse.Namespace) -> int:
    policy = _load_policy(args.policy)
    requests, report = _load_valid_requests(args.input, policy)
    decisions = [decide(request, policy) for request in requests]
    if args.id:
        known = {decision.request_id for decision in decisions}
        unknown = [request_id for request_id in args.id if request_id not in known]
        if unknown:
            raise _error(f"no request with id {', '.join(unknown)} in the input")
        decisions = [decision for decision in decisions if decision.request_id in args.id]
    if args.format == "json":
        _emit(
            _json(
                {
                    "schema": TRIAGE_SCHEMA,
                    "policy": policy.name,
                    "request_count": len(decisions),
                    "decisions": [decision.to_dict() for decision in decisions],
                    "warnings": [issue.to_dict() for issue in report.warnings],
                }
            )
        )
    else:
        _emit(render_triage_markdown(decisions, policy=policy.name))
    return 0


def _board_pack(args: argparse.Namespace) -> int:
    policy = _load_policy(args.policy)
    requests, _ = _load_valid_requests(args.input, policy)
    pack = build_board_pack(requests, period=args.period, policy=policy)
    markdown, payload = render_markdown(pack), _json(pack.to_dict())
    if args.out:
        _write(args.out, {"board-pack.md": markdown, "board-pack.json": payload})
    else:
        _emit(payload if args.format == "json" else markdown)
    if args.fail_on_breach and pack.totals["sla_breaches"] > 0:
        return 1
    return 0


def _validate(args: argparse.Namespace) -> int:
    policy = _load_policy(args.policy)
    try:
        loaded = load_requests(args.input)
    except InputError as exc:
        raise _error(str(exc)) from None
    report = validate_requests(loaded.requests, policy)
    if args.format == "json":
        _emit(
            _json(
                {
                    **report.to_dict(),
                    "source": loaded.source,
                    "policy": policy.name,
                    "notes": loaded.notes,
                }
            )
        )
    else:
        for note in loaded.notes:
            _emit(f"note: {note}")
        for line in report.lines(loaded.locate):
            _emit(line)
        verdict = "valid" if report.ok else "not valid"
        _emit(f"{loaded.source}: {verdict} ({report.summary()})")
    return 0 if report.ok else 2


def _load_dpa_documents(path: str) -> list[dict[str, Any]]:
    documents = _read_json(path, "DPA documents")
    problems = check_dpa_documents(documents)
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        print(f"{path} is not a usable list of DPA documents. Nothing was written.", file=sys.stderr)
        raise _Failure(2)
    return documents


def _dpa_review(args: argparse.Namespace) -> int:
    documents = _load_dpa_documents(args.input or str(bundled_path("dpa_documents.json")))
    review = build_dpa_review(documents)
    markdown, payload = render_dpa_markdown(review), _json(review)
    if args.out:
        _write(args.out, {"dpa-review.md": markdown, "dpa-review.json": payload})
    else:
        _emit(payload if args.format == "json" else markdown)
    return 0


def _demo_default(args: argparse.Namespace, option: str, value: str | None, bundled: str) -> str:
    """Fall back to bundled synthetic data only for a pure demo run without --input."""

    if value:
        return value
    if args.input is not None:
        raise _error(
            f"{option} is required with --input: the bundled synthetic file only fits "
            "the bundled synthetic requests"
        )
    return str(bundled_path(bundled))


def _capacity(args: argparse.Namespace) -> int:
    scenarios_path = _demo_default(args, "--scenarios", args.scenarios, "capacity_scenarios.json")
    policy = _load_policy(args.policy)
    requests, _ = _load_valid_requests(args.input, policy)
    scenarios = _read_json(scenarios_path, "capacity scenarios")
    try:
        simulation = build_capacity_simulation(requests, scenarios, policy)
    except (ValueError, KeyError, TypeError) as exc:
        raise _error(f"invalid capacity simulation input: {exc}") from None
    markdown, payload = render_capacity_markdown(simulation), _json(simulation)
    if args.out:
        _write(
            args.out,
            {"legal-capacity-simulation.md": markdown, "legal-capacity-simulation.json": payload},
        )
    else:
        _emit(payload if args.format == "json" else markdown)
    return 0


def _control_tower(args: argparse.Namespace) -> int:
    events_path = _demo_default(args, "--events", args.events, "service_events.json")
    config_path = _demo_default(args, "--config", args.config, "outcome_config.json")
    policy = _load_policy(args.policy)
    requests, _ = _load_valid_requests(args.input, policy)
    ledger = _read_json(events_path, "service event ledger")
    config = _read_json(config_path, "outcome configuration")
    try:
        tower = build_outcome_control_tower(requests, ledger, config, policy)
    except (ValueError, KeyError, TypeError) as exc:
        raise _error(f"invalid outcome control tower input: {exc}") from None
    if args.out:
        for path in write_outcome_artifacts(tower, Path(args.out)).values():
            print(f"wrote {path}", file=sys.stderr)
    else:
        _emit(_json(tower) if args.format == "json" else render_outcome_markdown(tower))
    return 0


def _init(args: argparse.Namespace) -> int:
    target = Path(args.out)
    if target.exists() and not args.force:
        raise _error(f"{target} already exists; pass --force to overwrite it")
    if args.defaults:
        policy = run_interview(lambda _prompt: "", lambda _line: None)
    else:

        def ask(prompt: str) -> str:
            try:
                return input(prompt)
            except EOFError:
                raise _error(
                    f"the interview needs an answer on standard input; run '{PROG} init "
                    "--defaults' to write the bundled default values instead"
                ) from None

        try:
            policy = run_interview(ask, print)
        except InterviewError as exc:
            raise _error(f"{exc}. Nothing was written.") from None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_policy_json(policy), encoding="utf-8")
    print(f"wrote {target}", file=sys.stderr)
    print(
        f"Next: {PROG} validate --policy {target} --input requests.csv, then "
        f"{PROG} board-pack --policy {target} --input requests.csv",
        file=sys.stderr,
    )
    return 0


# --- Parsers -----------------------------------------------------------------

Handler = Callable[[argparse.Namespace], int]

# name: (one-line summary, handler). The order is the order of the help and docs.
COMMANDS: dict[str, tuple[str, Handler]] = {
    "triage": (
        "Decide risk, priority, queue, SLA, approval chain and external counsel for each request, with the reasons.",
        _triage,
    ),
    "board-pack": (
        "Roll the decisions up into a board operations pack.",
        _board_pack,
    ),
    "validate": (
        "Check requests against the request format without deciding anything.",
        _validate,
    ),
    "dpa-review": (
        "Check data processing agreements for the Art. 28(3) GDPR (DSGVO) clauses.",
        _dpa_review,
    ),
    "capacity": (
        "Compare legal capacity scenarios and name the binding constraint.",
        _capacity,
    ),
    "control-tower": (
        "Measure business-time SLAs, waiting time and value from a service-event ledger.",
        _control_tower,
    ),
    "init": (
        "Write a policy file (value bands, queues, SLAs, thresholds) from a short interview.",
        _init,
    ),
}


def _add_input(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", metavar="PATH", help=INPUT_HELP)
    parser.add_argument("--policy", metavar="PATH", help=POLICY_HELP)


def _add_format(parser: argparse.ArgumentParser, *, out: str | None) -> None:
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="Output format on standard output: Markdown (default) or JSON.",
    )
    if out:
        parser.add_argument(
            "--out",
            metavar="DIR",
            help=f"Write {out} to this directory instead of printing.",
        )


def command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Legal front door rules: intake, triage, routing, SLA, approval tier and a "
            "board pack, from tested rules with no LLM in the decision path. Synthetic "
            "data only; every consequential decision requires human review."
        ),
        epilog=(
            "Without a command, legal-function-os prints the board pack for the bundled "
            "synthetic requests, and the original all-in-one flags (--input, --out, "
            "--capacity-scenarios, --dpa-input and the rest) still work. Reference: "
            "docs/CLI.md."
        ),
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", title="commands")
    parsers = {
        name: commands.add_parser(name, help=summary, description=summary)
        for name, (summary, _handler) in COMMANDS.items()
    }

    triage = parsers["triage"]
    _add_input(triage)
    triage.add_argument(
        "--id",
        action="append",
        metavar="ID",
        help="Only show this request. Repeat for several.",
    )
    _add_format(triage, out=None)

    board = parsers["board-pack"]
    _add_input(board)
    board.add_argument("--period", default="current period", help="Reporting period label.")
    _add_format(board, out="board-pack.md and board-pack.json")
    board.add_argument(
        "--fail-on-breach",
        action="store_true",
        help="Exit 1 if any request has a missed SLA (to gate a reporting pipeline).",
    )

    validate = parsers["validate"]
    _add_input(validate)
    _add_format(validate, out=None)

    dpa = parsers["dpa-review"]
    dpa.add_argument(
        "--input",
        metavar="PATH",
        help=(
            "A JSON array of agreements, each with an id, a title and a clauses object "
            "(see src/legal_function_os/data/dpa_documents.json). Default: the two "
            "bundled synthetic agreements."
        ),
    )
    _add_format(dpa, out="dpa-review.md and dpa-review.json")

    capacity = parsers["capacity"]
    _add_input(capacity)
    capacity.add_argument(
        "--scenarios",
        metavar="PATH",
        help=(
            "JSON array of at least two capacity scenarios. Required with --input; "
            "without --input the bundled synthetic scenarios are used."
        ),
    )
    _add_format(capacity, out="legal-capacity-simulation.md and .json")

    tower = parsers["control-tower"]
    _add_input(tower)
    tower.add_argument(
        "--events",
        metavar="PATH",
        help="Versioned service-event ledger JSON. Required with --input.",
    )
    tower.add_argument(
        "--config",
        metavar="PATH",
        help="Business calendar and value assumptions JSON. Required with --input.",
    )
    _add_format(tower, out="legal-outcome-control-tower.md, .json and .html")

    init = parsers["init"]
    init.add_argument(
        "--out",
        metavar="PATH",
        default="policy.json",
        help="Where to write the policy (default: policy.json).",
    )
    init.add_argument(
        "--defaults",
        action="store_true",
        help="Do not ask; write the bundled default values under the default name.",
    )
    init.add_argument("--force", action="store_true", help="Overwrite an existing file.")
    return parser


def legacy_parser() -> argparse.ArgumentParser:
    """The original single-command interface, kept so existing scripts keep working."""

    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Legal function operating system: board pack.",
        epilog=f"Commands: {', '.join(COMMANDS)}. Run '{PROG} --help' for them.",
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "Path to a JSON array of legal requests, or a .csv file with one request per "
            "row (see docs/INPUT_FORMAT.md); - reads JSON from standard input. Defaults to "
            "the bundled synthetic set."
        ),
    )
    parser.add_argument("--policy", default=None, help=POLICY_HELP)
    parser.add_argument("--out", default=None, help="Output directory for the board pack.")
    parser.add_argument("--period", default="current period", help="Reporting period label.")
    parser.add_argument(
        "--workspace-output",
        default=None,
        help="Optional path for the request vault, triage workflows and GC command center JSON.",
    )
    parser.add_argument(
        "--collaboration-output-dir",
        default=None,
        help="Optional directory for operational Lists, workflow runs and local knowledge portal.",
    )
    parser.add_argument(
        "--capacity-scenarios",
        default=None,
        help="Optional JSON file containing at least two illustrative capacity scenarios.",
    )
    parser.add_argument(
        "--capacity-output",
        default=None,
        help="Optional directory for the capacity simulation Markdown and JSON.",
    )
    parser.add_argument(
        "--events-input",
        default=None,
        help="Optional versioned legal-service event ledger JSON.",
    )
    parser.add_argument(
        "--outcome-config",
        default=None,
        help="Optional business calendar and value-assumption JSON.",
    )
    parser.add_argument(
        "--outcome-output",
        default=None,
        help="Optional directory for outcome control tower JSON, Markdown, and HTML.",
    )
    parser.add_argument(
        "--agent-runs-output",
        default=None,
        help="Optional path for the supervised matter agent runs JSON.",
    )
    parser.add_argument(
        "--shared-space-output",
        default=None,
        help="Optional path for the approval-gated requester shared space JSON.",
    )
    parser.add_argument(
        "--approvals",
        default=None,
        help="Optional JSON file mapping a request id to a documented share approval.",
    )
    parser.add_argument(
        "--dpa-input",
        default=None,
        help="Optional JSON array of DPA documents for the Art. 28(3) GDPR clause review.",
    )
    parser.add_argument(
        "--dpa-output",
        default=None,
        help="Optional path for the DPA clause review JSON.",
    )
    parser.add_argument("--quiet", action="store_true", help="Do not print the markdown pack.")
    parser.add_argument(
        "--fail-on-breach",
        action="store_true",
        help="Exit non-zero if there are SLA breaches (use to gate a reporting pipeline).",
    )
    return parser


def _legacy_main(argv: list[str]) -> int:
    args = legacy_parser().parse_args(argv)

    try:
        policy = _load_policy(args.policy)
        requests, _ = _load_valid_requests(args.input, policy)
    except _Failure as failure:
        return failure.status

    if args.dpa_output and not args.dpa_input:
        print("error: --dpa-output requires --dpa-input", file=sys.stderr)
        return 2
    if args.dpa_input and not args.dpa_output:
        print(
            "error: --dpa-input requires --dpa-output PATH (the review is written as JSON); "
            f"or run '{PROG} dpa-review --input PATH' to print it",
            file=sys.stderr,
        )
        return 2
    dpa_documents: list[dict[str, Any]] = []
    if args.dpa_input:
        try:
            dpa_documents = _load_dpa_documents(args.dpa_input)
        except _Failure as failure:
            return failure.status

    pack = build_board_pack(requests, period=args.period, policy=policy)
    markdown = render_markdown(pack)

    if not args.quiet:
        print(markdown)

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "board-pack.md").write_text(markdown, encoding="utf-8")
        (out_dir / "board-pack.json").write_text(
            json.dumps(pack.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    if args.workspace_output:
        workspace_path = Path(args.workspace_output)
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        workspace_path.write_text(
            json.dumps(
                build_legal_function_workspace(requests, period=args.period, policy=policy),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.collaboration_output_dir:
        output_dir = Path(args.collaboration_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        collaboration = build_collaboration_workspace(requests, args.period, policy)
        (output_dir / "collaboration-workspace.json").write_text(
            json.dumps(collaboration, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        render_portal(collaboration["knowledge_portal"], output_dir / "knowledge-portal.html")

    if args.capacity_scenarios or args.capacity_output:
        if not args.capacity_scenarios or not args.capacity_output:
            print(
                "--capacity-scenarios and --capacity-output must be supplied together.",
                file=sys.stderr,
            )
            return 2
        try:
            scenario_payloads = json.loads(
                Path(args.capacity_scenarios).read_text(encoding="utf-8")
            )
            simulation = build_capacity_simulation(requests, scenario_payloads, policy)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"Invalid capacity simulation input: {exc}", file=sys.stderr)
            return 2
        capacity_output = Path(args.capacity_output)
        capacity_output.mkdir(parents=True, exist_ok=True)
        (capacity_output / "legal-capacity-simulation.json").write_text(
            json.dumps(simulation, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (capacity_output / "legal-capacity-simulation.md").write_text(
            render_capacity_markdown(simulation),
            encoding="utf-8",
        )

    outcome_args = (args.events_input, args.outcome_config, args.outcome_output)
    if any(outcome_args):
        if not all(outcome_args):
            print(
                "--events-input, --outcome-config, and --outcome-output must be supplied together.",
                file=sys.stderr,
            )
            return 2
        try:
            event_ledger = json.loads(Path(args.events_input).read_text(encoding="utf-8"))
            outcome_config = json.loads(Path(args.outcome_config).read_text(encoding="utf-8"))
            tower = build_outcome_control_tower(requests, event_ledger, outcome_config, policy)
            write_outcome_artifacts(tower, Path(args.outcome_output))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"Invalid outcome control tower input: {exc}", file=sys.stderr)
            return 2

    if args.agent_runs_output:
        Path(args.agent_runs_output).write_text(
            json.dumps(
                build_agent_runs(requests, period=args.period, policy=policy),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.shared_space_output:
        approvals = {}
        if args.approvals:
            approvals = json.loads(Path(args.approvals).read_text(encoding="utf-8"))
        Path(args.shared_space_output).write_text(
            json.dumps(
                build_shared_space(requests, approvals, period=args.period, policy=policy),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.dpa_input and args.dpa_output:
        Path(args.dpa_output).write_text(_json(build_dpa_review(dpa_documents)), encoding="utf-8")

    # Board-attention items are normal management signal, not a failure. Only an
    # explicit --fail-on-breach gates the pipeline on missed SLAs.
    if args.fail_on_breach and pack.totals["sla_breaches"] > 0:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in {*COMMANDS, "-h", "--help"}:
        return _legacy_main(arguments)
    args = command_parser().parse_args(arguments)
    _summary, handler = COMMANDS[args.command]
    try:
        return handler(args)
    except _Failure as failure:
        return failure.status


if __name__ == "__main__":
    sys.exit(main())
