import { useState, useEffect } from "react";
import { api } from "../api/client";

export default function ValidationLab() {
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningEval, setRunningEval] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadRuns();
  }, []);

  async function loadRuns() {
    try {
      setLoading(true);
      const data = await api.getEvalRuns();
      setRuns(data);
      if (data.length > 0 && !selectedRunId) {
        setSelectedRunId(data[0].run_id);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load evaluation runs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedRunId || selectedRunId.startsWith("legacy_")) {
      setSelectedRunDetail(null);
      return;
    }
    api.getEvalRunDetail(selectedRunId)
      .then((detail) => setSelectedRunDetail(detail))
      .catch(() => setSelectedRunDetail(null));
  }, [selectedRunId]);

  async function handleTriggerRun() {
    try {
      setRunningEval(true);
      setError(null);
      const res = await api.triggerEvalRun();
      await loadRuns();
      setSelectedRunId(res.run_id);
    } catch (err: any) {
      setError(err.message || "Failed running evaluation");
    } finally {
      setRunningEval(false);
    }
  }

  const activeRun = runs.find((r) => r.run_id === selectedRunId);

  return (
    <div className="flex h-full flex-col bg-slate-900 text-slate-100 overflow-y-auto">
      {/* Header */}
      <div className="border-b border-slate-800 bg-slate-900/80 px-6 py-4 backdrop-blur">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center space-x-3">
              <h1 className="text-xl font-bold tracking-tight text-white">Validation Lab</h1>
              {loading && <span className="text-xs text-slate-400 animate-pulse">Loading…</span>}
              <span className="rounded-full bg-cyan-950 px-2.5 py-0.5 text-xs font-semibold text-cyan-400 border border-cyan-800">
                Synthetic Benchmark
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Offline multiset medication evaluation, attribute-level matching, and error attribution.
            </p>
          </div>
          <button
            onClick={handleTriggerRun}
            disabled={runningEval}
            className="flex items-center space-x-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500 disabled:opacity-50 transition-colors shadow-lg shadow-cyan-900/30"
          >
            {runningEval ? (
              <>
                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                </svg>
                <span>Evaluating 20 Notes…</span>
              </>
            ) : (
              <span>Run Strict Evaluation</span>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 rounded-lg bg-rose-950/50 border border-rose-800 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* Main Content Split */}
      <div className="grid flex-1 grid-cols-12 gap-6 p-6">
        {/* Left Column: Runs List */}
        <div className="col-span-4 flex flex-col rounded-xl border border-slate-800 bg-slate-950/60 p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
            Evaluation Runs ({runs.length})
          </h2>
          <div className="flex-1 space-y-2 overflow-y-auto">
            {runs.map((r) => {
              const isSelected = r.run_id === selectedRunId;
              const f1 = r.summary?.overall?.f1 ?? 0;
              return (
                <div
                  key={r.run_id}
                  onClick={() => setSelectedRunId(r.run_id)}
                  className={`cursor-pointer rounded-lg border p-3.5 transition-all ${
                    isSelected
                      ? "border-cyan-500/80 bg-cyan-950/30 shadow-md shadow-cyan-950/40"
                      : "border-slate-800/80 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/80"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-medium text-slate-200 truncate max-w-[180px]">
                      {r.run_id}
                    </span>
                    <span
                      className={`font-mono text-sm font-bold ${
                        f1 != null && f1 >= 0.75 ? "text-emerald-400" : f1 != null && f1 >= 0.60 ? "text-amber-400" : "text-rose-400"
                      }`}
                    >
                      F1: {f1 != null ? f1.toFixed(3) : "N/A"}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                    <span>{r.evaluator}</span>
                    <span>{r.started_at ? new Date(r.started_at).toLocaleTimeString() : ""}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Active Run Detail */}
        <div className="col-span-8 flex flex-col space-y-6">
          {activeRun ? (
            <>
              {/* Summary Metrics Cards */}
              <div className="grid grid-cols-4 gap-4">
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-xs font-medium text-slate-400">Overall F1</p>
                  <p className="mt-1 font-mono text-2xl font-bold text-cyan-400">
                    {activeRun.summary?.overall?.f1 != null ? activeRun.summary.overall.f1.toFixed(3) : "N/A"}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Prec: {activeRun.summary?.overall?.precision ?? "-"} | Rec: {activeRun.summary?.overall?.recall ?? "-"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-xs font-medium text-slate-400">Medications F1</p>
                  <p className="mt-1 font-mono text-2xl font-bold text-emerald-400">
                    {activeRun.summary?.medications?.f1 != null ? activeRun.summary.medications.f1.toFixed(3) : "N/A"}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Support: {activeRun.summary?.medications?.support ?? "-"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-xs font-medium text-slate-400">Vitals F1</p>
                  <p className="mt-1 font-mono text-2xl font-bold text-amber-400">
                    {activeRun.summary?.vitals?.f1 != null ? activeRun.summary.vitals.f1.toFixed(3) : "N/A"}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Support: {activeRun.summary?.vitals?.support ?? "-"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <p className="text-xs font-medium text-slate-400">Instructions F1</p>
                  <p className="mt-1 font-mono text-2xl font-bold text-violet-400">
                    {activeRun.summary?.instructions?.f1 != null ? activeRun.summary.instructions.f1.toFixed(3) : "N/A"}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Support: {activeRun.summary?.instructions?.support ?? "-"}
                  </p>
                </div>
              </div>

              {/* Case-by-Case Breakdown */}
              <div className="flex-1 rounded-xl border border-slate-800 bg-slate-950/60 p-5 overflow-hidden flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-slate-200">
                    Case Results & Mismatches
                  </h3>
                  <span className="text-xs font-mono text-slate-500">
                    {activeRun.note_count || 20} Test Cases
                  </span>
                </div>

                <div className="flex-1 overflow-y-auto space-y-3">
                  {selectedRunDetail?.cases ? (
                    selectedRunDetail.cases.map((c: any) => (
                      <div key={c.note_id} className="rounded-lg border border-slate-800/80 bg-slate-900/30 p-3.5">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-bold text-slate-300">
                            {c.note_id}
                          </span>
                          <div className="flex space-x-2 text-xs font-mono">
                            <span className="text-emerald-400">TP: {c.medications?.tp || 0}</span>
                            <span className="text-rose-400">FP: {c.medications?.fp || 0}</span>
                            <span className="text-amber-400">FN: {c.medications?.fn || 0}</span>
                          </div>
                        </div>

                        {c.medications?.false_negatives?.length > 0 && (
                          <div className="mt-2 text-xs text-rose-300">
                            <span className="font-semibold text-rose-400">Missed: </span>
                            {c.medications.false_negatives.map((m: any, idx: number) => (
                              <span key={idx} className="mr-2">
                                {m.name} {m.dose}
                              </span>
                            ))}
                          </div>
                        )}
                        {c.medications?.false_positives?.length > 0 && (
                          <div className="mt-1 text-xs text-amber-300">
                            <span className="font-semibold text-amber-400">Extra (FP): </span>
                            {c.medications.false_positives.map((m: any, idx: number) => (
                              <span key={idx} className="mr-2">
                                {m.name} {m.dose}
                              </span>
                            ))}
                          </div>
                        )}
                        {c.medications?.pairs?.filter((p: any) => Object.keys(p.attribute_mismatches || {}).length > 0).length > 0 && (
                          <div className="mt-1.5 text-xs text-rose-300">
                            <span className="font-semibold text-rose-400">Attribute Mismatches: </span>
                            {c.medications.pairs
                              .filter((p: any) => Object.keys(p.attribute_mismatches || {}).length > 0)
                              .map((p: any, idx: number) => {
                                const medName = p.pred?.name || p.label?.name || "Medication";
                                const diffs = Object.entries(p.attribute_mismatches || {})
                                  .map(([attr, vals]: [string, any]) => `${attr}: "${Array.isArray(vals) ? vals[0] : vals}" ≠ "${Array.isArray(vals) ? vals[1] : ''}"`)
                                  .join(", ");
                                return (
                                  <span key={idx} className="mr-3 inline-block">
                                    <span className="font-medium text-slate-300">{medName}</span> ({diffs})
                                  </span>
                                );
                              })}
                          </div>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-500">
                      Legacy baseline summary view. Run strict evaluation above to inspect per-case TP/FP/FN error attribution.
                    </p>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
              No evaluation run selected.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
