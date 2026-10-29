import { test, expect } from "@playwright/test";

const BASE = "http://localhost:5173";

test("hold and stop medication actions are reviewed, saved and restored", async ({ page }) => {
  await page.goto(BASE);

  // Synthetic only. This used to fail server review completion because
  // action was required but absent from the visible reviewer fields.
  const synthetic = [
    "Patient: Synthetic Example",
    "Date of Service: 2026-10-29",
    "",
    "Medications:",
    "Hold Warfarin 2.5 mg PO daily.",
    "Discontinue Aspirin 81 mg PO daily.",
  ].join("\n");

  await page.getByPlaceholder("Paste clinical note text here...").fill(synthetic);
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await expect(page).toHaveURL(/\/review\/\d+/, { timeout: 15_000 });
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({ timeout: 10_000 });

  // The action itself must be inspectable, never an invisible required
  // backend decision manufactured by a generic parent accept.
  await expect(page.getByText("action", { exact: true })).toHaveCount(2);
  await expect(page.getByText("hold", { exact: true })).toBeVisible();
  await expect(page.getByText("stop", { exact: true })).toBeVisible();

  for (const cat of ["metadata", "vitals", "medications", "instructions"]) {
    await page.locator('[data-testid="ack-' + cat + '"]').check();
  }

  const originalReviewUrl = page.url();
  await page.getByRole("button", { name: /Accept all/i }).click();

  await expect(
    page.getByText(/Saved|Review saved|Review completed/i).or(
      page.getByText(/All notes reviewed/i)
    )
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Missing explicit decision for medication/i)).toHaveCount(0);

  await page.goto(originalReviewUrl);
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("action", { exact: true })).toHaveCount(2);
  await expect(page.getByText("hold", { exact: true })).toBeVisible();
  await expect(page.getByText("stop", { exact: true })).toBeVisible();
});
