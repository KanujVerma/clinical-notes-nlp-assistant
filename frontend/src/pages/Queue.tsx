// frontend/src/pages/Queue.tsx
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";
import { QueueNote } from "../types";
import SourceBadge from "../components/SourceBadge";

export default function Queue() {
  const navigate = useNavigate();
  const [notes, setNotes] = useState<QueueNote[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getQueue()
      .then((data) => {
        setNotes(data.notes);
        setCount(data.count);
        setLoading(false);
      })
      .catch((e: any) => {
        setError(e.message ?? "Failed to load queue");
        setLoading(false);
      });
  }, []);

  return (
    <div className="h-full overflow-auto bg-slate-50">
      <main className="max-w-5xl mx-auto p-6">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-slate-800">Review Queue</h1>
          {!loading && !error && (
            <p className="text-slate-500 text-sm mt-1">
              {count} note{count !== 1 ? "s" : ""} pending review
            </p>
          )}
        </div>

        {loading && <p className="text-slate-400 text-sm">Loading...</p>}

        {error && (
          <p className="text-red-500 text-sm">{error}</p>
        )}

        {!loading && !error && notes.length === 0 && (
          <div className="text-center py-16 text-slate-400">
            <p className="text-base">No notes pending review.</p>
            <p className="text-sm mt-1">
              <Link to="/" className="text-cyan-600 hover:underline">
                Upload a note
              </Link>{" "}
              to get started.
            </p>
          </div>
        )}

        {!loading && !error && notes.length > 0 && (
          <table className="w-full text-sm bg-white rounded-lg shadow-sm overflow-hidden">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {["File", "Source", "Uploaded"].map((h) => (
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
                  onClick={() => navigate(`/review/${note.id}`)}
                  className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer"
                >
                  <td className="px-4 py-3 text-slate-700">
                    {note.filename ?? `Note #${note.id}`}
                  </td>
                  <td className="px-4 py-3">
                    <SourceBadge source={note.source} />
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(note.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}
