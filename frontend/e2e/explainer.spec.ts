/**
 * Explainer popover test — end-to-end contextual info feature.
 * Requires both servers running:
 *   backend: python app.py  (port 5000)
 *   frontend: npm run dev   (port 5173)
 */
import { test, expect, Page } from "@playwright/test";

const BASE = "http://localhost:5173";

// ── helpers ────────────────────────────────────────────────────────────────

async function waitForReviewPage(page: Page) {
  await expect(page).toHaveURL(/\/review\/\d+/, { timeout: 15_000 });
  // Wait for the Reviewer header — present regardless of field statuses
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({ timeout: 10_000 });
}

// ── tests ──────────────────────────────────────────────────────────────────

test("Medication popover — info icon shows explanation and disclaimer", async ({ page }) => {
  await page.goto(BASE);

  const SAMPLE = `Patient: Test Patient
Date of Service: 2025-01-15
Provider: Dr. Test

Vitals: BP 130/82. HR 76. Temp 98.6F. RR 14. SpO2 98%. Wt 165 lbs.

Medications:
- metformin 500 mg PO BID PRN

DISCHARGE INSTRUCTIONS:
Take medications as prescribed.

FOLLOW UP:
Return to clinic in 2 weeks.`;

  await page.getByPlaceholder("Paste clinical note text here...").fill(SAMPLE);
  await page.getByRole("button", { name: /Extract & Review/i }).click();

  await waitForReviewPage(page);

  // Find the info icon next to the metformin name field
  const infoIcon = page.getByRole("button", { name: /show explanation/i }).first();
  await expect(infoIcon).toBeVisible();

  // Click to open popover
  await infoIcon.click();

  // Assert popover shows medication name and disclaimer
  await expect(page.getByText("Metformin")).toBeVisible();
  await expect(page.getByText(/Informational only — not medical advice\./i)).toBeVisible();

  // Press Escape to close popover
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);

  // Assert popover is closed
  await expect(page.getByText("Metformin")).not.toBeVisible();
});
