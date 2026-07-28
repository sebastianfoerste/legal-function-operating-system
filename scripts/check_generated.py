"""Fail when committed demo artifacts differ from deterministic regeneration."""

from __future__ import annotations

import tempfile
from pathlib import Path

from legal_function_os.cli import main as board_cli
from legal_function_os.raas_cli import main as raas_cli

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (
    "board-pack.md",
    "board-pack.json",
    "legal-capacity-simulation.md",
    "legal-capacity-simulation.json",
    "raas-deal-pack.md",
    "raas-deal-pack.json",
    "raas-deal-room.html",
    "raas-deal-desk.svg",
    "raas-source-manifest.json",
)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp_dir:
        output = Path(tmp_dir)
        board_status = board_cli(
            [
                "--input",
                str(ROOT / "data" / "sample_requests.json"),
                "--out",
                str(output),
                "--period",
                "Q2 2026 (synthetic)",
                "--capacity-scenarios",
                str(ROOT / "data" / "capacity_scenarios.json"),
                "--capacity-output",
                str(output),
                "--quiet",
            ]
        )
        raas_status = raas_cli(
            [
                "--input",
                str(ROOT / "data" / "raas_deal.json"),
                "--out",
                str(output),
                "--quiet",
            ]
        )
        if board_status != 0 or raas_status != 0:
            print("generated-artifact check could not regenerate the demo")
            return 1

        drift = []
        for name in EXPECTED:
            committed = ROOT / "examples" / name
            generated = output / name
            if not committed.is_file():
                drift.append(f"missing committed artifact: examples/{name}")
            elif not generated.is_file():
                drift.append(f"missing regenerated artifact: {name}")
            elif committed.read_bytes() != generated.read_bytes():
                drift.append(f"generated artifact drift: examples/{name}")
        if drift:
            print("\n".join(drift))
            print("Run `make demo` and commit the regenerated artifacts.")
            return 1

    print("generated-artifact check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
