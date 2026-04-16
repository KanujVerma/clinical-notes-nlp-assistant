// frontend/src/pages/History.tsx
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import { NoteListItem } from "../types";
import StatusBadge from "../components/StatusBadge";
import SourceBadge from "../components/SourceBadge";

const PER_PAGE = 20;

export default function History() {
  const navigate = useNavigate();
  const [notes, setNotes] = useState<NoteListItem[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.getHistory(page)
      .then((d) => {
        setNotes(d.notes);
        setHasMore(d.notes.length === PER_PAGE);
        setLoading(false);
      })
      .catch((e: any) => {
        setError(e.message ?? "Failed to load history");
        setLoading(false);
      });
  }, [page]);

  return (
    <div className="h-full overflow-auto bg-slate-50">
      <main className="max-w-5xl mx-auto p-6">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-slate-800">History</h1>
          <p className="text-slate-500 text-sm mt-1">All extracted notes</p>
        </div>

        {loading && <p className="text-slate-400 text-sm">Loading...</p>}

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {!loading && !error && notes.length === 0 && (
          <p className="text-slate-400 text-sm">
            No notes yet.{" "}
            <Link to="/" className="text-cyan-600 hover:underline">
              Extract a note
            </Link>{" "}
            or seed demo data.
          </p>
        )}

        {!loading && !error && notes.length > 0 && (
          <>
            <table className="w-full text-sm bg-white rounded-lg shadow-sm overflow-hidden">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  {["File", "Source", "Created", "Status", "Corrections"].map((h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-3 text-slate-500 font-medium text-xs uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {notes.map((note) => (
                  <tr
                    key={note.id}
                    onClick={() => navigate(`/review/${note.id}`, { state: { from: "history" } })}
                    className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="px-4 py-3 text-slate-700">{note.filename ?? `note #${note.id}`}</td>
                    <td className="px-4 py-3"><SourceBadge source={note.source} /></td>
                    <td className="px-4 py-3 text-slate-500">
                      {new Date(note.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3"><StatusBadge status={note.status} /></td>
                    <td className="px-4 py-3 text-slate-500">{note.correction_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="mt-4 flex items-center gap-3">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 text-sm border border-slate-200 rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-40"
              >
                ← Prev
              </button>
              <span className="text-sm text-slate-500">Page {page}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={!hasMore}
                className="px-3 py-1.5 text-sm border border-slate-200 rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
