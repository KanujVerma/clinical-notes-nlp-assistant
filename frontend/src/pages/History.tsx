// frontend/src/pages/History.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { NoteListItem } from "../types";
import StatusBadge from "../components/StatusBadge";
import SourceBadge from "../components/SourceBadge";

export default function History() {
  const navigate = useNavigate();
  const [notes, setNotes] = useState<NoteListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getHistory().then((d) => { setNotes(d.notes); setLoading(false); });
  }, []);

  return (
    <div className="h-full overflow-auto bg-slate-50">
      <main className="max-w-5xl mx-auto p-6">
        {loading ? <p className="text-slate-400">Loading...</p> : notes.length === 0 ? (
          <p className="text-slate-400">No notes yet. <a href="/" className="text-blue-600 hover:underline">Extract a note</a> or seed demo data.</p>
        ) : (
          <table className="w-full text-sm bg-white rounded-lg shadow-sm overflow-hidden">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                {["File", "Source", "Created", "Status", "Corrections"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-slate-500 font-medium text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {notes.map((note) => (
                <tr key={note.id} onClick={() => navigate(`/review/${note.id}`)}
                  className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer">
                  <td className="px-4 py-3 text-slate-700">{note.filename ?? `note #${note.id}`}</td>
                  <td className="px-4 py-3"><SourceBadge source={note.source} /></td>
                  <td className="px-4 py-3 text-slate-500">{new Date(note.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3"><StatusBadge status={note.status} /></td>
                  <td className="px-4 py-3 text-slate-500">{note.correction_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}
