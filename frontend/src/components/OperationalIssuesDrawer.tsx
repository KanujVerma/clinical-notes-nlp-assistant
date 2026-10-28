import { useState, useEffect, useRef } from "react";
import { api, type AiAdapter } from "../api/client";

export default function OperationalIssuesDrawer({
  noteId,
  revisionId,
  extractionId,
  isOpen,
  onToggle,
  onIssuesUpdated,
}: {
  noteId: number;
  revisionId?: string | null;
  extractionId?: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onIssuesUpdated?: (openBlockersCount: number) => void;
}) {
  const [isHosted, setIsHosted] = useState(false);
  const [issues, setIssues] = useState<any[]>([]);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [aiDiscrepancies, setAiDiscrepancies] = useState<any[]>([]);
  const [loadingAi, setLoadingAi] = useState(false);
  const [aiAdapter, setAiAdapter] = useState<AiAdapter>("text");
  const [aiJobId, setAiJobId] = useState<string | null>(null);
  const [aiJobStatus, setAiJobStatus] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiCandidates, setAiCandidates] = useState<Record<string, unknown> | null>(null);

  const currentBindingRef = useRef({ noteId, revisionId, extractionId });
  currentBindingRef.current = { noteId, revisionId, extractionId };

  useEffect(() => {
    api.getCapabilities().then((caps) => setIsHosted(caps.mode === "hosted_demo"))
      .catch(() => setIsHosted(true)); // fail closed if capabilities unavailable
  }, []);

  useEffect(() => {
    setAiDiscrepancies([]);
    setAiCandidates(null);
    setAiJobId(null);
    setAiJobStatus(null);
    setAiError(null);
    setLoadingAi(false);
    loadIssues();
  }, [noteId, revisionId, extractionId]);

  async function loadIssues() {
    try {
      setLoadingIssues(true);
      const data = await api.getIssues({ note_id: noteId });
      const currentIssues = (data || []).filter((i: any) => {
        if (revisionId && i.source_revision_id && i.source_revision_id !== revisionId) return false;
        if (extractionId && i.extraction_id && i.extraction_id !== extractionId) return false;
        return true;
      });
      setIssues(currentIssues);
      const blockers = currentIssues.filter((i: any) => i.severity === "critical_blocker" && i.status === "open").length;
      if (onIssuesUpdated) onIssuesUpdated(blockers);
    } catch {
      // silently ignore
    } finally {
      setLoadingIssues(false);
    }
  }

  async function handleDisposition(issueId: string, disposition: string) {
    try {
      await api.updateIssueDisposition(issueId, disposition, "Reviewer acknowledged in workspace");
      await loadIssues();
    } catch (err: any) {
      alert(`Error updating issue: ${err.message}`);
    }
  }

  async function handleRequestAi() {
    if (!revisionId || !extractionId) {
      setAiError("Current source/extraction is not ready; refresh the note.");
      return;
    }
    const expected = { noteId, revisionId, extractionId };
    setAiError(null);
    setAiJobStatus(null);
    setAiCandidates(null);
    setAiDiscrepancies([]);
    setLoadingAi(true);
    try {
      const response = await api.requestAiCandidates(noteId, {
        adapter: aiAdapter,
        source_revision_id: revisionId,
        extraction_id: extractionId,
        page_number: 1,
        idempotency_key: crypto.randomUUID(),
      });
      const current = currentBindingRef.current;
      if (current.noteId !== expected.noteId ||
          current.revisionId !== expected.revisionId ||
          current.extractionId !== expected.extractionId) {
        return;
      }
      setAiJobId(response.job_id);
      setAiJobStatus(response.status);
    } catch (err) {
      const current = currentBindingRef.current;
      if (current.noteId === expected.noteId &&
          current.revisionId === expected.revisionId &&
          current.extractionId === expected.extractionId) {
        setAiError(err instanceof Error ? err.message : "Cannot queue local AI task");
        setLoadingAi(false);
      }
    }
  }

  useEffect(() => {
    if (!aiJobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const poll = async () => {
      try {
        const job = await api.getJob(aiJobId);
        if (stopped) return;
        setAiJobStatus(job.status);
        if (job.status === "succeeded") {
          const runs = await api.getAiCandidates(noteId);
          if (stopped) return;
          const matching = runs.find(
            (run) => run.id === job.result?.inference_run_id &&
              run.is_current && run.source_revision_id === revisionId
          );
          if (!matching) {
            setAiError("Inference result no longer matches the current source revision.");
          } else {
            setAiDiscrepancies(matching.discrepancies || []);
            setAiCandidates(matching.candidates || {});
          }
          setAiJobId(null);
          setLoadingAi(false);
        } else if (job.status === "failed" || job.status === "canceled" ||
                   job.status === "partial") {
          setAiError(`Local AI task did not complete: ${job.error_code || job.status}`);
          setAiJobId(null);
          setLoadingAi(false);
        } else {
          timer = setTimeout(poll, 2000);
        }
      } catch (err) {
        if (!stopped) {
          setAiError(err instanceof Error ? err.message : "Could not check AI job");
          setAiJobId(null);
          setLoadingAi(false);
        }
      }
    };
    void poll();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [aiJobId, noteId, revisionId]);


  const openIssues = issues.filter((i) => i.status === "open");
  const blockerCount = openIssues.filter((i) => i.severity === "critical_blocker").length;

  return (
    <div
      className={`fixed top-0 right-0 z-40 h-full w-[380px] border-l border-slate-700 bg-slate-900 shadow-2xl transition-transform duration-200 ease-in-out ${
        isOpen ? "translate-x-0" : "translate-x-full"
      } flex flex-col text-slate-100`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 p-4">
        <div className="flex items-center space-x-2">
          <h3 className="font-bold text-sm text-white">Operational Issues</h3>
          {loadingIssues && <span className="text-[10px] text-slate-500 animate-pulse">refreshing…</span>}
          {openIssues.length > 0 && (
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                blockerCount > 0 ? "bg-rose-950 text-rose-300 border border-rose-800" : "bg-amber-950 text-amber-300 border border-amber-800"
              }`}
            >
              {openIssues.length} open
            </span>
          )}
        </div>
        <button
          onClick={onToggle}
          className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Issues List */}
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            Validation Canaries & Checks
          </h4>
          {openIssues.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-center text-xs text-slate-500">
              No open issues detected for this revision.
            </div>
          ) : (
            <div className="space-y-2.5">
              {openIssues.map((iss) => {
                const isCrit = iss.severity === "critical_blocker";
                return (
                  <div
                    key={iss.id}
                    className={`rounded-lg border p-3 ${
                      isCrit
                        ? "border-rose-800/80 bg-rose-950/20 text-rose-200"
                        : "border-amber-800/80 bg-amber-950/20 text-amber-200"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[11px] font-bold">{iss.issue_code}</span>
                      <span className={`text-[10px] font-semibold uppercase ${isCrit ? "text-rose-400" : "text-amber-400"}`}>
                        {iss.severity.replace("_", " ")}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-300 leading-snug">
                      {iss.safe_explanation}
                    </p>
                    {!isHosted && (
                    <div className="mt-2.5 flex justify-end space-x-2">
                      <button
                        onClick={() => handleDisposition(iss.id, "dismissed")}
                        className="rounded bg-slate-800 px-2 py-1 text-[10px] font-medium text-slate-300 hover:bg-slate-700"
                      >
                        Dismiss
                      </button>
                      <button
                        onClick={() => handleDisposition(iss.id, "acknowledged")}
                        className="rounded bg-cyan-700 px-2 py-1 text-[10px] font-medium text-white hover:bg-cyan-600"
                      >
                        Acknowledge
                      </button>
                    </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Local AI Second Opinion */}
        <div className="border-t border-slate-800 pt-4">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Local AI Understanding
            </h4>
            {isHosted ? (
              <span className="text-[11px] text-slate-400">Live AI disabled in hosted sandbox</span>
            ) : (
              <div className="flex items-center gap-2">
                <select
                  aria-label="Local AI adapter"
                  value={aiAdapter}
                  onChange={(event) => setAiAdapter(event.target.value as AiAdapter)}
                  disabled={loadingAi}
                  className="bg-slate-800 border border-slate-700 rounded px-1.5 py-1 text-[11px]"
                >
                  <option value="text">Text proposal</option>
                  <option value="glm_ocr">GLM-OCR image</option>
                  <option value="qwen3_vl">Qwen3-VL image</option>
                </select>
                <button
                  onClick={handleRequestAi}
                  disabled={loadingAi || !revisionId || !extractionId}
                  className="rounded bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-cyan-400 hover:bg-slate-700 disabled:opacity-50"
                >
                  {loadingAi ? "Queued / processing" : "Request Proposals"}
                </button>
              </div>
            )}
          </div>

          {aiJobStatus && (
            <p role="status" className="mt-2 text-xs text-slate-300">
              Local AI job: {aiJobStatus}. A separate local worker must be running.
            </p>
          )}
          {aiError && (
            <p role="alert" className="mt-2 text-xs text-rose-300">{aiError}</p>
          )}
          {aiCandidates && (
            <details className="mt-2 text-xs text-slate-300">
              <summary className="cursor-pointer">Unverified AI candidate output</summary>
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words text-[11px]">
                {JSON.stringify(aiCandidates, null, 2).slice(0, 3000)}
              </pre>
            </details>
          )}
          {aiDiscrepancies.length > 0 && (
            <div className="rounded-lg border border-cyan-800/80 bg-cyan-950/20 p-3 space-y-2 mt-2">
              <span className="text-[11px] font-bold text-cyan-300 uppercase">
                Detected Discrepancies ({aiDiscrepancies.length})
              </span>
              {aiDiscrepancies.map((d, i) => (
                <div key={i} className="text-xs text-slate-300 border-t border-cyan-900/40 pt-1.5">
                  <p className="font-semibold text-cyan-200">{d.type}: {d.medication}</p>
                  <p className="text-[11px] text-slate-400">{d.detail}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
