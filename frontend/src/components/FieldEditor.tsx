// frontend/src/components/FieldEditor.tsx
import { useState, useEffect } from "react";
import ExplainerTrigger from "./ExplainerTrigger";

export type FieldStatus = "accepted" | "corrected" | "removed" | "pending";
export type FieldCategory = "vitals" | "med" | "instr" | "meta";

interface Props {
  label: string;
  value: string;          // current value (may have been corrected)
  originalValue?: string; // the original extracted value (for diff display)
  status: FieldStatus;
  category: FieldCategory;
  isActive: boolean;
  onActivate: () => void;
  onChange: (value: string, status: FieldStatus) => void;
  allowEdit?: boolean; // Hosted curated sandbox is accept/remove only
  triggerEdit?: boolean;  // when true, auto-open edit mode
  onEditTriggered?: () => void; // called after edit mode opens
  explainerKind?: 'medication' | 'abbreviation';
}

export default function FieldEditor({
  label, value, originalValue, status, isActive, onActivate, onChange,
  allowEdit = true, triggerEdit, onEditTriggered, explainerKind,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  // Handle external edit trigger (E key shortcut)
  useEffect(() => {
    if (allowEdit && triggerEdit && !editing) {
      setEditing(true);
      onEditTriggered?.();
    }
  }, [triggerEdit]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- REMOVED ---
  if (status === "removed") {
    return (
      <div
        className="rounded-lg border border-slate-100 px-3 py-2.5 opacity-50 bg-white"
        style={{ borderLeft: "3px solid #cbd5e1" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-medium text-slate-800">{label}</span>
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
          <span className="text-[13px] font-medium text-slate-800">{label}</span>
          <span className="flex items-center gap-2 text-[10px] text-green-600">
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
              <circle cx="6" cy="6" r="5.5" stroke="#16a34a" strokeWidth="1" />
              <path d="M3.5 6l1.8 1.8 3-3.6" stroke="#16a34a" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Accepted
            {/* Undo button */}
            <button
              onClick={() => onChange(value, "pending")}
              className="text-[10px] text-slate-400 hover:text-slate-600 hover:underline"
            >
              undo
            </button>
          </span>
        </div>
        <p className="mt-1 text-sm text-green-800">{value}</p>
      </div>
    );
  }

  // --- CORRECTED ---
  if (status === "corrected") {
    function saveCorrected() {
      setEditing(false);
      onChange(draft, draft !== value ? "corrected" : "accepted");
    }
    const showDiff = originalValue && originalValue !== value;
    return (
      <div
        className="rounded-lg border border-amber-100 px-3 py-2.5 bg-amber-50"
        style={{ borderLeft: "3px solid #f59e0b" }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-medium text-slate-800">{label}</span>
          <span className="text-[10px] text-amber-600">Edited</span>
        </div>
        {/* Diff view: original → corrected */}
        {showDiff && !editing && (
          <div className="mt-1 flex items-center gap-2 text-sm">
            <span className="text-slate-400 line-through">{originalValue}</span>
            <span className="text-slate-400">→</span>
            <span className="text-amber-700 font-medium">{draft || value}</span>
          </div>
        )}
        {/* Diff view inline above input when editing */}
        {showDiff && editing && (
          <div className="mt-1 flex items-center gap-2 text-sm mb-1">
            <span className="text-slate-400 line-through">{originalValue}</span>
            <span className="text-slate-400">→</span>
            <span className="text-amber-700 font-medium">{draft || value}</span>
          </div>
        )}
        {editing ? (
          <div className="mt-1 flex gap-2">
            <input value={draft} onChange={(e) => setDraft(e.target.value)}
              className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400" />
            <button onClick={saveCorrected} className="text-[10px] px-3 py-1 bg-amber-500 text-white rounded hover:bg-amber-600">save</button>
            <button onClick={() => { setEditing(false); setDraft(value); }} className="text-[10px] px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
          </div>
        ) : (
          !showDiff && (
            <>
              <p className="mt-1 text-sm text-slate-700" onClick={() => { if (allowEdit) setEditing(true); }}
                data-testid="field-value">{draft}</p>
              {explainerKind && <ExplainerTrigger value={draft} kind={explainerKind} />}
            </>
          )
        )}
        {/* Click-to-edit when showing diff — value is displayed in the diff row above */}
        {showDiff && !editing && allowEdit && (
          <p className="mt-0.5 text-[10px] text-slate-400 cursor-pointer hover:text-slate-600" onClick={() => setEditing(true)}>
            click to re-edit
          </p>
        )}
      </div>
    );
  }

  // --- PENDING (inactive or active) ---
  function savePending() {
    setEditing(false);
    onChange(draft, draft !== value ? "corrected" : "accepted");
  }

  return (
    <div
      className={`group rounded-lg border border-slate-200 px-3 py-2.5 transition-all duration-150 cursor-pointer
        ${isActive ? "bg-slate-50" : "bg-white"}`}
      style={{ borderLeft: `3px solid ${isActive ? "#0E7490" : "#E2E8F0"}` }}
      onMouseEnter={onActivate}
    >
      <div className="flex items-center justify-between min-h-[20px]">
        <span className="text-[13px] font-medium text-slate-800">
          {label}
        </span>
        {/* Action buttons: always shown when active; revealed on group-hover when inactive */}
        <div className="flex gap-1">
          <button onClick={(e) => { e.stopPropagation(); onChange(value, "accepted"); }}
            className="text-[10px] px-2 py-0.5 bg-white text-green-600 border border-green-200 rounded hover:bg-green-50">
            ✓ Accept
          </button>
          {allowEdit && (
            <button onClick={(e) => { e.stopPropagation(); setEditing(true); }}
              className="text-[10px] px-2 py-0.5 bg-white text-slate-500 border border-slate-200 rounded hover:bg-slate-50">
              Edit
            </button>
          )}
          <button onClick={(e) => { e.stopPropagation(); onChange(value, "removed"); }}
            className="text-[10px] px-2 py-0.5 bg-white text-red-500 border border-red-100 rounded hover:bg-red-50">
            ✕
          </button>
        </div>
        {/* "click to review" hint — hidden when active or on hover */}
        {!isActive && status === "pending" && (
          <span className="text-xs text-slate-500">Not checked</span>
        )}
      </div>
      {editing ? (
        <div className="mt-1 flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)}
            className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
          <button onClick={savePending} className="text-[10px] px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">save</button>
          <button onClick={() => { setEditing(false); setDraft(value); }} className="text-[10px] px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
        </div>
      ) : (
        <>
          <p className="mt-1 text-sm text-slate-700" data-testid="field-value">{draft}</p>
          {explainerKind && <ExplainerTrigger value={draft} kind={explainerKind} />}
        </>
      )}
    </div>
  );
}
