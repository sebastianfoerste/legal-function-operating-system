"""The intake page in a real browser: what a requester does, and what the page saves.

Runs a short Node Playwright script against the page opened from a file. It is
skipped when Node, its Playwright package or a Chromium build is not installed, so
``make test`` does not need a browser. With ``REQUIRE_BROWSER_TESTS=1`` (set in the CI
agent job, which installs Playwright) that skip becomes a failure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from legal_function_os.intake_page import (
    check_answers,
    download_name,
    render_download,
    request_from_answers,
    write_intake_page,
)
from tests.test_intake_page import form_for

UNAVAILABLE = 3
REQUIRE_BROWSER_TESTS = "REQUIRE_BROWSER_TESTS"

SCRIPT = r"""
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { process.exit(3); }
(async () => {
  let browser;
  try { browser = await chromium.launch(); } catch (e) { process.exit(3); }
  const fs = require("fs");
  const url = "file://" + process.argv[2];
  const out = {};
  const page = await (await browser.newContext({ viewport: { width: 390, height: 900 }, colorScheme: "dark", acceptDownloads: true })).newPage();
  const errors = [], requests = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push("console: " + m.text()); });
  page.on("request", (r) => requests.push(r.url()));
  await page.addInitScript(() => document.addEventListener("securitypolicyviolation", (e) => console.error("csp " + e.violatedDirective)));
  await page.goto(url);
  const group = (name) => page.getByRole("group", { name });
  const focused = () => page.evaluate(() => document.activeElement.id);

  // Nothing answered: the error summary takes focus and its first link focuses the title.
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.firstErrors = await page.locator("#error-summary li").allTextContents();
  out.focusAfterCheck = await focused();
  out.titleWithErrors = await page.title();
  out.titleInvalid = await page.locator("#f-title").getAttribute("aria-invalid");
  await page.locator("#error-summary a").first().click();
  out.focusAfterLink = await focused();

  // Enter in a text field goes nowhere: the page has no form.
  await page.locator("#f-title").fill("DPA with Example Hosting GmbH (synthetic)");
  await page.locator("#f-title").press("Enter");
  out.urlAfterEnter = page.url();

  await group("What do you need help with?").getByLabel("Data processing agreement (DPA)").check();
  out.typeAnnounced = await page.locator("#status").textContent();
  out.dpaShown = await page.locator("#type-2").isVisible();
  await group("Value of the contract or claim").getByLabel("Under EUR 50,000").check();
  await group("Does it involve personal data?").getByLabel("Yes").check();
  out.countriesBefore = await page.locator("#q2-transfer_countries-field").isVisible();
  await group(/outside the EEA/).getByLabel("Yes").check();
  out.countriesAfter = await page.locator("#q2-transfer_countries-field").isVisible();
  await group(/unlimited liability/).getByLabel("No").check();
  await group("How soon do you need an answer?").getByLabel("Within a few days").check();
  await page.getByLabel("What do you need from legal?").fill("Please review the DPA.\nIt covers support tickets.");
  out.counterpartyOptional = await page.locator("#f-counterparty-optional").isVisible();

  // The type makes the other party required, and its questions need answers.
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.secondErrors = await page.locator("#error-summary li").allTextContents();
  out.titleErrorCleared = await page.locator("#f-title-error").isHidden();
  await page.getByLabel(/^Other party/).fill("Example Hosting GmbH");
  await group("Who decides how the data is used?").getByLabel("Not sure").check();
  await page.getByLabel("What is the data used for?").fill("Support tickets.");
  await page.getByLabel("Which countries outside the EEA?").fill("United States");
  await group("Will sub-processors be involved?").getByLabel("Yes").check();
  await page.getByLabel(/^Which sub-processors\?/).fill("Example Mail Inc.");
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.summaryHidden = await page.locator("#error-summary").isHidden();
  out.titleAfterFix = await page.title();
  out.reviewFocused = await focused();
  out.review = await page.locator("#review-list .review-row").evaluateAll((rows) => rows.map((r) => [r.children[0].textContent, r.children[1].textContent]));
  out.file = await page.locator("#file").textContent();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save request file" }).click()]);
  out.saved = fs.readFileSync(await download.path(), "utf8");
  out.savedName = download.suggestedFilename();
  out.savedStatus = await page.locator("#status").textContent();
  out.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  out.background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

  // A change after the review hides it, so the file can never differ from what was shown.
  await group("How soon do you need an answer?").getByLabel("No special rush").check();
  out.reviewAfterChange = await page.locator("#review").isVisible();
  out.changeStatus = await page.locator("#status").textContent();
  // Hiding a controller hides what depends on it; the hidden answer is not saved.
  await group("Will sub-processors be involved?").getByLabel("No").check();
  out.listAfterNo = await page.locator("#q2-sub_processor_list-field").isVisible();
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.fileAfterNo = await page.locator("#file").textContent();

  out.requests = requests;
  out.errors = errors;
  await browser.close();
  console.log(JSON.stringify(out));
})();
"""


def run_page(path: Path) -> dict | None:
    """The browser run's results, or None when no browser is available."""

    if shutil.which("node") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "intake.cjs"
        script.write_text(SCRIPT, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script), str(path)], capture_output=True, text=True, timeout=180, env=os.environ.copy()
        )
    if result.returncode == UNAVAILABLE:
        return None
    if result.returncode != 0:
        raise AssertionError(f"browser script failed: {result.stderr}")
    return json.loads(result.stdout.split("\n")[0])


class IntakePageBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.form = form_for()
        cls.tmp = tempfile.TemporaryDirectory()
        path = write_intake_page(cls.form, Path(cls.tmp.name))["html"]
        cls.out = run_page(path)
        if cls.out is None:
            if os.environ.get(REQUIRE_BROWSER_TESTS) == "1":
                raise AssertionError("REQUIRE_BROWSER_TESTS=1 but Node, Playwright or Chromium is missing")
            raise unittest.SkipTest("Node, Playwright or Chromium is not installed")
        cls.path = path

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def answers(self, urgency: str = "1", sub_processors: str = "0") -> dict:
        fields = {
            "title": "DPA with Example Hosting GmbH (synthetic)",
            "type": "2",
            "counterparty": "Example Hosting GmbH",
            "value_band": "1",
            "personal_data": "0",
            "non_eea_transfer": "0",
            "uncapped_liability": "1",
            "urgency": urgency,
            "description": "Please review the DPA.\nIt covers support tickets.",
        }
        questions = {
            "processing_role": "2",
            "processing_purpose": "Support tickets.",
            "transfer_countries": "United States",
            "sub_processors": sub_processors,
            "sub_processor_list": "Example Mail Inc.",
        }
        return {"fields": fields, "questions": questions}

    def test_the_page_makes_no_request_and_raises_no_error(self) -> None:
        self.assertEqual(self.out["requests"], [self.path.as_uri()])
        self.assertEqual(self.out["errors"], [])
        self.assertEqual(self.out["overflow"], 0)
        self.assertEqual(self.out["background"], "rgb(25, 20, 19)")  # the dark --bg token
        self.assertEqual(self.out["urlAfterEnter"], self.path.as_uri())

    def test_missing_answers_are_named_and_linked(self) -> None:
        empty = {"fields": {}, "questions": {}}
        self.assertEqual(self.out["firstErrors"], [p["message"] for p in check_answers(self.form, empty)])
        self.assertEqual(self.out["focusAfterCheck"], "error-summary")
        self.assertEqual(self.out["titleWithErrors"], "Error: Prepare a legal request")
        self.assertEqual(self.out["titleInvalid"], "true")
        self.assertEqual(self.out["focusAfterLink"], "f-title")
        self.assertEqual(
            self.out["secondErrors"],
            [
                "Enter the other party",
                "Choose who decides how the data is used",
                "Enter what the data is used for",
                "Enter the countries outside the EEA",
                "Choose whether sub-processors will be involved",
            ],
        )
        self.assertTrue(self.out["titleErrorCleared"])
        self.assertTrue(self.out["summaryHidden"])
        self.assertEqual(self.out["titleAfterFix"], "Prepare a legal request")

    def test_type_questions_appear_in_place(self) -> None:
        self.assertEqual(
            self.out["typeAnnounced"],
            "3 more questions for Data processing agreement (DPA) appear after the questions about the request.",
        )
        self.assertTrue(self.out["dpaShown"])
        self.assertEqual((self.out["countriesBefore"], self.out["countriesAfter"]), (False, True))
        self.assertTrue(self.out["counterpartyOptional"] is False)
        self.assertFalse(self.out["listAfterNo"])

    def test_the_saved_file_is_the_reviewed_file(self) -> None:
        request = request_from_answers(self.form, self.answers())
        self.assertEqual(self.out["reviewFocused"], "review")
        self.assertEqual(self.out["file"], render_download(request))
        self.assertEqual(self.out["saved"], render_download(request))
        self.assertEqual(self.out["savedName"], download_name(request))
        self.assertEqual(self.out["savedName"], "legal-request-dpa-with-example-hosting-gmbh-synthetic.json")
        self.assertEqual(
            self.out["savedStatus"],
            f"Your browser is saving {self.out['savedName']} to this device. Nothing was sent. "
            "Give the file to legal yourself; a person in legal reviews every request.",
        )
        self.assertIn(["Who decides how the data is used?", "Not sure"], self.out["review"])
        self.assertIn(["Date you need an answer by", "Not given"], self.out["review"])

    def test_a_change_after_the_review_needs_a_new_check(self) -> None:
        self.assertFalse(self.out["reviewAfterChange"])
        self.assertEqual(
            self.out["changeStatus"], "You changed an answer. Check your answers again before you save the file."
        )
        request = request_from_answers(self.form, self.answers(urgency="2", sub_processors="1"))
        self.assertEqual(self.out["fileAfterNo"], render_download(request))
        self.assertNotIn("sub_processor_list: Example Mail Inc.", self.out["fileAfterNo"])


if __name__ == "__main__":
    unittest.main()
