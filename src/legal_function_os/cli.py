"""Command-line entry point.

    python -m legal_function_os.cli --out examples

Writes board-pack.md and board-pack.json. Exits non-zero when there are open
board-attention items or SLA breaches, so it can gate a reporting pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from legal_function_os.agent_run import build_agent_runs
from legal_function_os.bundled import bundled_path
from legal_function_os.board_pack import build_board_pack, render_markdown
from legal_function_os.capacity_simulator import (
    build_capacity_simulation,
    render_capacity_markdown,
)
from legal_function_os.contract_intelligence import build_dpa_review
from legal_function_os.shared_space import build_shared_space
from legal_function_os.workspace import build_legal_function_workspace
from legal_function_os.collaboration_workspace import build_collaboration_workspace, render_portal
from legal_function_os.outcome_control_tower import (
    build_outcome_control_tower,
    write_outcome_artifacts,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Legal function operating system: board pack.")
    parser.add_argument(
        "--input",
        default=None,
        help="Path to a JSON array of legal requests. Defaults to the bundled synthetic set.",
    )
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
    args = parser.parse_args(argv)

    source = Path(args.input) if args.input else bundled_path("sample_requests.json")
    requests = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(requests, list):
        print("Input must be a JSON array of requests.", file=sys.stderr)
        return 2

    if args.dpa_output and not args.dpa_input:
        print("error: --dpa-output requires --dpa-input", file=sys.stderr)
        return 2

    pack = build_board_pack(requests, period=args.period)
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
                build_legal_function_workspace(requests, period=args.period),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.collaboration_output_dir:
        output_dir = Path(args.collaboration_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        collaboration = build_collaboration_workspace(requests, args.period)
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
            simulation = build_capacity_simulation(requests, scenario_payloads)
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
            tower = build_outcome_control_tower(requests, event_ledger, outcome_config)
            write_outcome_artifacts(tower, Path(args.outcome_output))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"Invalid outcome control tower input: {exc}", file=sys.stderr)
            return 2

    if args.agent_runs_output:
        Path(args.agent_runs_output).write_text(
            json.dumps(
                build_agent_runs(requests, period=args.period), indent=2, ensure_ascii=False
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
                build_shared_space(requests, approvals, period=args.period),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.dpa_input and args.dpa_output:
        documents = json.loads(Path(args.dpa_input).read_text(encoding="utf-8"))
        Path(args.dpa_output).write_text(
            json.dumps(build_dpa_review(documents), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    # Board-attention items are normal management signal, not a failure. Only an
    # explicit --fail-on-breach gates the pipeline on missed SLAs.
    if args.fail_on_breach and pack.totals["sla_breaches"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
