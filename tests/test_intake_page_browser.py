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
    review_rows,
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
  const elsewhere = "file://" + process.argv[3];
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
  const attr = (selector, name) => page.locator(selector).getAttribute(name);
  const summary = () => page.locator("#error-summary li").allTextContents();
  const save = async () => {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save request file" }).click()]);
    return { text: fs.readFileSync(await download.path(), "utf8"), name: download.suggestedFilename() };
  };

  out.optionalMarks = await page.locator("#f-counterparty-optional").count();
  out.optionalAtStart = await page.locator("#f-counterparty-optional").isVisible();
  out.errorsHiddenAtStart = await page.locator(".field-error").evaluateAll((all) => all.every((e) => e.hidden));

  // Nothing answered: the error summary takes focus, and each error is wired to its field.
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.firstErrors = await summary();
  out.focusAfterCheck = await focused();
  out.titleWithErrors = await page.title();
  out.titleInvalid = await attr("#f-title", "aria-invalid");
  out.titleDescribed = await attr("#f-title", "aria-describedby");
  out.titleErrorText = await page.locator("#f-title-error-text").textContent();
  out.titleFieldClass = await attr("#f-title-field", "class");
  out.typeDescribed = await attr("#f-type", "aria-describedby");
  await page.locator("#error-summary a").first().click();
  out.focusAfterLink = await focused();
  await page.locator("#error-summary a", { hasText: "Choose what you need help with" }).click();
  out.focusAfterRadioLink = await focused();
  out.urlAfterSummaryLink = page.url();

  // Enter in a text field goes nowhere: the page has no form.
  await page.locator("#f-title").fill("DPA with Example Hosting GmbH (synthetic)");
  await page.locator("#f-title").press("Enter");
  out.urlAfterEnter = page.url();
  // Leaving the type question with nothing chosen says nothing.
  out.typeStatusUnchosen = await page.locator("#type-status").textContent();

  // "Not sure" as the first choice is announced too.
  await group("What do you need help with?").getByLabel("Something else, or not sure").check();
  await page.locator("#f-title").focus();
  out.firstNotSureStatus = await page.locator("#type-status").textContent();

  // The type is announced once the requester moves on: not at each arrow key, and not
  // when a click on an answer's label blurs the chosen radio before the type changes.
  await page.evaluate(() => {
    window.typeStatusChanges = 0;
    new MutationObserver(() => { window.typeStatusChanges++; }).observe(document.getElementById("type-status"), { childList: true, characterData: true, subtree: true });
  });
  await group("What do you need help with?").getByLabel("Data processing agreement (DPA)").check();
  await page.locator("#f-type label", { hasText: "Checking a new supplier" }).click();
  await page.locator("#f-type label", { hasText: "Data processing agreement (DPA)" }).click();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  out.typeStatusChangesOnType = await page.evaluate(() => window.typeStatusChanges);
  out.dpaShown = await page.locator("#type-2").isVisible();
  await group("Value of the contract or claim").getByLabel("Under EUR 50,000").check();
  out.typeAnnounced = await page.locator("#type-status").textContent();
  out.statusAfterAnnouncement = await page.locator("#status").textContent();
  out.optionalAfterDpa = await page.locator("#f-counterparty-optional").isVisible();
  await group("Does it involve personal data?").getByLabel("Yes").check();
  out.countriesBefore = await page.locator("#q2-transfer_countries-field").isVisible();
  await group(/outside the EEA/).getByLabel("Yes").check();
  out.countriesAfter = await page.locator("#q2-transfer_countries-field").isVisible();
  await group(/unlimited liability/).getByLabel("No").check();
  await group("How soon do you need an answer?").getByLabel("Within a few days").check();
  await page.getByLabel("What do you need from legal?").fill("Please review the DPA.\nIt covers support tickets.");

  // The type makes the other party required, and its questions need answers.
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.secondErrors = await summary();
  out.titleErrorHidden = await page.locator("#f-title-error").isHidden();
  out.titleDescribedAfterFix = await attr("#f-title", "aria-describedby");
  out.titleInvalidAfterFix = await attr("#f-title", "aria-invalid");
  out.titleFieldClassAfterFix = await attr("#f-title-field", "class");

  // A question hidden since the check is no longer asked for.
  await group(/outside the EEA/).getByLabel("No").check();
  out.errorsAfterHiding = await summary();
  await group(/outside the EEA/).getByLabel("Yes").check();
  // Shown again, the question no longer carries the dropped error.
  out.countriesShownAgain = await page.evaluate(() => [document.getElementById("q2-transfer_countries-error").hidden, document.getElementById("q2-transfer_countries-field").className]);

  // Another type hides this one's questions and their errors.
  await group("What do you need help with?").getByLabel("Checking a new supplier").check();
  await page.getByLabel(/^Other party/).focus();
  out.afterSwitch = {
    dpa: await page.locator("#type-2").isVisible(),
    vendor: await page.locator("#type-1").isVisible(),
    optional: await page.locator("#f-counterparty-optional").isVisible(),
    errors: await summary(),
    invalid: await attr("#f-counterparty", "aria-invalid"),
    title: await page.title(),
  };
  await group("What do you need help with?").getByLabel("Data processing agreement (DPA)").check();

  await page.getByLabel(/^Other party/).fill("Example Hosting GmbH");
  await group("Who decides how the data is used?").getByLabel("Not sure").check();
  await page.getByLabel("What is the data used for?").fill("Support tickets.");
  await page.getByLabel("Which countries outside the EEA?").fill("United States");
  await group("Will sub-processors be involved?").getByLabel("Yes").check();
  await page.getByLabel(/^Which sub-processors\?/).fill("Example Mail Inc.");
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.summaryHidden = await page.locator("#error-summary").isHidden();
  out.marksAtReview = await page.evaluate(() => document.querySelectorAll(".field-error:not([hidden]), .has-error").length);
  // A question with no hint is described by nothing once its error clears.
  out.purposeDescribedAfterFix = await attr("#q2-processing_purpose", "aria-describedby");
  out.titleAfterFix = await page.title();
  out.reviewFocused = await focused();
  out.statusAtReview = await page.locator("#status").textContent();
  out.typeStatusAtReview = await page.locator("#type-status").textContent();
  out.review = await page.locator("#review-list .review-row").evaluateAll((rows) => rows.map((r) => [r.children[0].textContent, r.children[1].textContent]));
  out.file = await page.locator("#file").textContent();

  // Change reaches the chosen answer, so Space would not change it.
  await page.locator("#review-list .review-row").nth(1).getByRole("link").click();
  out.focusAfterChange = await focused();
  // The link's own handler moves focus; following the #fragment would also focus it.
  out.urlAfterChange = page.url();
  const saved = await save();
  out.saved = saved.text;
  out.savedName = saved.name;
  out.savedStatus = await page.locator("#status").textContent();
  out.overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  out.background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);

  // A change after the review hides it, so the file can never differ from what was shown.
  await group("How soon do you need an answer?").getByLabel("No special rush").check();
  out.reviewAfterChange = await page.locator("#review").isVisible();
  out.changeStatus = await page.locator("#status").textContent();
  await page.evaluate(() => {
    window.statusChanges = 0;
    new MutationObserver(() => { window.statusChanges++; }).observe(document.getElementById("status"), { childList: true, characterData: true, subtree: true });
  });
  await page.getByLabel("What do you need from legal?").press("End");
  await page.getByLabel("What do you need from legal?").press("x");
  await page.getByLabel("What do you need from legal?").press("Backspace");
  out.statusChangesAfterTyping = await page.evaluate(() => window.statusChanges);
  // Hiding a controller hides what depends on it; the hidden answer is not saved.
  await group("Will sub-processors be involved?").getByLabel("No").check();
  out.listAfterNo = await page.locator("#q2-sub_processor_list-field").isVisible();
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.reviewRowsAfterNo = await page.locator("#review-list .review-row").count();
  // The new review replaces "You changed an answer".
  out.statusAtSecondReview = await page.locator("#status").textContent();
  out.fileAfterNo = await page.locator("#file").textContent();

  // Going back to the page restores the answers, and the page shows what it will save.
  await page.goto(elsewhere);
  await page.goBack();
  out.afterBack = {
    dpa: await page.locator("#type-2").isVisible(),
    optional: await page.locator("#f-counterparty-optional").isVisible(),
  };
  // The restored type is not a change, so focus moving on says nothing about it.
  await page.locator("#f-title").focus();
  out.typeStatusAfterBack = await page.locator("#type-status").textContent();
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.fileAfterBack = await page.locator("#file").textContent();

  // A long title does not push the page sideways on a narrow phone.
  await page.setViewportSize({ width: 320, height: 900 });
  await page.locator("#f-title").fill("A".repeat(300));
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.longName = (await save()).name;
  out.overflowAt320 = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

  // Choosing "not sure" drops errors that were only the type's.
  await page.getByLabel("What is the data used for?").fill("");
  await page.getByRole("button", { name: "Check your answers" }).click();
  out.typeOnlyErrors = await summary();
  await group("What do you need help with?").getByLabel("Something else, or not sure").check();
  out.afterNotSure = { hidden: await page.locator("#error-summary").isHidden(), title: await page.title() };

  // Announcing the type when focus moves to Check does not move Check from under the
  // pointer, so one click at the end of the page still checks the answers.
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  const box = await page.getByRole("button", { name: "Check your answers" }).boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  out.notSureStatus = await page.locator("#type-status").textContent();
  await page.mouse.up();
  out.reviewAfterOneClick = await page.locator("#review").isVisible();
  out.typeStatusAfterOneClick = await page.locator("#type-status").textContent();

  // One question is "appears", not "appear".
  await group("What do you need help with?").getByLabel("Brands, patents or software rights").check();
  await page.getByLabel("What do you need from legal?").focus();
  out.oneQuestionStatus = await page.locator("#type-status").textContent();

  // Check reads the page as it is, even after a change that fired no event.
  const fresh = await page.context().newPage();
  fresh.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  await fresh.goto(url);
  await fresh.evaluate(() => { document.getElementById("f-type-2").checked = true; });
  await fresh.getByRole("button", { name: "Check your answers" }).click();
  out.silentChange = { dpa: await fresh.locator("#type-2").isVisible(), errors: await fresh.locator("#error-summary li").allTextContents() };
  await fresh.close();

  out.requests = requests;
  out.errors = errors;
  await browser.close();
  console.log(JSON.stringify(out));
})();
"""


def run_page(path: Path, elsewhere: Path) -> dict | None:
    """The browser run's results, or None when no browser is available."""

    if shutil.which("node") is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "intake.cjs"
        script.write_text(SCRIPT, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script), str(path), str(elsewhere)],
            capture_output=True, text=True, timeout=180, env=os.environ.copy(),
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
        elsewhere = Path(cls.tmp.name) / "elsewhere.html"
        elsewhere.write_text("<!doctype html><title>Elsewhere</title><p>Another page</p>\n", encoding="utf-8")
        cls.out = run_page(path, elsewhere)
        if cls.out is None:
            if os.environ.get(REQUIRE_BROWSER_TESTS) == "1":
                raise AssertionError("REQUIRE_BROWSER_TESTS=1 but Node, Playwright or Chromium is missing")
            raise unittest.SkipTest("Node, Playwright or Chromium is not installed")
        cls.path, cls.elsewhere = path, elsewhere

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
        # The only loads are the page itself and the page the test visits before going back.
        self.assertEqual(self.out["requests"][0], self.path.as_uri())
        self.assertLessEqual(set(self.out["requests"]), {self.path.as_uri(), self.elsewhere.as_uri()})
        self.assertEqual(self.out["errors"], [])
        self.assertEqual((self.out["overflow"], self.out["overflowAt320"]), (0, 0))
        self.assertEqual(self.out["background"], "rgb(25, 20, 19)")  # the dark --bg token
        self.assertEqual(self.out["urlAfterEnter"], self.path.as_uri())
        self.assertEqual(self.out["longName"], "legal-request-" + "a" * 50 + ".json")

    def test_missing_answers_are_named_linked_and_wired(self) -> None:
        empty = {"fields": {}, "questions": {}}
        self.assertTrue(self.out["errorsHiddenAtStart"])
        self.assertEqual(self.out["firstErrors"], [p["message"] for p in check_answers(self.form, empty)])
        self.assertEqual(self.out["focusAfterCheck"], "error-summary")
        self.assertEqual(self.out["titleWithErrors"], "Error: Prepare a legal request")
        self.assertEqual(
            (self.out["titleInvalid"], self.out["titleDescribed"], self.out["titleErrorText"]),
            ("true", "f-title-hint f-title-error", "Enter a short title"),
        )
        self.assertEqual(self.out["titleFieldClass"], "field has-error")
        self.assertEqual(self.out["typeDescribed"], "f-type-hint f-type-error")
        self.assertEqual(self.out["focusAfterLink"], "f-title")
        self.assertEqual(self.out["focusAfterRadioLink"], "f-type-0")
        self.assertEqual(self.out["urlAfterSummaryLink"], self.path.as_uri())
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
        self.assertTrue(self.out["titleErrorHidden"])
        self.assertEqual(
            (self.out["titleDescribedAfterFix"], self.out["titleInvalidAfterFix"], self.out["titleFieldClassAfterFix"]),
            ("f-title-hint", None, "field"),
        )
        self.assertTrue(self.out["summaryHidden"])
        self.assertEqual(self.out["marksAtReview"], 0)
        self.assertIsNone(self.out["purposeDescribedAfterFix"])
        self.assertEqual(self.out["titleAfterFix"], "Prepare a legal request")

    def test_errors_for_hidden_questions_are_dropped(self) -> None:
        self.assertEqual(
            self.out["errorsAfterHiding"],
            [
                "Enter the other party",
                "Choose who decides how the data is used",
                "Enter what the data is used for",
                "Choose whether sub-processors will be involved",
            ],
        )
        self.assertEqual(self.out["countriesShownAgain"], [True, "field"])
        # The new type does not require the other party, so its error goes too.
        self.assertEqual(
            self.out["afterSwitch"],
            {"dpa": False, "vendor": True, "optional": True, "errors": [], "invalid": None, "title": "Prepare a legal request"},
        )
        self.assertEqual(self.out["typeOnlyErrors"], ["Enter what the data is used for"])
        silent = {"fields": {"type": "2"}, "questions": {}}
        self.assertEqual(
            self.out["silentChange"],
            {"dpa": True, "errors": [p["message"] for p in check_answers(self.form, silent)]},
        )
        self.assertEqual(self.out["afterNotSure"], {"hidden": True, "title": "Prepare a legal request"})

    def test_type_questions_appear_in_place(self) -> None:
        self.assertEqual((self.out["optionalMarks"], self.out["optionalAtStart"]), (1, True))
        self.assertEqual(self.out["typeStatusUnchosen"], "")
        self.assertEqual(self.out["firstNotSureStatus"], "No further questions for this answer.")
        self.assertEqual(self.out["typeStatusChangesOnType"], 0)
        self.assertEqual(
            self.out["typeAnnounced"],
            "3 more questions for Data processing agreement (DPA) appear after the questions about the request.",
        )
        # The visible status is left for the page's own messages.
        self.assertEqual(self.out["statusAfterAnnouncement"], "")
        self.assertEqual(
            self.out["oneQuestionStatus"],
            "1 more question for Brands, patents or software rights appears after the questions about the request.",
        )
        self.assertTrue(self.out["reviewAfterOneClick"])
        # The review shows every answer, so the announcement does not outlive it.
        self.assertEqual(self.out["typeStatusAfterOneClick"], "")
        self.assertTrue(self.out["dpaShown"])
        self.assertFalse(self.out["optionalAfterDpa"])
        self.assertEqual((self.out["countriesBefore"], self.out["countriesAfter"]), (False, True))
        self.assertFalse(self.out["listAfterNo"])
        self.assertEqual(self.out["notSureStatus"], "No further questions for this answer.")

    def test_the_saved_file_is_the_reviewed_file(self) -> None:
        answers = self.answers()
        request = request_from_answers(self.form, answers)
        self.assertEqual(self.out["reviewFocused"], "review")
        self.assertEqual(self.out["statusAtReview"], "")
        self.assertEqual(self.out["typeStatusAtReview"], "")
        self.assertEqual(self.out["review"], [[r["label"], r["answer"]] for r in review_rows(self.form, answers)])
        self.assertEqual(self.out["file"], render_download(request))
        self.assertEqual(self.out["saved"], render_download(request))
        self.assertEqual(self.out["focusAfterChange"], "f-type-2")
        self.assertEqual(self.out["urlAfterChange"], self.path.as_uri())
        self.assertEqual(self.out["savedName"], download_name(request))
        self.assertEqual(self.out["savedName"], "legal-request-dpa-with-example-hosting-gmbh-synthetic.json")
        self.assertEqual(
            self.out["savedStatus"],
            f"Your browser is saving {self.out['savedName']} to this device. Nothing was sent. "
            "Give the file to legal yourself; a person in legal reviews every request.",
        )

    def test_a_change_after_the_review_needs_a_new_check(self) -> None:
        self.assertFalse(self.out["reviewAfterChange"])
        self.assertEqual(
            self.out["changeStatus"], "You changed an answer. Check your answers again before you save the file."
        )
        self.assertEqual(self.out["statusChangesAfterTyping"], 0)
        self.assertEqual(self.out["statusAtSecondReview"], "")
        answers = self.answers(urgency="2", sub_processors="1")
        request = request_from_answers(self.form, answers)
        self.assertEqual(self.out["fileAfterNo"], render_download(request))
        self.assertEqual(self.out["reviewRowsAfterNo"], len(review_rows(self.form, answers)))
        self.assertNotIn("sub_processor_list: Example Mail Inc.", self.out["fileAfterNo"])

    def test_going_back_to_the_page_shows_what_it_will_save(self) -> None:
        self.assertEqual(self.out["afterBack"], {"dpa": True, "optional": False})
        self.assertEqual(self.out["typeStatusAfterBack"], "")
        request = request_from_answers(self.form, self.answers(urgency="2", sub_processors="1"))
        self.assertEqual(self.out["fileAfterBack"], render_download(request))


if __name__ == "__main__":
    unittest.main()
