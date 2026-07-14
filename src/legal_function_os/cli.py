"""Command-line entry point.

    python -m legal_function_os.cli --input data/sample_requests.json --out examples

Writes board-pack.md and board-pack.json. Exits non-zero when there are open
board-attention items or SLA breaches, so it can gate a reporting pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from legal_function_os.board_pack import build_board_pack, render_markdown
from legal_function_os.workspace import build_legal_function_workspace
from legal_function_os.collaboration_workspace import build_collaboration_workspace, render_portal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Legal function operating system: board pack.")
    parser.add_argument("--input", required=True, help="Path to a JSON array of legal requests.")
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
    parser.add_argument("--agent-runs-output", default=None, help="Optional path for the matter agent runs JSON.")
    parser.add_argument("--shared-space-output", default=None, help="Optional path for the requester shared space JSON.")
    parser.add_argument("--approvals", default=None, help="Optional JSON file mapping request id to a share approval.")
    parser.add_argument("--dpa-input", default=None, help="Optional JSON array of DPA documents for the clause review.")
    parser.add_argument("--dpa-output", default=None, help="Optional path for the DPA clause review JSON.")
    parser.add_argument("--quiet", action="store_true", help="Do not print the markdown pack.")
    parser.add_argument(
        "--fail-on-breach",
        action="store_true",
        help="Exit non-zero if there are SLA breaches (use to gate a reporting pipeline).",
    )
    args = parser.parse_args(argv)

    requests = json.loads(Path(args.input).read_text(encoding="utf-8"))
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

    if args.agent_runs_output:
        from legal_function_os.agent_run import build_agent_runs

        Path(args.agent_runs_output).write_text(
            json.dumps(build_agent_runs(requests, period=args.period), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if args.shared_space_output:
        from legal_function_os.shared_space import build_shared_space

        approvals = {}
        if args.approvals:
            approvals = json.loads(Path(args.approvals).read_text(encoding="utf-8"))
        Path(args.shared_space_output).write_text(
            json.dumps(build_shared_space(requests, approvals, period=args.period), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if args.dpa_input and args.dpa_output:
        from legal_function_os.contract_intelligence import build_dpa_review

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
