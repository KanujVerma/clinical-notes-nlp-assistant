// frontend/src/api/client.ts
const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || "Request failed");
  }
  return resp.json();
}

export const api = {
  extractText: (text: string) =>
    request<any>("/extract", { method: "POST", body: JSON.stringify({ text }) }),

  createNote: (text: string) =>
    request<{ note_id: number; extracted_json: any }>("/notes", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  uploadFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/upload`, { method: "POST", body: form })
      .then(async (r) => {
        if (!r.ok) {
          const err = await r.json().catch(() => ({ error: r.statusText }));
          throw new Error(err.error || "Upload failed");
        }
        return r.json() as Promise<{ note_id: number; extracted_json: any }>;
      });
  },

  validate: (payload: {
    note_id: number;
    validated_json: any;
    status: string;
    review_duration_ms: number;
  }) =>
    request<{ ok: boolean; correction_count: number }>("/validate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getHistory: (page = 1) =>
    request<{ notes: any[]; page: number }>(`/history?page=${page}`),

  getNoteDetail: (id: number) =>
    request<any>(`/history/${id}`),

  getMetrics: () => request<any>("/metrics"),

  seedDemo: () =>
    request<{ loaded: number; skipped: number }>("/seed-demo", { method: "POST" }),
};
