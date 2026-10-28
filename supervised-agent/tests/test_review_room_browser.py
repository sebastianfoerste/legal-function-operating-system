"""Browser smoke test of the review room's inline forms.

Runs a short Node Playwright script against a local server on 127.0.0.1. It is
skipped when Node, its Playwright package or a Chromium build is not installed, so
the gate does not depend on a browser. Everything it touches is synthetic.
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
from tests.pilot_support import APPROVER_LEAD, OWNER, REQUESTER, make_service, run_until

UNAVAILABLE = 3

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


def test_inline_forms_behave_in_a_browser(tmp_path, monkeypatch) -> None:
    env = _node_env()
    if env is None:
        pytest.skip("Node.js is not installed")
    import runtime_agent.app as app

    service = make_service(tmp_path)
    matter = run_until(service, "routine", "A06")  # in review, no comment yet
    monkeypatch.setattr(app, "_pilot_api", PilotApi(service))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.RuntimeHandler)
    except PermissionError:
        pytest.skip("this environment does not permit binding a local port")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script = tmp_path / "smoke.cjs"
    script.write_text(SCRIPT)
    try:
        result = subprocess.run(
            [
                "node",
                str(script),
                f"http://127.0.0.1:{server.server_address[1]}",
                matter,
                OWNER,
                REQUESTER,
                APPROVER_LEAD,
            ],
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
        pytest.skip("Node Playwright or its Chromium build is not installed")
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])

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
