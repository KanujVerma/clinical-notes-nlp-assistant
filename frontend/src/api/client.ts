// frontend/src/api/client.ts
import { QueueResponse } from "../types";
import { AiExplainRequest, AiExplainResponse, AiStatusResponse } from "../lib/aiExplain";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "") + "/api";

export type AiAdapter = "text" | "glm_ocr" | "qwen3_vl";
export interface AiJobRequest {
  adapter: AiAdapter;
  source_revision_id: string;
  extraction_id: string;
  page_number: number;
  idempotency_key: string;
}
export interface AiJobResponse {
  job_id: string;
  status: string;
  adapter: AiAdapter;
  source_revision_id: string;
  is_replay?: boolean;
}
export interface JobStatus {
  id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed" | "partial" | "canceled";
  progress: number;
  result: null | { inference_run_id?: string; source_revision_id?: string; status?: string };
  error_code?: string | null;
}
export interface InferenceCandidateRun {
  id: string;
  source_revision_id: string;
  is_current: boolean;
  task_type: string;
  status: string;
  error_code?: string | null;
  model_name: string;
  model_digest?: string | null;
  duration_ms?: number | null;
  discrepancies: Array<{ type: string; medication?: string; detail?: string }>;
  candidates: Record<string, unknown>;
}


export function getSessionId(): string {
  const KEY = "clinical_nlp_session_id";
  let sid = localStorage.getItem(KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(KEY, sid);
  }
  return sid;
}

// Hosted workspaces use server-issued capabilities. A browser-chosen UUID is
// only supported by the local legacy migration path, never by hosted mode.
const WORKSPACE_KEY = "clinical_nlp_workspace_capability_v1";
type WorkspaceCapability = { id: string; token: string; expiresAt: number };
let workspaceHeadersPromise: Promise<Record<string, string>> | null = null;
let workspaceExpiresAt = 0;

async function resolveWorkspaceHeaders(): Promise<Record<string, string>> {
  const raw = localStorage.getItem(WORKSPACE_KEY);
  if (raw) {
    try {
      const existing = JSON.parse(raw) as WorkspaceCapability;
      if (existing.id && existing.token && existing.expiresAt > Date.now() + 15_000) {
        workspaceExpiresAt = existing.expiresAt;
        return {
          "X-Workspace-ID": existing.id,
          "X-Workspace-Token": existing.token,
        };
      }
    } catch {
      // Corrupt local capability: request a new isolated synthetic workspace.
    }
    localStorage.removeItem(WORKSPACE_KEY);
  }

  // Query capabilities directly to avoid recursion through request<T>.
  const response = await fetch(`${BASE}/capabilities`, { cache: "no-store" });
  if (!response.ok) throw new Error("Cannot determine the server workspace mode");
  const capabilities = await response.json() as { mode?: string };
  if (capabilities.mode !== "hosted_demo") {
    const sid = getSessionId();
    return { "X-Session-ID": sid, "X-Workspace-ID": sid };
  }

  const created = await fetch(`${BASE}/workspaces`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!created.ok) throw new Error("Unable to initialize a synthetic demo workspace");
  const workspace = await created.json() as {
    workspace_id: string;
    token: string;
    expires_at: string;
  };
  if (!workspace.workspace_id || !workspace.token || !Number.isFinite(Date.parse(workspace.expires_at))) {
    throw new Error("The server returned an invalid workspace capability");
  }
  const record: WorkspaceCapability = {
    id: workspace.workspace_id,
    token: workspace.token,
    expiresAt: Date.parse(workspace.expires_at),
  };
  localStorage.setItem(WORKSPACE_KEY, JSON.stringify(record));
  workspaceExpiresAt = record.expiresAt;
  return { "X-Workspace-ID": record.id, "X-Workspace-Token": record.token };
}

async function getWorkspaceHeaders(): Promise<Record<string, string>> {
  if (workspaceExpiresAt && Date.now() + 15_000 >= workspaceExpiresAt) {
    // Never keep an expired capability alive in the cached Promise.
    workspaceHeadersPromise = null;
    workspaceExpiresAt = 0;
    localStorage.removeItem(WORKSPACE_KEY);
  }
  if (!workspaceHeadersPromise) {
    workspaceHeadersPromise = resolveWorkspaceHeaders().catch((error: unknown) => {
      workspaceHeadersPromise = null;
      throw error;
    });
  }
  return workspaceHeadersPromise;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const authHeaders = await getWorkspaceHeaders();
  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
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

  uploadFile: async (file: File) => {
    const authHeaders = await getWorkspaceHeaders();
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/upload`, {
      method: "POST",
      body: form,
      headers: authHeaders,
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

  getHistory: (page = 1) =>
    request<{ notes: any[]; page: number }>(`/history?page=${page}`),

  getNoteDetail: (id: number) =>
    request<any>(`/history/${id}`),

  getMetrics: () => request<any>("/metrics"),

  seedDemo: () =>
    request<{ loaded: number; skipped: number }>("/seed-demo", { method: "POST" }),

  getQueue: () => request<QueueResponse>("/queue"),

  // The previous unbound PUT endpoint could destroy extraction history.
  // Always use the version-bound append-only source revision API instead.
  updateNoteText: async (
    noteId: number,
    text: string,
    expectedRevisionId?: string | null,
    expectedLockVersion?: number | null
  ) =>
    api.appendNoteRevision(noteId, text, "ocr_preview_edit", expectedRevisionId, expectedLockVersion),

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

  getScenarios: () =>
    request<{ scenarios: Array<{ filename: string; title: string; sha256: string; has_issues: boolean; issues_count: number; snippet: string }>; count: number }>("/scenarios"),

  getNoteState: (noteId: number) =>
    request<any>(`/notes/${noteId}`),

  getNoteSource: (noteId: number) =>
    request<any>(`/notes/${noteId}/source`),

  // Protected source images cannot use a bare <img src="/api/...">: the
  // browser will not attach the workspace capability headers to that URL.
  // Keep the capability out of the URL and let the viewer create a temporary
  // revocable object URL from this authorized blob.
  getPageImageBlob: async (
    noteId: number,
    pageNumber: number,
    rotation: number,
    signal?: AbortSignal,
  ): Promise<Blob> => {
    if (!Number.isSafeInteger(noteId) || noteId < 1 ||
        !Number.isSafeInteger(pageNumber) || pageNumber < 1 ||
        ![0, 90, 180, 270].includes(rotation)) {
      throw new Error("Invalid source page request");
    }
    const authHeaders = await getWorkspaceHeaders();
    const response = await fetch(
      `${BASE}/notes/${noteId}/pages/${pageNumber}/image?rotation=${rotation}`,
      { method: "GET", headers: authHeaders, signal, cache: "no-store" },
    );
    if (!response.ok) {
      throw new Error(`Unable to load authorized source page (${response.status})`);
    }
    const mediaType = response.headers.get("Content-Type") || "";
    if (!mediaType.startsWith("image/")) {
      throw new Error("Unexpected source page content type");
    }
    return response.blob();
  },

  appendNoteRevision: async (
    noteId: number,
    raw_text: string,
    reason?: string,
    expectedRevisionId?: string | null,
    expectedLockVersion?: number | null
  ) => {
    const revId = expectedRevisionId;
    const lockVer = expectedLockVersion;
    if (!revId || typeof lockVer !== "number") {
      throw new Error("Source binding is unavailable. Reload the note before editing.");
    }
    return request<any>(`/notes/${noteId}/revisions`, {
      method: "POST",
      body: JSON.stringify({
        raw_text,
        reason: reason || "human_transcription_edit",
        expected_source_revision_id: revId,
        expected_lock_version: lockVer,
      }),
    });
  },

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
    request<InferenceCandidateRun[]>(`/notes/${noteId}/ai-candidates`),

  requestAiCandidates: (noteId: number, body: AiJobRequest) =>
    request<AiJobResponse>(`/notes/${noteId}/ai-candidates`, {
      method: "POST", body: JSON.stringify(body),
    }),

  getJob: (jobId: string) =>
    request<JobStatus>(`/jobs/${encodeURIComponent(jobId)}`),

  getEvalRuns: () =>
    request<any[]>("/evaluation/runs"),

  getEvalRunDetail: (runId: string) =>
    request<any>(`/evaluation/runs/${runId}`),

  triggerEvalRun: () =>
    request<any>("/evaluation/runs", { method: "POST" }),

  getExportUrl: (eventId: string) =>
    `${BASE}/review-events/${eventId}/export`,

  downloadExport: async (eventId: string, filename?: string) => {
    const authHeaders = await getWorkspaceHeaders();
    const res = await fetch(`${BASE}/review-events/${eventId}/export`, {
      headers: authHeaders,
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
