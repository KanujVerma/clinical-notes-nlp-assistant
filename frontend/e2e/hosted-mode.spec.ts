// frontend/e2e/hosted-mode.spec.ts
import { test, expect } from "@playwright/test";

const BASE = "http://localhost:5173";

test.describe("Hosted Demo Mode - Public Synthetic Sandbox Restrictions", () => {
  test.beforeEach(async ({ page }) => {
    // Intercept capabilities endpoint to simulate hosted demo sandbox
    await page.route("**/api/capabilities", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          mode: "hosted_demo",
          storage_mode: "sqlite",
          ai_provider_configured: false,
          max_workspaces: 50,
          workspace_retention_hours: 2,
        }),
      });
    });

    // Intercept scenarios endpoint
    await page.route("**/api/scenarios", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          count: 2,
          scenarios: [
            {
              filename: "showcase_polypharmacy.txt",
              title: "Cardiology Polypharmacy & Drug Discrepancies",
              snippet: "Patient on multiple cardiovascular medications requiring titration.",
              has_issues: true,
              issues_count: 2,
            },
            {
              filename: "showcase_sepsis.txt",
              title: "Severe Pediatric Sepsis with Tachycardia",
              snippet: "Acute pediatric clinical presentation with tachycardia and fever.",
              has_issues: false,
              issues_count: 0,
            },
          ],
        }),
      });
    });
  });

  test("Hosted mode disables free-text paste and arbitrary file upload, showing scenario cards", async ({ page }) => {
    await page.goto(BASE);

    // 1. Verify hosted mode banner
    await expect(page.getByText("Public Hosted Sandbox")).toBeVisible();
    await expect(
      page.getByText(/Live arbitrary file uploads and free-text NLP runs are disabled/i)
    ).toBeVisible();

    // 2. Verify free-text textarea is disabled
    const textarea = page.getByPlaceholder(/Free-text input is restricted in hosted demo mode/i);
    await expect(textarea).toBeVisible();
    await expect(textarea).toBeDisabled();

    // 3. Verify Extract Note button is disabled
    const extractBtn = page.getByRole("button", { name: /Extract & Review/i });
    await expect(extractBtn).toBeDisabled();

    // 4. Verify showcase scenario cards are displayed
    await expect(page.getByText("Curated Showcase Scenarios (2)")).toBeVisible();
    await expect(page.getByText("Cardiology Polypharmacy & Drug Discrepancies")).toBeVisible();
    await expect(page.getByText("Severe Pediatric Sepsis with Tachycardia")).toBeVisible();
    await expect(page.getByText("2 canary flags")).toBeVisible();

    // 5. Verify batch file dropzone is hidden / disabled
    await expect(page.getByText("Drop files here, or click to browse")).not.toBeVisible();
  });

  test("Document viewer renders and switches between Document and Transcript modes", async ({ page }) => {
    const mockExtracted = {
      vitals: {},
      medications: [
        {
          id: "med_1",
          source_occurrence_id: "med_1",
          name: "Metformin",
          dose: "500 mg",
          route: "PO",
          frequency: "BID",
          span: [11, 20],
          bbox: [50, 100, 200, 140],
          page_number: 1,
        },
      ],
      instructions: {},
      metadata: {},
    };

    // Intercept /notes/999 state endpoint
    await page.route("**/api/notes/999", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          note_id: 999,
          raw_text: "Prescribed Metformin 500 mg PO BID.",
          extracted_json: mockExtracted,
          lock_version: 0,
          current_source_revision_id: "rev-test-1",
          current_extraction_id: "ext-test-1",
          source: "ocr",
        }),
      });
    });

    // Intercept /history/999 detail endpoint
    await page.route("**/api/history/999", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 999,
          raw_text: "Prescribed Metformin 500 mg PO BID.",
          extracted_json: mockExtracted,
          lock_version: 0,
          current_source_revision_id: "rev-test-1",
          current_extraction_id: "ext-test-1",
          source: "ocr",
        }),
      });
    });

    await page.route("**/api/notes/999/source", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          note_id: 999,
          revision_id: "rev-test-1",
          revision_number: 1,
          raw_text: "Prescribed Metformin 500 mg PO BID.",
          sha256: "dummy-hash",
          pages: [
            {
              page_number: 1,
              width: 600,
              height: 800,
              acquisition_method: "tesseract_ocr",
              boxes: [{ bbox: [50, 100, 200, 140], text: "Metformin 500 mg" }],
            },
          ],
          source: "ocr",
        }),
      });
    });

    // Intercept image endpoint so it returns a 1x1 png dummy immediately
    await page.route("**/api/notes/999/pages/1/image*", async (route) => {
      // 1x1 transparent png
      const pngBuf = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
      await route.fulfill({
        status: 200,
        contentType: "image/png",
        body: pngBuf,
      });
    });

    await page.goto(`${BASE}/review/999`);

    // Verify left pane mode controls
    const docBtn = page.getByTestId("leftpane-mode-document");
    const transcriptBtn = page.getByTestId("leftpane-mode-transcript");
    await expect(docBtn).toBeVisible();
    await expect(transcriptBtn).toBeVisible();

    // In document mode, document source viewer is rendered
    await expect(page.getByTestId("document-source-viewer")).toBeVisible();
    await expect(page.getByTestId("rotate-btn")).toBeVisible();

    // Toggle to transcript mode
    await transcriptBtn.click();
    await expect(page.getByText("Prescribed Metformin 500 mg PO BID.")).toBeVisible();

    // Toggle back
    await docBtn.click();
    await expect(page.getByTestId("document-source-viewer")).toBeVisible();
  });
});
