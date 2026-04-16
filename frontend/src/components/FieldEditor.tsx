// frontend/src/components/FieldEditor.tsx
import { useState } from "react";

export type FieldStatus = "accepted" | "corrected" | "removed" | "pending";
export type FieldCategory = "vitals" | "med" | "instr" | "meta";

interface Props {
  label: string;
  value: string;
  status: FieldStatus;
  category: FieldCategory;
  isActive: boolean;
  onActivate: () => void;
  onChange: (value: string, status: FieldStatus) => void;
}

// Left border color per category, inactive vs active
// Uses inline style because Tailwind v3 has no directional border-color utilities
const CAT_BORDER: Record<FieldCategory, { inactive: string; active: string }> = {
  vitals: { inactive: "#93c5fd", active: "#3b82f6" },
  med:    { inactive: "#86efac", active: "#22c55e" },
  instr:  { inactive: "#fcd34d", active: "#f59e0b" },
  meta:   { inactive: "#c4b5fd", active: "#8b5cf6" },
};

const CAT_ACTIVE_BG: Record<FieldCategory, string> = {
  vitals: "bg-blue-50",
  med:    "bg-green-50",
  instr:  "bg-amber-50",
  meta:   "bg-violet-50",
};

const CAT_LABEL_ACTIVE: Record<FieldCategory, string> = {
  vitals: "text-blue-600",
  med:    "text-green-600",
  instr:  "text-amber-600",
  meta:   "text-violet-600",
};

export default function FieldEditor({
  label, value, status, category, isActive, onActivate, onChange,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  // --- REMOVED ---
  if (status === "removed") {
    return (
      <div
        className="rounded-lg border border-slate-100 px-3 py-2.5 opacity-50 bg-white"
        style={{ borderLeft: "3px solid #cbd5e1" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{label}</span>
          <button onClick={() => onChange(value, "accepted")} className="text-[10px] text-blue-500 hover:underline">
            restore
          </button>
        </div>
        <p className="mt-1 text-sm text-slate-400 line-through">{value}</p>
      </div>
    );
  }

  // --- ACCEPTED ---
  if (status === "accepted") {
    return (
      <div
        className="rounded-lg border border-green-100 px-3 py-2.5 bg-green-50"
        style={{ borderLeft: "3px solid #22c55e" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-green-300">{label}</span>
          <span className="flex items-center gap-1 text-[10px] text-green-600">
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
              <circle cx="6" cy="6" r="5.5" stroke="#16a34a" strokeWidth="1" />
              <path d="M3.5 6l1.8 1.8 3-3.6" stroke="#16a34a" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            accepted
          </span>
        </div>
        <p className="mt-1 text-sm text-green-800">{value}</p>
      </div>
    );
  }

  // --- CORRECTED ---
  if (status === "corrected") {
    function save() {
      setEditing(false);
      onChange(draft, draft !== value ? "corrected" : "accepted");
    }
    return (
      <div
        className="rounded-lg border border-amber-100 px-3 py-2.5 bg-amber-50"
        style={{ borderLeft: "3px solid #f59e0b" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-amber-600">{label}</span>
          <span className="text-[10px] text-amber-600">corrected</span>
        </div>
        {editing ? (
          <div className="mt-1 flex gap-2">
            <input value={draft} onChange={(e) => setDraft(e.target.value)}
              className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400" />
            <button onClick={save} className="text-[10px] px-3 py-1 bg-amber-500 text-white rounded hover:bg-amber-600">save</button>
            <button onClick={() => { setEditing(false); setDraft(value); }} className="text-[10px] px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
          </div>
        ) : (
          <p className="mt-1 text-sm text-slate-700 cursor-pointer hover:opacity-80" onClick={() => setEditing(true)}
            data-testid="field-value">{draft}</p>
        )}
      </div>
    );
  }

  // --- PENDING (inactive or active) ---
  function save() {
    setEditing(false);
    onChange(draft, draft !== value ? "corrected" : "accepted");
  }

  return (
    <div
      className={`group rounded-lg border border-slate-200 px-3 py-2.5 transition-all duration-150 cursor-pointer
        ${isActive ? CAT_ACTIVE_BG[category] : "bg-white"}`}
      style={{ borderLeft: `3px solid ${CAT_BORDER[category][isActive ? "active" : "inactive"]}` }}
      onMouseEnter={onActivate}
    >
      <div className="flex items-center justify-between min-h-[20px]">
        <span className={`text-[10px] font-semibold uppercase tracking-widest
          ${isActive ? CAT_LABEL_ACTIVE[category] : "text-slate-400"}`}>
          {label}
        </span>
        {/* Action buttons: always shown when active; revealed on group-hover when inactive */}
        <div className={`flex gap-1 ${isActive ? "flex" : "hidden group-hover:flex"}`}>
          <button onClick={(e) => { e.stopPropagation(); onChange(value, "accepted"); }}
            className="text-[10px] px-2 py-0.5 bg-white text-green-600 border border-green-200 rounded hover:bg-green-50">
            ✓ Accept
          </button>
          <button onClick={(e) => { e.stopPropagation(); setEditing(true); }}
            className="text-[10px] px-2 py-0.5 bg-white text-slate-500 border border-slate-200 rounded hover:bg-slate-50">
            Edit
          </button>
          <button onClick={(e) => { e.stopPropagation(); onChange(value, "removed"); }}
            className="text-[10px] px-2 py-0.5 bg-white text-red-500 border border-red-100 rounded hover:bg-red-50">
            ✕
          </button>
        </div>
        {/* "click to review" hint — hidden when active or on hover */}
        {!isActive && (
          <span className="text-[10px] text-slate-300 group-hover:hidden">click to review</span>
        )}
      </div>
      {editing ? (
        <div className="mt-1 flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)}
            className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
          <button onClick={save} className="text-[10px] px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">save</button>
          <button onClick={() => { setEditing(false); setDraft(value); }} className="text-[10px] px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
        </div>
      ) : (
        <p className="mt-1 text-sm text-slate-700" data-testid="field-value">{draft}</p>
      )}
    </div>
  );
}
