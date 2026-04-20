/**
 * Hybrid explainer e2e tests — AI status and explanation modal.
 * Fully self-contained: mocks queue, note detail, AI status, and AI explain.
 */
import { test, expect, Page } from "@playwright/test";

const BASE = "http://localhost:5173";
const NOTE_ID = 1;

// ── shared mock data ────────────────────────────────────────────────────────

const MOCK_QUEUE = {
  notes: [
    { id: NOTE_ID, filename: "dev_001.txt", source: "demo", created_at: "2026-04-20T00:00:00" },
  ],
  count: 1,
};

const MOCK_NOTE_DETAIL = {
  id: NOTE_ID,
  filename: "dev_001.txt",
  raw_text: "Patient is on metformin 500 mg PO BID for type 2 diabetes.",
  source: "demo",
  created_at: "2026-04-20T00:00:00",
  pipeline_version: "1.0",
  extracted_json: {
    pipeline_version: "1.0",
    vitals: {},
    instructions: {},
    metadata: {},
    medications: [
      {
        name: "metformin",
        dose: "500 mg",
        route: "PO",
        frequency: "BID",
        duration: "",
        qualifier: "",
        span: [14, 22],
        source: "medspacy",
        confidence: 0.95,
      },
    ],
  },
  validation: null,
};

// ── helpers ─────────────────────────────────────────────────────────────────

async function setupBaseMocks(page: Page) {
  // Note: Playwright routes are evaluated last-registered-first. Register
  // specific routes AFTER the explain routes (which callers register before
  // calling this helper), so they win over any catch-all.
  await page.route("**/api/queue*", (route) =>
    route.fulfill({ json: MOCK_QUEUE })
  );
  await page.route(`**/api/history/${NOTE_ID}`, (route) =>
    route.fulfill({ json: MOCK_NOTE_DETAIL })
  );
}

async function navigateToReviewPage(page: Page) {
  // Navigate directly to the review URL — avoids needing a queue API call.
  await page.goto(`${BASE}/review/${NOTE_ID}`);
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({
    timeout: 10_000,
  });
}

// ── tests ───────────────────────────────────────────────────────────────────

test("dictionary popover works when AI unavailable", async ({ page }) => {
  // AI unavailable
  await page.route("**/api/explain/status", (route) =>
    route.fulfill({ json: { available: false } })
  );
  await setupBaseMocks(page);
  await navigateToReviewPage(page);

  // Find info buttons rendered by ExplainerTrigger
  const infoButtons = page.locator('[data-testid="info-button"]');
  const count = await infoButtons.count();
  expect(count).toBeGreaterThan(0);

  await infoButtons.first().click();
  await page.waitForTimeout(300);

  // Popover should appear
  const popover = page.locator('[data-testid="popover"]');
  await expect(popover).toBeVisible({ timeout: 5_000 });

  // No AI buttons when AI is unavailable
  const aiButtons = page.locator(
    'button:has-text("Explain in more detail"), button:has-text("Generate AI explanation")'
  );
  await expect(aiButtons).toHaveCount(0);

  // Disclaimer is present
  await expect(page.getByText(/Informational only/i)).toBeVisible();
});

test("AI explanation modal shows when requested", async ({ page }) => {
  // AI available
  await page.route("**/api/explain/status", (route) =>
    route.fulfill({ json: { available: true } })
  );

  // Canned AI explain response
  await page.route("**/api/explain", (route) =>
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
    })
  );

  await setupBaseMocks(page);
  await navigateToReviewPage(page);

  // Find an info button
  const infoButtons = page.locator('[data-testid="info-button"]');
  const count = await infoButtons.count();
  expect(count).toBeGreaterThan(0);

  await infoButtons.first().click();
  await page.waitForTimeout(300);

  // Popover should appear
  const popover = page.locator('[data-testid="popover"]');
  await expect(popover).toBeVisible({ timeout: 5_000 });

  // AI action button should be present (metformin is a dictionary hit → "Explain in more detail")
  const aiButton = page.locator(
    'button:has-text("Explain in more detail"), button:has-text("Generate AI explanation")'
  );
  const buttonCount = await aiButton.count();
  expect(buttonCount).toBeGreaterThan(0);

  // Click AI action and wait for the mocked /api/explain response
  const explainResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes('/api/explain') && !resp.url().includes('/status') && resp.request().method() === 'POST'
  );
  await aiButton.first().click();
  await explainResponsePromise;
  await page.waitForTimeout(300);

  // Modal should appear
  const modal = page.locator('[data-testid="modal"]');
  await expect(modal).toBeVisible({ timeout: 5_000 });

  // Mocked explanation content is visible
  await expect(page.getByText(/biguanide|antidiabetic/i)).toBeVisible({ timeout: 5_000 });

  // Disclaimer is visible
  await expect(
    page.getByText(/AI-generated explanation.*informational review/i)
  ).toBeVisible({ timeout: 5_000 });

  // Escape closes the modal
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  await expect(modal).not.toBeVisible();
});
