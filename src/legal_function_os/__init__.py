"""legal_function_os — a deterministic legal function operating system.

Routes synthetic legal requests through intake -> risk -> priority -> queue ->
SLA -> approval matrix -> external-counsel decision tree -> escalation, and rolls
them up into a board-ready operations pack. Not legal advice; data is synthetic."""

from legal_function_os.rules import decide, Decision
from legal_function_os.board_pack import build_board_pack, render_markdown, BoardPack

__all__ = ["decide", "Decision", "build_board_pack", "render_markdown", "BoardPack"]
__version__ = "0.1.0"
