/**
 * Smoke test — end-to-end review workflow.
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

test("Upload page loads", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.getByText("Extract structured data")).toBeVisible();
  await expect(page.getByPlaceholder("Paste clinical note text here...")).toBeVisible();
});

test("Seed demo → toast → auto-navigate to Queue", async ({ page }) => {
  await page.goto(BASE);

  // Accept any confirm dialogs (seed may prompt if data exists)
  page.on("dialog", (d) => d.accept());

  await page.getByRole("button", { name: /Seed demo data/i }).click();

  // Toast should appear
  await expect(page.getByText(/Seeded|already exist/i)).toBeVisible({ timeout: 8_000 });

  // Either navigates to /queue (new data) or stays on upload (already seeded)
  // Either is acceptable — just confirm no crash
  await page.waitForTimeout(1500);
  const url = page.url();
  expect(url === `${BASE}/` || url === `${BASE}/queue`).toBeTruthy();
});

test("Queue page lists pending notes", async ({ page }) => {
  await page.goto(`${BASE}/queue`);
  // Should show at least one note or an empty-state message — either is fine
  const hasNotes = await page.locator("table tbody tr").count() > 0;
  const hasEmpty = await page.getByText(/no pending/i).isVisible().catch(() => false);
  expect(hasNotes || hasEmpty).toBeTruthy();
});

test("Paste text → extract → Review page opens", async ({ page }) => {
  await page.goto(BASE);
  const SAMPLE = `Patient: Test Patient
Date of Service: 2025-01-15
Provider: Dr. Test

Vitals: BP 130/82. HR 76. Temp 98.6F. RR 14. SpO2 98%. Wt 165 lbs.

Medications:
- lisinopril 10 mg PO daily

DISCHARGE INSTRUCTIONS:
Take medications as prescribed.

FOLLOW UP:
Return to clinic in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if chest pain.`;

  await page.getByPlaceholder("Paste clinical note text here...").fill(SAMPLE);
  await page.getByRole("button", { name: /Extract & Review/i }).click();

  await waitForReviewPage(page);

  // Source badge should be visible (CSS uppercases the value so match case-insensitively)
  await expect(page.locator("header span").filter({ hasText: /text|paste/i })).toBeVisible();
});

test("Review page — progress bar updates on accept", async ({ page }) => {
  await page.goto(BASE);
  await page.getByRole("button", { name: /Load sample note/i }).click();
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await waitForReviewPage(page);

  // Read initial reviewed count
  const barText = page.locator("text=/\\d+ of \\d+ fields reviewed/");
  await expect(barText).toBeVisible();
  const before = await barText.textContent();

  // Accept the first field card
  const firstCard = page.locator('[data-testid="field-value"]').first();
  await firstCard.hover();
  await page.getByRole("button", { name: /✓ Accept/i }).first().click();

  // Count should have increased
  const after = await barText.textContent();
  expect(before).not.toEqual(after);
});

test("Review page — keyboard shortcut Tab activates field, A accepts it", async ({ page }) => {
  await page.goto(BASE);
  await page.getByRole("button", { name: /Load sample note/i }).click();
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await waitForReviewPage(page);

  // Focus the page (not an input) then Tab to activate first field
  await page.keyboard.press("Tab");
  await page.waitForTimeout(200);

  // Press A to accept
  await page.keyboard.press("a");
  await page.waitForTimeout(200);

  // At least one field should be in "accepted" state
  await expect(page.getByText("accepted").first()).toBeVisible();
});

test("Review page — edit a field value and save corrections", async ({ page }) => {
  await page.goto(BASE);
  await page.getByRole("button", { name: /Load sample note/i }).click();
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await waitForReviewPage(page);

  // Click Edit on first field
  const firstValue = page.locator('[data-testid="field-value"]').first();
  await firstValue.hover();
  await page.getByRole("button", { name: "Edit" }).first().click();

  // Type a new value
  const input = page.locator("input").first();
  await input.triple_click?.() ?? await input.click({ clickCount: 3 });
  await input.fill("edited value");
  await page.getByRole("button", { name: "save" }).first().click();

  // Save corrections button should be enabled
  const saveBtn = page.getByRole("button", { name: /Save corrections/i });
  await expect(saveBtn).toBeEnabled();
  await saveBtn.click();

  // Flash message or auto-advance
  await expect(
    page.getByText(/Saved|loading next/i).or(page.getByText(/All notes reviewed/i))
  ).toBeVisible({ timeout: 6_000 });
});

test("Review page — unsaved changes blocks in-app navigation", async ({ page }) => {
  await page.goto(BASE);
  await page.getByRole("button", { name: /Load sample note/i }).click();
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await waitForReviewPage(page);

  // Accept one field to make the page dirty
  const firstCard = page.locator('[data-testid="field-value"]').first();
  await firstCard.hover();
  await page.getByRole("button", { name: /✓ Accept/i }).first().click();

  // Set up dialog handler BEFORE clicking nav — dismiss (stay on page)
  let dialogFired = false;
  page.once("dialog", async (dialog) => {
    dialogFired = true;
    await dialog.dismiss();
  });

  // Click History in the sidebar
  await page.getByRole("link", { name: "History" }).click();
  await page.waitForTimeout(500);

  expect(dialogFired).toBe(true);
  // Should still be on review page
  await expect(page).toHaveURL(/\/review\//);
});

test("History page — reviewed notes appear", async ({ page }) => {
  await page.goto(`${BASE}/history`);
  // May be empty (if no notes have been reviewed yet) — that's fine
  await expect(
    page.locator("table tbody tr").first().or(page.getByText(/No notes yet/i))
  ).toBeVisible({ timeout: 6_000 });
});

test("Re-review — previously reviewed note shows banner", async ({ page }) => {
  // First submit and save a note
  await page.goto(BASE);
  await page.getByRole("button", { name: /Load sample note/i }).click();
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await waitForReviewPage(page);

  // Accept all
  await page.getByRole("button", { name: /Accept all/i }).click();
  await page.waitForTimeout(2_000);

  // Go to History and re-open the note
  await page.goto(`${BASE}/history`);
  await expect(page.locator("table tbody tr").first()).toBeVisible({ timeout: 6_000 });

  // Set up dialog handler to accept any unsaved-changes prompt
  page.on("dialog", (d) => d.accept());
  await page.locator("table tbody tr").first().click();
  await waitForReviewPage(page);

  // Re-review banner should be visible
  await expect(page.getByText(/Previously reviewed/i)).toBeVisible({ timeout: 5_000 });
});

test("Metrics page loads without error", async ({ page }) => {
  await page.goto(`${BASE}/metrics`);
  // Either shows metrics content or the eval-not-run banner — no red error text
  await expect(page.getByText(/Metrics|Evaluation|Correction Rate/i).first()).toBeVisible({ timeout: 5_000 });
  await expect(page.locator("text=/Failed to load/i")).not.toBeVisible();
});
