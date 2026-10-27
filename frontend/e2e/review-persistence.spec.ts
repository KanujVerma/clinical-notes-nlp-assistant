import { test, expect, Page } from "@playwright/test";

const BASE = "http://localhost:5173";

async function waitForReviewPage(page: Page) {
  await expect(page).toHaveURL(/\/review\/\d+/, { timeout: 15_000 });
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({ timeout: 10_000 });
}

test.describe("P0 Review Persistence & Category Acknowledgments", () => {
  test("Category completeness acknowledgments are initially unchecked and required", async ({ page }) => {
    await page.goto(BASE);
    const SAMPLE = `Patient: Jane Doe
Date of Service: 2026-03-01
Provider: Dr. Specialist

Vitals: BP 120/80. HR 72. Temp 98.6F. RR 16. SpO2 99%. Wt 140 lbs.

Medications:
- Lisinopril 10 mg PO daily
- Metformin 500 mg PO BID

Instructions:
Take medications as directed.
Follow up in 2 weeks.`;

    await page.getByPlaceholder("Paste clinical note text here...").fill(SAMPLE);
    await page.getByRole("button", { name: /Extract & Review/i }).click();
    await waitForReviewPage(page);

    // Verify all 4 category completeness checkboxes start unchecked
    const ackMeta = page.locator('[data-testid="ack-metadata"]');
    const ackVitals = page.locator('[data-testid="ack-vitals"]');
    const ackMeds = page.locator('[data-testid="ack-medications"]');
    const ackInst = page.locator('[data-testid="ack-instructions"]');

    await expect(ackMeta).toBeVisible();
    await expect(ackVitals).toBeVisible();
    await expect(ackMeds).toBeVisible();
    await expect(ackInst).toBeVisible();

    await expect(ackMeta).not.toBeChecked();
    await expect(ackVitals).not.toBeChecked();
    await expect(ackMeds).not.toBeChecked();
    await expect(ackInst).not.toBeChecked();

    // Clicking Accept all without acknowledging completeness should fail and show error
    await page.getByRole("button", { name: /Accept all/i }).click();
    await expect(page.getByText(/Completeness must be acknowledged for all categories/i)).toBeVisible({ timeout: 5_000 });
  });

  test("Removing medication frequency preserves medication name and persists on reload", async ({ page }) => {
    await page.goto(BASE);
    const SAMPLE = `Patient: John Doe
Date of Service: 2026-03-02
Provider: Dr. Clinician

Vitals: BP 130/85. HR 75.

Medications:
- Metformin 500 mg PO BID
- Metformin 1000 mg PO nightly

Instructions:
Diet and exercise.`;

    await page.getByPlaceholder("Paste clinical note text here...").fill(SAMPLE);
    await page.getByRole("button", { name: /Extract & Review/i }).click();
    await waitForReviewPage(page);

    // Check all 4 category acknowledgments
    await page.locator('[data-testid="ack-metadata"]').check();
    await page.locator('[data-testid="ack-vitals"]').check();
    await page.locator('[data-testid="ack-medications"]').check();
    await page.locator('[data-testid="ack-instructions"]').check();

    // Find the frequency field editor for the first medication and remove it
    const freqCard = page.locator(".group").filter({ has: page.getByText("frequency", { exact: true }) }).first();
    await freqCard.hover();
    const removeBtn = freqCard.locator("button:has-text('✕')");
    await removeBtn.click();

    // Verify the frequency now shows restore button (marked removed)
    await expect(page.getByText("restore")).toBeVisible();

    // Both Metformin entries should still exist (same-name medications remain distinct)
    const metforminCards = page.getByText(/Metformin/i);
    expect(await metforminCards.count()).toBeGreaterThanOrEqual(2);

    // Accept remaining fields and save
    await page.getByRole("button", { name: /Accept all/i }).click();

    // Wait for saved toast or redirect
    await expect(
      page.getByText(/Saved|Review saved|Review completed/i).or(page.getByText(/All notes reviewed/i))
    ).toBeVisible({ timeout: 10_000 });

    // Reload page
    await page.reload();
    await waitForReviewPage(page);

    // Verify Metformin medications still remain after reload
    const reloadedMeds = page.getByText(/Metformin/i);
    expect(await reloadedMeds.count()).toBeGreaterThanOrEqual(2);
  });
});
