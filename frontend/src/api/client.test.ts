import { beforeEach, describe, expect, it, vi } from "vitest";

describe("hosted workspace capabilities", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it("uses a server-issued token rather than a browser UUID in hosted mode", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/capabilities")) {
        return { ok: true, json: async () => ({ mode: "hosted_demo" }) };
      }
      if (url.endsWith("/workspaces")) {
        return { ok: true, json: async () => ({
          workspace_id: "server-owned-workspace",
          token: "server-issued-secret",
          expires_at: "2099-01-01T00:00:00Z",
        }) };
      }
      return {
        ok: true,
        json: async () => ({ notes: [], count: 0 }),
        headers: { get: (key: string) => key.toLowerCase() === "content-type" ? "image/png" : null },
        blob: async () => new Blob(["synthetic-page"], { type: "image/png" }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("./client");
    await api.getQueue();
    await api.getQueue();
    const page = await api.getPageImageBlob(12, 1, 90);
    expect(page.type).toBe("image/png");

    const pageRequest = calls.find((call) => call.url.includes("/notes/12/pages/1/image"));
    expect(pageRequest).toBeDefined();
    expect(pageRequest!.url).not.toContain("server-issued-secret");
    const imageHeaders = pageRequest!.init?.headers as Record<string, string>;
    expect(imageHeaders["X-Workspace-Token"]).toBe("server-issued-secret");
    expect(imageHeaders["X-Workspace-ID"]).toBe("server-owned-workspace");

    expect(calls.filter((call) => call.url.endsWith("/workspaces"))).toHaveLength(1);
    const requests = calls.filter((call) => call.url.endsWith("/queue"));
    expect(requests).toHaveLength(2);
    for (const call of requests) {
      const headers = call.init?.headers as Record<string, string>;
      expect(headers["X-Workspace-ID"]).toBe("server-owned-workspace");
      expect(headers["X-Workspace-Token"]).toBe("server-issued-secret");
      expect(headers["X-Session-ID"]).toBeUndefined();
    }
    vi.unstubAllGlobals();
  });

  it("rejects API requests when workspace bootstrap fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false,
      statusText: "Service unavailable",
    })));
    const { api } = await import("./client");
    await expect(api.getQueue()).rejects.toThrow(/server workspace mode/i);
    vi.unstubAllGlobals();
  });

  it("permits same-origin API calls when VITE_ALLOW_SAME_ORIGIN is enabled", async () => {
    const originalProd = import.meta.env.PROD;
    const originalUrl = import.meta.env.VITE_API_BASE_URL;
    const originalSame = import.meta.env.VITE_ALLOW_SAME_ORIGIN;
    (import.meta.env as Record<string, unknown>).PROD = true;
    (import.meta.env as Record<string, unknown>).VITE_API_BASE_URL = "";
    (import.meta.env as Record<string, unknown>).VITE_ALLOW_SAME_ORIGIN = "true";

    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/capabilities")) {
        return { ok: true, json: async () => ({ mode: "local_dev" }) };
      }
      return { ok: true, json: async () => ({ notes: [], count: 0 }) };
    });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("./client");
    const queue = await api.getQueue();
    expect(queue.count).toBe(0);

    (import.meta.env as Record<string, unknown>).PROD = originalProd;
    (import.meta.env as Record<string, unknown>).VITE_API_BASE_URL = originalUrl;
    (import.meta.env as Record<string, unknown>).VITE_ALLOW_SAME_ORIGIN = originalSame;
    vi.unstubAllGlobals();
  });
});
