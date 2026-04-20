// frontend/src/pages/Metrics.tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { MetricsResponse } from "../types";

export default function Metrics() {
  const [data, setData] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getMetrics()
      .then((d) => { setData(d); setLoading(false); })
      .catch((e: any) => { setError(e.message ?? "Failed to load metrics"); setLoading(false); });
  }, []);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400 text-sm">
        Loading metrics...
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-red-500 text-sm">{error}</p>
      </div>
    );
  }

  if (!data) return null;

  const corrRates = data.db_stats.correction_rates;
  const corrByCategory = corrRates?.by_category ?? {};
  const corrByField = corrRates?.by_field ?? {};

  // Sort categories by correction rate descending
  const corrCatChartData = Object.entries(corrByCategory)
    .filter(([, v]) => v.reviewed > 0)
    .map(([cat, v]) => ({ category: cat, rate: Math.round(v.rate * 100), reviewed: v.reviewed }))
    .sort((a, b) => b.rate - a.rate);

  // Sort fields by correction rate descending, show top 10
  const corrFieldRows = Object.entries(corrByField)
    .filter(([, v]) => v.reviewed > 0)
    .map(([field, v]) => ({ field, ...v }))
    .sort((a, b) => b.rate - a.rate)
    .slice(0, 10);

  return (
    <div className="h-full overflow-auto bg-slate-50">
      <main className="max-w-5xl mx-auto p-6 space-y-8">
        {/* Correction rate by category */}
        {corrCatChartData.length > 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-600 mb-4">Correction Rate by Category</h2>
            <div className="space-y-3">
              {corrCatChartData.map(({ category, rate, reviewed }) => (
                <div key={category}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-slate-600 capitalize">{category}</span>
                    <span className="text-xs text-slate-400">{rate}% of {reviewed} fields</span>
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        rate >= 30 ? "bg-amber-400" : rate >= 15 ? "bg-yellow-300" : "bg-green-400"
                      }`}
                      style={{ width: `${rate}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Per-field correction rate table */}
        {corrFieldRows.length > 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-600 mb-3">Correction Rate by Field (top 10)</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-400 border-b border-slate-100">
                  <th className="text-left py-1.5 font-medium">Field</th>
                  <th className="text-right py-1.5 font-medium">Reviewed</th>
                  <th className="text-right py-1.5 font-medium">Corrected</th>
                  <th className="text-right py-1.5 font-medium">Rate</th>
                </tr>
              </thead>
              <tbody>
                {corrFieldRows.map(({ field, reviewed, corrected, rate }) => (
                  <tr key={field} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-700 font-mono text-xs">{field}</td>
                    <td className="py-1.5 text-right text-slate-500">{reviewed}</td>
                    <td className="py-1.5 text-right text-slate-500">{corrected}</td>
                    <td className="py-1.5 text-right">
                      <span className={`font-medium ${
                        rate >= 0.3 ? "text-amber-600" : rate >= 0.15 ? "text-yellow-600" : "text-green-600"
                      }`}>
                        {Math.round(rate * 100)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* DB correction stats */}
        {data.db_stats.by_status.length > 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-600 mb-3">Review Activity</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-400 border-b border-slate-100">
                  <th className="text-left py-1 font-medium">Status</th>
                  <th className="text-right py-1 font-medium">Count</th>
                  <th className="text-right py-1 font-medium">Avg corrections</th>
                  <th className="text-right py-1 font-medium">Avg review time</th>
                </tr>
              </thead>
              <tbody>
                {data.db_stats.by_status.map((row) => (
                  <tr key={row.status} className="border-t border-slate-100">
                    <td className="py-1.5 text-slate-700">{row.status}</td>
                    <td className="py-1.5 text-right text-slate-600">{row.count}</td>
                    <td className="py-1.5 text-right text-slate-600">{Number(row.avg_corrections ?? 0).toFixed(1)}</td>
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
