"""Deterministic legal-function and industrial robotics deal-desk workflows.

The package routes synthetic legal requests through intake, risk, priority, queues,
SLAs, approval matrices, external-counsel decisions, and board reporting. It also
includes a synthetic RaaS deal desk with negotiation guardrails, Finance handoff,
regulatory readiness, and human approval gates. Not legal advice; data is synthetic.
"""

from legal_function_os.rules import decide, Decision
from legal_function_os.board_pack import build_board_pack, render_markdown, BoardPack

__all__ = ["decide", "Decision", "build_board_pack", "render_markdown", "BoardPack"]
__version__ = "0.2.0"
