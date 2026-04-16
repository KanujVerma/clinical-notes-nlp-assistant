// frontend/src/pages/Metrics.tsx
import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { api } from "../api/client";
import { MetricsResponse } from "../types";

export default function Metrics() {
  const [data, setData] = useState<MetricsResponse | null>(null);

  useEffect(() => { api.getMetrics().then(setData); }, []);

  if (!data) return <div className="p-8 text-slate-400">Loading...</div>;

  const evalData = data.eval;
  const chartData = evalData
    ? Object.entries(evalData.by_category).map(([cat, m]) => ({
        category: cat, precision: m.precision, recall: m.recall, f1: m.f1,
      }))
    : [];

  return (
    <div className="h-full overflow-auto bg-slate-50">
      <main className="max-w-5xl mx-auto p-6 space-y-8">
        {!evalData ? (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-amber-700 text-sm">
            Evaluation results not yet available. Run <code className="bg-amber-100 px-1 rounded">python scripts/run_evaluation.py</code> to generate metrics.
          </div>
        ) : (
          <>
            {/* Overall cards */}
            <div className="grid grid-cols-3 gap-4">
              {(["precision", "recall", "f1"] as const).map((metric) => (
                <div key={metric} className="bg-white rounded-lg border border-slate-200 p-4 text-center shadow-sm">
                  <p className="text-xs text-slate-500 uppercase tracking-wide">{metric}</p>
                  <p className="text-3xl font-semibold text-blue-600 mt-1">{(evalData.overall[metric] * 100).toFixed(1)}%</p>
                </div>
              ))}
            </div>

            {/* Per-category chart */}
            <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-600 mb-4">Performance by Category</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="category" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v) => typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v ?? "")} />
                  <Legend />
                  <Bar dataKey="precision" fill="#93c5fd" name="Precision" />
                  <Bar dataKey="recall" fill="#6ee7b7" name="Recall" />
                  <Bar dataKey="f1" fill="#818cf8" name="F1" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <p className="text-xs text-slate-400">
              Evaluated on 20 hand-written synthetic notes · pipeline v{evalData.pipeline_version} · run at {new Date(evalData.run_at).toLocaleString()}
            </p>
          </>
        )}

        {/* DB correction stats */}
        {data.db_stats.by_status.length > 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-600 mb-3">Review Activity</h2>
            <table className="w-full text-sm">
              <thead><tr className="text-xs text-slate-400">
                <th className="text-left py-1">Status</th>
                <th className="text-right py-1">Count</th>
                <th className="text-right py-1">Avg corrections</th>
                <th className="text-right py-1">Avg review time</th>
              </tr></thead>
              <tbody>
                {data.db_stats.by_status.map((row) => (
                  <tr key={row.status} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-700">{row.status}</td>
                    <td className="py-1.5 text-right text-slate-600">{row.count}</td>
                    <td className="py-1.5 text-right text-slate-600">{row.avg_corrections.toFixed(1)}</td>
                    <td className="py-1.5 text-right text-slate-600">
                      {row.avg_review_ms ? `${Math.round(row.avg_review_ms / 1000)}s` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
