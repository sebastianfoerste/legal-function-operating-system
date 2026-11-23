"""Browser smoke tests of the review room: inline forms, presence and the audit timeline.

Runs short Node Playwright scripts against a local server on 127.0.0.1. It is
skipped when Node, its Playwright package or a Chromium build is not installed, so
the gate does not depend on a browser. With ``REQUIRE_BROWSER_TESTS=1`` (set in CI,
where Playwright is installed) that skip becomes a failure, so a broken browser
install cannot pass silently. Everything it touches is synthetic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer

import pytest

from src.pilot.api import PilotApi
from src.pilot.scenario_runner import seed_actors
from src.pilot.service import PermissionDeniedError, PilotService
from src.pilot.store import PilotStore
from src.pilot.timeline import event_class
from tests.pilot_support import (
    APPROVER_LEAD,
    OWNER,
    REQUESTER,
    make_service,
    revision,
    run_until,
)

UNAVAILABLE = 3
REQUIRE_BROWSER_TESTS = "REQUIRE_BROWSER_TESTS"

SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const [base, matter, OWNER, REQUESTER, APPROVER] = process.argv.slice(2);
  const out = {};
  const errors = [];
  async function open(actor, width, query) {
    const page = await (await browser.newContext({ viewport: { width, height: 900 } })).newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("dialog", (d) => { errors.push("dialog: " + d.message()); d.dismiss(); });
    await page.goto(base + "/pilot" + (query || ""));
    await page.waitForSelector("#actor option", { state: "attached" });
    await page.selectOption("#actor", actor);
    await page.waitForTimeout(300);
    return page;
  }
  async function openMatter(page) {
    await page.locator("#list button", { hasText: matter }).first().click();
    await page.waitForTimeout(500);
  }
  const focused = (page) => page.evaluate(() => {
    const a = document.activeElement;
    return { tag: a.tagName, text: a.textContent.trim().slice(0, 60), cls: a.className };
  });

  // Owner, review state, no comment yet: the revision request explains itself.
  let page = await open(OWNER, 1280);
  await openMatter(page);
  const revision = page.locator("button", { hasText: "request revision" });
  out.revisionDisabled = await revision.isDisabled();
  const describedBy = await revision.getAttribute("aria-describedby");
  out.revisionReason = describedBy ? await page.locator("#" + describedBy).innerText() : "";

  // Empty submit: the error summary takes focus; its link focuses the field.
  const withdraw = page.getByRole("button", { name: "withdraw matter" });
  await withdraw.click();
  out.expandedOpen = await withdraw.getAttribute("aria-expanded");
  await page.getByRole("button", { name: "Withdraw", exact: true }).click();
  out.summaryFocused = (await focused(page)).cls;
  await page.locator(".error-summary a").first().click();
  out.linkFocused = (await focused(page)).tag;
  await page.keyboard.press("Escape");
  out.expandedClosed = await withdraw.getAttribute("aria-expanded");
  out.focusAfterEscape = (await focused(page)).text;

  // Narrow layout: hidden form rows stay hidden.
  await page.setViewportSize({ width: 390, height: 900 });
  out.hiddenRowsShown = await page.locator("table.changes tr[hidden]").evaluateAll(
    (rows) => rows.filter((r) => getComputedStyle(r).display !== "none").length);

  // Requester: "another fact" field appears only when chosen.
  page = await open(REQUESTER, 1280);
  await openMatter(page);
  await page.getByRole("button", { name: "Change a fact" }).click();
  out.otherBefore = await page.getByLabel("Name of the other fact").isVisible();
  await page.getByLabel("Fact", { exact: true }).selectOption("__other");
  out.otherAfter = await page.getByLabel("Name of the other fact").isVisible();

  // Requester: cancelling the intake form restores the pane and the focus.
  const scenario = page.getByRole("button", { name: "Scenario 2: specialist input and revision" });
  await scenario.click();
  await page.getByRole("button", { name: "Cancel" }).click();
  out.paneAfterCancel = await page.locator("#matter").innerText();
  out.focusAfterCancel = (await focused(page)).text;

  // Opening the matter: while its GET is slow, the pane must not claim nothing was opened.
  await scenario.click();
  await page.getByLabel("Business owner on your side").fill("Synthetic Account Executive G");
  await page.route(/\/pilot\/api\/matters\/PM-UI-/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.getByRole("button", { name: "Open the matter" }).click();
  await page.waitForTimeout(500);
  out.paneDuringLoad = await page.locator("#matter").innerText();
  await page.waitForTimeout(2000);
  out.flashAfterOpen = await page.locator("#flash").innerText();

  // Presence: the approver has the matter open; the owner sees it, labelled as simulated.
  const approver = await open(APPROVER, 1280, "?presence_ms=1000");
  await openMatter(approver);
  const owner = await open(OWNER, 1280);
  await openMatter(owner);
  out.ownerPresence = await owner.locator("#presence").innerText();
  // The owner writes; the approver's open room checks in and warns that it is behind.
  await owner.getByLabel("Comment", { exact: true }).fill("Checked against the playbook position.");
  await owner.getByRole("button", { name: "add comment" }).click();
  await owner.waitForTimeout(500);
  await approver.waitForTimeout(2500);
  out.approverStale = await approver.locator("#stale").innerText();
  out.approverPresence = await approver.locator("#presence").innerText();
  // A second write: the warning names the newest revision, not the first one it saw.
  await owner.getByLabel("Comment", { exact: true }).fill("Second note on the same finding.");
  await owner.getByRole("button", { name: "add comment" }).click();
  await owner.waitForTimeout(500);
  await approver.waitForTimeout(2500);
  out.approverStaleAgain = await approver.locator("#stale").innerText();
  // Scrolled to the bottom of the page, the warning is still in view.
  await approver.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await approver.waitForTimeout(200);
  out.staleInView = await approver.locator("#stale").evaluate((el) => {
    const box = el.getBoundingClientRect();
    return box.top >= 0 && box.bottom <= window.innerHeight;
  });
  // A keyboard user on the reload button keeps focus when a further write arrives.
  await approver.getByRole("button", { name: "Reload the matter" }).focus();
  await owner.getByLabel("Comment", { exact: true }).fill("Third note on the same finding.");
  await owner.getByRole("button", { name: "add comment" }).click();
  await owner.waitForTimeout(500);
  await approver.waitForTimeout(2500);
  out.focusAfterRebuild = (await focused(approver)).text;
  out.approverStaleThird = await approver.locator("#stale").innerText();
  // At phone width, walking back up with Shift+Tab never leaves focus under the warning.
  await approver.setViewportSize({ width: 390, height: 900 });
  await approver.waitForTimeout(200);
  await approver.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  out.focusUnderWarning = 0;
  for (let i = 0; i < 40; i++) {
    await approver.keyboard.press("Shift+Tab");
    const hidden = await approver.evaluate(() => {
      const el = document.activeElement, stale = document.getElementById("stale");
      if (!el || el === document.body || stale.contains(el)) return false;
      const box = el.getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return Boolean(hit && stale.contains(hit));
    });
    if (hidden) out.focusUnderWarning += 1;
  }
  await approver.setViewportSize({ width: 1280, height: 900 });
  await approver.getByRole("button", { name: "Reload the matter" }).click();
  await approver.waitForTimeout(500);
  out.staleAfterReload = await approver.locator("#stale").innerText();
  // At phone width, a control that already has focus is moved clear when the warning appears.
  await approver.setViewportSize({ width: 390, height: 900 });
  const respond = approver.getByRole("button", { name: "respond", exact: true }).first();
  await respond.focus();
  await respond.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await owner.getByLabel("Comment", { exact: true }).fill("Fourth note, after the reload.");
  await owner.getByRole("button", { name: "add comment" }).click();
  await owner.waitForTimeout(500);
  await approver.waitForTimeout(2500);
  out.focusedCoveredOnAppear = await approver.evaluate(() => {
    const el = document.activeElement, stale = document.getElementById("stale");
    if (!stale.childNodes.length || !el || el === document.body) return "no warning or no focus";
    const box = el.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return Boolean(hit && stale.contains(hit));
  });
  // Switching role stops the check-ins: nothing is sent as the new role afterwards.
  let checkIns = 0, sentAsRequester = 0;
  approver.on("request", (r) => {
    if (r.method() !== "POST" || !r.url().endsWith("/presence")) return;
    if (r.headers()["x-pilot-actor"] === REQUESTER) sentAsRequester += 1; else checkIns += 1;
  });
  await approver.waitForTimeout(1500);
  out.checkInsWhileOpen = checkIns;
  await approver.selectOption("#actor", REQUESTER);
  await approver.waitForTimeout(2800);
  out.checkInsAfterSwitch = sentAsRequester;

  out.errors = errors;
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


TIMELINE_SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const [base, intact, broken, OWNER, REQUESTER] = process.argv.slice(2);
  const out = {};
  const errors = [];
  async function open(actor, matter) {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(base + "/pilot");
    await page.waitForSelector("#actor option", { state: "attached" });
    await page.selectOption("#actor", actor);
    await page.waitForTimeout(300);
    await page.locator("#list button", { hasText: matter }).first().click();
    await page.waitForSelector("#matter h2.title");
    return page;
  }
  const timeline = (page) => page.locator("section", { has: page.locator("#timeline-h") });
  const card = (page, index) => page.locator("#ev-" + index).evaluate((li) => ({
    badge: li.querySelector(".badge").textContent, badgeClass: li.querySelector(".badge").className,
    head: li.children[0].textContent, place: li.children[1].textContent, pre: li.querySelector("pre").textContent,
  }));

  // Intact chain: the status comes first, then the legend, then the events by version.
  let page = await open(OWNER, intact);
  out.firstAfterHeading = await timeline(page).evaluate((s) => {
    const first = s.querySelector("h2").nextElementSibling;
    return { cls: first.className, text: first.textContent };
  });
  out.legend = await timeline(page).locator("ul.legend .badge").allInnerTexts();
  out.events = await timeline(page).locator("li.ev").count();
  out.heading = await page.locator("#timeline-h").innerText();
  out.openGroups = await timeline(page).locator("details.version-group[open]").count();
  out.cards = [await card(page, 0), await card(page, 12)];
  out.findingsHeading = await page.locator("#findings-h").innerText();
  out.timing = await page.locator("section", { has: page.locator("#timing-h") }).innerText();
  out.timingTiles = await page.locator("ul.kpis li.kpi .kpi-title").allInnerTexts();
  await page.setViewportSize({ width: 390, height: 900 });
  await page.waitForTimeout(200);
  out.narrowOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  out.sectionOverflow = await timeline(page).evaluate((s) => s.scrollWidth > s.clientWidth);

  // Broken chain: the status explains it, and its link moves focus to the first bad event,
  // opening its version group even when the reviewer had closed it.
  page = await open(OWNER, broken);
  out.brokenStatus = await timeline(page).locator(".chain-status").innerText();
  out.badOpenBeforeJump = await timeline(page).locator("li.ev.first-bad").evaluate((li) => li.closest("details").open);
  out.openGroupsBroken = await timeline(page).locator("details.version-group[open]").count();
  out.legendBroken = await timeline(page).locator("ul.legend li").allInnerTexts();
  out.groupSummaries = await timeline(page).locator("details.version-group > summary").allInnerTexts();
  out.groupHashes = await timeline(page).locator("details.version-group > p.muted .hash").evaluateAll((spans) => spans.map((s) => s.textContent));
  out.setAside = await timeline(page).locator("details.version-group .context").allInnerTexts();
  await page.locator("#ev-5").evaluate((li) => { li.closest("details").open = false; });
  await page.getByRole("link", { name: "Go to the first event that is not verified" }).click();
  out.focused = await page.evaluate(() => {
    const a = document.activeElement;
    return { id: a.id, cls: a.className, open: Boolean(a.closest("details") && a.closest("details").open), text: a.innerText };
  });
  out.unverified = await timeline(page).locator("li.ev.unverified").count();
  out.brokenTiles = await page.locator("ul.kpis li.kpi strong").allInnerTexts();
  out.brokenTiming = await page.locator("section", { has: page.locator("#timing-h") }).innerText();

  // Requester: no timeline at all, checked once the requester's own view is on screen.
  page = await open(REQUESTER, intact);
  await page.waitForSelector("#status-h");
  out.requesterTimeline = await page.locator("#timeline-h, li.ev, .chain-status, #timing-h").count();

  out.errors = errors;
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


TIMING_SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const [base, OWNER, ...matters] = process.argv.slice(2);
  const out = {};
  for (const matter of matters) {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(base + "/pilot");
    await page.waitForSelector("#actor option", { state: "attached" });
    await page.selectOption("#actor", OWNER);
    await page.waitForTimeout(300);
    await page.locator("#list button", { hasText: matter }).first().click();
    await page.waitForSelector("#matter h2.title");
    await page.waitForTimeout(300);
    out[matter] = {
      errors,
      timing: await page.locator("#timing-h").count() ? await page.locator("section", { has: page.locator("#timing-h") }).innerText() : "",
      sections: await page.locator("#ready-h, #findings-h, #timeline-h").count(),
    };
  }
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


TRIAGE_SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const [base, blocked, open, OWNER, REQUESTER, REASON, PAUSE, QUESTION, ANSWER] = process.argv.slice(2);
  const out = {};
  const errors = [];
  async function room(actor, matter) {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("dialog", (d) => { errors.push("dialog: " + d.message()); d.dismiss(); });
    await page.goto(base + "/pilot");
    await page.waitForSelector("#actor option", { state: "attached" });
    await page.selectOption("#actor", actor);
    await page.waitForTimeout(300);
    await page.locator("#list button", { hasText: matter }).first().click();
    await page.waitForSelector("#matter h2.title");
    await page.waitForTimeout(300);
    return page;
  }
  const section = (page, id) => page.locator("section", { has: page.locator("#" + id) }).innerText();

  // The owner declines the matter that cannot leave triage, with a reason the requester sees.
  let page = await room(OWNER, blocked);
  await page.getByRole("button", { name: "mark duplicate → duplicate" }).click();
  out.duplicateLabels = await page.locator("form.inline label").allInnerTexts();
  await page.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "decline → declined" }).click();
  out.declineHint = await page.locator("form.inline .hint").first().innerText();
  out.declineEmpty = await page.locator("form.inline textarea").inputValue();
  await page.getByRole("button", { name: "Decline", exact: true }).click();
  out.declineSummary = await page.locator(".error-summary").innerText();
  await page.locator("form.inline textarea").fill(REASON);
  await page.getByRole("button", { name: "Decline", exact: true }).click();
  await page.waitForTimeout(500);
  out.declineFlash = await page.locator("#flash").innerText();
  out.declinedNext = await section(page, "next-h");
  out.declinedTiming = await section(page, "timing-h");
  page = await room(REQUESTER, blocked);
  out.requesterDeclined = await section(page, "status-h");

  // The owner snoozes the open matter until the requester answers a question.
  page = await room(OWNER, open);
  await page.getByRole("button", { name: "snooze", exact: true }).click();
  out.untilShown = await page.getByLabel("Until (date, time and time zone)").isVisible();
  out.untilHint = await page.locator("[data-field='until'] .hint").innerText();
  await page.getByLabel("Snooze until").selectOption("question");
  out.untilAfter = await page.getByLabel("Until (date, time and time zone)").isVisible();
  await page.getByLabel("Reason", { exact: true }).fill(PAUSE);
  await page.getByLabel("Question for the requester").fill(QUESTION);
  await page.getByRole("button", { name: "Snooze", exact: true }).click();
  await page.waitForTimeout(500);
  out.snoozedNext = await section(page, "next-h");
  out.endButtons = await page.getByRole("button", { name: "end snooze" }).count();

  // The requester sees the pause and answers its question in the room.
  page = await room(REQUESTER, open);
  out.requesterPaused = await section(page, "status-h");
  out.requesterQuestions = await section(page, "q-h");
  await page.getByRole("button", { name: "Answer", exact: true }).click();
  await page.getByLabel("Your answer").fill(ANSWER);
  await page.getByRole("button", { name: "Send the answer" }).click();
  await page.waitForTimeout(500);
  out.answerFlash = await page.locator("#flash").innerText();
  out.requesterAfter = await section(page, "status-h");
  page = await room(OWNER, open);
  out.ownerAfter = await section(page, "next-h");
  out.errors = errors;
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


FRAMING_SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const [base, matter, OWNER] = process.argv.slice(2);
  const out = {};
  const errors = [];

  // The room shows the approved package in its own sandboxed srcdoc frame.
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base + "/pilot");
  await page.waitForSelector("#actor option", { state: "attached" });
  await page.selectOption("#actor", OWNER);
  await page.waitForTimeout(300);
  await page.locator("#list button", { hasText: matter }).first().click();
  await page.waitForSelector("#matter h2.title");
  await page.getByRole("link", { name: "Open the approved customer package" }).first().click();
  const frame = page.frameLocator('iframe[title="Customer package"]');
  await frame.locator("h1").waitFor();
  out.packageHeading = await frame.locator("h1").innerText();
  out.packageFrameSrc = await page.locator('iframe[title="Customer package"]').evaluate((f) => f.src);
  out.errors = errors;

  // A page on another origin tries to frame the room.
  const context = await browser.newContext();
  const requested = [];
  context.on("request", (r) => requested.push(new URL(r.url()).pathname));
  const foreign = await context.newPage();
  await foreign.setContent('<iframe src="' + base + '/pilot" width="800" height="600"></iframe>');
  await foreign.waitForTimeout(1500);
  const child = foreign.frames().find((f) => f !== foreign.mainFrame());
  out.framedTitle = child ? await child.title().catch(() => "") : "";
  out.framedControls = child ? await child.locator("#actor").count().catch(() => 0) : 0;
  out.requested = requested;

  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


PACKAGE_SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const [base, ready, accepted, untouched, OWNER, REQUESTER, APPROVER, REASON] = process.argv.slice(2);
  const out = {};
  const errors = [];
  async function room(actor, matter) {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("dialog", (d) => { errors.push("dialog: " + d.message()); d.dismiss(); });
    await page.goto(base + "/pilot");
    await page.waitForSelector("#actor option", { state: "attached" });
    await page.selectOption("#actor", actor);
    await page.waitForTimeout(300);
    await page.locator("#list button", { hasText: matter }).first().click();
    await page.waitForSelector("#matter h2.title");
    await page.waitForTimeout(300);
    return page;
  }
  const LINK = "Open the approved customer package";
  // The requester's package line is under "Delivery package", a reviewer's under
  // "State and next steps". "links" counts the whole page, so no second link can hide.
  const line = async (page, heading) => ({
    links: await page.getByRole("link", { name: LINK }).count(),
    here: await page.locator("section", { has: page.locator("#" + heading) }).getByRole("link", { name: LINK }).count(),
    muted: await page.locator("section", { has: page.locator("#" + heading) }).locator("p.muted").allInnerTexts(),
  });
  const openIt = async (page) => {
    await page.getByRole("link", { name: LINK }).click();
    const frame = page.frameLocator('iframe[title="Customer package"]');
    await frame.locator("h1").waitFor();
    return frame.locator("h1").innerText();
  };

  // Ready for delivery: the requester and a reviewer each have the link.
  const stale = await room(REQUESTER, ready);
  out.readyRequester = await line(stale, "d-h");
  let page = await room(OWNER, ready);
  out.readyOwner = await line(page, "next-h");

  // The owner withdraws the matter in the room. The link goes and the reason takes its place.
  await page.getByRole("button", { name: "withdraw matter" }).click();
  await page.locator("form.inline textarea").fill(REASON);
  await page.getByRole("button", { name: "Withdraw", exact: true }).click();
  await page.locator("#flash", { hasText: "withdraw saved." }).waitFor();
  out.withdrawnOwner = await line(page, "next-h");

  // The requester's page was loaded before the withdrawal and still shows the link. The
  // server refuses the package, and the page says why in the server's words.
  out.staleLinks = (await line(stale, "d-h")).links;
  await stale.getByRole("link", { name: LINK }).click();
  await stale.locator("#flash.error").waitFor();
  out.staleFlash = await stale.locator("#flash").innerText();
  out.staleFrames = await stale.locator("iframe").count();

  // Loaded afresh, no view of the withdrawn matter has the link.
  page = await room(REQUESTER, ready);
  out.withdrawnRequester = await line(page, "d-h");
  out.withdrawnStatus = await page.locator("#status-h").innerText();
  page = await room(APPROVER, ready);
  out.withdrawnApprover = await line(page, "next-h");

  // Delivered and accepted: the package still opens, for the requester and for a reviewer.
  page = await room(REQUESTER, accepted);
  out.acceptedRequester = await line(page, "d-h");
  out.acceptedRequesterHeading = await openIt(page);
  page = await room(OWNER, accepted);
  out.acceptedOwner = await line(page, "next-h");
  out.acceptedOwnerHeading = await openIt(page);

  // Nothing was ever prepared: the plain sentence, and no reason.
  page = await room(REQUESTER, untouched);
  out.untouchedRequester = await line(page, "d-h");
  page = await room(OWNER, untouched);
  out.untouchedOwner = await line(page, "next-h");

  out.errors = errors;
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


ACCEPT_SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const [base, standing, ended, REQUESTER] = process.argv.slice(2);
  const out = {};
  const errors = [];
  async function room(actor, matter) {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("dialog", (d) => { errors.push("dialog: " + d.message()); d.dismiss(); });
    await page.goto(base + "/pilot");
    await page.waitForSelector("#actor option", { state: "attached" });
    await page.selectOption("#actor", actor);
    await page.waitForTimeout(300);
    await page.locator("#list button", { hasText: matter }).first().click();
    await page.waitForSelector("#matter h2.title");
    await page.waitForTimeout(300);
    return page;
  }
  // The requester's "Delivery package" section: the link, the Accept delivery button and
  // any muted sentence. The button is counted on the whole page, so none can hide elsewhere.
  const delivery = async (page) => {
    const section = page.locator("section", { has: page.locator("#d-h") });
    return {
      links: await section.getByRole("link", { name: "Open the approved customer package" }).count(),
      accept: await page.getByRole("button", { name: "Accept delivery" }).count(),
      muted: await section.locator("p.muted").allInnerTexts(),
    };
  };
  // The requester's "Status" section: the heading, the stage marked as current, and the
  // explanation and the next step as the page words them.
  const status = async (page) => {
    const section = page.locator("section", { has: page.locator("#status-h") });
    return {
      heading: await page.locator("#status-h").innerText(),
      current: await section.locator("ol.stages li[aria-current='step']").allTextContents(),
      said: await section.locator(":scope > p:not(.muted)").allInnerTexts(),
    };
  };
  let page = await room(REQUESTER, standing);
  out.standing = await delivery(page);
  out.standingStatus = await status(page);
  page = await room(REQUESTER, ended);
  out.ended = await delivery(page);
  out.endedStatus = await status(page);
  // Nowhere does the page of the ended delivery tell the requester to accept one.
  out.endedPage = await page.locator("#matter").innerText();
  out.errors = errors;
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _node_env() -> dict[str, str] | None:
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        return None
    root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, check=False)
    env = dict(os.environ)
    if root.returncode == 0 and root.stdout.strip():
        env["NODE_PATH"] = os.pathsep.join(
            filter(None, [root.stdout.strip(), env.get("NODE_PATH")])
        )
    return env


def _browser_unavailable(reason: str) -> None:
    """Skip, or fail when the environment promises a browser (REQUIRE_BROWSER_TESTS=1)."""

    if os.environ.get(REQUIRE_BROWSER_TESTS) == "1":
        pytest.fail(f"{reason} (REQUIRE_BROWSER_TESTS=1, so this is a failure, not a skip)")
    pytest.skip(reason)


def _run_node(tmp_path, monkeypatch, service, script: str, *args: str) -> dict:
    """Serve ``service`` on 127.0.0.1, run ``script`` with the base URL and ``args``."""

    env = _node_env()
    if env is None:
        _browser_unavailable("Node.js is not installed")
        return {}
    import runtime_agent.app as app

    monkeypatch.setattr(app, "_pilot_api", PilotApi(service))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.RuntimeHandler)
    except PermissionError:
        pytest.skip("this environment does not permit binding a local port")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path = tmp_path / "smoke.cjs"
    path.write_text(script)
    try:
        result = subprocess.run(
            ["node", str(path), f"http://127.0.0.1:{server.server_address[1]}", *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
    if result.returncode == UNAVAILABLE:
        _browser_unavailable("Node Playwright or its Chromium build is not installed")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_inline_forms_behave_in_a_browser(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    matter = run_until(service, "routine", "A06")  # in review, no comment yet
    out = _run_node(tmp_path, monkeypatch, service, SCRIPT, matter, OWNER, REQUESTER, APPROVER_LEAD)

    assert out["errors"] == []
    assert out["revisionDisabled"] and "must name an open comment" in out["revisionReason"]
    assert out["expandedOpen"] == "true" and out["expandedClosed"] == "false"
    assert out["summaryFocused"] == "error-summary" and out["linkFocused"] == "TEXTAREA"
    assert out["focusAfterEscape"] == "withdraw matter"
    assert out["hiddenRowsShown"] == 0
    assert (out["otherBefore"], out["otherAfter"]) == (False, True)
    assert "No matter was opened" in out["paneAfterCancel"]
    assert out["focusAfterCancel"] == "Scenario 2: specialist input and revision"
    assert "No matter was opened" not in out["paneDuringLoad"]
    assert "opened" in out["flashAfterOpen"]
    assert out["ownerPresence"].startswith(
        "Also open in the last two minutes (simulated local role, not authentication)"
    )
    assert " s ago" not in out["ownerPresence"]
    assert "Synthetic Approver D (Legal Ops Lead) on revision" in out["ownerPresence"]
    assert "changed after you loaded it" in out["approverStale"]
    assert "Synthetic Matter Owner B (Commercial Counsel) on revision" in out["approverPresence"]
    assert out["staleAfterReload"] == ""
    first = out["approverStale"].split("now revision ")[1].split(",")[0]
    again = out["approverStaleAgain"].split("now revision ")[1].split(",")[0]
    assert int(again) == int(first) + 1
    assert out["staleInView"] is True
    assert out["focusAfterRebuild"] == "Reload the matter"
    third = out["approverStaleThird"].split("now revision ")[1].split(",")[0]
    assert int(third) == int(again) + 1
    assert out["focusUnderWarning"] == 0
    assert out["focusedCoveredOnAppear"] is False
    assert out["checkInsWhileOpen"] >= 1 and out["checkInsAfterSwitch"] == 0


def test_audit_timeline_in_a_browser(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    intact = run_until(service, "routine", "A13")  # delivered, 12 events
    long_actor = "syn-" + "x" * 90  # refused and recorded: a long unbroken id and note
    with pytest.raises(PermissionDeniedError):
        service.withdraw(long_actor, intact, revision(service, intact), note="Long id test note.")
    broken = run_until(service, "specialist-revision", "B45")  # 43 events in 3 versions
    with service.store.transaction() as connection:  # edit position 5, in version 2
        connection.execute(
            "UPDATE events SET note = 'Edited later.' WHERE matter_id = ? AND seq = 5", (broken,)
        )
    out = _run_node(
        tmp_path, monkeypatch, service, TIMELINE_SCRIPT, intact, broken, OWNER, REQUESTER
    )
    history = service.history(OWNER, intact)["events"]
    broken_view = service.view_matter(OWNER, broken)

    assert out["errors"] == []
    assert "chain-status ok" in out["firstAfterHeading"]["cls"]
    assert out["firstAfterHeading"]["text"].startswith("✓ Event chain intact: 13 events")
    assert out["legend"] == ["Command", "Refusal", "Decision", "Export"]
    assert out["events"] == 13 and out["heading"] == "Audit-chain timeline (13 events)"
    assert out["openGroups"] == 1
    # Each card shows its class, type, actor, role, position, hash prefix and payload.
    for shown, row in zip(out["cards"], (history[0], history[12]), strict=True):
        label = {"command": "Command", "refusal": "Refusal"}[event_class(row["event_type"])]
        assert (shown["badge"], shown["badgeClass"]) == (
            label,
            "badge " + event_class(row["event_type"]),
        )
        assert shown["head"] == (
            f"{label} {row['event_type'].replace('_', ' ')} by {row['actor_id']} "
            f"({row['role'].replace('_', ' ')})"
        )
        assert shown["place"] == f"Position {row['seq']} · hash {row['event_hash'][:12]}"
        assert json.loads(shown["pre"]) == row["payload"]
    assert out["findingsHeading"].startswith("Findings (")
    # Time on the matter: four tiles on the scripted clock, measured to the closing event.
    assert out["timingTiles"] == ["Elapsed", "Business time", "First response", "Resolution"]
    assert "Scripted rehearsal time, up to the closing event" in out["timing"]
    assert "Target 16.0 h: ✓ met" in out["timing"]
    assert not any(word in out["timing"] for word in ("null", "undefined", "NaN"))
    # At phone width nothing runs out of the page or out of the timeline section.
    assert out["narrowOverflow"] is False and out["sectionOverflow"] is False

    assert "✗ Event chain broken: event_hash mismatch at seq 5." in out["brokenStatus"]
    assert (
        "Positions 0 to 4 are verified. The event at position 5 and every later event are not "
        "verified." in out["brokenStatus"]
    )
    assert [line.split(":")[0] for line in out["legendBroken"]] == [
        "Command 21 events",
        "Refusal 7 events",
        "Decision 13 events",
        "Export 2 events",
    ]
    assert out["groupSummaries"] == [
        "Version 1: 3 events, positions 0 to 2",
        "Version 2: 33 events, positions 3 to 35 · ✗ first bad event",
        "Version 3: 7 events, positions 36 to 42 · ✗ not verified",
    ]
    hashes = [
        v[key][:12] for v in broken_view["versions"] for key in ("document_sha256", "content_hash")
    ]
    assert out["groupHashes"] == hashes
    [set_aside] = out["setAside"]
    assert set_aside.startswith("Decisions on this version set aside later (1)")
    assert "specialist signoff: signed off by syn-specialist-privacy" in set_aside
    # Version 2 holds the first bad event and version 3 is current: both open, version 1 not.
    assert out["badOpenBeforeJump"] is True and out["openGroupsBroken"] == 2
    assert out["focused"]["id"] == "ev-5" and "first-bad" in out["focused"]["cls"]
    assert out["focused"]["open"] and "✗ First bad event" in out["focused"]["text"]
    assert out["unverified"] == 37
    timing = broken_view["timing"]
    assert out["brokenTiles"] == [
        f"{timing[key]:.1f} h"
        for key in ("elapsed_hours", "business_hours", "first_response_business_hours")
    ] + [f"{timing['legal_controlled_hours']:.1f} h"]
    assert "These times come from events the chain check did not verify." in out["brokenTiming"]
    assert out["requesterTimeline"] == 0


class _SetClock:
    def __init__(self, now: str) -> None:
        self.value = now

    def now(self) -> str:
        return self.value


def test_time_on_the_matter_never_stops_the_room(tmp_path, monkeypatch) -> None:
    clock = _SetClock("2026-11-02T08:00:00Z")  # Monday 09:00 in Berlin
    service = PilotService(
        PilotStore(tmp_path / "pilot.sqlite3"), export_root=tmp_path / "exports", clock=clock
    )
    seed_actors(service)
    api = PilotApi(service)
    made = api.handle(
        "POST",
        "/pilot/api/matters",
        {"X-Pilot-Actor": REQUESTER},
        {"scenario_id": "routine", "matter_id": "PM-OP-1"},
    )
    assert made[0] == 201, made
    body = {"command": "submit_intake", "expected_revision": made[1]["matter"]["revision"]}
    submitted = api.handle(
        "POST", "/pilot/api/matters/PM-OP-1/commands", {"X-Pilot-Actor": REQUESTER}, body
    )
    assert submitted[0] == 200, submitted
    open_matter = run_until(service, "blocked", "C10")  # in triage, nobody has responded
    unreadable = run_until(service, "routine", "A13")
    with service.store.transaction() as connection:
        connection.execute(
            "UPDATE events SET fixture_at = 'not a time' "
            "WHERE matter_id = ? AND event_type = 'intake_submitted'",
            (unreadable,),
        )
    clock.value = "2026-11-04T09:00:00Z"  # two days on: 19 business hours, no response
    out = _run_node(
        tmp_path, monkeypatch, service, TIMING_SCRIPT, OWNER, open_matter, unreadable, "PM-OP-1"
    )

    for matter in (open_matter, unreadable, "PM-OP-1"):
        assert out[matter]["errors"] == [] and out[matter]["sections"] == 3, matter
        assert not any(w in out[matter]["timing"] for w in ("null", "undefined", "NaN")), matter
    shown = out[open_matter]["timing"]
    assert "none yet" in shown and "Target 8.0 h: not measured yet" in shown
    assert "Scripted rehearsal time, up to the latest scripted step" in shown
    assert "of a 27.0 h target: still open" in shown
    assert "Time on this matter cannot be measured:" in out[unreadable]["timing"]
    recorded = out["PM-OP-1"]["timing"]
    assert "Target 16.0 h: ✗ past target, no response yet" in recorded
    assert "Time recorded by this server, up to when this page was loaded" in recorded


def test_room_shows_its_package_but_cannot_be_framed_by_another_page(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    matter = run_until(service, "routine", "A12")  # ready for delivery: the package exists
    out = _run_node(tmp_path, monkeypatch, service, FRAMING_SCRIPT, matter, OWNER)

    # The room's own package frame is a srcdoc document, which the no-framing headers allow.
    assert out["errors"] == []
    assert out["packageHeading"].startswith("Customer package")
    assert out["packageFrameSrc"] == ""
    # Another origin's frame asked for /pilot, and the browser refused to show it: the room
    # never ran, so it never fetched its actors.
    assert "/pilot" in out["requested"]
    assert out["framedTitle"] != "Pilot review room" and out["framedControls"] == 0
    assert "/pilot/api/actors" not in out["requested"]


def test_the_room_offers_the_package_only_while_its_delivery_stands(tmp_path, monkeypatch) -> None:
    service = make_service(tmp_path)
    ready = run_until(service, "routine", "A12")  # ready for delivery: the package exists
    accepted = run_until(service, "specialist-revision", "B45")  # delivered and accepted
    untouched = run_until(service, "blocked", "C02")  # in triage: nothing was ever prepared
    reason = "Customer paused the deal; closing without delivery."
    out = _run_node(
        tmp_path, monkeypatch, service, PACKAGE_SCRIPT, ready, accepted, untouched, OWNER,
        REQUESTER, APPROVER_LEAD, reason,
    )  # fmt: skip
    withdrawn = (
        "The package prepared earlier is no longer approved: the matter was withdrawn "
        "without delivery."
    )
    never = "No approved package yet."

    assert out["errors"] == []
    # While the delivery stands, each view has exactly one link, in its own section.
    assert out["readyRequester"] == {"links": 1, "here": 1, "muted": []}
    assert (out["readyOwner"]["links"], out["readyOwner"]["here"]) == (1, 1)
    assert withdrawn not in out["readyOwner"]["muted"] and never not in out["readyOwner"]["muted"]
    # Withdrawn after the package was prepared: no link for anyone, and the reason is shown.
    for view in ("withdrawnOwner", "withdrawnApprover"):
        assert (out[view]["links"], out[view]["here"]) == (0, 0), view
        assert withdrawn in out[view]["muted"] and never not in out[view]["muted"], view
    assert out["withdrawnRequester"] == {"links": 0, "here": 0, "muted": [withdrawn]}
    assert out["withdrawnStatus"] == "Status: Closed: withdrawn without delivery"
    # A page loaded before the withdrawal: the route refuses, and the page shows its sentence.
    assert out["staleLinks"] == 1
    assert out["staleFlash"] == withdrawn and out["staleFrames"] == 0
    # A delivered and accepted matter keeps its package.
    assert out["acceptedRequester"] == {"links": 1, "here": 1, "muted": []}
    assert (out["acceptedOwner"]["links"], out["acceptedOwner"]["here"]) == (1, 1)
    assert out["acceptedRequesterHeading"].startswith("Customer package")
    assert out["acceptedOwnerHeading"] == out["acceptedRequesterHeading"]
    # No package was ever prepared: the plain sentence, in both views.
    assert out["untouchedRequester"] == {"links": 0, "here": 0, "muted": [never]}
    assert (out["untouchedOwner"]["links"], out["untouchedOwner"]["here"]) == (0, 0)
    assert never in out["untouchedOwner"]["muted"]


def test_the_room_offers_acceptance_only_beside_a_package_that_may_be_opened(
    tmp_path, monkeypatch
) -> None:
    service = make_service(tmp_path)
    standing = run_until(service, "routine", "A12")  # ready for delivery: the package stands
    ended = run_until(service, "specialist-revision", "B44")  # ready for delivery as well
    # A note written after the package was prepared ends that delivery; the matter stays
    # ready for delivery, where the room used to keep offering the button and the status
    # used to read "Ready for you" with the next step "Accept delivery.".
    service.comment(
        OWNER,
        ended,
        revision(service, ended),
        anchor_kind="deliverable_section",
        anchor_id="accepted_exceptions",
        body="A late note on this section, written after the package was prepared.",
    )
    out = _run_node(tmp_path, monkeypatch, service, ACCEPT_SCRIPT, standing, ended, REQUESTER)
    changed = (
        "The package prepared earlier is no longer approved: the matter changed after it was "
        "prepared."
    )

    assert out["errors"] == []
    assert out["standing"] == {"links": 1, "accept": 1, "muted": []}
    assert out["ended"] == {"links": 0, "accept": 0, "muted": [changed]}
    # The status above the package line says the same. A standing delivery is ready for
    # the requester. One that ended is back with legal, and nothing asks for an acceptance.
    assert out["standingStatus"] == {
        "heading": "Status: Ready for you",
        "current": ["Ready for you (current stage)"],
        "said": [
            "The approved package is ready. Read it, then accept delivery.",
            "Your next step: Accept delivery.",
        ],
    }
    assert out["endedStatus"] == {
        "heading": "Status: In review",
        "current": ["In review (current stage)"],
        "said": [
            "The package prepared earlier is no longer approved, because the matter changed "
            "after it was prepared. Legal has to review the matter again before a package is "
            "ready for you.",
            "Your next step: No action needed from you.",
        ],
    }
    assert "ccept delivery" not in out["endedPage"]
    assert "approved package is ready" not in out["endedPage"]


def test_triage_verbs_take_a_typed_reason_in_the_room(tmp_path, monkeypatch) -> None:
    clock = _SetClock("2026-11-02T08:00:00Z")
    service = PilotService(
        PilotStore(tmp_path / "pilot.sqlite3"), export_root=tmp_path / "exports", clock=clock
    )
    seed_actors(service)
    blocked = run_until(service, "blocked", "C02")  # in triage; it can never leave it
    made = PilotApi(service).handle(
        "POST",
        "/pilot/api/matters",
        {"X-Pilot-Actor": REQUESTER},
        {"scenario_id": "routine", "matter_id": "PM-OP-1"},
    )
    assert made[0] == 201, made
    service.submit_intake(REQUESTER, "PM-OP-1", made[1]["matter"]["revision"])
    reason = "Outside the pilot charter: uncapped liability was requested."
    pause = "Waiting for the signed order form from the sales team."
    question = "Which order form does this draft belong to?"
    answer = "Order form OF-2026-118, signed on 1 November."
    out = _run_node(
        tmp_path, monkeypatch, service, TRIAGE_SCRIPT, blocked, "PM-OP-1", OWNER, REQUESTER,
        reason, pause, question, answer,
    )  # fmt: skip

    assert out["errors"] == []
    assert out["duplicateLabels"][0] == "Matter this request duplicates"
    # Nothing is proposed: the reason starts empty and must be typed.
    assert out["declineEmpty"] == "" and "The requester sees this reason." in out["declineHint"]
    assert "There is a problem" in out["declineSummary"] and "Enter reason" in out["declineSummary"]
    assert "decline saved." in out["declineFlash"]
    assert "declined" in out["declinedNext"] and "decline → declined" not in out["declinedNext"]
    assert "not applicable, declined" in out["declinedTiming"]
    assert "Status: Closed: declined by legal" in out["requesterDeclined"]
    assert reason in out["requesterDeclined"]
    assert (out["untilShown"], out["untilAfter"]) == (True, False)
    assert "2026-11-02T08:00:00Z" in out["untilHint"] and "2026-12-02T08:00:00Z" in out["untilHint"]
    assert "Snoozed since" in out["snoozedNext"] and question in out["snoozedNext"]
    assert out["endButtons"] == 1
    assert "Paused by legal" in out["requesterPaused"] and pause in out["requesterPaused"]
    assert question in out["requesterQuestions"]
    assert "answer snooze saved." in out["answerFlash"]
    assert "Paused by legal" not in out["requesterAfter"]
    assert "Last snooze" in out["ownerAfter"] and "the requester answered" in out["ownerAfter"]
    assert answer in out["ownerAfter"]
