import { test, expect } from "@playwright/test";

/** Real hosted-mode integration: no Playwright route mocks or canned responses. */
test.describe("Real hosted synthetic sandbox", () => {
  test.skip(process.env.RUN_REAL_HOSTED_E2E !== "1",
    "Requires hosted Flask and an independently migrated disposable database");

  test("curated scenarios, browser bootstrap and workspace isolation", async ({ page, request }) => {
    const capabilities = await request.get("/api/capabilities");
    expect(capabilities.ok()).toBeTruthy();
    expect((await capabilities.json()).mode).toBe("hosted_demo");

    const workspaceA = await request.post("/api/workspaces");
    const workspaceB = await request.post("/api/workspaces");
    expect(workspaceA.status()).toBe(201);
    expect(workspaceB.status()).toBe(201);
    const a = await workspaceA.json();
    const b = await workspaceB.json();
    const headersA = { "X-Workspace-ID": a.workspace_id, "X-Workspace-Token": a.token };
    const headersB = { "X-Workspace-ID": b.workspace_id, "X-Workspace-Token": b.token };

    const seeded = await request.post("/api/seed-demo", { headers: headersA });
    expect(seeded.status()).toBe(200);
    expect((await seeded.json()).loaded).toBe(10);
    const listA = await request.get("/api/queue", { headers: headersA });
    const listB = await request.get("/api/queue", { headers: headersB });
    expect((await listA.json()).count).toBe(10);
    expect((await listB.json()).count).toBe(0);
    const noteId = (await listA.json()).notes[0].id;
    expect((await request.get("/api/notes/" + noteId, { headers: headersB })).status())
      .toBeGreaterThanOrEqual(403);

    const freeText = await request.post("/api/notes", {
      headers: headersA, data: { text: "Non-curated clinical note" },
    });
    expect(freeText.status()).toBe(403);
    expect((await request.post("/api/jobs", {
      headers: headersA, data: { kind: "ai_inference" },
    })).status()).toBe(403);

    await page.goto("/");
    await expect(page.getByText("Public Hosted Sandbox")).toBeVisible();
    await expect(page.getByText("Curated Showcase Scenarios (10)")).toBeVisible();
    await expect(page.getByPlaceholder(/Free-text input is restricted/i)).toBeDisabled();
    await expect(page.getByRole("button", { name: /Extract & Review/i })).toBeDisabled();
    await page.getByRole("button", { name: /Seed Showcase Scenarios/i }).click();
    await expect(page.getByText(/Seeded 10 notes/i)).toBeVisible();
    await expect(page).toHaveURL(/\/queue/, { timeout: 15_000 });

    const appQueue = await page.evaluate(async () => {
      // The UI's capability remains in localStorage, not URLs.
      const stored = localStorage.getItem("clinical_nlp_workspace_capability_v1");
      const cap = stored ? JSON.parse(stored) : null;
      if (!cap || !cap.token) return { hasCapability: false };
      const response = await fetch("/api/queue", {
        headers: { "X-Workspace-ID": cap.id, "X-Workspace-Token": cap.token },
      });
      const body = await response.json();
      return { hasCapability: true, count: body.count, status: response.status };
    });
    expect(appQueue).toMatchObject({ hasCapability: true, count: 10, status: 200 });
  });

  test("hosted backend forbids uploads, model calls and edits", async ({ request }) => {
    const created = await request.post("/api/workspaces");
    expect(created.status()).toBe(201);
    const ws = await created.json();
    const headers = { "X-Workspace-ID": ws.workspace_id, "X-Workspace-Token": ws.token };
    for (const [path, data] of [
      ["/api/extract", { text: "Anything" }],
      ["/api/evaluation/runs", {}],
      ["/api/notes/1/ai-candidates", { adapter: "qwen3_vl" }],
      ["/api/notes/1/revisions", { text: "arbitrary" }],
    ] as const) {
      const response = await request.post(path, { headers, data });
      expect(response.status()).toBe(403);
    }
    const upload = await request.post("/api/upload", {
      headers,
      multipart: { file: {
        name: "arbitrary.txt", mimeType: "text/plain",
        buffer: Buffer.from("Synthetic arbitrary source"),
      } },
    });
    expect(upload.status()).toBe(403);
  });
});
