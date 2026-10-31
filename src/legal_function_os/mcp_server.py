"""MCP server (stdio) exposing the tested rules to LLM agents.

The tool functions below are plain Python and need nothing beyond the standard
library. Only ``build_server``/``main`` import the optional ``mcp`` package:

    pip install "legal-function-os[mcp]"
    legal-function-os-mcp

An agent can then call the approval matrix instead of interpreting a prose one.
The decision path stays deterministic: no LLM is involved in any tool result.
"""

from __future__ import annotations

from typing import Any

from legal_function_os.board_pack import build_board_pack
from legal_function_os.contract_intelligence import build_dpa_review, check_dpa_documents
from legal_function_os.policy import load_policy
from legal_function_os.rules import decide
from legal_function_os.validation import request_schema, validate_requests


class InputRejected(ValueError):
    """Raised when input breaks the published contract; nothing is decided."""


def _issues(requests: Any, policy_path: str | None) -> Any:
    policy = load_policy(policy_path)
    report = validate_requests(requests, policy)
    if not report.ok:
        raise InputRejected("; ".join(issue.describe() for issue in report.errors))
    return policy, [issue.describe() for issue in report.warnings]


def triage_requests(requests: list[dict[str, Any]], policy_path: str | None = None) -> dict[str, Any]:
    """Validate legal requests and return risk, priority, queue, SLA, approval chain and escalations."""
    policy, warnings = _issues(requests, policy_path)
    return {"decisions": [decide(r, policy).to_dict() for r in requests], "warnings": warnings}


def board_pack(
    requests: list[dict[str, Any]], period: str = "current period", policy_path: str | None = None
) -> dict[str, Any]:
    """Aggregate decided requests into a board-ready pack (totals, approvals, referrals, breaches)."""
    policy, warnings = _issues(requests, policy_path)
    pack = build_board_pack(requests, period, policy).to_dict()
    pack["warnings"] = warnings
    return pack


def dpa_review(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Check DPA clause coverage against the bundled playbook (Art. 28(3) GDPR, element by element).

    The caller maps clauses to playbook keys; the result depends on that mapping.
    """
    problems = check_dpa_documents(documents)
    if problems:
        raise InputRejected("; ".join(problems))
    return build_dpa_review(documents)


def legal_request_schema() -> dict[str, Any]:
    """The published JSON Schema for one legal request."""
    return request_schema()


TOOLS = (triage_requests, board_pack, dpa_review, legal_request_schema)


def build_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - exercised without the extra
        raise SystemExit('The MCP server needs the extra: pip install "legal-function-os[mcp]"') from exc

    server = FastMCP("legal-function-os")
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    for tool in TOOLS:
        server.add_tool(tool, annotations=read_only)
    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
