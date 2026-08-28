#!/usr/bin/env python3
"""Assemble the published reviewer site from generated artifacts.

The site hosts the self-contained HTML and SVG artifacts so a reviewer can read
them in a browser without cloning. Markdown and JSON artifacts stay on GitHub,
where they already render, and are linked rather than copied.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
REPO = "https://github.com/sebastianfoerste/legal-function-operating-system"
BLOB = f"{REPO}/blob/main"

# (source, destination) for artifacts served directly from the site.
HOSTED = (
    (ROOT / "examples" / "legal-outcome-control-tower.html", "legal-outcome-control-tower.html"),
    (ROOT / "examples" / "raas-deal-room.html", "raas-deal-room.html"),
    (ROOT / "examples" / "raas-deal-desk.svg", "raas-deal-desk.svg"),
    (ROOT / "docs" / "architecture.svg", "architecture.svg"),
    (ROOT / "docs" / "demo.svg", "demo.svg"),
)

# (title, href, blurb, kind) — kind drives the badge on each card.
CARDS = (
    (
        "Board operations pack",
        f"{BLOB}/examples/board-pack.md",
        "Executive roll-up over eight synthetic requests: three board-attention items, "
        "one SLA breach, three external-counsel referrals.",
        "GitHub",
    ),
    (
        "Outcome control tower",
        "legal-outcome-control-tower.html",
        "Business-time SLAs, wait-state reconciliation, effort calibration, the "
        "stalled-work queue and value proxies over a versioned service-event ledger.",
        "Hosted",
    ),
    (
        "Industrial RaaS deal room",
        "raas-deal-room.html",
        "Clause-level playbook reviews, signing blockers, named approvers, Finance "
        "review questions and a regulatory readiness matrix. Signing answer: do not sign.",
        "Hosted",
    ),
    (
        "Deal decision cockpit",
        "raas-deal-desk.svg",
        "The specialist deal desk at a glance: blockers, approvals and referrals.",
        "Hosted",
    ),
    (
        "Capacity simulation",
        f"{BLOB}/examples/legal-capacity-simulation.md",
        "Which constraint actually binds — queue throughput, General Counsel approval "
        "or external-counsel coordination — and the minimum uplift that clears it.",
        "GitHub",
    ),
    (
        "Architecture flow",
        "architecture.svg",
        "Intake through risk, priority, routing, SLA, approval matrix, external "
        "counsel, escalation and board reporting.",
        "Hosted",
    ),
    (
        "Shared control contract",
        f"{BLOB}/contracts/README.md",
        "The versioned interoperability boundary between the operating model and the "
        "supervised agent: review state, approval gates, source boundaries, audit events.",
        "GitHub",
    ),
    (
        "DPA clause review",
        f"{BLOB}/data/dpa_documents.json",
        "Art. 28 Abs. 3 lit. a to h DSGVO coverage across two synthetic agreements, "
        "returning pass, review or missing per requirement with pinpoint citations.",
        "GitHub",
    ),
)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legal Function Operating System</title>
<style>
:root {{
  --bg:#fbf9f7; --surface:#ffffff; --ink:#211d1c; --muted:#6e6462;
  --line:#e2dad4; --accent:#8a2d2b; --accent-soft:#f2e4e2;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#191413; --surface:#221c1a; --ink:#ede7e4; --muted:#a89c98;
    --line:#38302d; --accent:#d97d75; --accent-soft:#3a2523;
  }}
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.6 "Public Sans", -apple-system, "Segoe UI", sans-serif;
  padding:3.5rem 1.25rem 5rem;
}}
main {{ max-width:56rem; margin:0 auto; }}
.eyebrow {{
  font-size:.72rem; text-transform:uppercase; letter-spacing:.14em;
  color:var(--accent); font-weight:700; margin-bottom:.6rem;
}}
h1 {{ font:600 2.4rem/1.15 Georgia, serif; margin:0 0 .75rem; text-wrap:balance; }}
.lede {{ color:var(--muted); max-width:42rem; margin:0 0 1.5rem; font-size:1.05rem; }}
.note {{
  border-left:3px solid var(--accent); background:var(--accent-soft);
  padding:.9rem 1.15rem; border-radius:0 6px 6px 0; margin:0 0 2.5rem;
  font-size:.95rem;
}}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(17rem,1fr)); gap:1rem; }}
a.card {{
  display:block; background:var(--surface); border:1px solid var(--line);
  border-radius:8px; padding:1.1rem 1.25rem; text-decoration:none; color:inherit;
  transition:border-color .15s ease, transform .15s ease;
}}
a.card:hover, a.card:focus-visible {{ border-color:var(--accent); transform:translateY(-2px); }}
a.card h2 {{ margin:0 0 .35rem; font-size:1.05rem; font-weight:700; }}
a.card p {{ margin:0; color:var(--muted); font-size:.9rem; }}
.badge {{
  display:inline-block; font-size:.65rem; font-weight:700; text-transform:uppercase;
  letter-spacing:.08em; padding:.1rem .45rem; border-radius:999px;
  border:1px solid var(--line); color:var(--muted); margin-bottom:.5rem;
}}
footer {{
  margin-top:3rem; padding-top:1.5rem; border-top:1px solid var(--line);
  color:var(--muted); font-size:.85rem;
}}
footer a {{ color:var(--accent); }}
code {{
  font-family:"IBM Plex Mono", ui-monospace, "SF Mono", monospace;
  font-size:.87em; background:var(--accent-soft); color:var(--ink);
  padding:.1em .35em; border-radius:3px;
}}
:focus-visible {{ outline:2px solid var(--accent); outline-offset:3px; }}
</style>
</head>
<body>
<main>
  <p class="eyebrow">Reviewer artifacts</p>
  <h1>Legal Function Operating System</h1>
  <p class="lede">A deterministic operating model for intake, risk, priority, routing,
  service levels, approvals, external-counsel decisions, escalation and board reporting.
  Every artifact below is generated by <code>make demo</code> and committed to the
  repository.</p>
  <p class="note"><strong>All data is synthetic.</strong> These are reviewable
  prototypes, not claims of production deployment. Nothing here is legal advice, and
  every consequential decision stays behind human review.</p>
  <div class="grid">
{cards}
  </div>
  <footer>
    <p>Source, tests and known limitations: <a href="{repo}">{repo}</a>.
    Run the full gate with <code>make check</code>.</p>
  </footer>
</main>
</body>
</html>
"""

CARD = """    <a class="card" href="{href}">
      <span class="badge">{kind}</span>
      <h2>{title}</h2>
      <p>{blurb}</p>
    </a>"""


def main() -> int:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    missing = [str(src.relative_to(ROOT)) for src, _ in HOSTED if not src.exists()]
    if missing:
        raise SystemExit(f"missing artifact, run make demo first: {', '.join(missing)}")

    for src, name in HOSTED:
        shutil.copyfile(src, SITE / name)

    cards = "\n".join(
        CARD.format(href=href, kind=kind, title=title, blurb=blurb)
        for title, href, blurb, kind in CARDS
    )
    (SITE / "index.html").write_text(
        PAGE.format(cards=cards, repo=REPO), encoding="utf-8"
    )
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    print(f"site built with {len(HOSTED)} hosted artifacts and {len(CARDS)} cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
