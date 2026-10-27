// frontend/src/api/client.ts
import { QueueResponse } from "../types";
import { AiExplainRequest, AiExplainResponse, AiStatusResponse } from "../lib/aiExplain";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "") + "/api";

export function getSessionId(): string {
  const KEY = "clinical_nlp_session_id";
  let sid = localStorage.getItem(KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(KEY, sid);
  }
  return sid;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const sid = getSessionId();
  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Session-ID": sid,
      "X-Workspace-ID": sid,
      ...(options?.headers as Record<string, string>),
    },
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
    request<{ note_id: number; revision_id?: string; extraction_id?: string; extracted_json: any }>("/notes", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  uploadFile: (file: File) => {
    const sid = getSessionId();
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/upload`, {
      method: "POST",
      body: form,
      headers: { "X-Session-ID": sid, "X-Workspace-ID": sid },
    }).then(async (r) => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({ error: r.statusText }));
        throw new Error(err.error || "Upload failed");
      }
      return r.json() as Promise<{
        note_id: number;
        revision_id?: string;
        extraction_id?: string;
        extracted_json: any;
        raw_text: string;
        ocr_confidence: number | null;
        source: string;
      }>;
    });
  },

  validate: (payload: {
    note_id: number;
    validated_json: any;
    status: string;
    review_duration_ms: number;
  }) =>
    request<{ ok: boolean; correction_count: number; next_pending_id: number | null }>("/validate", {
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

  getQueue: () => request<QueueResponse>("/queue"),

  updateNoteText: (noteId: number, text: string) =>
    request<{ note_id: number; extracted_json: any }>(`/notes/${noteId}/text`, {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),

  resetWorkspace: () =>
    request<{ deleted_notes: number; deleted_extractions: number; deleted_validations: number }>(
      "/reset",
      { method: "DELETE" }
    ),

  aiExplain: (req: AiExplainRequest) =>
    request<AiExplainResponse>("/explain", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  explainTerm: (req: AiExplainRequest) =>
    request<AiExplainResponse>("/explain", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  getAiStatus: () =>
    request<AiStatusResponse>("/explain/status"),

  // Validation Workbench APIs
  getCapabilities: () =>
    request<any>("/capabilities"),

  getNoteState: (noteId: number) =>
    request<any>(`/notes/${noteId}`),

  getNoteSource: (noteId: number) =>
    request<any>(`/notes/${noteId}/source`),

  appendNoteRevision: (noteId: number, raw_text: string, reason?: string) =>
    request<any>(`/notes/${noteId}/revisions`, {
      method: "POST",
      body: JSON.stringify({ raw_text, reason }),
    }),

  getNoteRevisions: (noteId: number) =>
    request<any[]>(`/notes/${noteId}/revisions`),

  submitReview: (extId: string, payload: any, idempotencyKey?: string) =>
    request<any>(`/extractions/${extId}/reviews`, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    }),

  getNoteReviewEvents: (noteId: number) =>
    request<any[]>(`/notes/${noteId}/review-events`),

  getIssues: (params?: { note_id?: number; status?: string; severity?: string; category?: string }) => {
    const q = params ? new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])
    ).toString() : "";
    return request<any[]>(`/issues${q ? `?${q}` : ""}`);
  },

  updateIssueDisposition: (issueId: string, disposition: string, reason?: string) =>
    request<any>(`/issues/${issueId}/disposition`, {
      method: "POST",
      body: JSON.stringify({ disposition, reason }),
    }),

  getAiCandidates: (noteId: number) =>
    request<any[]>(`/notes/${noteId}/ai-candidates`),

  requestAiCandidates: (noteId: number) =>
    request<any>(`/notes/${noteId}/ai-candidates`, { method: "POST" }),

  getEvalRuns: () =>
    request<any[]>("/evaluation/runs"),

  getEvalRunDetail: (runId: string) =>
    request<any>(`/evaluation/runs/${runId}`),

  triggerEvalRun: () =>
    request<any>("/evaluation/runs", { method: "POST" }),

  getExportUrl: (eventId: string) =>
    `${BASE}/review-events/${eventId}/export`,

  downloadExport: async (eventId: string, filename?: string) => {
    const res = await fetch(`${BASE}/review-events/${eventId}/export`, {
      headers: {
        "X-Session-ID": getSessionId(),
        "X-Workspace-ID": getSessionId(),
      },
    });
    if (!res.ok) {
      throw new Error(`Export download failed: ${res.statusText}`);
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || `reviewed_note_${eventId.slice(0, 8)}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },
};
