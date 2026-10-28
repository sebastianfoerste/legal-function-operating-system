"""The review room page. Self-contained: no external script, style or font.

Every action posts a command with the revision the page loaded. Nothing is kept in
the page: after each command it re-renders from the server's answer, and a stale
submission reloads the matter and tells the reviewer their input was not saved.

Decisions are taken in inline forms that name each required field and list what is
missing before anything is sent; the server's checks stay the authority.
"""

from src.pilot.design_tokens import TOKENS_CSS

_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pilot review room</title>
<style>
/*TOKENS*/
*{box-sizing:border-box}body{font:14.5px/1.45 var(--font);color:var(--ink);margin:0;background:var(--bg)}
header{padding:12px 20px;border-bottom:1px solid var(--line);display:flex;gap:10px 16px;align-items:center;flex-wrap:wrap;background:var(--surface)}
header h1{font:600 19px/1.2 var(--font-head);margin:0}
.notice{background:var(--warn-bg);border-bottom:1px solid var(--line);color:var(--warn);padding:8px 20px;font-weight:600}
main{display:grid;grid-template-columns:270px minmax(0,1fr);min-height:80vh}
nav{border-right:1px solid var(--line);padding:14px;background:var(--surface)}
nav button.matter{display:block;width:100%;overflow-wrap:anywhere;text-align:left;margin:0 0 8px;padding:9px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);cursor:pointer;font:inherit}
nav button.matter[aria-current="true"]{border-color:var(--accent);background:var(--accent-soft)}
#pane{padding:16px 22px;min-width:0}
section{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:0 0 14px;overflow-x:auto;background:var(--surface)}
h2{font-size:15.5px;margin:0 0 10px}h3{font-size:14px;margin:12px 0 6px}
.title{font:600 20px/1.25 var(--font-head);margin:0 0 12px}
table{width:100%;border-collapse:collapse;font-size:13.5px}th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:var(--panel)}
code,.hash{font-family:var(--font-mono);overflow-wrap:anywhere;font-size:12px}
.pill{display:inline-block;white-space:nowrap;padding:2px 9px;border-radius:999px;background:var(--panel);border:1px solid var(--pill-line);font-size:12.5px;margin:0 6px 4px 0}
.ok{color:var(--ok)}.bad{color:var(--bad)}.muted{color:var(--muted)}
button.act{font:inherit;font-size:13.5px;padding:6px 11px;border:1px solid var(--accent);background:var(--accent);color:var(--on-accent);border-radius:7px;cursor:pointer;margin:3px 4px 3px 0}
button.act.secondary{background:var(--surface);color:var(--accent)}button.act:disabled{opacity:.55;cursor:not-allowed}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
input,select,textarea{font:inherit;padding:5px 7px;border:1px solid var(--pill-line);border-radius:6px;max-width:100%;background:var(--surface);color:var(--ink)}
textarea{width:100%;min-height:64px}
label,.label{display:block;margin:8px 0 3px;font-weight:600;font-size:13.5px}
.hint{display:block;color:var(--muted);font-size:12.5px;margin:0 0 4px}
.inline-label{display:inline;margin:0;font-weight:400}
#flash{margin:0 0 14px;padding:10px 12px;border-radius:8px}#flash:empty{display:none}
.presence{margin:0 0 12px;padding:8px 12px;border-left:3px solid var(--accent);background:var(--accent-soft);border-radius:0 8px 8px 0}.presence:empty,.stale:empty{display:none}
.stale{margin:0 0 12px;padding:8px 12px;border:1px solid var(--warn);background:var(--warn-bg);color:var(--warn);border-radius:8px;font-weight:600}
#flash.error{background:var(--bad-bg);border:1px solid var(--bad);color:var(--bad)}
#flash.info{background:var(--ok-bg);border:1px solid var(--ok);color:var(--ok)}
form.inline{border:1px solid var(--accent);border-radius:8px;padding:10px 12px;margin:8px 0;background:var(--panel)}
form.inline h3{margin-top:0}
.error-summary{border:2px solid var(--bad);border-radius:8px;padding:8px 12px;margin:0 0 10px;background:var(--bad-bg)}
.error-summary h3{color:var(--bad);margin:0 0 4px}.error-summary a{color:var(--bad);font-weight:600}
.field-error{display:block;color:var(--bad);font-weight:600;font-size:13px;margin:0 0 3px}
[aria-invalid="true"]{border:2px solid var(--bad)}
.context{border-left:3px solid var(--pill-line);padding:4px 10px;margin:6px 0 8px;background:var(--surface)}
.reason{display:block;font-size:12px;color:var(--muted)}
ol.stages{list-style:none;padding:0;margin:8px 0 10px;display:flex;flex-wrap:wrap;gap:6px}
ol.stages li{padding:3px 10px;border:1px solid var(--pill-line);border-radius:999px;font-size:12.5px;color:var(--muted)}
ol.stages li[aria-current="step"]{border:2px solid var(--accent);color:var(--ink);font-weight:700}
dl.facts{display:grid;grid-template-columns:minmax(10rem,16rem) 1fr;gap:4px 12px;margin:6px 0}
dl.facts dt{font-weight:600}dl.facts dd{margin:0;overflow-wrap:anywhere}
table.changes{table-layout:fixed}
table.changes th:nth-child(1){width:12%}table.changes th:nth-child(2){width:25%}table.changes th:nth-child(3){width:21%}table.changes th:nth-child(4){width:12%}table.changes th:nth-child(5){width:18%}table.changes th:nth-child(6){width:12%}
del{color:var(--bad)}ins{color:var(--ok);text-decoration:none;font-weight:600}
.tag{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
details{margin:6px 0}summary{cursor:pointer;color:var(--accent)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media(max-width:820px){main{grid-template-columns:1fr}nav{border-right:0;border-bottom:1px solid var(--line)}}
@media(max-width:600px){#pane{padding:12px}header,.notice{padding-left:12px;padding-right:12px}
table.changes,table.changes tbody,table.changes tr,table.changes td{display:block;width:100%}
table.changes tr.head,table.changes tr[hidden]{display:none}table.changes tr{border:1px solid var(--line);border-radius:8px;margin:0 0 10px}
table.changes td{border:0;border-top:1px solid var(--line)}table.changes td:first-child{border-top:0}
table.changes td[data-label]::before{content:attr(data-label);display:block;font-weight:700;font-size:12px;color:var(--muted)}
dl.facts{grid-template-columns:1fr}dl.facts dd{margin-bottom:6px}}
</style>
</head>
<body>
<header>
  <h1>Pilot review room</h1>
  <label for="actor" class="inline-label">Simulated local role</label>
  <select id="actor"></select>
  <label for="effort" class="inline-label">Minutes spent on the next action</label>
  <input id="effort" type="number" min="0" max="600" style="width:80px">
</header>
<div class="notice" id="notice">Simulated local roles. Selecting an actor is not authentication. Synthetic data only. External delivery is disabled.</div>
<main>
  <nav aria-label="Matters"><div id="create"></div><h2>Matters</h2><div id="list"></div></nav>
  <div id="pane"><div id="flash" role="status" aria-live="polite"></div><div id="matter"><p class="muted">Choose a role, then a matter.</p></div></div>
</main>
<script>
"use strict";
const state = {actors: [], scenarios: [], actor: "", matterId: "", view: null, presenceTimer: null};
// How often an open review room checks in (presence_ms in the address overrides it, minimum 1 s).
const PRESENCE_MS = Math.max(1000, parseInt(new URLSearchParams(location.search).get("presence_ms"), 10) || 30000);
const $ = (id) => document.getElementById(id);
let uid = 0;
function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "class") node.className = value;
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}
const words = (text) => String(text).replaceAll("_", " ");
function flash(kind, text) { const box = $("flash"); box.className = kind; box.textContent = text; }
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
  if (status === 200) { state.view = payload; render(); flash("info", words(name) + " saved."); await loadList(); return; }
  if (payload.error === "stale_submission") {
    await loadMatter(state.matterId);
    flash("error", "Not saved. The matter changed while you were working (now revision " + payload.current_revision + "). It has been reloaded; check it and submit again.");
    return;
  }
  await loadMatter(state.matterId);
  flash("error", "Refused: " + (payload.message || "the server did not accept this command."));
}
// ------------------------------------------------------------- inline forms
// One form is open at a time. Fields: {name, label, kind: text|textarea|checkbox|select|checks,
// min, required, hint, value, options: [[value, label]]}. Nothing is sent until every field passes.
let openForm = null;
function closeForm() { if (!openForm) return; const {host, trigger, onclose} = openForm; openForm = null; host.replaceChildren(); if (host.dataset.hideEmpty) host.closest("tr").hidden = true; if (onclose) onclose(); if (trigger && trigger.isConnected) { trigger.setAttribute("aria-expanded", "false"); trigger.focus(); } }
function field(spec, id) {
  const hintId = id + "-hint", errorId = id + "-error";
  const describedBy = [spec.hint ? hintId : null, errorId].filter(Boolean).join(" ");
  const hint = spec.hint ? h("span", {class: "hint", id: hintId}, spec.hint) : null;
  const error = h("span", {class: "field-error", id: errorId});
  const mark = spec.required === false ? " (optional)" : "";
  if (spec.kind === "checkbox") {
    return h("div", {"data-field": spec.name}, error, h("label", {class: "inline-label"}, h("input", {type: "checkbox", id, name: spec.name, "aria-describedby": describedBy}), " " + spec.label), hint);
  }
  if (spec.kind === "checks") {
    return h("fieldset", {"data-field": spec.name, id, tabindex: "-1", "aria-describedby": describedBy, style: "border:0;padding:0;margin:8px 0"}, h("legend", {class: "label"}, spec.label), hint, error,
      spec.options.map(([value, label], i) => h("div", null, h("label", {class: "inline-label"}, h("input", {type: "checkbox", name: spec.name, value, id: id + "-" + i}), " " + label))));
  }
  const control = spec.kind === "select"
    ? h("select", {id, name: spec.name, "aria-describedby": describedBy}, spec.options.map(([value, label]) => h("option", {value, selected: value === spec.value}, label)))
    : h(spec.kind === "textarea" ? "textarea" : "input", {id, name: spec.name, "aria-describedby": describedBy, value: spec.kind === "textarea" ? null : spec.value, autocomplete: "off"});
  if (spec.kind === "textarea" && spec.value) control.value = spec.value;
  if (spec.onchange) control.addEventListener("change", spec.onchange);
  return h("div", {"data-field": spec.name}, h("label", {for: id}, spec.label + mark), hint, error, control);
}
function readField(form, spec) {
  if (spec.kind === "checkbox") return form.querySelector("[name='" + spec.name + "']").checked;
  if (spec.kind === "checks") return [...form.querySelectorAll("[name='" + spec.name + "']:checked")].map((box) => box.value);
  return form.querySelector("[name='" + spec.name + "']").value.trim();
}
function problem(spec, value) {
  if (spec.kind === "checkbox") return spec.required !== false && !value ? "Confirm: " + spec.label : null;
  if (spec.kind === "checks") return spec.required !== false && !value.length ? "Choose at least one: " + spec.label : null;
  if (spec.required === false && !value) return null;
  if (!value) return "Enter " + spec.label.toLowerCase();
  if (spec.min && value.length < spec.min) return spec.label + " needs at least " + spec.min + " characters (now " + value.length + ")";
  return null;
}
function showForm(host, trigger, spec) {
  closeForm();
  const base = "f" + (++uid);
  const fields = spec.fields.map((f, i) => ({...f, id: base + "-" + i}));
  const summary = h("div", {class: "error-summary", tabindex: "-1", role: "alert", hidden: true});
  const form = h("form", {class: "inline", novalidate: true, "aria-labelledby": base + "-title"},
    h("h3", {id: base + "-title"}, spec.title), summary, spec.context || null,
    fields.map((f) => field(f, f.id)),
    h("div", {class: "row"}, h("button", {class: "act", type: "submit"}, spec.submit || "Save"), h("button", {class: "act secondary", type: "button", onclick: closeForm}, "Cancel")));
  form.addEventListener("keydown", (event) => { if (event.key === "Escape") { event.preventDefault(); closeForm(); } });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = {}, problems = [];
    for (const f of fields) {
      const box = form.querySelector("[data-field='" + f.name + "']");
      const control = box.querySelector("input,select,textarea");
      if (f.hidden && f.hidden(form)) { values[f.name] = ""; continue; }
      values[f.name] = readField(form, f);
      const message = problem(f, values[f.name]);
      box.querySelector(".field-error").textContent = message ? message : "";
      if (control) control.setAttribute("aria-invalid", message ? "true" : "false");
      if (message) problems.push([f, message]);
    }
    if (spec.check) { const extra = spec.check(values); if (extra) problems.push([fields[0], extra]); }
    if (problems.length) {
      summary.hidden = false;
      summary.replaceChildren(h("h3", null, "There is a problem"), h("ul", null, problems.map(([f, message]) => h("li", null, h("a", {href: "#" + f.id, onclick: (e) => { e.preventDefault(); const target = $(f.id); const focusable = target.matches("input,select,textarea") ? target : target.querySelector("input"); (focusable || target).focus(); }}, message)))));
      summary.focus();
      return;
    }
    await spec.onsubmit(values);
  });
  // A field with a hidden(form) test is shown only when it applies (progressive disclosure).
  const toggle = () => { for (const f of fields) if (f.hidden) form.querySelector("[data-field='" + f.name + "']").hidden = f.hidden(form); };
  form.addEventListener("change", toggle);
  host.replaceChildren(form);
  toggle();
  if (host.dataset.hideEmpty) host.closest("tr").hidden = false;
  openForm = {host, trigger, onclose: spec.onclose};
  const first = form.querySelector("input,select,textarea"); if (first) first.focus();
}
// A button that opens a form in `host`, placed right after the button by default.
function formButton(label, spec, opts) {
  const host = (opts && opts.host) || h("div");
  const button = h("button", {class: "act" + (opts && opts.primary ? "" : " secondary"), type: "button", "aria-expanded": "false", onclick: () => { showForm(host, button, spec); button.setAttribute("aria-expanded", "true"); }}, label);
  return (opts && opts.host) ? button : h("span", null, button, host);
}
const refsField = {name: "evidence", label: "Evidence references", kind: "text", required: false, hint: "Comma separated, for example synthetic:note-1"};
const splitRefs = (text) => text.split(",").map((r) => r.trim()).filter(Boolean);
const note = (label, min, hint) => ({name: "note", label, kind: "textarea", min, hint: hint || ("At least " + min + " characters.")});
// ------------------------------------------------------------------- matters
async function loadList() {
  const {payload} = await api("GET", "/matters");
  const list = $("list"); list.replaceChildren();
  for (const matter of payload.matters || []) {
    list.append(h("button", {class: "matter", "aria-current": matter.matter_id === state.matterId ? "true" : null, onclick: () => loadMatter(matter.matter_id)},
      h("strong", null, matter.matter_id), h("br"), matter.title, h("br"), h("span", {class: "pill"}, words(matter.state)), "v" + matter.current_version));
  }
  if (!(payload.matters || []).length) list.append(h("p", {class: "muted"}, "No matter is visible to this role."));
  const create = $("create"); create.replaceChildren();
  const actor = state.actors.find((a) => a.actor_id === state.actor);
  if (actor && actor.role === "business_requester") {
    create.append(h("h2", null, "Open a synthetic matter"));
    for (const scenario of state.scenarios) { const button = h("button", {class: "matter", onclick: () => renderIntake(scenario, button)}, scenario.title); create.append(button); }
  }
}
async function loadMatter(id) {
  // Set the matter first, so a closing intake form knows a matter is on its way.
  state.matterId = id;
  closeForm();
  const {status, payload} = await api("GET", "/matters/" + encodeURIComponent(id));
  if (status !== 200) { stopPresence(); $("matter").replaceChildren(); flash("error", payload.message); return; }
  state.view = payload; render(); await loadList();
}
// The intake form: the five required facts, pre-filled from the scenario, checked before the
// matter is opened so the first version is complete (rehearsal step B02).
function renderIntake(scenario, trigger) {
  stopPresence();
  closeForm(); state.matterId = ""; state.view = null; flash("", "");
  const host = h("div");
  $("matter").replaceChildren(h("h2", {class: "title", tabindex: "-1", id: "intake-title"}, "New request: " + scenario.title), host);
  const missing = scenario.required_facts.filter((f) => !f.present);
  const fields = scenario.required_facts.map((f) => ({name: f.key, label: f.label, kind: f.key === "requested_deviations" ? "textarea" : "text", value: f.value,
    hint: f.present ? "Pre-filled from the synthetic scenario. Change it if it is wrong." : "Missing in the synthetic scenario. Legal refuses a request without it."}));
  showForm(host, trigger, {title: "Required facts (5)", submit: "Open the matter", fields,
    onclose: () => { if (!state.view && !state.matterId) $("matter").replaceChildren(h("p", {class: "muted"}, "No matter was opened. Choose a scenario or a matter.")); },
    context: h("p", {class: "muted"}, "Legal checks these five facts before triage. " + (missing.length ? missing.length + " of 5 are still empty." : "All five are filled in.") + " The customer's draft and the instructions come from the synthetic scenario."),
    onsubmit: async (values) => {
      const {status, payload: made} = await api("POST", "/matters", {scenario_id: scenario.scenario_id, matter_id: "PM-UI-" + Date.now().toString(36).toUpperCase(), facts: values, effort_minutes: effort()});
      if (status === 201) { await loadList(); await loadMatter(made.matter.matter_id); flash("info", "Matter " + made.matter.matter_id + " opened. Submit it when you are ready."); } else flash("error", "Refused: " + made.message);
    }});
  $("intake-title").focus();
}
function evidenceList(items) {
  return h("ul", null, items.map((e) => h("li", {class: e.ok ? "ok" : "bad"}, (e.ok ? "✓ Met: " : "✗ Not met: ") + words(e.name) + ": " + e.detail)));
}
function factList(facts) {
  return h("dl", {class: "facts"}, facts.map((f) => [h("dt", null, f.label), h("dd", null, f.present ? f.value : h("span", {class: "bad"}, "✗ Missing"))]));
}
function renderRequester(view, root) {
  const status = view.requester_status, missing = view.required_facts.filter((f) => !f.present);
  const submitHost = h("div");
  const submit = h("button", {class: "act", type: "button", onclick: () => {
    if (!missing.length) return command("submit_intake");
    // The server would refuse on intake_complete; say which facts before sending anything.
    submitHost.replaceChildren(h("div", {class: "error-summary", role: "alert", tabindex: "-1"}, h("h3", null, "Not submitted: " + missing.length + " required fact" + (missing.length > 1 ? "s are" : " is") + " missing"),
      h("ul", null, missing.map((f) => h("li", null, f.label)))));
    submitHost.firstChild.focus();
  }}, "Submit to legal");
  root.append(h("section", {"aria-labelledby": "status-h"}, h("h2", {id: "status-h"}, "Status: " + status.label),
    h("ol", {class: "stages", "aria-label": "Stages"}, status.stages.map((s) => h("li", {"aria-current": s.current ? "step" : null}, s.label, s.current ? h("span", {class: "visually-hidden"}, " (current stage)") : null))),
    h("p", null, status.explanation), h("p", null, h("strong", null, "Your next step: "), status.your_action),
    h("p", {class: "muted"}, "Version " + view.matter.current_version + ". " + status.withheld)));
  const factsHost = h("div");
  const keys = view.required_facts.map((f) => [f.key, f.label]).concat([["__other", "Another fact"]]);
  root.append(h("section", {"aria-labelledby": "facts-h"}, h("h2", {id: "facts-h"}, "Required facts (" + (5 - missing.length) + " of 5 provided)"), factList(view.required_facts),
    view.matter.state === "intake" && missing.length ? h("p", {class: "bad"}, "Legal will refuse this request until every required fact is provided.") : null,
    view.matter.state === "intake" && missing.length ? formButton("Add the missing facts", {title: "Add the missing facts", submit: "Save the facts",
      fields: missing.map((f) => ({name: f.key, label: f.label, kind: "text"})).concat([{name: "reason", label: "Reason for the change", kind: "text", min: 10, hint: "At least 10 characters. Saved in the matter history."}]),
      onsubmit: (values) => { const {reason, ...facts} = values; return command("amend_matter", {reason, facts}); }}, {primary: true}) : null,
    formButton("Change a fact", {title: "Change a fact", submit: "Save the change", fields: [
      {name: "key", label: "Fact", kind: "select", options: keys},
      {name: "other", label: "Name of the other fact", kind: "text", hint: "Only for another fact, for example deal_desk_ticket.", hidden: (form) => form.querySelector("[name='key']").value !== "__other"},
      {name: "value", label: "New value", kind: "text"},
      {name: "reason", label: "Reason for the change", kind: "text", min: 10, hint: "At least 10 characters."}],
      onsubmit: (v) => command("amend_matter", {reason: v.reason, facts: {[v.key === "__other" ? v.other : v.key]: v.value}})}),
    factsHost));
  if (view.matter.state === "intake") root.append(h("section", null, h("h2", null, "Submit"), submitHost, submit));
  root.append(h("section", {"aria-labelledby": "q-h"}, h("h2", {id: "q-h"}, "Questions for you"),
    view.clarifications.length ? view.clarifications.map((c) => h("div", null, h("p", null, h("span", {class: "pill"}, c.state), c.body),
      c.responses.map((r) => h("p", {class: "muted"}, words(r.author_role) + ": " + r.body)),
      c.state === "open" ? formButton("Answer", {title: "Answer the question", submit: "Send the answer", context: h("p", {class: "context"}, c.body),
        fields: [{name: "body", label: "Your answer", kind: "textarea", min: 10, hint: "At least 10 characters."}, refsField],
        onsubmit: (v) => command("respond_comment", {comment_id: c.comment_id, body: v.body, evidence_refs: splitRefs(v.evidence)})}, {primary: true}) : null)) : h("p", {class: "muted"}, "None.")));
  root.append(h("section", {"aria-labelledby": "d-h"}, h("h2", {id: "d-h"}, "Delivery package"),
    view.delivery.length ? h("a", {href: "/pilot/api/matters/" + encodeURIComponent(view.matter.matter_id) + "/package?actor=1", onclick: openPackage}, "Open the approved customer package") : h("p", {class: "muted"}, "No approved package yet."),
    view.matter.state === "ready_for_delivery" ? h("div", null, formButton("Accept delivery", {title: "Accept delivery", submit: "Accept delivery", fields: [note("Acceptance note", 20)], onsubmit: (v) => command("accept_delivery", {note: v.note})}, {primary: true})) : null));
}
async function openPackage(event) {
  event.preventDefault();
  const response = await fetch("/pilot/api/matters/" + encodeURIComponent(state.matterId) + "/package", {headers: {"X-Pilot-Actor": state.actor}});
  if (!response.ok) { flash("error", (await response.json()).message); return; }
  const frame = h("iframe", {title: "Customer package", style: "width:100%;height:80vh;border:1px solid var(--line);border-radius:10px;background:#fff", sandbox: ""});
  frame.srcdoc = await response.text();
  $("matter").append(h("section", null, h("h2", null, "Approved customer package (local copy)"), frame));
  frame.scrollIntoView();
}
// ------------------------------------------------------------------- review
const CONFIRM = "I checked that the cited source supports this wording for this matter";
const NOTE_COMMANDS = {approve: ["Approval note", 30], submit_revision: ["Revision note", 20], accept_delivery: ["Acceptance note", 20]};
function transitionControl(item, role) {
  const allowed = item.roles.includes(role), label = words(item.command) + " → " + words(item.target);
  // A control that cannot be used says why, in visible text tied to the button.
  const blocked = (reason) => { const id = "why-" + (++uid); return h("span", null, h("button", {class: "act", disabled: true, "aria-describedby": id}, label), h("span", {class: "reason", id}, reason)); };
  if (!allowed) return blocked("Needs role: " + item.roles.map(words).join(" or "));
  if (item.command === "request_revision") {
    const open = state.view.comments.filter((c) => c.state === "open");
    // The server refuses a revision request that names no open comment.
    if (!open.length) return blocked("Add a comment first: a revision request must name an open comment.");
    return formButton(label, {title: "Request a revision", submit: "Request the revision", fields: [
      {name: "comment_ids", label: "Open comments this revision concerns", kind: "checks", options: open.map((c) => [c.comment_id, c.comment_id + ": " + c.body.slice(0, 80)])},
      note("Reason for the revision", 20)], onsubmit: (v) => command("request_revision", {comment_ids: v.comment_ids, note: v.note})}, {primary: true});
  }
  const needs = NOTE_COMMANDS[item.command];
  if (!needs) return h("button", {class: "act", onclick: () => command(item.command)}, label);
  return formButton(label, {title: label, submit: words(item.command), fields: [note(needs[0], needs[1])], onsubmit: (v) => command(item.command, {note: v.note})}, {primary: true});
}
function changeControls(change, host) {
  if (!["review", "revision_requested"].includes(state.view.matter.state)) return h("span", {class: "muted"}, "Closed for decisions in this state");
  const quote = h("div", {class: "context"}, h("span", {class: "tag"}, "Proposed"), h("br"), change.proposed_text || "(delete clause)");
  return h("div", null,
    formButton("accept", {title: "Accept change " + change.id, submit: "Accept", context: quote, fields: [{name: "confirmed", label: CONFIRM, kind: "checkbox"}],
      onsubmit: () => command("decide_change", {change_id: change.id, outcome: "accepted", source_support_confirmed: true})}, {host, primary: true}),
    formButton("reject", {title: "Keep the counterparty wording for " + change.id, submit: "Record the exception", fields: [note("Reason for keeping the counterparty wording (accepted exception)", 20)],
      onsubmit: (v) => command("decide_change", {change_id: change.id, outcome: "rejected", reason: v.note})}, {host}),
    formButton("amend", {title: "Amend the wording of " + change.id, submit: "Save the amendment", context: quote, fields: [
      {name: "text", label: "Amended wording", kind: "textarea", value: change.proposed_text}, note("Reason for the amended wording", 20), {name: "confirmed", label: CONFIRM, kind: "checkbox"}],
      onsubmit: (v) => command("decide_change", {change_id: change.id, outcome: "amended", amended_text: v.text, reason: v.note, source_support_confirmed: true})}, {host}),
    formButton("ask requester", {title: "Ask the requester about " + change.id, submit: "Send the question", fields: [{name: "question", label: "Question for the requester", kind: "textarea", min: 10, hint: "At least 10 characters. The requester sees only this question."}],
      onsubmit: (v) => command("decide_change", {change_id: change.id, outcome: "clarification_requested", reason: v.question})}, {host}));
}
function playbookCell(position) {
  if (!position) return h("span", {class: "muted"}, "No playbook rule");
  return h("div", null, h("span", {class: "tag"}, "Standard"), h("div", null, position.standard_position),
    h("span", {class: "tag"}, "Fallback"), h("div", null, position.fallback_position),
    h("div", {class: "muted"}, position.topic + " · " + position.rule_id));
}
function commentThread(c) {
  const evidence = c.responses.flatMap((r) => r.evidence_refs.map((ref) => [ref, r.author_id, r.body]));
  // The approver reads the cited evidence before resolving (rehearsal steps B33 to B36).
  const evidenceBlock = h("div", {class: "context"}, h("strong", null, "Evidence cited in this thread"),
    evidence.length ? h("ul", null, evidence.map(([ref, who, body]) => h("li", null, h("code", null, ref), " from " + who + ": " + body))) : h("p", {class: "bad"}, "No evidence reference has been cited yet."));
  return h("div", {style: "border-top:1px solid var(--line);padding:8px 0"},
    h("p", null, h("span", {class: "pill"}, c.comment_id), h("span", {class: "pill"}, c.kind), h("span", {class: "pill"}, c.severity), h("span", {class: "pill " + (c.state === "open" ? "bad" : "ok")}, c.state), c.blocking ? h("span", {class: "pill bad"}, "blocks approval") : null, c.anchor_status === "orphaned" ? h("span", {class: "pill bad"}, "anchor no longer in this version") : null),
    h("p", null, c.body), h("p", {class: "muted"}, "On " + c.anchor_kind + " " + c.anchor_id + ": " + c.anchor_excerpt + " | by " + c.author_id + ", version " + c.created_on_version),
    c.responses.map((r) => h("p", {class: "muted"}, r.author_id + ": " + r.body + (r.evidence_refs.length ? " [" + r.evidence_refs.join(", ") + "]" : ""))),
    c.resolution ? h("p", {class: "ok"}, "Resolved by " + c.resolved_by + ": " + c.resolution + " [" + c.resolution_evidence.join(", ") + "]") : null,
    formButton("respond", {title: "Respond to " + c.comment_id, submit: "Send the response", fields: [{name: "body", label: "Response", kind: "textarea", min: 10, hint: "At least 10 characters."}, refsField],
      onsubmit: (v) => command("respond_comment", {comment_id: c.comment_id, body: v.body, evidence_refs: splitRefs(v.evidence)})}),
    c.state === "open"
      ? formButton("resolve", {title: "Resolve " + c.comment_id, submit: "Resolve", context: h("div", null, h("p", {class: "context"}, c.body), evidenceBlock),
          fields: [{name: "resolution", label: "Resolution", kind: "textarea", min: 10, hint: "At least 10 characters."}, {...refsField, required: true, hint: "Comma separated. Name the evidence you read above."}],
          onsubmit: (v) => command("resolve_comment", {comment_id: c.comment_id, resolution: v.resolution, evidence_refs: splitRefs(v.evidence)})})
      : formButton("reopen", {title: "Reopen " + c.comment_id, submit: "Reopen", fields: [{name: "reason", label: "Reason for reopening", kind: "textarea", min: 10, hint: "At least 10 characters."}],
          onsubmit: (v) => command("reopen_comment", {comment_id: c.comment_id, reason: v.reason})}));
}
function renderReview(view, root) {
  const role = view.actor.role, version = view.version;
  root.append(h("section", {"aria-labelledby": "next-h"}, h("h2", {id: "next-h"}, "State and next steps"),
    h("p", null, h("span", {class: "pill"}, words(view.matter.state)), h("span", {class: "pill"}, "version " + version.version), h("span", {class: "pill"}, "revision " + view.matter.revision),
      h("span", {class: "pill"}, "risk " + version.routing.risk), h("span", {class: "pill"}, "queue " + version.routing.queue), h("span", {class: "pill"}, "approval tier " + version.required_final_tier)),
    version.scope_exclusions.length ? h("p", {class: "bad"}, "Outside the pilot charter: " + version.scope_exclusions.join("; ")) : null,
    view.allowed.length ? view.allowed.map((item) => h("div", null, transitionControl(item, role), item.evidence.length ? evidenceList(item.evidence) : null)) : h("p", {class: "muted"}, "No transition is available from this state."),
    h("button", {class: "act secondary", onclick: () => command("export_internal_review")}, "write internal review draft"),
    formButton("withdraw matter", {title: "Withdraw the matter", submit: "Withdraw", fields: [note("Reason for closing without delivery", 20)], onsubmit: (v) => command("withdraw", {note: v.note})}),
    view.manifests.some((m) => m.kind === "delivery_package") ? h("a", {href: "#", onclick: openPackage}, "Open the approved customer package") : null));
  root.append(h("section", {"aria-labelledby": "ready-h"}, h("h2", {id: "ready-h"}, "Readiness check"), evidenceList(view.readiness),
    h("h3", null, "Required facts"), factList(view.required_facts),
    h("h3", null, "Assignments"), h("p", null, Object.entries(view.assignments).map(([r, ids]) => words(r) + ": " + ids.join(", ")).join(" | ")),
    role === "matter_owner" ? h("div", {class: "row"}, h("div", null, h("label", {for: "assignee"}, "Assign a reviewer"), h("select", {id: "assignee"}, state.actors.filter((a) => ["specialist_reviewer", "final_approver"].includes(a.role)).map((a) => h("option", {value: a.actor_id + "|" + a.role}, a.display_name + (a.onboarded ? "" : " (not onboarded)"))))),
      h("button", {class: "act secondary", onclick: () => { const [assignee_id, r] = $("assignee").value.split("|"); command("assign", {role: r, assignee_id}); }}, "assign")) : null));
  const support = Object.fromEntries(view.source_support.map((s) => [s.change_id, s]));
  root.append(h("section", {"aria-labelledby": "changes-h"}, h("h2", {id: "changes-h"}, "Proposed changes (" + view.changes.length + ")"),
    view.changes.length ? h("table", {class: "changes"}, h("tbody", null, h("tr", {class: "head"}, ["Locator", "Wording", "Playbook position", "Decision", "Source verification", "Action"].map((t) => h("th", {scope: "col"}, t))),
      view.changes.flatMap((c) => { const s = support[c.id]; const formCell = h("td", {colspan: "6", "data-hide-empty": "1"}); const formRow = h("tr", {hidden: true}, formCell); return [h("tr", null,
        h("td", {"data-label": "Locator"}, c.locator, h("br"), h("span", {class: "muted"}, c.rule_id + (c.specialist_role ? " (" + c.specialist_role + ")" : ""))),
        h("td", {"data-label": "Wording"}, h("span", {class: "tag"}, "Removed"), h("br"), h("del", null, c.original_text || "(nothing)"), h("br"), h("span", {class: "tag"}, "Added"), h("br"), h("ins", null, c.proposed_text || "(delete clause)"), c.amended_text ? [h("br"), h("strong", null, "Amended: "), c.amended_text] : null, h("br"), h("span", {class: "muted"}, c.rationale)),
        h("td", {"data-label": "Playbook position"}, playbookCell(c.playbook_position)),
        h("td", {"data-label": "Decision"}, h("span", {class: "pill"}, words(c.decision)), c.decision_reason ? h("div", {class: "muted"}, c.decision_reason) : null, c.decided_by ? h("div", {class: "muted"}, "by " + c.decided_by) : null, c.carried_from_version ? h("div", {class: "muted"}, "carried from v" + c.carried_from_version) : null),
        h("td", {"data-label": "Source verification"}, s.sources.map((src) => h("div", null, h("code", null, src.source_ref), h("br"), "allowlist: " + src.allowlist_check.status + " (prefix only)", h("br"), "quote check: " + src.quote_check.status, h("br"), h("span", {class: "muted"}, "source version: " + Object.entries(src.source_version).map(([k, v]) => k + " " + String(v).slice(0, 12)).join(", ")))),
          h("div", {class: s.human_review.status === "confirmed" ? "ok" : "bad"}, "human review: " + s.human_review.status), h("div", {class: "muted"}, "Not verified by software: " + s.not_verified_by_software)),
        h("td", {"data-label": "Action"}, changeControls(c, formCell))), formRow]; }))) : h("p", {class: "muted"}, "No change proposed for this version.")));
  const anchors = [...view.findings.map((f) => ["finding", f.key, "finding: " + f.summary]), ...view.changes.map((c) => ["change", c.id, "change: " + c.id]),
    ...["executive_summary", "issue_and_deviation_list", "reviewed_document", "accepted_exceptions", "outstanding_obligations", "approval_record"].map((s) => ["deliverable_section", s, "deliverable: " + words(s)])];
  root.append(h("section", {"aria-labelledby": "comments-h"}, h("h2", {id: "comments-h"}, "Comments (" + view.comments.length + ")"),
    view.comments.map(commentThread),
    h("h3", null, "Add a comment"), h("div", {class: "row"}, h("div", null, h("label", {for: "anchor"}, "Comment on"), h("select", {id: "anchor"}, anchors.map(([kind, id, label]) => h("option", {value: kind + "|" + id}, label.slice(0, 90))))),
      h("div", null, h("label", {for: "severity"}, "Severity"), h("select", {id: "severity"}, ["note", "major", "critical"].map((s) => h("option", {value: s}, s))))),
    h("label", {for: "comment-body"}, "Comment"), h("textarea", {id: "comment-body"}),
    h("button", {class: "act", onclick: () => { const [anchor_kind, anchor_id] = $("anchor").value.split("|"); command("comment", {anchor_kind, anchor_id, body: $("comment-body").value, severity: $("severity").value}); }}, "add comment"),
    role === "specialist_reviewer" ? formButton("specialist sign-off", {title: "Specialist sign-off", submit: "Sign off", fields: [note("Sign-off note", 20)], onsubmit: (v) => command("specialist_signoff", {note: v.note})}, {primary: true}) : null));
  root.append(h("section", {"aria-labelledby": "elig-h"}, h("h2", {id: "elig-h"}, "Export eligibility (delivery package)"),
    h("p", {class: view.eligibility.eligible ? "ok" : "bad"}, view.eligibility.eligible ? "✓ Eligible." : "✗ Not eligible."),
    h("table", null, h("tbody", null, h("tr", null, ["Check", "Result", "Detail"].map((t) => h("th", {scope: "col"}, t))), view.eligibility.checks.map((c) => h("tr", null, h("td", null, c.check_id), h("td", {class: c.status === "pass" ? "ok" : "bad"}, (c.status === "pass" ? "✓ " : "✗ ") + c.status), h("td", null, c.detail)))))));
  root.append(h("section", {"aria-labelledby": "hist-h"}, h("h2", {id: "hist-h"}, "Findings, decisions and history"),
    h("details", null, h("summary", null, "Findings (" + view.findings.length + ")"), h("ul", null, view.findings.map((f) => h("li", null, "[" + f.severity + "] " + f.summary + " Evidence: " + f.evidence)))),
    h("details", null, h("summary", null, "Decisions (" + view.decisions.length + ")"), h("ul", null, view.decisions.map((d) => h("li", {class: d.invalidated_at ? "bad" : ""}, "v" + d.version + " " + d.kind + " " + (d.target_id || "") + " " + d.outcome + " by " + d.actor_id + (d.invalidated_at ? " | INVALIDATED: " + d.invalidated_reason : ""))))),
    h("details", null, h("summary", null, "Versions (" + view.versions.length + "), all kept"), h("ul", null, view.versions.map((v) => h("li", null, "v" + v.version + " " + v.created_at + " document ", h("span", {class: "hash"}, v.document_sha256.slice(0, 12)), " content ", h("span", {class: "hash"}, v.content_hash.slice(0, 12)))))),
    h("p", {class: view.audit_chain.verified ? "ok" : "bad"}, (view.audit_chain.verified ? "✓ " : "✗ ") + "Event chain: " + view.audit_chain.reason + " (" + view.audit_chain.event_count + " events)")));
}
// ---------------------------------------------------------------- presence
// Who else has this matter open: simulated local roles, held in server memory only.
function presenceText(others) {
  if (!others.length) return "";
  return "Also open (simulated local role, not authentication): " + others.map((o) =>
    o.display_name + " on revision " + o.revision + (o.behind ? " (older than yours)" : "") + ", " + o.seconds_ago + " s ago").join("; ") + ".";
}
function showPresence(others, current) {
  const line = $("presence"), stale = $("stale");
  if (!line || !stale) return;
  const text = presenceText(others || []);
  if (line.textContent !== text) line.textContent = text;
  const loaded = state.view.matter.revision;
  if (current > loaded && !stale.childNodes.length) {
    stale.replaceChildren("This matter changed after you loaded it (now revision " + current + ", you have " + loaded + "). Reload it before you decide. ",
      h("button", {class: "act secondary", type: "button", onclick: () => loadMatter(state.matterId)}, "Reload the matter"));
  } else if (current <= loaded && stale.childNodes.length) stale.replaceChildren();
}
function stopPresence() { if (state.presenceTimer) clearInterval(state.presenceTimer); state.presenceTimer = null; }
function startPresence() {
  stopPresence();
  if (!state.view || state.view.view !== "review_room") return;
  const matterId = state.matterId;
  state.presenceTimer = setInterval(async () => {
    if (state.matterId !== matterId || !state.view) { stopPresence(); return; }
    const {status, payload} = await api("POST", "/matters/" + encodeURIComponent(matterId) + "/presence", {revision: state.view.matter.revision});
    if (state.matterId !== matterId) return;
    if (status !== 200) { stopPresence(); return; }
    showPresence(payload.also_open_by, payload.current_revision);
  }, PRESENCE_MS);
}
function render() {
  const view = state.view, root = $("matter");
  openForm = null;
  root.replaceChildren(h("h2", {class: "title"}, view.matter.matter_id + ": " + view.matter.title));
  if (view.view === "requester_summary") { stopPresence(); renderRequester(view, root); return; }
  root.append(h("p", {id: "presence", class: "presence", "aria-live": "polite"}), h("div", {id: "stale", class: "stale", "aria-live": "polite"}));
  showPresence(view.also_open_by, view.matter.revision);
  renderReview(view, root);
  startPresence();
}
async function start() {
  const response = await fetch("/pilot/api/actors"); const payload = await response.json();
  state.actors = payload.actors; state.scenarios = payload.scenarios; $("notice").textContent = payload.identity_notice + " Synthetic data only. External delivery is disabled.";
  const select = $("actor");
  for (const actor of state.actors) select.append(h("option", {value: actor.actor_id}, actor.display_name + " [" + words(actor.role) + "]"));
  state.actor = select.value;
  select.addEventListener("change", async () => { stopPresence(); closeForm(); state.actor = select.value; state.matterId = ""; state.view = null; flash("", ""); $("matter").replaceChildren(h("p", {class: "muted"}, "Choose a matter.")); await loadList(); });
  await loadList();
}
start();
</script>
</body>
</html>
"""

REVIEW_ROOM_HTML = _PAGE.replace("/*TOKENS*/", TOKENS_CSS)
