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

  useEffect(() => {
    api.getQueue().then((data) => {
      setPendingCount(data.count);
      setPendingNotes(data.notes.slice(0, 8));
    }).catch(() => {
      // silently fail — sidebar is non-critical
    });
  }, [queueVersion]);

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
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-hidden bg-slate-50">
        <Outlet />
      </main>
    </div>
  );
}
