"""CLI for the synthetic industrial robotics RaaS deal decision pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from legal_function_os.raas_deal_desk import (
    build_raas_deal_pack,
    render_raas_markdown,
    write_raas_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a review-gated RaaS deal decision pack from synthetic JSON."
    )
    parser.add_argument("--input", required=True, help="Path to one synthetic RaaS deal JSON object.")
    parser.add_argument("--out", default=None, help="Output directory for reviewer artifacts.")
    parser.add_argument("--quiet", action="store_true", help="Do not print the markdown pack.")
    parser.add_argument(
        "--fail-on-blocker",
        action="store_true",
        help="Exit non-zero when the signing gate is blocked.",
    )
    args = parser.parse_args(argv)

    try:
        deal = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(deal, dict):
            raise ValueError("RaaS deal input must be one JSON object")
        pack = build_raas_deal_pack(deal)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.quiet:
        print(render_raas_markdown(pack))
    if args.out:
        write_raas_outputs(pack, Path(args.out))
    if args.fail_on_blocker and pack.signing_gate["status"] == "blocked":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
