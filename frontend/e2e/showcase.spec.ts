import { test, expect } from "@playwright/test";

const BASE = "http://localhost:5173";

/** Real local Flask + browser, no mock network route or fabricated model result. */
test("showcase presents only the committed measured Tesseract result", async ({ page }) => {
  await page.goto(BASE + "/showcase");
  await expect(page.getByRole("heading", { name: "Synthetic evidence showcase" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recorded Tesseract OCR baseline" })).toBeVisible();
  await expect(page.getByText("3.83%")).toBeVisible();
  await expect(page.getByText("27.14%")).toBeVisible();
  await expect(page.getByText("11/11")).toBeVisible();
  await expect(page.getByText(/No reviewed local-model recordings are published/i)).toBeVisible();
  await page.getByText(/synthetic print decimal/i).click();
  await expect(page.getByLabel(/Recorded OCR transcript for synthetic_print_decimal/i)).toContainText("2.5 mg");
});

test("metrics issue count drills to a source-authorized note and selected issue", async ({ page }) => {
  await page.goto(BASE);
  const seed = page.getByRole("button", { name: /Seed demo data/i });
  await expect(seed).toBeEnabled();
  const seededResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/seed-demo") && response.request().method() === "POST",
  );
  await seed.click();
  const seeded = await (await seededResponse).json();
  expect(seeded.loaded).toBeGreaterThan(0);
  await expect(page).toHaveURL(/\/queue/, { timeout: 15_000 });
  await page.goto(BASE + "/metrics");
  const warningLink = page.getByRole("link", {
    name: "Inspect current open warning issues and source evidence",
  });
  await expect(warningLink).toBeVisible();
  await warningLink.click();
  await expect(page).toHaveURL(/\/metrics\/drilldown\?kind=issues/);
  const inspect = page.getByRole("link", { name: /Inspect source and evidence for note/i }).first();
  await expect(inspect).toBeVisible({ timeout: 12_000 });
  await inspect.click();
  await expect(page).toHaveURL(/\/review\/\d+\?.*source_revision_id=.*extraction_id=.*issue=/);
  await expect(page.getByRole("region", { name: "Operational issues for current note" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByLabel(/Selected issue/i)).toBeVisible();
});

test("stale metric evidence link refuses to display a different note source", async ({ page }) => {
  await page.goto(BASE);
  const input = page.getByPlaceholder("Paste clinical note text here...");
  await input.fill("Synthetic note only. BP: 120/80. HR: 72. No identifying data.");
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await expect(page).toHaveURL(/\/review\/\d+/, { timeout: 15_000 });
  const noteId = page.url().match(/\/review\/(\d+)/)?.[1];
  expect(noteId).toBeTruthy();

  await page.goto(BASE + "/review/" + noteId +
    "?source_revision_id=outdated-source&extraction_id=outdated-extraction&field=vitals.blood_pressure");
  await expect(page.getByRole("heading", { name: "Evidence link needs refreshing" }))
    .toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("button", { name: "Return to metrics" })).toBeVisible();
  await expect(page.getByText("Reviewer", { exact: true })).not.toBeVisible();
});
