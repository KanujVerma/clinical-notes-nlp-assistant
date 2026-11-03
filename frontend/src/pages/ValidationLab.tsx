import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatF1, formatRunWhen } from "../lib/reviewCopy";

export default function ValidationLab() {
  const [runs, setRuns] = useState<any[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [runningEval, setRunningEval] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [caseFilter, setCaseFilter] = useState<"all" | "differences" | "exact">("all");
  const [detailAttempt, setDetailAttempt] = useState(0);

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
    setDetailError(null);
    api.getEvalRunDetail(selectedRunId)
      .then((detail) => setSelectedRunDetail(detail))
      .catch(() => {
        setSelectedRunDetail(null);
        setDetailError("Couldn't load case details.");
      });
  }, [selectedRunId, detailAttempt]);

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
    <div className="flex h-full flex-col bg-slate-50 text-slate-900 overflow-y-auto">
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Validation Lab</h1>
            {loading && <p className="text-sm text-slate-500">Loading…</p>}
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              See what the extractor matched, missed, or added across 20 fictional notes.{" "}
              <Link to="/showcase" className="font-medium text-cyan-800 underline">See the 24-image OCR test</Link>.
            </p>
            <p className="mt-1 text-sm text-slate-500">F1 combines missed and extra results. It is not a clinical accuracy score.</p>
          </div>
          <button
            onClick={handleTriggerRun}
            disabled={runningEval}
            className="rounded-lg bg-cyan-800 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-900 disabled:opacity-50"
          >
            {runningEval ? "Running evaluation…" : "Run evaluation"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 rounded-lg bg-rose-50 border border-rose-200 p-4 text-sm text-rose-800">
          {error}
        </div>
      )}

      {/* Main Content Split */}
      <div className="grid flex-1 grid-cols-12 gap-6 p-6">
        {/* Left Column: Runs List */}
        <div className="col-span-4 flex flex-col rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-800 mb-3">
            Past runs ({runs.length})
          </h2>
          <div className="flex-1 space-y-2 overflow-y-auto">
            {runs.map((r) => {
              const isSelected = r.run_id === selectedRunId;
              const f1 = r.summary?.overall?.f1;
              return (
                <div
                  key={r.run_id}
                  onClick={() => setSelectedRunId(r.run_id)}
                  className={`cursor-pointer rounded-lg border p-3.5 ${
                    isSelected
                      ? "border-cyan-700 bg-cyan-50"
                      : "border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-slate-800">
                      {formatRunWhen(r.started_at)}
                    </span>
                    <span className="font-mono text-sm text-slate-900">
                      {formatF1(f1)}
                    </span>
                  </div>
                  {String(r.evaluator || "").includes("relaxed") && (
                    <p className="mt-1 text-xs text-slate-500">Earlier scoring method. Not directly comparable with current runs.</p>
                  )}
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
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-medium text-slate-400">Overall F1</p>
                  <p className="mt-1 font-mono text-2xl font-semibold text-slate-900">
                    {formatF1(activeRun.summary?.overall?.f1)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Prec: {activeRun.summary?.overall?.precision ?? "-"} | Rec: {activeRun.summary?.overall?.recall ?? "-"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-medium text-slate-400">Medications F1</p>
                  <p className="mt-1 font-mono text-2xl font-semibold text-slate-900">
                    {formatF1(activeRun.summary?.medications?.f1)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Support: {activeRun.summary?.medications?.support ?? "-"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-medium text-slate-400">Vitals F1</p>
                  <p className="mt-1 font-mono text-2xl font-semibold text-slate-900">
                    {formatF1(activeRun.summary?.vitals?.f1)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Support: {activeRun.summary?.vitals?.support ?? "-"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-medium text-slate-400">Instructions F1</p>
                  <p className="mt-1 font-mono text-2xl font-semibold text-slate-900">
                    {formatF1(activeRun.summary?.instructions?.f1)}
                  </p>
                  <p className="mt-1 text-[11px] text-slate-500">
                    Support: {activeRun.summary?.instructions?.support ?? "-"}
                  </p>
                </div>
              </div>

              {/* Case-by-Case Breakdown */}
              <div className="flex-1 rounded-xl border border-slate-200 bg-white p-5 overflow-hidden flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-semibold text-slate-900">
                    Medication findings by note
                  </h3>
                  <span className="text-xs font-mono text-slate-500">
                    {activeRun.note_count || 20} Test Cases
                  </span>
                </div>

                <div className="mb-3 flex gap-2 text-sm" role="group" aria-label="Filter notes">
                  {(["all", "differences", "exact"] as const).map((key) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setCaseFilter(key)}
                      className={`rounded-md border px-3 py-1.5 ${caseFilter === key ? "border-cyan-800 bg-cyan-50 text-cyan-900" : "border-slate-200 text-slate-700"}`}
                    >
                      {key === "all" ? "All" : key === "differences" ? "Has differences" : "Exact matches"}
                    </button>
                  ))}
                </div>
                <div className="flex-1 overflow-y-auto space-y-3">
                  {selectedRunDetail?.cases ? (
                    selectedRunDetail.cases.filter((c: any) => {
                      const diffs = (c.medications?.fp || 0) + (c.medications?.fn || 0) + (c.medications?.pairs || []).filter((p: any) => Object.keys(p.attribute_mismatches || {}).length > 0).length;
                      if (caseFilter === "differences") return diffs > 0;
                      if (caseFilter === "exact") return diffs === 0;
                      return true;
                    }).map((c: any) => (
                      <div key={c.note_id} className="rounded-lg border border-slate-800/80 bg-slate-900/30 p-3.5">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-bold text-slate-300">
                            {c.note_id}
                          </span>
                          <div className="flex space-x-2 text-xs font-mono">
                            <span className="text-slate-700">{c.medications?.tp || 0} matched · {c.medications?.fp || 0} extra · {c.medications?.fn || 0} missed</span>
                          </div>
                        </div>

                        {c.medications?.false_negatives?.length > 0 && (
                          <div className="mt-2 text-xs text-rose-300">
                            <span className="font-semibold text-rose-800">Missed: </span>
                            {c.medications.false_negatives.map((m: any, idx: number) => (
                              <span key={idx} className="mr-2">
                                {m.name} {m.dose}
                              </span>
                            ))}
                          </div>
                        )}
                        {c.medications?.false_positives?.length > 0 && (
                          <div className="mt-1 text-xs text-amber-300">
                            <span className="font-semibold text-amber-900">Extra extracted medication: </span>
                            {c.medications.false_positives.map((m: any, idx: number) => (
                              <span key={idx} className="mr-2">
                                {m.name} {m.dose}
                              </span>
                            ))}
                          </div>
                        )}
                        {c.medications?.pairs?.filter((p: any) => Object.keys(p.attribute_mismatches || {}).length > 0).length > 0 && (
                          <div className="mt-1.5 text-xs text-rose-300">
                            <span className="font-semibold text-slate-800">Different details: </span>
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
                    <p className="text-sm text-slate-600">
                      {detailError ? (
                        <>Couldn't load case details. <button type="button" className="underline" onClick={() => setDetailAttempt((n) => n + 1)}>Try again</button></>
                      ) : "This older run has summary results only."}
                    </p>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-slate-600">
              {runs.length === 0 ? "No evaluation runs yet." : "No evaluation run selected."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
