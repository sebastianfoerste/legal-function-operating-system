"""The review room page. Self-contained: no external script, style or font.

Every action posts a command with the revision the page loaded. Nothing is kept in
the page: after each command it re-renders from the server's answer, and a stale
submission reloads the matter and tells the reviewer their input was not saved.
"""

REVIEW_ROOM_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pilot review room</title>
<style>
:root{--ink:#172033;--muted:#5b6577;--line:#d9dee8;--soft:#f4f6fa;--warn:#9a3412;--warnbg:#fff7ed;--ok:#166534;--bad:#b91c1c;--accent:#1d4ed8}
*{box-sizing:border-box}body{font:14.5px/1.45 system-ui,sans-serif;color:var(--ink);margin:0;background:#fff}
header{padding:12px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header h1{font-size:18px;margin:0}
.notice{background:var(--warnbg);border-bottom:1px solid #fed7aa;color:var(--warn);padding:8px 20px;font-weight:600}
main{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:80vh}
nav{border-right:1px solid var(--line);padding:14px}
nav button{display:block;width:100%;overflow-wrap:anywhere;text-align:left;margin:0 0 8px;padding:9px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer}
nav button.active{border-color:var(--accent);background:#eff6ff}
#matter{padding:16px 22px;min-width:0}
section{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:0 0 14px;overflow-x:auto}
h2{font-size:15.5px;margin:0 0 10px}h3{font-size:14px;margin:12px 0 6px}
table{width:100%;border-collapse:collapse;font-size:13.5px}th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}code{overflow-wrap:anywhere;font-size:12px}th{background:var(--soft)}
.pill{display:inline-block;white-space:nowrap;padding:2px 9px;border-radius:999px;background:var(--soft);border:1px solid var(--line);font-size:12.5px;margin-right:6px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.muted{color:var(--muted)}
button.act{padding:6px 11px;border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:7px;cursor:pointer;margin:3px 4px 3px 0}
button.act.secondary{background:#fff;color:var(--accent)}button.act:disabled{opacity:.45;cursor:not-allowed}
input,select,textarea{font:inherit;padding:5px 7px;border:1px solid var(--line);border-radius:6px;max-width:100%}
textarea{width:100%;min-height:54px}label{display:block;margin:6px 0 2px;font-size:12.5px;color:var(--muted)}
#flash{margin:0 0 14px;padding:10px 12px;border-radius:8px;display:none}
#flash.error{display:block;background:#fef2f2;border:1px solid #fecaca;color:var(--bad)}
#flash.info{display:block;background:#f0fdf4;border:1px solid #bbf7d0;color:var(--ok)}
table.changes{table-layout:fixed}table.changes th:nth-child(1){width:15%}table.changes th:nth-child(2){width:31%}table.changes th:nth-child(3){width:15%}table.changes th:nth-child(4){width:26%}table.changes th:nth-child(5){width:13%}del{color:var(--bad)}ins{color:var(--ok);text-decoration:none;font-weight:600}
details{margin:6px 0}summary{cursor:pointer;color:var(--accent)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
@media(max-width:820px){main{grid-template-columns:1fr}nav{border-right:0;border-bottom:1px solid var(--line)}}
</style>
</head>
<body>
<header>
  <h1>Pilot review room</h1>
  <label for="actor" style="margin:0">Simulated local role</label>
  <select id="actor"></select>
  <label for="effort" style="margin:0">Minutes spent on the next action</label>
  <input id="effort" type="number" min="0" max="600" style="width:80px">
</header>
<div class="notice" id="notice">Simulated local roles. Selecting an actor is not authentication. Synthetic data only. External delivery is disabled.</div>
<main>
  <nav><div id="create"></div><h2>Matters</h2><div id="list"></div></nav>
  <div id="matter"><div id="flash"></div><p class="muted">Choose a role, then a matter.</p></div>
</main>
<script>
"use strict";
const state = {actors: [], scenarios: [], actor: "", matterId: "", view: null};
const $ = (id) => document.getElementById(id);
function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === "onclick") node.addEventListener("click", value);
    else if (key === "class") node.className = value;
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}
function flash(kind, text) { const box = $("flash"); if (!box) return; box.className = kind; box.textContent = text; }
async function api(method, path, body) {
  const response = await fetch("/pilot/api" + path, {
    method, headers: {"Content-Type": "application/json", "X-Pilot-Actor": state.actor},
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json();
  return {status: response.status, payload};
}
function effort() { const value = parseInt($("effort").value, 10); $("effort").value = ""; return Number.isInteger(value) ? value : undefined; }
async function command(name, args) {
  const body = {command: name, expected_revision: state.view.matter.revision, args: args || {}, effort_minutes: effort()};
  const {status, payload} = await api("POST", "/matters/" + encodeURIComponent(state.matterId) + "/commands", body);
  if (status === 200) { state.view = payload; render(); flash("info", name.replaceAll("_", " ") + " saved."); await loadList(); return; }
  if (payload.error === "stale_submission") {
    await loadMatter(state.matterId);
    flash("error", "Not saved. The matter changed while you were working (now revision " + payload.current_revision + "). It has been reloaded; check it and submit again.");
    return;
  }
  await loadMatter(state.matterId);
  flash("error", payload.message || "Refused.");
}
async function loadList() {
  const {payload} = await api("GET", "/matters");
  const list = $("list"); list.replaceChildren();
  for (const matter of payload.matters || []) {
    list.append(h("button", {class: matter.matter_id === state.matterId ? "active" : "", onclick: () => loadMatter(matter.matter_id)},
      h("strong", null, matter.matter_id), h("br"), matter.title, h("br"), h("span", {class: "pill"}, matter.state), "v" + matter.current_version));
  }
  if (!(payload.matters || []).length) list.append(h("p", {class: "muted"}, "No matter is visible to this role."));
  const create = $("create"); create.replaceChildren();
  const actor = state.actors.find((a) => a.actor_id === state.actor);
  if (actor && actor.role === "business_requester") {
    create.append(h("h2", null, "Open a synthetic matter"));
    for (const scenario of state.scenarios) {
      create.append(h("button", {onclick: async () => {
        const {status, payload: made} = await api("POST", "/matters", {scenario_id: scenario.scenario_id, matter_id: "PM-UI-" + Date.now().toString(36).toUpperCase(), effort_minutes: effort()});
        if (status === 201) { await loadList(); await loadMatter(made.matter.matter_id); } else flash("error", made.message);
      }}, scenario.title));
    }
  }
}
async function loadMatter(id) {
  state.matterId = id;
  const {status, payload} = await api("GET", "/matters/" + encodeURIComponent(id));
  if (status !== 200) { $("matter").replaceChildren(h("div", {id: "flash"})); flash("error", payload.message); return; }
  state.view = payload; render(); await loadList();
}
function ask(label, minimum) { const text = window.prompt(label); if (text == null) return null; if (text.trim().length < (minimum || 0)) { flash("error", label + " (at least " + minimum + " characters)"); return null; } return text.trim(); }
function refs(label) { const text = window.prompt(label || "Evidence references, comma separated (for example synthetic:note-1)"); return text == null ? null : text.split(",").map((r) => r.trim()).filter(Boolean); }
function evidenceList(items) {
  return h("ul", null, items.map((e) => h("li", {class: e.ok ? "ok" : "bad"}, (e.ok ? "✓ " : "✗ ") + e.name.replaceAll("_", " ") + ": " + e.detail)));
}
const NOTE_COMMANDS = {approve: ["Approval note", 30], submit_revision: ["Revision note", 20], accept_delivery: ["Acceptance note", 20]};
function transitionButton(item, role) {
  const allowed = item.roles.includes(role);
  return h("button", {class: "act", disabled: !allowed, title: allowed ? "" : "Needs role: " + item.roles.join(", "), onclick: () => {
    if (item.command === "request_revision") {
      const open = state.view.comments.filter((c) => c.state === "open").map((c) => c.comment_id);
      const ids = window.prompt("Open comment ids this revision concerns, comma separated. Open: " + open.join(", "));
      if (ids == null) return; const note = ask("Reason for the revision", 20); if (note == null) return;
      return command("request_revision", {comment_ids: ids.split(",").map((s) => s.trim()).filter(Boolean), note});
    }
    const needs = NOTE_COMMANDS[item.command];
    if (!needs) return command(item.command);
    const note = ask(needs[0], needs[1]); if (note != null) command(item.command, {note});
  }}, item.command.replaceAll("_", " ") + " → " + item.target);
}
function renderRequester(view, root) {
  root.append(h("section", null, h("h2", null, "Your request"),
    h("p", null, h("span", {class: "pill"}, view.matter.state), "version " + view.matter.current_version),
    h("p", {class: "muted"}, "You see status, questions addressed to you and the approved package. Internal review comments are not shown."),
    view.matter.state === "intake" ? h("button", {class: "act", onclick: () => command("submit_intake")}, "submit intake") : null,
    h("button", {class: "act secondary", onclick: () => { const key = window.prompt("Fact to add or change (for example business_owner)"); if (!key) return; const value = window.prompt("New value"); if (value == null) return; const reason = ask("Reason for the change", 10); if (reason != null) command("amend_matter", {reason, facts: {[key.trim()]: value}}); }}, "add or change a fact"),
    view.matter.state === "ready_for_delivery" ? h("button", {class: "act", onclick: () => { const note = ask("Acceptance note", 20); if (note != null) command("accept_delivery", {note}); }}, "accept delivery") : null));
  root.append(h("section", null, h("h2", null, "Questions for you"),
    view.clarifications.length ? view.clarifications.map((c) => h("div", null, h("p", null, h("span", {class: "pill"}, c.state), c.body),
      c.responses.map((r) => h("p", {class: "muted"}, r.author_role + ": " + r.body)),
      c.state === "open" ? h("button", {class: "act", onclick: () => { const body = ask("Your answer", 10); if (body == null) return; const evidence = refs(); if (evidence != null) command("respond_comment", {comment_id: c.comment_id, body, evidence_refs: evidence}); }}, "answer") : null)) : h("p", {class: "muted"}, "None.")));
  root.append(h("section", null, h("h2", null, "Delivery package"),
    view.delivery.length ? h("a", {href: "/pilot/api/matters/" + encodeURIComponent(view.matter.matter_id) + "/package?actor=1", onclick: openPackage}, "Open the approved customer package") : h("p", {class: "muted"}, "No approved package yet.")));
}
async function openPackage(event) {
  event.preventDefault();
  const response = await fetch("/pilot/api/matters/" + encodeURIComponent(state.matterId) + "/package", {headers: {"X-Pilot-Actor": state.actor}});
  if (!response.ok) { flash("error", (await response.json()).message); return; }
  const frame = h("iframe", {title: "Customer package", style: "width:100%;height:80vh;border:1px solid #d9dee8;border-radius:10px", sandbox: ""});
  frame.srcdoc = await response.text();
  $("matter").append(h("section", null, h("h2", null, "Approved customer package (local copy)"), frame));
  frame.scrollIntoView();
}
function changeControls(change) {
  if (!["review", "revision_requested"].includes(state.view.matter.state)) return h("span", {class: "muted"}, "closed for decisions in this state");
  const confirm = "I checked that the cited source supports this wording for this matter";
  return h("div", null,
    h("button", {class: "act", onclick: () => { if (window.confirm(confirm + "?")) command("decide_change", {change_id: change.id, outcome: "accepted", source_support_confirmed: true}); }}, "accept"),
    h("button", {class: "act secondary", onclick: () => { const reason = ask("Reason for keeping the counterparty wording (accepted exception)", 20); if (reason != null) command("decide_change", {change_id: change.id, outcome: "rejected", reason}); }}, "reject"),
    h("button", {class: "act secondary", onclick: () => { const text = ask("Amended wording", 1); if (text == null) return; const reason = ask("Reason for the amended wording", 20); if (reason == null) return; if (window.confirm(confirm + "?")) command("decide_change", {change_id: change.id, outcome: "amended", amended_text: text, reason, source_support_confirmed: true}); }}, "amend"),
    h("button", {class: "act secondary", onclick: () => { const question = ask("Question for the requester", 10); if (question != null) command("decide_change", {change_id: change.id, outcome: "clarification_requested", reason: question}); }}, "ask requester"));
}
function renderReview(view, root) {
  const role = view.actor.role, version = view.version;
  root.append(h("section", null, h("h2", null, "State and next steps"),
    h("p", null, h("span", {class: "pill"}, view.matter.state), h("span", {class: "pill"}, "version " + version.version), h("span", {class: "pill"}, "revision " + view.matter.revision),
      h("span", {class: "pill"}, "risk " + version.routing.risk), h("span", {class: "pill"}, "queue " + version.routing.queue), h("span", {class: "pill"}, "approval tier " + version.required_final_tier)),
    version.scope_exclusions.length ? h("p", {class: "bad"}, "Outside the pilot charter: " + version.scope_exclusions.join("; ")) : null,
    view.allowed.length ? view.allowed.map((item) => h("div", null, transitionButton(item, role), item.evidence.length ? evidenceList(item.evidence) : null)) : h("p", {class: "muted"}, "No transition is available from this state."),
    h("button", {class: "act secondary", onclick: () => command("export_internal_review")}, "write internal review draft"),
    h("button", {class: "act secondary", onclick: () => { const reason = ask("Reason for closing without delivery", 20); if (reason != null) command("withdraw", {note: reason}); }}, "withdraw matter"),
    view.manifests.some((m) => m.kind === "delivery_package") ? h("a", {href: "#", onclick: openPackage}, "Open the approved customer package") : null));
  root.append(h("section", null, h("h2", null, "Readiness check"), evidenceList(view.readiness),
    h("h3", null, "Assignments"), h("p", null, Object.entries(view.assignments).map(([r, ids]) => r + ": " + ids.join(", ")).join(" | ")),
    role === "matter_owner" ? h("div", {class: "row"}, h("select", {id: "assignee"}, state.actors.filter((a) => ["specialist_reviewer", "final_approver"].includes(a.role)).map((a) => h("option", {value: a.actor_id + "|" + a.role}, a.display_name + (a.onboarded ? "" : " (not onboarded)")))),
      h("button", {class: "act secondary", onclick: () => { const [assignee_id, r] = $("assignee").value.split("|"); command("assign", {role: r, assignee_id}); }}, "assign")) : null));
  const support = Object.fromEntries(view.source_support.map((s) => [s.change_id, s]));
  root.append(h("section", null, h("h2", null, "Proposed changes (" + view.changes.length + ")"),
    view.changes.length ? h("table", {class: "changes"}, h("tr", null, ["Locator", "Wording", "Decision", "Source verification", "Action"].map((t) => h("th", null, t))),
      view.changes.map((c) => { const s = support[c.id]; return h("tr", null,
        h("td", null, c.locator, h("br"), h("span", {class: "muted"}, c.rule_id + (c.specialist_role ? " (" + c.specialist_role + ")" : ""))),
        h("td", null, h("del", null, c.original_text || "(nothing)"), h("br"), h("ins", null, c.proposed_text || "(delete clause)"), c.amended_text ? [h("br"), h("strong", null, "Amended: "), c.amended_text] : null, h("br"), h("span", {class: "muted"}, c.rationale)),
        h("td", null, h("span", {class: "pill"}, c.decision), c.decision_reason ? h("div", {class: "muted"}, c.decision_reason) : null, c.decided_by ? h("div", {class: "muted"}, "by " + c.decided_by) : null, c.carried_from_version ? h("div", {class: "muted"}, "carried from v" + c.carried_from_version) : null),
        h("td", null, s.sources.map((src) => h("div", null, h("code", null, src.source_ref), h("br"), "allowlist: " + src.allowlist_check.status + " (prefix only)", h("br"), "quote check: " + src.quote_check.status, h("br"), h("span", {class: "muted"}, "source version: " + Object.entries(src.source_version).map(([k, v]) => k + " " + String(v).slice(0, 12)).join(", ")))),
          h("div", {class: s.human_review.status === "confirmed" ? "ok" : "bad"}, "human review: " + s.human_review.status), h("div", {class: "muted"}, "Not verified by software: " + s.not_verified_by_software)),
        h("td", null, changeControls(c))); })) : h("p", {class: "muted"}, "No change proposed for this version.")));
  const anchors = [...view.findings.map((f) => ["finding", f.key, "finding: " + f.summary]), ...view.changes.map((c) => ["change", c.id, "change: " + c.id]),
    ...["executive_summary", "issue_and_deviation_list", "reviewed_document", "accepted_exceptions", "outstanding_obligations", "approval_record"].map((s) => ["deliverable_section", s, "deliverable: " + s.replaceAll("_", " ")])];
  root.append(h("section", null, h("h2", null, "Comments (" + view.comments.length + ")"),
    view.comments.map((c) => h("div", {style: "border-top:1px solid #d9dee8;padding:8px 0"},
      h("p", null, h("span", {class: "pill"}, c.comment_id), h("span", {class: "pill"}, c.kind), h("span", {class: "pill"}, c.severity), h("span", {class: "pill " + (c.state === "open" ? "bad" : "ok")}, c.state), c.blocking ? h("span", {class: "pill bad"}, "blocks approval") : null, c.anchor_status === "orphaned" ? h("span", {class: "pill bad"}, "anchor no longer in this version") : null),
      h("p", null, c.body), h("p", {class: "muted"}, "On " + c.anchor_kind + " " + c.anchor_id + ": " + c.anchor_excerpt + " | by " + c.author_id + ", version " + c.created_on_version),
      c.responses.map((r) => h("p", {class: "muted"}, r.author_id + ": " + r.body + (r.evidence_refs.length ? " [" + r.evidence_refs.join(", ") + "]" : ""))),
      c.resolution ? h("p", {class: "ok"}, "Resolved by " + c.resolved_by + ": " + c.resolution + " [" + c.resolution_evidence.join(", ") + "]") : null,
      h("button", {class: "act secondary", onclick: () => { const body = ask("Response", 10); if (body == null) return; const evidence = refs(); if (evidence != null) command("respond_comment", {comment_id: c.comment_id, body, evidence_refs: evidence}); }}, "respond"),
      c.state === "open" ? h("button", {class: "act secondary", onclick: () => { const resolution = ask("Resolution", 10); if (resolution == null) return; const evidence = refs(); if (evidence != null) command("resolve_comment", {comment_id: c.comment_id, resolution, evidence_refs: evidence}); }}, "resolve")
        : h("button", {class: "act secondary", onclick: () => { const reason = ask("Reason for reopening", 10); if (reason != null) command("reopen_comment", {comment_id: c.comment_id, reason}); }}, "reopen"))),
    h("h3", null, "Add a comment"), h("div", {class: "row"}, h("select", {id: "anchor"}, anchors.map(([kind, id, label]) => h("option", {value: kind + "|" + id}, label.slice(0, 90)))),
      h("select", {id: "severity"}, ["note", "major", "critical"].map((s) => h("option", {value: s}, s)))),
    h("textarea", {id: "comment-body", placeholder: "Comment, tied to the item selected above"}),
    h("button", {class: "act", onclick: () => { const [anchor_kind, anchor_id] = $("anchor").value.split("|"); command("comment", {anchor_kind, anchor_id, body: $("comment-body").value, severity: $("severity").value}); }}, "add comment"),
    role === "specialist_reviewer" ? h("button", {class: "act", onclick: () => { const note = ask("Sign-off note", 20); if (note != null) command("specialist_signoff", {note}); }}, "specialist sign-off") : null));
  root.append(h("section", null, h("h2", null, "Export eligibility (delivery package)"),
    h("p", {class: view.eligibility.eligible ? "ok" : "bad"}, view.eligibility.eligible ? "Eligible." : "Not eligible."),
    h("table", null, h("tr", null, ["Check", "Result", "Detail"].map((t) => h("th", null, t))), view.eligibility.checks.map((c) => h("tr", null, h("td", null, c.check_id), h("td", {class: c.status === "pass" ? "ok" : "bad"}, c.status), h("td", null, c.detail))))));
  root.append(h("section", null, h("h2", null, "Findings, decisions and history"),
    h("details", null, h("summary", null, "Findings (" + view.findings.length + ")"), h("ul", null, view.findings.map((f) => h("li", null, "[" + f.severity + "] " + f.summary + " Evidence: " + f.evidence)))),
    h("details", null, h("summary", null, "Decisions (" + view.decisions.length + ")"), h("ul", null, view.decisions.map((d) => h("li", {class: d.invalidated_at ? "bad" : ""}, "v" + d.version + " " + d.kind + " " + (d.target_id || "") + " " + d.outcome + " by " + d.actor_id + (d.invalidated_at ? " | INVALIDATED: " + d.invalidated_reason : ""))))),
    h("details", null, h("summary", null, "Versions (" + view.versions.length + "), all kept"), h("ul", null, view.versions.map((v) => h("li", null, "v" + v.version + " " + v.created_at + " document " + v.document_sha256.slice(0, 12) + " content " + v.content_hash.slice(0, 12))))),
    h("p", {class: view.audit_chain.verified ? "ok" : "bad"}, "Event chain: " + view.audit_chain.reason + " (" + view.audit_chain.event_count + " events)")));
}
function render() {
  const view = state.view, root = $("matter");
  root.replaceChildren(h("div", {id: "flash"}), h("h2", {style: "font-size:19px"}, view.matter.matter_id + ": " + view.matter.title));
  if (view.view === "requester_summary") renderRequester(view, root); else renderReview(view, root);
}
async function start() {
  const response = await fetch("/pilot/api/actors"); const payload = await response.json();
  state.actors = payload.actors; state.scenarios = payload.scenarios; $("notice").textContent = payload.identity_notice + " Synthetic data only. External delivery is disabled.";
  const select = $("actor");
  for (const actor of state.actors) select.append(h("option", {value: actor.actor_id}, actor.display_name + " [" + actor.role + "]"));
  state.actor = select.value;
  select.addEventListener("change", async () => { state.actor = select.value; state.matterId = ""; state.view = null; $("matter").replaceChildren(h("div", {id: "flash"}), h("p", {class: "muted"}, "Choose a matter.")); await loadList(); });
  await loadList();
}
start();
</script>
</body>
</html>
"""
