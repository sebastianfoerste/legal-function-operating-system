"""Deterministic Markdown, HTML, SVG, and JSON outputs for RaaS review."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Iterable

from legal_function_os.raas_models import RaaSDealPack


def render_raas_markdown(pack: RaaSDealPack) -> str:
    gate = pack.signing_gate
    facts = pack.deal_facts
    lines = [
        f"# {pack.title}",
        "",
        f"**Deal:** {pack.deal_id}",
        f"**Input contract:** `{pack.input_schema}`",
        f"**Verified legal-source snapshot:** {pack.verified_on}",
        f"**Signing decision:** {gate['answer']}",
        "",
        "## Executive signing gate",
        "",
        f"- Status: **{str(gate['status']).upper()}**",
        f"- Core blocking items: **{len(gate['blocking_items'])}**",
        f"- Signing-blocker regulatory controls: **{len(gate['blocking_regulatory_items'])}**",
        f"- Deployment-blocker regulatory controls: **{len(gate['blocking_deployment_items'])}**",
        f"- Required approvers: **{len(gate['required_approvals'])}**",
        f"- Ready for human approval: **{str(gate['ready_for_human_approval']).lower()}**",
        f"- Signature action allowed: **{str(gate['signature_action_allowed']).lower()}**",
        "",
        "### Core blocking items",
        "",
        *_gate_item_lines(gate["blocking_items"]),
        "",
        "### Regulatory signing blockers",
        "",
        *_regulatory_item_lines(gate["blocking_regulatory_items"]),
        "",
        "### Deployment blockers",
        "",
        *_regulatory_item_lines(gate["blocking_deployment_items"]),
        "",
        "### Transition follow-up",
        "",
        *_regulatory_item_lines(gate["transition_follow_up_items"]),
        "",
        "### Required approvals",
        "",
        *[f"- {approval}" for approval in gate["required_approvals"]],
        "",
        "### What could delay deployment",
        "",
        *[f"- {item}" for item in gate["deployment_delay_drivers"]],
        "",
        "### What could delay revenue",
        "",
        *[f"- {item}" for item in gate["revenue_delay_drivers"]],
        "",
        "## Deal facts",
        "",
        f"- Provider: {facts['provider']}",
        f"- Provider affiliate: {facts['provider_affiliate']}",
        f"- Customer: {facts['customer']}",
        f"- Customer affiliate: {facts['customer_affiliate']}",
        f"- Sites: {', '.join(facts['sites'])}",
        f"- Commercial model: {facts['commercial_model']}",
        f"- Annual contract value: {facts['annual_contract_value']} {facts['currency']}",
        f"- Term: {facts['term_months']} months",
        f"- Requested governing law: {facts['governing_law_request']}",
        f"- Requested signing date: {facts['requested_signing_date']}",
        "",
        "## Negotiation playbook",
        "",
        "| Rule | Category | Severity | Issue | Standard position | Fallback | Approvals |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in pack.clause_reviews:
        lines.append(
            _table_row(
                item.rule_id,
                item.category,
                item.severity,
                item.issue,
                item.standard_position,
                item.fallback_position,
                ", ".join(item.required_approvals),
            )
        )

    lines.extend(
        [
            "",
            "## Finance handoff",
            "",
            "Every item requires Finance validation. The output makes no accounting conclusion.",
            "",
            "| ID | Topic | Status | Finance question | Legal action | Framework |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in pack.finance_handoff:
        lines.append(
            _table_row(
                item.issue_id,
                item.topic,
                item.status,
                item.question,
                item.legal_action,
                item.framework,
            )
        )

    lines.extend(
        [
            "",
            "## Regulatory readiness matrix",
            "",
            "| Control | Regime | Actor | Status | Gate effect | Deal question | Owner | Target | Source |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in pack.regulatory_readiness:
        lines.append(
            _table_row(
                item.control_id,
                item.regime,
                item.actor,
                item.status,
                item.gate_effect,
                item.obligation_or_question,
                item.owner,
                item.target_date,
                f"[{item.source_id}]({item.source_url})",
            )
        )

    lines.extend(["", "## External-counsel instruction packs", ""])
    for brief in pack.external_counsel_briefs:
        lines.extend(
            [
                f"### {brief.brief_id}: {brief.workstream}",
                "",
                f"- Jurisdiction: {brief.jurisdiction}",
                f"- Question: {brief.question}",
                f"- Deliverable: {brief.deliverable}",
                f"- Deadline: {brief.deadline}",
                f"- Budget ceiling: {brief.budget_ceiling}",
                f"- Internal owner: {brief.internal_owner}",
                f"- Approval required: {brief.approval_required}",
                f"- External action allowed: {str(brief.external_action_allowed).lower()}",
                "",
                "Facts:",
                "",
                *[f"- {fact}" for fact in brief.facts],
                "",
                "Assumptions:",
                "",
                *[f"- {assumption}" for assumption in brief.assumptions],
                "",
            ]
        )

    lines.extend(["## Founding General Counsel 100-day plan", ""])
    for phase in pack.hundred_day_plan:
        lines.extend(
            [
                f"### {phase.phase}",
                "",
                phase.objective,
                "",
                *[f"- {item}" for item in phase.deliverables],
                "",
                f"**Proof metric:** {phase.proof_metric}",
                "",
            ]
        )

    lines.extend(["## Primary-source manifest", ""])
    for source in pack.source_manifest:
        lines.append(
            f"- **[{source['id']}]({source['url']}):** {source['title']}, "
            f"{source['pinpoint']}. Legal effect: `{source['legal_effect']}`. "
            f"{source['timing']}"
        )
    lines.extend(
        [
            "",
            f"Source digest: `{pack.source_digest}`",
            "",
            f"_{pack.disclaimer}_",
            "",
        ]
    )
    return "\n".join(lines)


def render_raas_html(pack: RaaSDealPack) -> str:
    gate = pack.signing_gate
    blockers = "".join(
        (
            '<article class="issue critical">'
            f"<span>{html.escape(str(item.get('rule_id') or item.get('issue_id')))}</span>"
            f"<h3>{html.escape(str(item.get('category') or item.get('topic')))}</h3>"
            f"<p>{html.escape(str(item.get('issue') or item.get('question')))}</p>"
            "</article>"
        )
        for item in gate["blocking_items"]
    )
    playbook_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(item.rule_id)}</code></td>"
        f"<td>{html.escape(item.category)}</td>"
        f'<td><span class="badge {item.severity}">{html.escape(item.severity)}</span></td>'
        f"<td>{html.escape(item.issue)}</td>"
        f"<td>{html.escape(', '.join(item.required_approvals))}</td>"
        "</tr>"
        for item in pack.clause_reviews
    )
    finance_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(item.issue_id)}</code></td>"
        f"<td>{html.escape(item.topic)}</td>"
        f"<td>{html.escape(item.status)}</td>"
        f"<td>{html.escape(item.question)}</td>"
        "</tr>"
        for item in pack.finance_handoff
    )
    regulatory_rows = "".join(
        "<tr>"
        f"<td><code>{html.escape(item.control_id)}</code></td>"
        f"<td>{html.escape(item.regime)}</td>"
        f"<td>{html.escape(item.gate_effect)}</td>"
        f"<td>{html.escape(item.owner)}</td>"
        f'<td><a href="{html.escape(item.source_url)}">{html.escape(item.source_id)}</a></td>'
        "</tr>"
        for item in pack.regulatory_readiness
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(pack.title)}</title>
  <style>
    :root {{ color-scheme: light; --ink: #17202b; --muted: #64717d; --line: #d7dee4; --panel: #fff; --bg: #f3f6f7; --teal: #10383b; --danger: #a72e31; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 15px/1.5 system-ui, sans-serif; color: var(--ink); background: var(--bg); }}
    header {{ padding: 36px max(24px, calc((100% - 1120px) / 2)); color: white; background: var(--teal); }}
    header p {{ max-width: 820px; color: #c9e0e0; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    section {{ margin: 18px 0; padding: 22px; border: 1px solid var(--line); border-radius: 14px; background: var(--panel); }}
    .offline {{ margin: 0; padding: 10px 14px; border-radius: 8px; color: #355; background: #dceeee; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
    .metric {{ padding: 16px; border: 1px solid var(--line); border-radius: 12px; background: white; }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .metric strong {{ display: block; margin-top: 5px; font-size: 28px; }}
    .blocked strong {{ color: var(--danger); }}
    .issues {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .issue {{ padding: 14px; border: 1px solid var(--line); border-radius: 10px; }}
    .issue span {{ color: var(--danger); font: 12px ui-monospace, monospace; }}
    .issue h3 {{ margin: 5px 0; font-size: 15px; }}
    .issue p {{ margin: 0; color: var(--muted); }}
    .delay-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .badge {{ padding: 3px 7px; border-radius: 999px; background: #edf1f3; font-size: 12px; }}
    .nonstarter {{ color: var(--danger); background: #f9e1e1; }}
    .note {{ color: var(--muted); }}
    a {{ color: #176b72; }}
    @media (max-width: 760px) {{
      header {{ padding: 26px 18px; }}
      main {{ padding: 14px; }}
      section {{ padding: 16px; overflow-x: auto; }}
      .metrics, .issues, .delay-grid {{ grid-template-columns: 1fr; }}
      table {{ min-width: 720px; }}
    }}
  </style>
</head>
<body>
  <header>
    <p class="offline">Offline local reviewer artifact. Open this generated file locally. GitHub reviewers should start with the Markdown decision pack.</p>
    <h1>{html.escape(pack.title)}</h1>
    <p>{html.escape(str(pack.deal_facts['provider']))} and {html.escape(str(pack.deal_facts['customer']))}. Human review remains required for every consequential decision.</p>
  </header>
  <main>
    <div class="metrics">
      <div class="metric blocked"><span>Signing decision</span><strong>{html.escape(str(gate['status']).upper())}</strong></div>
      <div class="metric"><span>Core blockers</span><strong>{len(gate['blocking_items'])}</strong></div>
      <div class="metric"><span>Required approvers</span><strong>{len(gate['required_approvals'])}</strong></div>
      <div class="metric"><span>Regulatory controls</span><strong>{gate['open_regulatory_controls']}</strong></div>
    </div>
    <section>
      <h2>Can we sign?</h2>
      <p><strong>{html.escape(gate['answer'])}</strong></p>
      <div class="issues">{blockers}</div>
    </section>
    <section class="delay-grid">
      <div><h2>What could delay deployment?</h2>{_html_list(gate['deployment_delay_drivers'])}</div>
      <div><h2>What could delay revenue?</h2>{_html_list(gate['revenue_delay_drivers'])}</div>
    </section>
    <section>
      <h2>Negotiation playbook</h2>
      <table><thead><tr><th>Rule</th><th>Category</th><th>Severity</th><th>Issue</th><th>Approvers</th></tr></thead><tbody>{playbook_rows}</tbody></table>
    </section>
    <section>
      <h2>Finance handoff</h2>
      <p class="note">Questions for Finance under IFRS 15, ASC 606, and the applicable lease framework. No accounting conclusion is automated.</p>
      <table><thead><tr><th>ID</th><th>Topic</th><th>Status</th><th>Question</th></tr></thead><tbody>{finance_rows}</tbody></table>
    </section>
    <section>
      <h2>Regulatory readiness</h2>
      <table><thead><tr><th>Control</th><th>Regime</th><th>Gate effect</th><th>Owner</th><th>Source</th></tr></thead><tbody>{regulatory_rows}</tbody></table>
    </section>
    <section><h2>Review boundary</h2><p>{html.escape(pack.disclaimer)}</p></section>
  </main>
</body>
</html>
"""


def render_raas_svg(pack: RaaSDealPack) -> str:
    gate = pack.signing_gate
    visible = gate["blocking_items"][:5]
    additional = max(0, len(gate["blocking_items"]) - len(visible))
    rows = []
    for index, item in enumerate(visible, start=1):
        category = html.escape(str(item.get("category") or item.get("topic")))
        y = 385 + ((index - 1) * 42)
        rows.append(
            f'<text x="84" y="{y}" class="row-number">{index:02d}</text>'
            f'<text x="132" y="{y}" class="row-title">{category}</text>'
            f'<text x="920" y="{y}" class="row-status">BLOCKER</text>'
        )
    additional_line = (
        f'<text x="132" y="604" class="more">+ {additional} additional blockers in the decision pack</text>'
        if additional
        else ""
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 720" width="1200" height="720" style="max-width:100%;height:auto" role="img" aria-labelledby="title desc">
  <title id="title">RaaS Deal Decision Pack</title>
  <desc id="desc">Synthetic industrial robotics deal showing a blocked signing decision, seven core blockers, required approvers, and regulatory controls.</desc>
  <style>
    .eyebrow {{ font: 700 14px system-ui; letter-spacing: 2px; fill: #a9cccc; }}
    .hero {{ font: 700 44px system-ui; fill: #fff; }}
    .subtitle {{ font: 600 17px system-ui; fill: #c9dddd; }}
    .label {{ font: 700 14px system-ui; fill: #64717d; }}
    .metric {{ font: 700 32px system-ui; fill: #17202b; }}
    .danger {{ fill: #a72e31; }}
    .section {{ font: 700 23px system-ui; fill: #17202b; }}
    .row-number {{ font: 700 15px system-ui; fill: #6c7984; }}
    .row-title {{ font: 700 16px system-ui; fill: #17202b; }}
    .row-status {{ font: 700 13px system-ui; fill: #a72e31; }}
    .more {{ font: 600 14px system-ui; fill: #64717d; }}
    .foot {{ font: 14px system-ui; fill: #53636d; }}
  </style>
  <rect width="1200" height="720" fill="#f3f6f7"/>
  <rect width="1200" height="188" fill="#10383b"/>
  <text x="60" y="50" class="eyebrow">SYNTHETIC CROSS-BORDER INDUSTRIAL ROBOTICS DEAL</text>
  <text x="60" y="106" class="hero">RaaS Deal Decision Pack</text>
  <text x="60" y="146" class="subtitle">Can we sign, who must approve, and what could delay deployment or revenue?</text>
  <g>
    <rect x="60" y="150" width="250" height="112" rx="15" fill="#f9e1e1" stroke="#e7a3a5"/>
    <text x="84" y="184" class="label">SIGNING DECISION</text>
    <text x="84" y="229" class="metric danger">{html.escape(str(gate['status']).upper())}</text>
    <rect x="330" y="150" width="250" height="112" rx="15" fill="#fff" stroke="#d7dee4"/>
    <text x="354" y="184" class="label">CORE BLOCKING ITEMS</text>
    <text x="354" y="229" class="metric">{len(gate['blocking_items'])}</text>
    <rect x="600" y="150" width="250" height="112" rx="15" fill="#fff" stroke="#d7dee4"/>
    <text x="624" y="184" class="label">REQUIRED APPROVERS</text>
    <text x="624" y="229" class="metric">{len(gate['required_approvals'])}</text>
    <rect x="870" y="150" width="270" height="112" rx="15" fill="#fff" stroke="#d7dee4"/>
    <text x="894" y="184" class="label">REGULATORY CONTROLS</text>
    <text x="894" y="229" class="metric">{gate['open_regulatory_controls']}</text>
  </g>
  <rect x="60" y="286" width="1080" height="330" rx="16" fill="#fff" stroke="#d7dee4"/>
  <text x="84" y="326" class="section">Current core signing blockers</text>
  <line x1="84" y1="348" x2="1116" y2="348" stroke="#d7dee4"/>
  {''.join(rows)}
  {additional_line}
  <rect x="60" y="640" width="1080" height="58" rx="12" fill="#dceeee"/>
  <text x="84" y="675" class="foot">Human review gate: General Counsel plus accountable Finance, Product, Safety, Security, and Commercial owners.</text>
</svg>
"""


def write_raas_outputs(pack: RaaSDealPack, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "json": out_dir / "raas-deal-pack.json",
        "markdown": out_dir / "raas-deal-pack.md",
        "html": out_dir / "raas-deal-room.html",
        "svg": out_dir / "raas-deal-desk.svg",
        "sources": out_dir / "raas-source-manifest.json",
    }
    outputs["json"].write_text(
        json.dumps(pack.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    outputs["markdown"].write_text(render_raas_markdown(pack), encoding="utf-8")
    outputs["html"].write_text(render_raas_html(pack), encoding="utf-8")
    outputs["svg"].write_text(render_raas_svg(pack), encoding="utf-8")
    outputs["sources"].write_text(
        json.dumps(
            {
                "schema": "legal-function-os.source-manifest.v1",
                "verified_on": pack.verified_on,
                "source_digest": pack.source_digest,
                "sources": list(pack.source_manifest),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return outputs


def _gate_item_lines(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- None."]
    return [
        f"- **{item.get('rule_id') or item.get('issue_id')}:** "
        f"{item.get('issue') or item.get('question')}"
        for item in items
    ]


def _regulatory_item_lines(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- None."]
    return [
        f"- **{item['control_id']}:** {item['regime']}. "
        f"Owner: {item['owner']}. {item['question']}"
        for item in items
    ]


def _table_row(*values: Any) -> str:
    return "| " + " | ".join(_escape_markdown_table(str(value)) for value in values) + " |"


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _html_list(items: Iterable[str]) -> str:
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"
