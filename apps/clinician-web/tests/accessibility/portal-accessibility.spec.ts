import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoWcagViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
}

test("desktop access boundary has no detectable WCAG A/AA violations", async ({ page }) => {
  await page.goto("/access?reason=authentication-required");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Sign in through your clinic.",
  );
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expectNoWcagViolations(page);
});

test("representative dashboard and form states have no detectable WCAG A/AA violations", async ({ page }) => {
  await page.goto("/accessibility-preview");
  await expect(page.getByRole("heading", {
    level: 1,
    name: "Representative clinical workspace states.",
  })).toBeVisible();
  await expect(page.getByRole("region", { name: "Learner practice records" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create learner record" })).toBeVisible();
  await expectNoWcagViolations(page);
});

test("keyboard users can skip repeated navigation", async ({ page }) => {
  await page.goto("/access?reason=authentication-required");
  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "Skip to main content" });
  await expect(skipLink).toBeFocused();
  await skipLink.press("Enter");
  await expect(page.locator("main")).toBeFocused();
});

test("current consent stays visible while earlier choices expand with the keyboard", async ({ page }) => {
  await page.goto("/accessibility-preview");
  const current = page.getByRole("list", { name: "Current consent", exact: true });
  const earlier = page.getByRole("list", { name: "Earlier consent choices", exact: true });
  const toggle = page.locator(".consent-history-disclosure > summary");
  await expect(current.getByText("Consent v2", { exact: false })).toBeVisible();
  await expect(earlier).toBeHidden();
  await toggle.focus();
  await toggle.press("Enter");
  await expect(earlier.getByText("Consent v1", { exact: true })).toBeVisible();
  await expect(earlier.getByText("Clinician review · Off", { exact: true })).toBeVisible();
  await expect(current.getByText("Clinician review · On", { exact: true })).toBeVisible();
  await expectNoWcagViolations(page);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  await toggle.press("Space");
  await expect(earlier).toBeHidden();
  await expect(current).toBeVisible();
});

test("practice worklist exposes activity, filters, and direct actions", async ({ page }) => {
  await page.goto("/accessibility-preview?view=overview");
  await expect(page.getByText("Demo workspace", { exact: true })).toBeVisible();
  const records = page.getByRole("list", { name: "Learner practice records" });
  await expect(records.locator("li")).toHaveCount(5);
  const avery = records.locator("li").filter({ hasText: "Avery M." });
  await expect(avery).toContainText("Beginning /b/");
  await expect(avery).toContainText("Sep 21, 2026");
  await expect(avery).toContainText("12");
  await expect(avery).toContainText("Available");
  await expect(avery.getByRole("link", { name: "Review attempts" })).toHaveAttribute("href", "/accessibility-preview/review?learner=demo-learner-01");
  await expect(avery.getByRole("link", { name: "Preview assignment" })).toHaveCount(0);
  await expect(page.locator("#notebook-inspector")).toHaveCount(0);

  await page.getByRole("button", { name: "Review available", exact: true }).click();
  await expect(records.locator("li")).toHaveCount(2);
  await expect(records).toContainText("Jordan L.");
  const search = page.getByRole("searchbox", { name: "Search demo learners" });
  await search.fill("Jordan");
  await expect(records.locator("li")).toHaveCount(1);
  await search.fill("Taylor");
  await expect(page.getByText("No learners match this view.")).toBeVisible();
  await search.fill("");
  await page.getByRole("button", { name: "All learners", exact: true }).click();
  await expect(records.locator("li")).toHaveCount(5);
  await expectNoWcagViolations(page);

  await page.setViewportSize({ width: 960, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(search).toBeVisible();
  await expect(avery.getByRole("link", { name: "Review attempts" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  await expectNoWcagViolations(page);
  await avery.getByRole("link", { name: "Review attempts" }).focus();
  await avery.getByRole("link", { name: "Review attempts" }).press("Enter");
  await expect(page).toHaveURL(/\/accessibility-preview\/review\?learner=demo-learner-01$/);
});

test("mobile menu and forced-colors states remain operable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/access?reason=authentication-required");

  const menu = page.getByText("Menu", { exact: true });
  await expect(menu).toBeVisible();
  await menu.click();
  await expect(page.getByRole("navigation", { name: "Mobile primary navigation" }))
    .toBeVisible();
  await expectNoWcagViolations(page);

  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await expect(menu).toBeVisible();
  await expect(page.getByRole("link", { name: "Try workspace again" })).toBeVisible();

  const horizontalOverflow = await page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(horizontalOverflow).toBe(false);
});

test("demo navigation stays in the preview and assignment changes stay local", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) writes.push(request.url());
  });
  await page.goto("/accessibility-preview?view=overview");
  await page.getByRole("list", { name: "Learner practice records" }).locator("li").filter({ hasText: "Sam K." }).getByRole("link", { name: "Preview assignment" }).click();
  await expect(page).toHaveURL(/\/accessibility-preview\/assignments\?learner=demo-learner-03#assignment-form$/);
  await expect(page.getByRole("navigation", { name: "Primary", exact: true }).getByRole("link", { name: "Assignments" })).toHaveAttribute("aria-current", "page");
  const learnerSelect = page.getByRole("combobox", { name: "Learner", exact: true });
  await expect(learnerSelect).toHaveValue("demo-learner-03");
  await expect(page.getByRole("heading", { name: "Prepare a practice dose for Sam K." })).toBeVisible();
  await expect(page.getByText("Initial /m/ · bilabial closure")).toBeVisible();
  const planFit = page.getByRole("checkbox", { name: "I checked the learner's current practice plan and confirmed this exercise fits." });
  const previewButton = page.getByRole("button", { name: "Preview assignment" });
  await expect(previewButton).toBeDisabled();
  await expect(page.getByText("Beginning /b/ · audio practice")).toBeVisible();
  await expect(page.getByText("Silent capture only")).toBeVisible();
  await expect(page.getByText("Off", { exact: true })).toBeVisible();
  await learnerSelect.selectOption("demo-learner-01");
  await expect(page.getByRole("heading", { name: "Prepare a practice dose for Avery M." })).toBeVisible();
  await expect(page.getByText("Beginning /b/ · bilabial closure")).toBeVisible();
  await planFit.check();
  await expect(previewButton).toBeEnabled();
  await learnerSelect.selectOption("demo-learner-02");
  await expect(planFit).not.toBeChecked();
  await expect(previewButton).toBeDisabled();
  await planFit.check();
  await page.getByLabel("Accepted repetitions").selectOption("8");
  await page.getByLabel("Capture retries").selectOption("2");
  await previewButton.click();
  await expect(page.getByRole("status")).toHaveText("Jordan L. · ball · 8 repetitions · 2 retries. Nothing was saved or sent.");
  await page.getByLabel("Accepted repetitions").selectOption("3");
  await expect(page.getByRole("status")).toBeEmpty();
  await expectNoWcagViolations(page);
  expect(writes).toEqual([]);

  for (const [link, title] of [["Learners", "Learners"], ["Attempt review", "Attempt review"], ["Safety desk", "Safety desk"]] as const) {
    const navigation = page.getByRole("navigation", { name: "Primary", exact: true });
    await navigation.getByRole("link", { name: link, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: title, exact: true })).toBeVisible();
    await expect(navigation.getByRole("link", { name: link, exact: true })).toHaveAttribute("aria-current", "page");
    if (link === "Safety desk") {
      await expect(page.getByRole("heading", { level: 2, name: "Capture retry" })).toBeVisible();
      await expect(page.getByText("Fictional record", { exact: true })).toBeVisible();
      await expect(page.getByRole("link", { name: "Jordan L." })).toHaveAttribute("href", "/accessibility-preview/learners?learner=demo-learner-02");
    }
    await expectNoWcagViolations(page);
  }
  await page.getByRole("link", { name: "Privacy and data controls" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Privacy and consent" })).toBeVisible();
  await expectNoWcagViolations(page);
  expect(writes).toEqual([]);
  const unknown = await page.goto("/accessibility-preview/not-a-view");
  expect(unknown?.status()).toBe(404);
  const removedComparison = await page.goto("/accessibility-preview?view=compare");
  expect(removedComparison?.status()).toBe(404);
});

test("general assignment entry requires an explicit learner choice", async ({ page }) => {
  await page.goto("/accessibility-preview/assignments");
  const learnerSelect = page.getByRole("combobox", { name: "Learner", exact: true });
  const planFit = page.getByRole("checkbox", { name: "I checked the learner's current practice plan and confirmed this exercise fits." });
  const previewButton = page.getByRole("button", { name: "Preview assignment" });
  await expect(learnerSelect).toHaveValue("");
  await expect(page.getByRole("heading", { name: "Prepare a practice dose", exact: true })).toBeVisible();
  await expect(planFit).toBeDisabled();
  await expect(previewButton).toBeDisabled();
  await learnerSelect.selectOption("demo-learner-01");
  await expect(planFit).toBeEnabled();
  await expect(page.getByRole("heading", { name: "Prepare a practice dose for Avery M." })).toBeVisible();
  await planFit.check();
  await expect(previewButton).toBeEnabled();
  await learnerSelect.selectOption("demo-learner-02");
  await expect(planFit).not.toBeChecked();
  await expect(previewButton).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  await expectNoWcagViolations(page);
});

test("mobile preview navigation closes and keeps the selected page reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/accessibility-preview/overview");
  await page.getByText("Menu", { exact: true }).click();
  const navigation = page.getByRole("navigation", { name: "Mobile primary navigation" });
  await navigation.getByRole("link", { name: "Assignments" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Assignments" })).toBeVisible();
  await expect(navigation).toBeHidden();
  await expectNoWcagViolations(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  await page.getByText("Menu", { exact: true }).click();
  await expect(navigation.getByRole("link", { name: "Assignments" })).toHaveAttribute("aria-current", "page");
  await navigation.getByRole("link", { name: "Practice", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Practice overview" })).toBeVisible();
});

test("selected learner review keeps capture evidence visible on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/accessibility-preview/overview");
  await page.getByRole("list", { name: "Learner practice records" }).locator("li").filter({ hasText: "Jordan L." }).getByRole("link", { name: "Review attempts" }).click();
  await expect(page).toHaveURL(/\/accessibility-preview\/review\?learner=demo-learner-02$/);
  const evidence = page.getByRole("list", { name: "Authorized attempt evidence" });
  await expect(evidence.locator("li")).toHaveCount(1);
  await expect(evidence.getByText("Retry requested")).toBeVisible();
  await expect(evidence.getByText(/background noise/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  await expectNoWcagViolations(page);
  await evidence.getByRole("link", { name: "Jordan L." }).click();
  await expect(page).toHaveURL(/\/accessibility-preview\/learners\?learner=demo-learner-02$/);
  await expect(page.getByRole("heading", { level: 1, name: "Jordan L." })).toBeVisible();
  await page.goBack();
  await expect(evidence.locator("li")).toHaveCount(1);
  await page.getByRole("link", { name: "All attempts" }).click();
  await expect(evidence.locator("li")).toHaveCount(2);
});

test("preview learner records are read-only and return to the learner list", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) writes.push(request.url());
  });
  await page.goto("/accessibility-preview/learners");
  await page.getByRole("link", { name: "Open record for Avery M." }).click();
  await expect(page).toHaveURL(/\/accessibility-preview\/learners\?learner=demo-learner-01$/);
  await expect(page.getByRole("heading", { level: 1, name: "Avery M." })).toBeVisible();
  await expect(page.getByText("Read-only demo record", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Current consent", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save consent choices" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Create device link code" })).toHaveCount(0);
  await expect(page.getByText("Review consent choices and capture details for this learner.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Connect a device" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Export or delete" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Export learner data" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Delete learner data" })).toHaveCount(0);
  await page.locator(".consent-history-disclosure > summary").click();
  await expect(page.getByRole("list", { name: "Earlier consent choices", exact: true })).toBeVisible();
  const captures = page.getByRole("list", { name: "Recent learner capture evidence" });
  await expect(captures).toContainText("ball");
  await expect(captures).toContainText("Beginning /b/");
  await expect(captures).toContainText("Capture accepted");
  await expect(page.locator(".record-status-strip dt").first()).toHaveText("Practice access");
  await expect(page.locator(".record-status-strip dd").first()).toHaveText("Audio permitted");
  await expect(captures).not.toContainText("Research benchmark");
  await expect(captures).not.toContainText("foundation-ball-initial-b-v1");
  await expect(page.getByText("No pronunciation score or audio recording is available.", { exact: false })).toBeVisible();
  await expectNoWcagViolations(page);
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(captures.getByText("Capture accepted")).toBeVisible();
    expect(await captures.evaluate((list) => list.scrollWidth <= list.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  }
  await page.getByRole("link", { name: "All learners" }).click();
  await expect(page).toHaveURL(/\/accessibility-preview\/learners$/);
  const mobileRecords = page.getByRole("list", { name: "Tenant learner records" });
  await expect(mobileRecords.getByRole("link")).toHaveCount(5);
  const riley = mobileRecords.getByRole("link", { name: /Riley N\. Open record/ });
  await expect(riley.locator(".clinical-learner-facts dt")).toHaveText(["Last practice", "Attempts", "Active devices"]);
  await expect(riley.locator(".clinical-learner-facts dd")).toHaveText(["No practice yet", "0", "0"]);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  }
  await expectNoWcagViolations(page);
  await riley.click();
  await expect(page.getByText("No practice attempts yet.", { exact: true })).toBeVisible();
  expect(writes).toEqual([]);
  for (const path of [
    "/accessibility-preview/learners?learner=unknown",
    "/accessibility-preview/learners?learner=demo-learner-01&learner=demo-learner-02",
    "/accessibility-preview/review?learner=unknown",
    "/accessibility-preview/review?learner=demo-learner-01&learner=demo-learner-02",
    "/accessibility-preview/assignments?learner=unknown",
    "/accessibility-preview/assignments?learner=demo-learner-01&learner=demo-learner-02",
    "/accessibility-preview/safety?learner=demo-learner-02",
  ]) expect((await page.goto(path))?.status()).toBe(404);
});
