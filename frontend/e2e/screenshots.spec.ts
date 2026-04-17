/**
 * Screenshot capture for README.
 * Run with: npx playwright test e2e/screenshots.spec.ts
 * Both servers must be running.
 */
import { test, Page } from "@playwright/test";
import { fileURLToPath } from "url";
import path from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUT = path.resolve(__dirname, "../../docs/screenshots");
const BASE = "http://localhost:5173";

const SAMPLE_NOTE = `Patient: Eleanor Price
Date: 2025-03-04
Doctor: Dr. Jason Liu

O:
BP 102/64
HR: 96
T 99.3 F
Resp 18
SpO2 97% RA
Wt 146 lb

Current Medications:
1. Albuterol inhaler 2 puffs q6h PRN wheezing
2. Azithromycin 250 mg PO daily for 3 more days
3. Lisinopril 10 mg PO daily
4. Benzonatate 100 mg PO TID as needed for cough

A/P:
Encourage fluids and slow position changes. Continue nitrofurantoin 100 mg BID for 3 more days.
May use ondansetron 4 mg q8h PRN nausea.
RTC with PCP in 2-3 days if not improving.
Go to the ER for fainting, chest pain, worsening weakness, inability to keep fluids down.`;

async function waitForReview(page: Page) {
  await page.waitForURL(/\/review\/\d+/, { timeout: 15_000 });
  await page.getByText("Reviewer", { exact: true }).waitFor({ timeout: 10_000 });
  // Let field cards render
  await page.waitForTimeout(800);
}

test.describe("README screenshots", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("upload page", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT}/upload.png`, fullPage: false });
  });

  test("queue page", async ({ page }) => {
    await page.goto(`${BASE}/queue`);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/queue.png`, fullPage: false });
  });

  test("review page", async ({ page }) => {
    // Submit the sample note so we get a realistic extraction
    await page.goto(BASE);
    await page.getByPlaceholder("Paste clinical note text here...").fill(SAMPLE_NOTE);
    await page.getByRole("button", { name: /Extract & Review/i }).click();
    await waitForReview(page);

    // Activate the first field so the card highlights visually
    await page.keyboard.press("Tab");
    await page.waitForTimeout(200);

    await page.screenshot({ path: `${OUT}/review.png`, fullPage: false });
  });

  test("history page", async ({ page }) => {
    await page.goto(`${BASE}/history`);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/history.png`, fullPage: false });
  });

  test("metrics page", async ({ page }) => {
    await page.goto(`${BASE}/metrics`);
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${OUT}/metrics.png`, fullPage: false });
  });
});
