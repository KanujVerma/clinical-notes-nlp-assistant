// frontend/src/components/FieldEditor.tsx
import { useState } from "react";

export type FieldStatus = "accepted" | "corrected" | "removed" | "pending";

interface Props {
  label: string;
  value: string;
  status: FieldStatus;
  onChange: (value: string, status: FieldStatus) => void;
}

export default function FieldEditor({ label, value, status, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  const statusColors: Record<FieldStatus, string> = {
    accepted: "border-green-300 bg-green-50",
    corrected: "border-amber-300 bg-amber-50",
    removed: "border-red-200 bg-red-50 opacity-60",
    pending: "border-slate-200 bg-white",
  };

  function save() {
    setEditing(false);
    onChange(draft, draft !== value ? "corrected" : "accepted");
  }

  if (status === "removed") {
    return (
      <div className={`rounded border p-2 text-sm ${statusColors.removed}`}>
        <span className="font-medium text-slate-500 text-xs uppercase tracking-wide">{label}</span>
        <span className="ml-2 text-slate-400 line-through">{value}</span>
        <button onClick={() => onChange(value, "accepted")} className="ml-2 text-xs text-blue-500 hover:underline">restore</button>
      </div>
    );
  }

  return (
    <div className={`rounded border p-2 text-sm ${statusColors[status]}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-slate-500 text-xs uppercase tracking-wide">{label}</span>
        <div className="flex gap-1">
          {status !== "accepted" && (
            <button onClick={() => onChange(value, "accepted")}
              className="text-xs px-2 py-0.5 rounded bg-green-100 text-green-700 hover:bg-green-200">✓</button>
          )}
          <button onClick={() => setEditing(true)}
            className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 hover:bg-slate-200">edit</button>
          <button onClick={() => onChange(value, "removed")}
            className="text-xs px-2 py-0.5 rounded bg-red-100 text-red-600 hover:bg-red-200">✕</button>
        </div>
      </div>
      {editing ? (
        <div className="mt-1 flex gap-2">
          <input value={draft} onChange={(e) => setDraft(e.target.value)}
            className="flex-1 border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400" />
          <button onClick={save} className="text-xs px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700">save</button>
          <button onClick={() => { setEditing(false); setDraft(value); }}
            className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50">cancel</button>
        </div>
      ) : (
        <p className="mt-1 text-slate-700">{draft}</p>
      )}
    </div>
  );
}
