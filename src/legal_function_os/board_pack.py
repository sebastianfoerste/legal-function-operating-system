"""Aggregates per-request decisions into a board-ready legal operations pack."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from legal_function_os.rules import Decision, decide

DISCLAIMER = (
    "Board pack generated from deterministic legal-operations rules over synthetic "
    "requests. It is a management and triage artifact, not legal advice, and does not "
    "establish a lawyer-client relationship."
)


@dataclass
class BoardPack:
    title: str
    period: str
    totals: dict[str, Any]
    by_type: dict[str, int]
    by_priority: dict[str, int]
    by_risk: dict[str, int]
    by_queue: dict[str, int]
    approvals_pending: dict[str, int]
    external_referrals: list[dict[str, str]]
    board_attention: list[dict[str, str]]
    sla_breaches: list[dict[str, str]]
    decisions: list[Decision]

    def to_dict(self) -> dict[str, Any]:
        d = {
            "title": self.title,
            "period": self.period,
            "disclaimer": DISCLAIMER,
            "totals": self.totals,
            "by_type": self.by_type,
            "by_priority": self.by_priority,
            "by_risk": self.by_risk,
            "by_queue": self.by_queue,
            "approvals_pending": self.approvals_pending,
            "external_referrals": self.external_referrals,
            "board_attention": self.board_attention,
            "sla_breaches": self.sla_breaches,
            "decisions": [dec.to_dict() for dec in self.decisions],
        }
        return d


def build_board_pack(requests: list[dict], period: str = "current period") -> BoardPack:
    decisions = [decide(r) for r in requests]

    by_type = dict(Counter(d.type for d in decisions))
    by_priority = dict(Counter(d.priority for d in decisions))
    by_risk = dict(Counter(d.risk for d in decisions))
    by_queue = dict(Counter(d.queue for d in decisions))

    approvals_pending: Counter = Counter()
    for d in decisions:
        # The highest tier in the chain is the binding approver.
        approvals_pending[d.approval_chain[-1]] += 1

    external_referrals = [
        {"id": d.request_id, "title": d.title, "referral": d.external_counsel}
        for d in decisions
        if d.external_counsel != "in-house"
    ]
    board_attention = [
        {"id": d.request_id, "title": d.title, "risk": d.risk, "type": d.type}
        for d in decisions
        if d.board_attention
    ]
    sla_breaches = [
        {"id": r.get("id", "REQ-?"), "title": r.get("title", "")}
        for r in requests
        if r.get("sla_breached")
    ]

    totals = {
        "requests": len(decisions),
        "high_risk": by_risk.get("HIGH", 0),
        "external_referrals": len(external_referrals),
        "board_attention_items": len(board_attention),
        "sla_breaches": len(sla_breaches),
        "gc_approvals_required": sum(1 for d in decisions if "General Counsel" in d.approval_chain),
    }

    return BoardPack(
        title="Legal Function — Board Operations Pack",
        period=period,
        totals=totals,
        by_type=by_type,
        by_priority=by_priority,
        by_risk=by_risk,
        by_queue=by_queue,
        approvals_pending=dict(approvals_pending),
        external_referrals=external_referrals,
        board_attention=board_attention,
        sla_breaches=sla_breaches,
        decisions=decisions,
    )


def _kv_table(title: str, data: dict[str, Any]) -> list[str]:
    lines = [f"### {title}", "", "| Key | Count |", "| --- | --- |"]
    for k, v in sorted(data.items(), key=lambda kv: (-kv[1] if isinstance(kv[1], int) else 0, str(kv[0]))):
        lines.append(f"| {k} | {v} |")
    lines.append("")
    return lines


def render_markdown(pack: BoardPack) -> str:
    t = pack.totals
    lines: list[str] = []
    lines.append(f"# {pack.title}")
    lines.append("")
    lines.append(f"_Period: {pack.period}_")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(
        f"- **{t['requests']}** legal requests handled · **{t['high_risk']}** high-risk"
    )
    lines.append(
        f"- **{t['gc_approvals_required']}** require GC sign-off · "
        f"**{t['board_attention_items']}** flagged for board attention"
    )
    lines.append(
        f"- **{t['external_referrals']}** external-counsel referrals · "
        f"**{t['sla_breaches']}** SLA breaches"
    )
    lines.append("")

    if pack.board_attention:
        lines.append("## Board attention")
        lines.append("")
        lines.append("| ID | Title | Risk | Type |")
        lines.append("| --- | --- | --- | --- |")
        for item in pack.board_attention:
            lines.append(f"| {item['id']} | {item['title']} | {item['risk']} | {item['type']} |")
        lines.append("")

    if pack.sla_breaches:
        lines.append("## SLA breaches")
        lines.append("")
        for item in pack.sla_breaches:
            lines.append(f"- {item['id']} — {item['title']}")
        lines.append("")

    if pack.external_referrals:
        lines.append("## External-counsel referrals")
        lines.append("")
        lines.append("| ID | Title | Referral |")
        lines.append("| --- | --- | --- |")
        for item in pack.external_referrals:
            lines.append(f"| {item['id']} | {item['title']} | {item['referral']} |")
        lines.append("")

    lines.extend(_kv_table("By risk", pack.by_risk))
    lines.extend(_kv_table("By priority", pack.by_priority))
    lines.extend(_kv_table("By queue", pack.by_queue))
    lines.extend(_kv_table("By type", pack.by_type))
    lines.extend(_kv_table("Pending approvals (binding tier)", pack.approvals_pending))

    lines.append("## Request register")
    lines.append("")
    lines.append("| ID | Title | Risk | Priority | Queue | Approver | Counsel |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for d in pack.decisions:
        lines.append(
            f"| {d.request_id} | {d.title} | {d.risk} | {d.priority} | {d.queue} | "
            f"{d.approval_chain[-1]} | {d.external_counsel} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"_{DISCLAIMER}_")
    lines.append("")
    return "\n".join(lines)
