// frontend/src/components/AppShell.tsx
import { useEffect, useState } from "react";
import { NavLink, Outlet, useMatch } from "react-router-dom";
import { api } from "../api/client";
import { QueueNote } from "../types";
import { useQueue } from "../context/QueueContext";

function NavItem({
  to,
  label,
  badge,
}: {
  to: string;
  label: string;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        `flex items-center justify-between px-3 py-1.5 rounded-md text-sm transition-colors ${
          isActive
            ? "bg-slate-700 text-slate-100"
            : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        }`
      }
    >
      <span>{label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="ml-2 inline-flex items-center justify-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-500 text-slate-900 min-w-[18px]">
          {badge}
        </span>
      )}
    </NavLink>
  );
}

export default function AppShell() {
  const reviewMatch = useMatch("/review/:noteId");
  const activeNoteId = reviewMatch?.params.noteId;
  const { queueVersion } = useQueue();
  const [pendingNotes, setPendingNotes] = useState<QueueNote[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [resetMsg, setResetMsg] = useState<string | null>(null);

  useEffect(() => {
    api.getQueue().then((data) => {
      setPendingCount(data.count);
      setPendingNotes(data.notes.slice(0, 8));
    }).catch(() => {
      // silently fail — sidebar is non-critical
    });
  }, [queueVersion]);

  async function handleReset() {
    try {
      const result = await api.resetWorkspace();
      const { deleted_notes, deleted_extractions, deleted_validations } = result;
      setResetMsg(
        `Cleared ${deleted_notes} note${deleted_notes !== 1 ? "s" : ""}, ` +
        `${deleted_extractions} extraction${deleted_extractions !== 1 ? "s" : ""}, ` +
        `${deleted_validations} validation${deleted_validations !== 1 ? "s" : ""}.`
      );
      setPendingNotes([]);
      setPendingCount(0);
      setTimeout(() => setResetMsg(null), 4000);
    } catch {
      setResetMsg("Reset failed.");
      setTimeout(() => setResetMsg(null), 3000);
    }
  }

  return (
    <div className="flex h-screen bg-slate-900 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-[220px] flex-shrink-0 bg-slate-900 border-r border-slate-700 flex flex-col">
        {/* Logo */}
        <div className="px-4 py-4 border-b border-slate-700">
          <span className="text-slate-100 font-semibold text-sm tracking-wide">Clinical NLP</span>
          <p className="text-slate-500 text-[10px] mt-0.5">Demo mode — synthetic data</p>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-4">
          {/* Pipeline group */}
          <div>
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              Pipeline
            </p>
            <div className="space-y-0.5">
              <NavItem to="/" label="Upload" />
              <NavItem to="/queue" label="Queue" badge={pendingCount} />
            </div>
          </div>

          {/* Data group */}
          <div>
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              Data
            </p>
            <div className="space-y-0.5">
              <NavItem to="/history" label="History" />
              <NavItem to="/metrics" label="Metrics" />
            </div>
          </div>

          {/* Pending Review section */}
          {pendingNotes.length > 0 && (
            <div>
              <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Pending Review
              </p>
              <div className="space-y-0.5">
                {pendingNotes.map((note) => (
                  <NavLink
                    key={note.id}
                    to={`/review/${note.id}`}
                    className={`block px-3 py-1.5 rounded-md text-xs transition-colors truncate ${
                      activeNoteId === String(note.id)
                        ? "bg-cyan-900 text-cyan-300 border border-cyan-700"
                        : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                    }`}
                    title={note.filename ?? `Note #${note.id}`}
                  >
                    {note.filename ?? `Note #${note.id}`}
                  </NavLink>
                ))}
              </div>
            </div>
          )}
        </nav>

        {/* Reset workspace */}
        <div className="px-3 py-3 border-t border-slate-700">
          {resetMsg ? (
            <p className="text-[10px] text-slate-400 leading-tight">{resetMsg}</p>
          ) : (
            <button
              onClick={handleReset}
              className="w-full text-left px-3 py-1.5 rounded-md text-xs text-slate-500 hover:bg-slate-800 hover:text-rose-400 transition-colors"
            >
              Reset workspace
            </button>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden bg-slate-50">
        <Outlet />
      </main>
    </div>
  );
}
