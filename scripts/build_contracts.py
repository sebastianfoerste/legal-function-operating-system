#!/usr/bin/env python3
"""Write the JSON Schemas that are generated from code into contracts/.

The request and policy schemas are built from the same code the validator, the
policy checks and the rules use, so the published contracts cannot drift from
what the CLI accepts. A test fails if a committed file differs from what this
script writes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_function_os.policy import policy_schema  # noqa: E402
from legal_function_os.validation import request_schema  # noqa: E402

GENERATED = {
    ROOT / "contracts" / "legal-request.v1.schema.json": request_schema,
    ROOT / "contracts" / "legal-function-policy.v1.schema.json": policy_schema,
}


def render(builder) -> str:
    return json.dumps(builder(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    for path, builder in GENERATED.items():
        path.write_text(render(builder), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
