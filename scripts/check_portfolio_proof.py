"""Validate the machine-readable reviewer route and referenced proof files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = ROOT / "docs" / "portfolio-proof.json"


def main() -> int:
    try:
        proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"portfolio proof could not be read: {exc}")
        return 1

    failures: list[str] = []
    if proof.get("schema_version") != "portfolio-proof.v1":
        failures.append("schema_version must equal portfolio-proof.v1")
    if proof.get("repository") != "legal-function-operating-system":
        failures.append("repository name is incorrect")
    if not proof.get("reviewer_path"):
        failures.append("reviewer_path must contain at least one file")

    referenced = [
        *proof.get("reviewer_path", []),
        *[
            item.get("path")
            for item in proof.get("proof_surfaces", [])
            if isinstance(item, dict)
        ],
    ]
    for path in referenced:
        if not isinstance(path, str) or not path:
            failures.append("proof paths must be non-empty strings")
            continue
        if not (ROOT / path).is_file():
            failures.append(f"missing proof file: {path}")

    expected_gates = {
        "make test",
        "make demo",
        "make check-generated",
        "make proof-check",
    }
    actual_gates = set(_strings(proof.get("validation_gates")))
    missing_gates = sorted(expected_gates - actual_gates)
    if missing_gates:
        failures.append(f"missing validation gates: {missing_gates}")

    if failures:
        print("\n".join(failures))
        return 1
    print("portfolio-proof check passed")
    return 0


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


if __name__ == "__main__":
    raise SystemExit(main())
