import { useState, useEffect } from "react";
import { api } from "../api/client";

export default function OperationalIssuesDrawer({
  noteId,
  revisionId,
  isOpen,
  onToggle,
  onIssuesUpdated,
}: {
  noteId: number;
  revisionId?: string | null;
  isOpen: boolean;
  onToggle: () => void;
  onIssuesUpdated?: (openBlockersCount: number) => void;
}) {
  const [issues, setIssues] = useState<any[]>([]);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [aiDiscrepancies, setAiDiscrepancies] = useState<any[]>([]);
  const [loadingAi, setLoadingAi] = useState(false);

  useEffect(() => {
    loadIssues();
  }, [noteId, revisionId]);

  async function loadIssues() {
    try {
      setLoadingIssues(true);
      const data = await api.getIssues({ note_id: noteId });
      setIssues(data);
      const blockers = data.filter((i) => i.severity === "critical_blocker" && i.status === "open").length;
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
    try {
      setLoadingAi(true);
      const res = await api.requestAiCandidates(noteId);
      setAiDiscrepancies(res.discrepancies || []);
    } catch (err: any) {
      alert(`AI proposal failed: ${err.message}`);
    } finally {
      setLoadingAi(false);
    }
  }

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
            <button
              onClick={handleRequestAi}
              disabled={loadingAi}
              className="rounded bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-cyan-400 hover:bg-slate-700 disabled:opacity-50"
            >
              {loadingAi ? "Analyzing…" : "Request Proposals"}
            </button>
          </div>

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
