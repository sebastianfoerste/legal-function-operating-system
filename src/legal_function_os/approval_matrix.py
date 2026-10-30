"""Who must sign off, by value band and risk, read from the rules and the policy.

Every cell is ``rules.approval_chain`` for one value band and risk level of the policy,
so the matrix cannot drift from the rules. A combination that no request can reach is
marked as such: reachability comes from running ``rules.assess_risk`` over every
combination of the request fields it reads. The portfolio's requests are placed in the
cell each of them lands in. Deterministic; nothing reads a clock. The chain names who
must sign off; the matrix approves nothing.
"""

from __future__ import annotations

import html
import json
from itertools import product
from pathlib import Path
from typing import Any

from legal_function_os.design_tokens import TOKENS_CSS
from legal_function_os.policy import Policy, default_policy
from legal_function_os.rules import approval_chain, assess_risk, decide

SCHEMA = "legal-function-os.approval-matrix.v1"
RISKS = ("LOW", "MEDIUM", "HIGH")
# The request fields assess_risk reads; tests fail if it starts reading another one.
RISK_FIELDS = ("value_band", "personal_data", "non_eea_transfer", "uncapped_liability", "type")


def _risk_inputs(policy: Policy) -> list[dict[str, Any]]:
    """Every combination of the risk fields: each band, flag and kind of request type."""

    # "" stands for every type that is neither elevated nor a dispute.
    types = list(dict.fromkeys(("", *policy.elevated_types, "dispute")))
    return [
        {
            "value_band": band,
            "personal_data": personal,
            "non_eea_transfer": non_eea,
            "uncapped_liability": uncapped,
            "type": request_type,
        }
        for band in policy.value_bands
        for personal, non_eea, uncapped in product((False, True), repeat=3)
        for request_type in types
    ]


def _band(policy: Policy, value_band: str | None) -> str:
    """The policy band a request counts as; a request without one is in the lowest."""

    return policy.value_bands[policy.band_index(value_band)]


def _unreachable(risk: str, reached: set[str]) -> str:
    lowest = min(reached, key=RISKS.index)
    if RISKS.index(risk) < RISKS.index(lowest):
        if lowest == "HIGH":
            return "Every request in this band is HIGH risk."
        return f"Every request in this band is at least {lowest} risk."
    return f"No combination of request details gives {risk} risk in this band."


def build_approval_matrix(
    requests: list[dict[str, Any]] | None = None, policy: Policy | None = None
) -> dict[str, Any]:
    """The approval matrix of ``policy`` (the bundled default without one)."""

    rules = policy if policy is not None else default_policy()
    reached: dict[str, set[str]] = {band: set() for band in rules.value_bands}
    for request in _risk_inputs(rules):
        reached[request["value_band"]].add(assess_risk(request, rules)[0])

    placed: dict[tuple[str, str], list[str]] = {}
    portfolio = []
    for request in sorted(requests or [], key=lambda item: str(item.get("id", ""))):
        decision = decide(request, rules)
        band = _band(rules, request.get("value_band"))
        placed.setdefault((band, decision.risk), []).append(decision.request_id)
        portfolio.append(
            {
                "request_id": decision.request_id,
                "title": decision.title,
                "value_band": band,
                "risk": decision.risk,
                "approval_chain": decision.approval_chain,
            }
        )

    rows = []
    for band in rules.value_bands:
        cells = []
        for risk in RISKS:
            reachable = risk in reached[band]
            cells.append(
                {
                    "risk": risk,
                    "reachable": reachable,
                    "approval_chain": (
                        approval_chain({"value_band": band}, risk, rules) if reachable else []
                    ),
                    "unreachable_reason": None if reachable else _unreachable(risk, reached[band]),
                    "requests": placed.get((band, risk), []),
                }
            )
        rows.append({"value_band": band, "cells": cells})

    medium_any = [
        f'Value band "{rules.medium_risk_from.value_band}" or above',
        "Personal data processed",
    ]
    if rules.elevated_types:
        medium_any.append("Request type " + ", ".join(rules.elevated_types))
    return {
        "schema": SCHEMA,
        "policy": rules.name,
        "approval_ladder": [
            {"when": "Every request", "adds": "Reviewer"},
            {"when": f'Value band "{rules.legal_ops_lead_from}" or above', "adds": "Legal Ops Lead"},
            {
                "when": f'Value band "{rules.general_counsel_from}" or above, or HIGH risk',
                "adds": "General Counsel",
            },
            {"when": f'Value band "{rules.board_note_from}" or above', "adds": "Board note"},
        ],
        "risk_ladder": [
            {
                "risk": "HIGH",
                "any_of": [
                    "Personal data transferred outside the EEA",
                    f'Value band "{rules.high_risk_from.value_band}" or above',
                    "Uncapped liability",
                    f'A dispute at value band "{rules.dispute_high_risk_from.value_band}" or above',
                ],
            },
            {"risk": "MEDIUM", "any_of": medium_any},
            {"risk": "LOW", "any_of": []},  # otherwise
        ],
        "rows": rows,
        "requests": portfolio,
        "review_gate": (
            "The chain names who must sign off before a request can close. Every chain "
            "starts with a human reviewer, and the matrix approves nothing."
        ),
    }


def _risk_step(step: dict[str, Any]) -> str:
    if not step["any_of"]:
        return f"{step['risk']} otherwise."
    return f"{step['risk']} if any of: " + "; ".join(step["any_of"]) + "."


def _chain_text(chain: list[str]) -> str:
    return " → ".join(chain)


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _cell_md(cell: dict[str, Any]) -> str:
    if not cell["reachable"]:
        return "Not reachable"
    text = _chain_text(cell["approval_chain"])
    if cell["requests"]:
        text += " (" + ", ".join(cell["requests"]) + ")"
    return _md_cell(text)


def render_approval_markdown(matrix: dict[str, Any]) -> str:
    lines = [
        "# Approval matrix",
        "",
        f"Policy: {matrix['policy']}. {matrix['review_gate']}",
        "",
        "## Who is added to the chain",
        "",
        *(f"- {step['when']}: {step['adds']}" for step in matrix["approval_ladder"]),
        "",
        "## What sets the risk",
        "",
    ]
    for step in matrix["risk_ladder"]:
        lines.append(f"- {_risk_step(step)}")
    lines += [
        "",
        "## Chain by value band and risk",
        "",
        "Portfolio requests are in brackets in the cell they land in.",
        "",
        "| Value band | " + " | ".join(RISKS) + " |",
        "| --- | " + " | ".join("---" for _ in RISKS) + " |",
    ]
    for row in matrix["rows"]:
        cells = " | ".join(_cell_md(cell) for cell in row["cells"])
        lines.append(f"| {_md_cell(row['value_band'])} | {cells} |")
    lines += ["", "## Portfolio requests", ""]
    if not matrix["requests"]:
        lines.append("No request was given.")
    else:
        lines += [
            "| Request | Title | Value band | Risk | Approval chain |",
            "| --- | --- | --- | --- | --- |",
        ]
        for item in matrix["requests"]:
            lines.append(
                f"| {_md_cell(item['request_id'])} | {_md_cell(item['title'])} "
                f"| {_md_cell(item['value_band'])} | {item['risk']} "
                f"| {_md_cell(_chain_text(item['approval_chain']))} |"
            )
    return "\n".join(lines) + "\n"


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _cell_html(cell: dict[str, Any]) -> str:
    label = f' data-label="{cell["risk"]} risk"'
    if not cell["reachable"]:
        return (
            f'<td class="unreachable"{label}><span class="muted">Not reachable.</span> '
            f'{_esc(cell["unreachable_reason"])}</td>'
        )
    steps = "".join(f"<li>{_esc(step)}</li>" for step in cell["approval_chain"])
    matched = ""
    cls = ""
    if cell["requests"]:
        count = len(cell["requests"])
        cls = ' class="matched"'
        matched = (
            f'<p class="match">✓ {count} portfolio request{"" if count == 1 else "s"}: '
            f'{_esc(", ".join(cell["requests"]))}</p>'
        )
    return f'<td{cls}{label}><ol class="chain">{steps}</ol>{matched}</td>'


def render_approval_html(matrix: dict[str, Any]) -> str:
    approval = "".join(
        f"<li><strong>{_esc(step['when'])}:</strong> {_esc(step['adds'])}</li>"
        for step in matrix["approval_ladder"]
    )
    risk = "".join(
        f"<li><strong>{_esc(step['risk'])}</strong> {_esc(_risk_step(step)[len(step['risk']) + 1:])}</li>"
        for step in matrix["risk_ladder"]
    )
    header = "".join(f'<th scope="col">{risk} risk</th>' for risk in RISKS)
    rows = "".join(
        f'<tr><th scope="row" data-label="Value band">{_esc(row["value_band"])}</th>'
        + "".join(_cell_html(cell) for cell in row["cells"])
        + "</tr>"
        for row in matrix["rows"]
    )
    portfolio = (
        "".join(
            "<tr>"
            f'<td class="nowrap" data-label="Request">{_esc(item["request_id"])}</td>'
            f'<td data-label="Title">{_esc(item["title"])}</td>'
            f'<td class="nowrap" data-label="Value band">{_esc(item["value_band"])}</td>'
            f'<td class="nowrap" data-label="Risk">{_esc(item["risk"])}</td>'
            f'<td data-label="Approval chain">{_esc(_chain_text(item["approval_chain"]))}</td>'
            "</tr>"
            for item in matrix["requests"]
        )
        or '<tr><td colspan="5">No request was given.</td></tr>'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Approval matrix</title>
<style>
{TOKENS_CSS}* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 var(--font); }}
main {{ max-width:1100px; margin:0 auto; padding:40px 20px 64px; }}
h1 {{ margin:0 0 8px; font:600 32px/1.15 var(--font-head); }}
h2 {{ margin:32px 0 10px; font-size:18px; }}
.eyebrow {{ margin:0 0 6px; color:var(--accent); font-weight:700; font-size:12px; letter-spacing:.08em; text-transform:uppercase; }}
.muted {{ color:var(--muted); }}
section {{ margin-top:18px; padding:18px 20px; background:var(--surface); border:1px solid var(--line); border-radius:10px; overflow-wrap:break-word; }}
section h2 {{ margin-top:0; }}
.nowrap {{ white-space:nowrap; }}
ol.ladder {{ margin:0; padding-left:22px; }} ol.ladder li {{ margin:4px 0; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:10px; border:1px solid var(--line); text-align:left; vertical-align:top; }}
thead th {{ background:var(--panel); }}
th[scope="row"] {{ background:var(--panel); white-space:nowrap; }}
ol.chain {{ margin:0; padding-left:20px; }}
td.matched {{ background:var(--accent-soft); box-shadow:inset 4px 0 0 var(--accent); }}
td.unreachable {{ color:var(--muted); }}
p.match {{ margin:8px 0 0; font-weight:600; }}
@media (max-width:640px) {{
  main {{ padding:28px 16px 48px; }}
  table, tbody, tr, th, td {{ display:block; width:100%; }}
  thead {{ display:none; }}
  tr {{ margin:0 0 12px; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
  th, td {{ border:0; border-top:1px solid var(--line); }}
  tr > :first-child {{ border-top:0; }}
  td[data-label]::before, th[data-label]::before {{ content:attr(data-label); display:block; font-weight:700; font-size:12px; color:var(--muted); }}
  .nowrap {{ white-space:normal; }}
}}
</style>
</head>
<body>
<main>
<p class="eyebrow">Approval routing · synthetic demonstration</p>
<h1>Approval matrix</h1>
<p class="muted">Policy: {_esc(matrix['policy'])}. {_esc(matrix['review_gate'])} Nothing here is legal advice.</p>
<section aria-labelledby="ladder-h"><h2 id="ladder-h">Who is added to the chain</h2><ol class="ladder">{approval}</ol></section>
<section aria-labelledby="risk-h"><h2 id="risk-h">What sets the risk</h2><ol class="ladder">{risk}</ol></section>
<section aria-labelledby="matrix-h"><h2 id="matrix-h">Chain by value band and risk</h2>
<p class="muted">Each cell is the approval chain the rules give. Cells marked ✓ hold portfolio requests.</p>
<table><thead><tr><th scope="col">Value band</th>{header}</tr></thead><tbody>{rows}</tbody></table></section>
<section aria-labelledby="portfolio-h"><h2 id="portfolio-h">Portfolio requests</h2>
<table><thead><tr><th scope="col">Request</th><th scope="col">Title</th><th scope="col">Value band</th><th scope="col">Risk</th><th scope="col">Approval chain</th></tr></thead><tbody>{portfolio}</tbody></table></section>
</main>
</body>
</html>
"""


def write_approval_matrix(matrix: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_dir / "approval-matrix.json",
        "markdown": output_dir / "approval-matrix.md",
        "html": output_dir / "approval-matrix.html",
    }
    paths["json"].write_text(json.dumps(matrix, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["markdown"].write_text(render_approval_markdown(matrix), encoding="utf-8")
    paths["html"].write_text(render_approval_html(matrix), encoding="utf-8")
    return paths
