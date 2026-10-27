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
      return { ok: true, json: async () => ({ notes: [], count: 0 }) };
    });
    vi.stubGlobal("fetch", fetchMock);

    const { api } = await import("./client");
    await api.getQueue();
    await api.getQueue();

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
});
