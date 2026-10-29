import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type MetricDrilldownResponse, type MetricEvidenceRow } from "../api/client";

function evidenceUrl(row: MetricEvidenceRow): string {
  const params = new URLSearchParams();
  if (row.kind === "issue" && row.issue_id) params.set("issue", row.issue_id);
  if (row.field_path) params.set("field", row.field_path);
  return `/review/${row.note_id}${params.size ? `?${params.toString()}` : ""}`;
}

/** A bounded index of current note evidence, never a public PHI/data export. */
export default function MetricsDrilldown() {
  const [searchParams] = useSearchParams();
  const query = searchParams.toString();
  const [data, setData] = useState<MetricDrilldownResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let canceled = false;
    setLoading(true);
    setError(null);
    setData(null);
    api.getMetricDrilldown(Object.fromEntries(new URLSearchParams(query)))
      .then((result) => { if (!canceled) setData(result); })
      .catch((reason: unknown) => {
        if (!canceled) setError(reason instanceof Error ? reason.message : "Unable to load current evidence.");
      })
      .finally(() => { if (!canceled) setLoading(false); });
    return () => { canceled = true; };
  }, [query]);

  useEffect(() => { if (!loading && data) titleRef.current?.focus(); }, [loading, data]);

  return (
    <main id="main-content" className="h-full overflow-auto bg-slate-50 p-6">
      <div className="mx-auto max-w-4xl space-y-5">
        <Link to="/metrics" className="text-sm font-medium text-cyan-700 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-cyan-600">
          Back to Metrics
        </Link>
        <div>
          <h1 ref={titleRef} tabIndex={-1} className="text-xl font-semibold text-slate-900 focus:outline-none">
            {data?.title ?? "Evidence drilldown"}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Only current, workspace-authorized records appear here. Open a note to inspect its actual source and review history.
          </p>
        </div>
        {loading && <p role="status" className="text-sm text-slate-600">Loading current evidence…</p>}
        {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
        {data && !loading && (
          <section aria-label="Evidence results" className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 p-4 text-sm text-slate-600" aria-live="polite">
              {data.count_returned} current record{data.count_returned === 1 ? "" : "s"}
              {data.has_more ? ` (first ${data.max_rows} shown)` : ""}
            </div>
            {data.rows.length === 0 ? (
              <p className="p-6 text-sm text-slate-600">No current records match this filter.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {data.rows.map((row, index) => (
                  <li key={row.issue_id ?? row.review_event_id ?? `${row.note_id}-${index}`} className="p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-sm text-slate-900">
                          {row.label} <span className="font-normal text-slate-500">· Synthetic note #{row.note_id}</span>
                        </p>
                        <p className="mt-1 text-xs text-slate-600">{row.detail}</p>
                        {row.field_path && (
                          <p className="mt-1 font-mono text-xs text-slate-500">Field: {row.field_path}</p>
                        )}
                      </div>
                      <Link
                        to={evidenceUrl(row)}
                        className="shrink-0 rounded-md border border-cyan-700 px-3 py-2 text-sm font-medium text-cyan-800 hover:bg-cyan-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-600"
                        aria-label={`Inspect source and evidence for note ${row.note_id}: ${row.label}`}
                      >
                        Inspect source
                      </Link>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
