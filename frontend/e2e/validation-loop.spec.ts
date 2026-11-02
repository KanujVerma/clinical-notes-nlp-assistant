/**
 * Deterministic v1 loop: source, independent issue, correction, reload,
 * metric drilldown membership, stale source, and rejected historical replay.
 */
import { test, expect, Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = "http://localhost:5173";
const NOTE = readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../data/validation_loop/v1_synthetic_note.txt"),
  "utf8",
);

async function openReview(page: Page) {
  await page.goto(BASE);
  await page.getByPlaceholder("Paste clinical note text here...").fill(NOTE);
  await page.getByRole("button", { name: /Extract & Review/i }).click();
  await expect(page).toHaveURL(/\/review\/\d+/, { timeout: 15_000 });
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({ timeout: 10_000 });
}

test("validation loop keeps correction, drilldown, and stale replay distinct", async ({ page }) => {
  test.setTimeout(120_000);
  await openReview(page);
  const noteId = page.url().match(/\/review\/(\d+)/)?.[1];
  expect(noteId).toBeTruthy();

  await expect(page.getByText("2.5 mg").first()).toBeVisible();
  await expect(page.getByText("500 mg").first()).toBeVisible();
  await expect(page.getByText("1000 mg").first()).toBeVisible();

  await page.getByRole("button", { name: /^Issues/ }).click();
  const issues = page.getByRole("region", { name: "Operational issues for current note" });
  await expect(issues).toBeVisible();
  await expect(issues.getByText("A02_DUPLICATE_MEDICATION_CONFLICT")).toBeVisible();
  await expect(issues.getByText("A10_NON_ACTIVE_MEDICATION")).toBeVisible();
  await page.getByRole("button", { name: /^Issues/ }).click();

  const dose = page.locator(".group").filter({ hasText: "2.5 mg" }).first();
  await dose.hover();
  await dose.getByRole("button", { name: "Edit" }).click();
  await page.locator("input[value='2.5 mg']").fill("2.0 mg");
  await page.getByRole("button", { name: "save", exact: true }).click();
  await expect(page.getByText("2.0 mg").first()).toBeVisible();

  for (const name of ["ack-metadata", "ack-vitals", "ack-medications", "ack-instructions"]) {
    await page.locator(`[data-testid="${name}"]`).check();
  }

  const reviewPost = page.waitForResponse((response) =>
    response.url().includes("/reviews") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Accept all/i }).click();
  const saved = await reviewPost;
  expect(saved.status()).toBe(201);
  const savedBody = saved.request().postDataJSON() as Record<string, unknown>;
  const reviewUrl = saved.url();

  await page.reload();
  await expect(page.getByText("Reviewer", { exact: true })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("2.0 mg").first()).toBeVisible();

  await page.goto(`${BASE}/metrics/drilldown?kind=issues&severity=warning&state=open`);
  const row = page.locator("li").filter({ hasText: `Synthetic note #${noteId}` }).filter({ hasText: "A10_NON_ACTIVE_MEDICATION" });
  await expect(row).toBeVisible({ timeout: 10_000 });
  const inspect = row.getByRole("link", { name: new RegExp(`Inspect source and evidence for note ${noteId}`) });
  await expect(inspect).toBeVisible();
  await inspect.click();
  await expect(page).toHaveURL(new RegExp(`/review/${noteId}\\?`));
  await expect(page.getByRole("region", { name: "Operational issues for current note" })).toBeVisible();

  await page.getByRole("button", { name: /Update Transcription/ }).click();
  const editor = page.getByRole("heading", { name: "Edit Document Transcription" });
  await expect(editor).toBeVisible();
  const sourceBox = page.locator("textarea").last();
  await sourceBox.fill(NOTE.trimEnd() + "\nRevised synthetic follow-up.\n");
  await page.getByRole("button", { name: "Save New Revision" }).click();
  await expect(editor).toBeHidden({ timeout: 10_000 });
  await expect(page.locator('[data-testid="ack-medications"]')).not.toBeChecked();

  const sessionId = await page.evaluate(() => localStorage.getItem("clinical_nlp_session_id"));
  expect(sessionId).toBeTruthy();
  const replay = await page.request.post(reviewUrl, {
    data: savedBody,
    headers: {
      "X-Session-ID": sessionId ?? "",
      "X-Workspace-ID": sessionId ?? "",
    },
  });
  expect(replay.status()).toBe(409);
  const replayBody = await replay.json();
  expect(replayBody.code).toBe("STALE_REVIEW");
});
