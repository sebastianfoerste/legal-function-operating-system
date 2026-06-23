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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Legal function operating system — board pack.")
    parser.add_argument("--input", required=True, help="Path to a JSON array of legal requests.")
    parser.add_argument("--out", default=None, help="Output directory for the board pack.")
    parser.add_argument("--period", default="current period", help="Reporting period label.")
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

    # Board-attention items are normal management signal, not a failure. Only an
    # explicit --fail-on-breach gates the pipeline on missed SLAs.
    if args.fail_on_breach and pack.totals["sla_breaches"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
