"""Deterministic legal-function and industrial robotics deal-desk workflows.

The package routes synthetic legal requests through intake, risk, priority, queues,
SLAs, approval matrices, external-counsel decisions, and board reporting. It also
includes a synthetic RaaS deal desk with negotiation guardrails, Finance handoff,
regulatory readiness, and human approval gates. Not legal advice; data is synthetic.
"""

from legal_function_os.board_pack import BoardPack, build_board_pack, render_markdown
from legal_function_os.rules import Decision, decide

__all__ = ["decide", "Decision", "build_board_pack", "render_markdown", "BoardPack"]
__version__ = "0.3.0"
