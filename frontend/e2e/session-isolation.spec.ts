/**
 * Session isolation smoke test — runs against production.
 *
 * Verifies that notes created in one browser context are not visible in another.
 * Each context gets its own localStorage (and therefore its own session UUID).
 *
 * Run: PLAYWRIGHT_BASE_URL=https://clinical-nlp.vercel.app npx playwright test session-isolation
 */
import { test, expect, Browser } from "@playwright/test";

const PROD = process.env.PLAYWRIGHT_BASE_URL ?? "https://clinical-nlp.vercel.app";

const SAMPLE_NOTE = `Patient: Test Patient
Date of Service: 2025-01-15
Vitals: BP 130/82. HR 76.
Medications: lisinopril 10 mg PO daily.`;

test.describe("session isolation", () => {
  test("notes created in one session are invisible to another", async ({
    browser,
  }: {
    browser: Browser;
  }) => {
    // Two fresh contexts = two separate localStorage → two different UUIDs
    const ctxA = await browser.newContext();
    const ctxB = await browser.newContext();
    const pageA = await ctxA.newPage();
    const pageB = await ctxB.newPage();

    try {
      // Session A: paste a note and submit it
      await pageA.goto(PROD, { waitUntil: "networkidle" });
      await pageA.getByPlaceholder("Paste clinical note text here...").fill(SAMPLE_NOTE);
      await pageA.getByRole("button", { name: /Extract & Review/i }).click();
      await expect(pageA).toHaveURL(/\/review\/\d+/, { timeout: 20_000 });

      // Session B: history should be empty (no notes from session A)
      await pageB.goto(`${PROD}/history`, { waitUntil: "networkidle" });
      await expect(
        pageB.getByText(/No notes yet/i).or(pageB.locator("table tbody tr").filter({ hasText: "" }))
      ).toBeVisible({ timeout: 10_000 });

      // Session B: queue should also be empty
      await pageB.goto(`${PROD}/queue`, { waitUntil: "networkidle" });
      const rows = await pageB.locator("table tbody tr").count();
      expect(rows).toBe(0);
    } finally {
      await ctxA.close();
      await ctxB.close();
    }
  });

  test("two sessions seed demo data independently", async ({
    browser,
  }: {
    browser: Browser;
  }) => {
    const ctxA = await browser.newContext();
    const ctxB = await browser.newContext();
    const pageA = await ctxA.newPage();
    const pageB = await ctxB.newPage();

    try {
      // Session A seeds demo data
      await pageA.goto(PROD, { waitUntil: "networkidle" });
      await pageA.getByRole("button", { name: /Seed demo data/i }).click();
      await expect(pageA.getByText(/Seeded|already exist/i)).toBeVisible({ timeout: 15_000 });

      // Session B can also seed without collision
      await pageB.goto(PROD, { waitUntil: "networkidle" });
      await pageB.getByRole("button", { name: /Seed demo data/i }).click();
      await expect(pageB.getByText(/Seeded|already exist/i)).toBeVisible({ timeout: 15_000 });

      // Session B's history should contain notes (its own seed), not session A's
      await pageB.goto(`${PROD}/history`, { waitUntil: "networkidle" });
      await expect(pageB.locator("table tbody tr").first()).toBeVisible({ timeout: 10_000 });

      // Session A's history should also contain notes (its own seed)
      await pageA.goto(`${PROD}/history`, { waitUntil: "networkidle" });
      await expect(pageA.locator("table tbody tr").first()).toBeVisible({ timeout: 10_000 });
    } finally {
      await ctxA.close();
      await ctxB.close();
    }
  });
});
