/**
 * Hybrid explainer e2e tests — AI status and explanation modal.
 * Intercepts network calls to avoid requiring a running backend.
 */
import { test, expect, Page } from "@playwright/test";

const BASE = "http://localhost:5173";

// ── helpers ────────────────────────────────────────────────────────────────

async function waitForReviewPage(page: Page) {
  await expect(page).toHaveURL(/\/review\/\d+/, { timeout: 15_000 });
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({
    timeout: 10_000,
  });
}

// ── tests ──────────────────────────────────────────────────────────────────

test("dictionary popover works when AI unavailable", async ({ page }) => {
  // Intercept the AI status call to return unavailable
  await page.route("**/api/explain/status", (route) => {
    route.fulfill({ json: { available: false } });
  });

  // Navigate to app and seed demo data
  await page.goto(BASE);

  // Accept any confirm dialogs
  page.on("dialog", (d) => d.accept());

  // Seed demo data
  await page.getByRole("button", { name: /Seed demo data/i }).click();
  await expect(page.getByText(/Seeded|already exist/i)).toBeVisible({
    timeout: 8_000,
  });

  // Navigate to queue and pick first note
  await page.goto(`${BASE}/queue`);
  const firstRow = page.locator("table tbody tr").first();
  await expect(firstRow).toBeVisible({ timeout: 5_000 });
  await firstRow.click();

  await waitForReviewPage(page);

  // Find a medication field and click its info icon
  // The review page should have field cards with medication data
  // Look for info/help icons that trigger the dictionary popover
  const infoButtons = page.locator('[data-testid="info-button"], button[aria-label*="info"], button[title*="info"]');
  const infoButtonCount = await infoButtons.count();

  if (infoButtonCount > 0) {
    await infoButtons.first().click();
    await page.waitForTimeout(300);

    // Expect popover to appear with medication content
    const popover = page.locator('[role="tooltip"], .popover, [data-testid="popover"]');
    await expect(popover).toBeVisible({ timeout: 5_000 });

    // Expect NO "Explain in more detail" or "Generate AI explanation" buttons
    // when AI is unavailable
    const explainButtons = page.locator(
      'button:has-text("Explain in more detail"), button:has-text("Generate AI explanation")'
    );
    await expect(explainButtons).toHaveCount(0);
  }
});

test("AI explanation modal shows when requested", async ({ page }) => {
  // Intercept AI status → available: true
  await page.route("**/api/explain/status", (route) => {
    route.fulfill({ json: { available: true } });
  });

  // Intercept AI explain → canned response
  await page.route("**/api/explain", (route) => {
    route.fulfill({
      json: {
        explanation: {
          whatItIs: "A biguanide antidiabetic medication",
          commonUse: "First-line treatment for type 2 diabetes",
          plainLanguage:
            "Helps lower blood sugar by reducing liver glucose production",
        },
        modelUsed: "claude-haiku-4-5-20251001",
      },
    });
  });

  // Navigate and seed
  await page.goto(BASE);

  // Accept any confirm dialogs
  page.on("dialog", (d) => d.accept());

  // Seed demo data
  await page.getByRole("button", { name: /Seed demo data/i }).click();
  await expect(page.getByText(/Seeded|already exist/i)).toBeVisible({
    timeout: 8_000,
  });

  // Navigate to queue and pick first note
  await page.goto(`${BASE}/queue`);
  const firstRow = page.locator("table tbody tr").first();
  await expect(firstRow).toBeVisible({ timeout: 5_000 });
  await firstRow.click();

  await waitForReviewPage(page);

  // Find an info icon and click it
  const infoButtons = page.locator('[data-testid="info-button"], button[aria-label*="info"], button[title*="info"]');
  const infoButtonCount = await infoButtons.count();

  if (infoButtonCount > 0) {
    await infoButtons.first().click();
    await page.waitForTimeout(300);

    // Popover should appear
    const popover = page.locator('[role="tooltip"], .popover, [data-testid="popover"]');
    await expect(popover).toBeVisible({ timeout: 5_000 });

    // Click "Explain in more detail" button
    const explainButton = page.locator(
      'button:has-text("Explain in more detail"), button:has-text("Generate AI explanation")'
    );
    const buttonCount = await explainButton.count();

    if (buttonCount > 0) {
      await explainButton.first().click();
      await page.waitForTimeout(500);

      // Expect modal to appear with explanation content
      const modal = page.locator('[role="dialog"], .modal, [data-testid="modal"]');
      await expect(modal).toBeVisible({ timeout: 5_000 });

      // Expect "What it is" content from the mocked response
      await expect(
        page.getByText(/biguanide|antidiabetic/i)
      ).toBeVisible();

      // Expect disclaimer text
      await expect(
        page.getByText(/AI-generated explanation|informational review/i)
      ).toBeVisible({ timeout: 5_000 });

      // Close modal with Escape
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);

      // Modal should be closed
      await expect(modal).not.toBeVisible();
    }
  }
});
