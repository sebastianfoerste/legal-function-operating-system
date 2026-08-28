"""Validate the machine-readable verification manifest and every file it names."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "verification-manifest.json"

REQUIRED_GATES = {
    "make test",
    "make demo",
    "make check-generated",
    "make manifest-check",
    "make contract-check",
    "make agent-check",
}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def main() -> int:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"verification manifest could not be read: {exc}")
        return 1

    failures: list[str] = []
    if manifest.get("schema_version") != "verification-manifest.v1":
        failures.append("schema_version must equal verification-manifest.v1")
    if manifest.get("repository") != "legal-function-operating-system":
        failures.append("repository name is incorrect")
    if not manifest.get("quickstart"):
        failures.append("quickstart must contain at least one file")

    referenced = [
        *_strings(manifest.get("quickstart")),
        *[
            item.get("path")
            for item in manifest.get("verification_artifacts", [])
            if isinstance(item, dict)
        ],
    ]
    for path in referenced:
        if not isinstance(path, str) or not path:
            failures.append("manifest paths must be non-empty strings")
            continue
        if not (ROOT / path).is_file():
            failures.append(f"missing verification artifact: {path}")

    missing_gates = sorted(REQUIRED_GATES - set(_strings(manifest.get("validation_commands"))))
    if missing_gates:
        failures.append(f"missing validation commands: {missing_gates}")

    # The manifest records what a reviewer can verify; it must not carry claims
    # about how the repository is presented.
    for retired in ("pinned_on_github", "reviewer_path", "proof_surfaces"):
        if retired in manifest:
            failures.append(f"retired portfolio-proof field must be removed: {retired}")

    if failures:
        print("\n".join(failures))
        return 1
    print("verification-manifest check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
