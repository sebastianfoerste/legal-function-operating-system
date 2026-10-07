#!/usr/bin/env python3
"""Validate the shared control schema and cross-component state mappings."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "legal-workflow-controls.v1.schema.json"

REVIEW_STATE_MAP = {
    "legal-function-os": {
        "review_required": "pending_review",
        "blocked": "blocked",
    },
    "supervised-agent": {
        "needs_review": "pending_review",
        "approved": "approved",
        "rejected": "rejected",
        "revision_requested": "revision_requested",
        "escalated": "escalated",
    },
}

PILOT_STATE_MAP = {
    "intake": "pending_review",
    "triage": "pending_review",
    "assignment": "pending_review",
    "review": "pending_review",
    "revision_requested": "revision_requested",
    "revised": "pending_review",
    "approved": "approved",
    "ready_for_delivery": "approved",
    "closed": "approved",
}


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    allowed = set(schema["properties"]["review_state"]["enum"])
    mapped = {
        shared
        for component in REVIEW_STATE_MAP.values()
        for shared in component.values()
    }
    if not mapped <= allowed:
        raise SystemExit(f"state mapping exceeds shared contract: {sorted(mapped - allowed)}")

    agent_models = ROOT / "supervised-agent" / "models.py"
    agent_text = agent_models.read_text(encoding="utf-8")
    for local_state in REVIEW_STATE_MAP["supervised-agent"]:
        if f'"{local_state}"' not in agent_text:
            raise SystemExit(f"supervised-agent state is missing: {local_state}")

    function_workspace = ROOT / "src" / "legal_function_os" / "workspace.py"
    function_text = function_workspace.read_text(encoding="utf-8")
    for local_state in REVIEW_STATE_MAP["legal-function-os"]:
        if f'"{local_state}"' not in function_text:
            raise SystemExit(f"legal-function state is missing: {local_state}")

    required_agent_controls = {
        "export requires approved review state",
        "external_actions_allowed: bool = False",
        "verify_audit_chain",
        "SourceVerificationRecord",
    }
    missing = sorted(item for item in required_agent_controls if item not in agent_text)
    if missing:
        raise SystemExit(f"supervised-agent control is missing: {', '.join(missing)}")

    # The pilot maps its own state machine onto the shared contract in one place.
    bridge = (ROOT / "supervised-agent" / "src" / "pilot" / "parent_bridge.py").read_text(
        encoding="utf-8"
    )
    machine = (ROOT / "supervised-agent" / "src" / "pilot" / "state_machine.py").read_text(
        encoding="utf-8"
    )
    for pilot_state, shared_state in PILOT_STATE_MAP.items():
        if f'"{pilot_state}": "{shared_state}"' not in bridge:
            raise SystemExit(f"pilot state mapping is missing or changed: {pilot_state}")
        if f'"{pilot_state}"' not in machine:
            raise SystemExit(f"pilot state is missing from the state machine: {pilot_state}")
    if not set(PILOT_STATE_MAP.values()) <= allowed:
        raise SystemExit("pilot state mapping exceeds shared contract")

    print("shared legal workflow control contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
