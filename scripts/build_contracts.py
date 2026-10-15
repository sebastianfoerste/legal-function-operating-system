#!/usr/bin/env python3
"""Write the JSON Schemas that are generated from code into contracts/.

The request schema is built from the same constants the validator and the rules
use, so the published contract cannot drift from what the CLI accepts. A test
fails if the committed file differs from what this script writes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_function_os.validation import request_schema  # noqa: E402

GENERATED = {
    ROOT / "contracts" / "legal-request.v1.schema.json": request_schema,
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
