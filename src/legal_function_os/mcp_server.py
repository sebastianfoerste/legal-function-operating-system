"""MCP server (stdio) exposing the tested rules to LLM agents.

The tool functions below are plain Python and need nothing beyond the standard
library. Only ``build_server``/``main`` import the optional ``mcp`` package:

    pip install "legal-function-os[mcp]"
    legal-function-os-mcp [--policy PATH]

An agent can then call the approval matrix instead of interpreting a prose one.
The decision path stays deterministic: no LLM is involved in any tool result.

The tools take requests and agreements as data. None of them takes a file path:
the model calling the server does not choose what this process reads. Your own
policy (value bands, queues, service levels, thresholds) is applied either once
at start, with ``--policy PATH``, or per call as an inline ``policy`` object in
the format ``legal-function-os init`` writes. Either is checked in full before
it is used.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from legal_function_os.board_pack import build_board_pack
from legal_function_os.contract_intelligence import build_dpa_review, check_dpa_documents
from legal_function_os.policy import Policy, PolicyError, default_policy, load_policy, parse_policy
from legal_function_os.rules import decide
from legal_function_os.validation import request_schema, validate_requests


class InputRejected(ValueError):
    """Raised when input breaks the published contract; nothing is decided."""


# The policy a call without an inline ``policy`` gets: the bundled default, or the
# file given to ``main`` with ``--policy``, read once at start.
_server_policy: Policy | None = None


def set_server_policy(policy: Policy | None) -> None:
    """Set the policy applied to calls without an inline one (None: the bundled default)."""

    global _server_policy
    _server_policy = policy


def _resolve_policy(policy: dict[str, Any] | None) -> Policy:
    if policy is None:
        return _server_policy or default_policy()
    try:
        return parse_policy(policy, "policy")
    except PolicyError as exc:
        raise InputRejected("; ".join(f"policy: {problem}" for problem in exc.problems)) from None


def _issues(requests: Any, policy: dict[str, Any] | None) -> Any:
    applied = _resolve_policy(policy)
    report = validate_requests(requests, applied)
    if not report.ok:
        raise InputRejected("; ".join(issue.describe() for issue in report.errors))
    return applied, [issue.describe() for issue in report.warnings]


def triage_requests(
    requests: list[dict[str, Any]], policy: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate legal requests and return risk, priority, queue, SLA, approval chain and escalations.

    ``policy`` is an optional policy object (the format ``legal-function-os init``
    writes); without it the server's policy applies.
    """
    applied, warnings = _issues(requests, policy)
    return {"decisions": [decide(r, applied).to_dict() for r in requests], "warnings": warnings}


def board_pack(
    requests: list[dict[str, Any]],
    period: str = "current period",
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate decided requests into a board-ready pack (totals, approvals, referrals, breaches).

    ``policy`` is an optional policy object; without it the server's policy applies.
    """
    applied, warnings = _issues(requests, policy)
    pack = build_board_pack(requests, period, applied).to_dict()
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="legal-function-os-mcp",
        description=(
            "Local stdio MCP server with four read-only tools: triage_requests, board_pack, "
            "dpa_review and legal_request_schema. Tools take data, never file paths."
        ),
    )
    parser.add_argument(
        "--policy",
        metavar="PATH",
        help=(
            "Apply this policy file (the format legal-function-os init writes) to every call "
            "that carries no inline policy object. Default: the bundled illustrative policy."
        ),
    )
    return parser.parse_args(argv)


def configure(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the options and apply ``--policy`` once; a policy that cannot be applied exits with status 2."""

    args = parse_args(argv)
    if args.policy:
        try:
            set_server_policy(load_policy(args.policy))
        except PolicyError as exc:
            for problem in exc.problems:
                print(f"error: {exc.source}: {problem}", file=sys.stderr)
            print("The policy cannot be applied. The server was not started.", file=sys.stderr)
            raise SystemExit(2) from None
    return args


def main(argv: list[str] | None = None) -> None:
    configure(argv)
    build_server().run()


if __name__ == "__main__":
    main()
