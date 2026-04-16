// frontend/src/pages/Review.tsx
import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation, useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { ExtractionResult, NoteDetail } from "../types";
import NoteViewer from "../components/NoteViewer";
import FieldEditor, { FieldStatus, FieldCategory } from "../components/FieldEditor";
import { useQueue } from "../context/QueueContext";

type FieldState = { value: string; originalValue: string; status: FieldStatus };
type FieldMap = Record<string, FieldState>;

function getCategoryFromKey(key: string): FieldCategory {
  const prefix = key.split(".")[0];
  if (prefix === "vitals") return "vitals";
  if (prefix === "med") return "med";
  if (prefix === "instr") return "instr";
  return "meta";
}

const CATEGORY_DISPLAY: Record<FieldCategory, string> = {
  vitals: "Vitals", med: "Medications", instr: "Instructions", meta: "Metadata",
};

const CATEGORY_PREFIX: Record<FieldCategory, string> = {
  vitals: "vitals.", med: "med.", instr: "instr.", meta: "meta.",
};

const CATEGORIES: FieldCategory[] = ["vitals", "med", "instr", "meta"];

// Standard field names per category (for the add-field select dropdown)
const STD_FIELDS: Record<FieldCategory, string[]> = {
  vitals: ["respiratory_rate", "oxygen_saturation", "weight"],
  med:    [],  // medications use a multi-input form
  instr:  ["discharge_instructions", "follow_up", "return_precautions"],
  meta:   ["patient_name", "date_of_service", "provider_name"],
};

const CAT_DASHED_BORDER: Record<FieldCategory, string> = {
  vitals: "border-blue-200",
  med:    "border-green-200",
  instr:  "border-amber-200",
  meta:   "border-violet-200",
};

const CAT_LABEL_COLOR: Record<FieldCategory, string> = {
  vitals: "text-blue-400",
  med:    "text-green-400",
  instr:  "text-amber-400",
  meta:   "text-violet-400",
};

function AddFieldRow({
  category,
  existingKeys,
  onAdd,
}: {
  category: FieldCategory;
  existingKeys: string[];
  onAdd: (key: string, value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState("");
  const [value, setValue] = useState("");
  const [medName, setMedName] = useState("");
  const [medDose, setMedDose] = useState("");
  const [medRoute, setMedRoute] = useState("");
  const [medFreq, setMedFreq] = useState("");
  const customCount = useRef(0);

  const categoryKeyPrefix = category === "instr" ? "instr" : category === "meta" ? "meta" : category;
  const availableStdFields = STD_FIELDS[category].filter(
    (f) => !existingKeys.includes(`${categoryKeyPrefix}.${f}`)
  );

  function handleAdd() {
    if (category === "med") {
      if (!medName.trim()) return;
      const medIndices = existingKeys
        .filter((k) => k.startsWith("med.") && /^med\.\d+\.name$/.test(k))
        .map((k) => parseInt(k.split(".")[1]));
      const nextIdx = medIndices.length > 0 ? Math.max(...medIndices) + 1 : 0;
      onAdd(`med.${nextIdx}.name`, medName.trim());
      if (medDose.trim()) onAdd(`med.${nextIdx}.dose`, medDose.trim());
      if (medRoute.trim()) onAdd(`med.${nextIdx}.route`, medRoute.trim());
      if (medFreq.trim()) onAdd(`med.${nextIdx}.frequency`, medFreq.trim());
      setMedName(""); setMedDose(""); setMedRoute(""); setMedFreq("");
    } else {
      if (!value.trim()) return;
      const fieldName = selected === "custom" || !selected
        ? `custom_${++customCount.current}`
        : selected;
      onAdd(`${categoryKeyPrefix}.${fieldName}`, value.trim());
      setValue(""); setSelected("");
    }
    setOpen(false);
  }

  const addLabel = category === "med" ? "Add Medication" : `Add ${CATEGORY_DISPLAY[category].replace(/s$/, "")}`;

  return (
    <div className={`rounded-lg border-2 border-dashed ${CAT_DASHED_BORDER[category]} px-3 py-2.5`}>
      {!open ? (
        <button
          onClick={() => setOpen(true)}
          className={`text-[10px] font-semibold uppercase tracking-widest ${CAT_LABEL_COLOR[category]} hover:opacity-70 transition-opacity`}
        >
          + {addLabel}
        </button>
      ) : category === "med" ? (
        <div>
          <p className={`text-[10px] font-semibold uppercase tracking-widest mb-2 ${CAT_LABEL_COLOR[category]}`}>
            + Add Medication
          </p>
          <div className="grid grid-cols-4 gap-1.5 mb-2">
            {[
              { ph: "name *", val: medName, set: setMedName },
              { ph: "dose", val: medDose, set: setMedDose },
              { ph: "route", val: medRoute, set: setMedRoute },
              { ph: "frequency", val: medFreq, set: setMedFreq },
            ].map(({ ph, val, set }) => (
              <input key={ph} placeholder={ph} value={val} onChange={(e) => set(e.target.value)}
                className="text-[11px] px-2 py-1.5 border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-green-400" />
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd} className="text-[11px] px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 font-medium">Add</button>
            <button onClick={() => setOpen(false)} className="text-[11px] px-3 py-1 border border-slate-200 rounded hover:bg-slate-50">Cancel</button>
          </div>
        </div>
      ) : (
        <div>
          <p className={`text-[10px] font-semibold uppercase tracking-widest mb-2 ${CAT_LABEL_COLOR[category]}`}>
            + {addLabel}
          </p>
          <div className="flex gap-2 items-center">
            <select value={selected} onChange={(e) => setSelected(e.target.value)}
              className="text-[11px] px-2 py-1.5 border border-slate-200 rounded bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 flex-shrink-0">
              <option value="">field…</option>
              {availableStdFields.map((f) => <option key={f} value={f}>{f}</option>)}
              <option value="custom">custom…</option>
            </select>
            <input placeholder="value" value={value} onChange={(e) => setValue(e.target.value)}
              className="flex-1 text-[11px] px-2 py-1.5 border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-blue-400" />
            <button onClick={handleAdd}
              className="text-[11px] px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 font-medium whitespace-nowrap">
              Add
            </button>
            <button onClick={() => setOpen(false)} className="text-[11px] px-2 py-1.5 border border-slate-200 rounded hover:bg-slate-50">&#x2715;</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Flatten an ExtractionResult into FieldMap, using provided status/value overrides */
function flattenExtracted(
  extracted: ExtractionResult,
  overrides?: Record<string, { value: string; status: FieldStatus }>
): FieldMap {
  const m: FieldMap = {};
  Object.entries(extracted.vitals).forEach(([k, v]) => {
    if (v) {
      const key = `vitals.${k}`;
      m[key] = { value: v.value, originalValue: v.value, status: overrides?.[key]?.status ?? "pending" };
      if (overrides?.[key]) { m[key].value = overrides[key].value; }
    }
  });
  extracted.medications.forEach((med, i) => {
    const entries: [string, string][] = [
      [`med.${i}.name`, med.name],
      ...(med.dose ? [[`med.${i}.dose`, med.dose] as [string, string]] : []),
      ...(med.route ? [[`med.${i}.route`, med.route] as [string, string]] : []),
      ...(med.frequency ? [[`med.${i}.frequency`, med.frequency] as [string, string]] : []),
    ];
    entries.forEach(([key, val]) => {
      m[key] = { value: val, originalValue: val, status: overrides?.[key]?.status ?? "pending" };
      if (overrides?.[key]) { m[key].value = overrides[key].value; }
    });
  });
  Object.entries(extracted.instructions).forEach(([k, v]) => {
    if (v) {
      const key = `instr.${k}`;
      m[key] = { value: v.value, originalValue: v.value, status: overrides?.[key]?.status ?? "pending" };
      if (overrides?.[key]) { m[key].value = overrides[key].value; }
    }
  });
  Object.entries(extracted.metadata).forEach(([k, v]) => {
    if (v) {
      const key = `meta.${k}`;
      m[key] = { value: v.value, originalValue: v.value, status: overrides?.[key]?.status ?? "pending" };
      if (overrides?.[key]) { m[key].value = overrides[key].value; }
    }
  });
  return m;
}

export default function Review() {
  const location = useLocation();
  const { noteId } = useParams();
  const navigate = useNavigate();
  const startTime = useRef(Date.now());
  const { bumpQueue } = useQueue();

  const [rawText, setRawText] = useState("");
  const [extracted, setExtracted] = useState<ExtractionResult | null>(null);
  const [noteIdState, setNoteIdState] = useState<number | null>(null);
  const [source, setSource] = useState("");
  const [fields, setFields] = useState<FieldMap>({});
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveFlash, setSaveFlash] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [reReviewBanner, setReReviewBanner] = useState(false);

  const deactivateTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Timer
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startTime.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  // Cleanup deactivate timeout on unmount
  useEffect(() => () => {
    if (deactivateTimeout.current) clearTimeout(deactivateTimeout.current);
  }, []);

  // Load data from nav state or API
  useEffect(() => {
    const state = location.state as {
      note_id?: number; extracted_json?: ExtractionResult; raw_text?: string; source?: string;
    } | null;
    if (state?.extracted_json) {
      setRawText(state.raw_text ?? "");
      setExtracted(state.extracted_json);
      setNoteIdState(state.note_id ?? null);
      setSource(state.source ?? "");
    } else if (noteId) {
      api.getNoteDetail(Number(noteId)).then((d: NoteDetail) => {
        setRawText(d.raw_text);
        setExtracted(d.extracted_json);
        setNoteIdState(d.id);
        setSource(d.source ?? "");

        // G: Re-review awareness
        if (d.validation && d.extracted_json) {
          setReReviewBanner(true);
          // Offset timer by previous review duration
          if (d.validation.review_duration_ms) {
            startTime.current = Date.now() - d.validation.review_duration_ms;
          }
          // Reconstruct per-field statuses
          const ext = d.extracted_json;
          const val = d.validation.validated_json;
          const overrides: Record<string, { value: string; status: FieldStatus }> = {};

          // Build a flat map of validated fields
          const valFlat: Record<string, string> = {};
          Object.entries(val.vitals ?? {}).forEach(([k, v]) => { if (v) valFlat[`vitals.${k}`] = (v as { value: string }).value; });
          (val.medications ?? []).forEach((med: { name: string; dose?: string; route?: string; frequency?: string }, i: number) => {
            valFlat[`med.${i}.name`] = med.name;
            if (med.dose) valFlat[`med.${i}.dose`] = med.dose;
            if (med.route) valFlat[`med.${i}.route`] = med.route;
            if (med.frequency) valFlat[`med.${i}.frequency`] = med.frequency;
          });
          Object.entries(val.instructions ?? {}).forEach(([k, v]) => { if (v) valFlat[`instr.${k}`] = (v as { value: string }).value; });
          Object.entries(val.metadata ?? {}).forEach(([k, v]) => { if (v) valFlat[`meta.${k}`] = (v as { value: string }).value; });

          // Build flat map of extracted fields
          const extFlat: Record<string, string> = {};
          Object.entries(ext.vitals ?? {}).forEach(([k, v]) => { if (v) extFlat[`vitals.${k}`] = (v as { value: string }).value; });
          (ext.medications ?? []).forEach((med: { name: string; dose?: string; route?: string; frequency?: string }, i: number) => {
            extFlat[`med.${i}.name`] = med.name;
            if (med.dose) extFlat[`med.${i}.dose`] = med.dose;
            if (med.route) extFlat[`med.${i}.route`] = med.route;
            if (med.frequency) extFlat[`med.${i}.frequency`] = med.frequency;
          });
          Object.entries(ext.instructions ?? {}).forEach(([k, v]) => { if (v) extFlat[`instr.${k}`] = (v as { value: string }).value; });
          Object.entries(ext.metadata ?? {}).forEach(([k, v]) => { if (v) extFlat[`meta.${k}`] = (v as { value: string }).value; });

          // Diff extracted vs validated
          Object.keys(extFlat).forEach((key) => {
            if (!(key in valFlat)) {
              // In extracted but not in validated → removed
              overrides[key] = { value: extFlat[key], status: "removed" };
            } else if (extFlat[key] === valFlat[key]) {
              // Same value → accepted
              overrides[key] = { value: valFlat[key], status: "accepted" };
            } else {
              // Different value → corrected
              overrides[key] = { value: valFlat[key], status: "corrected" };
            }
          });
          // In validated but not in extracted → reviewer-added (corrected)
          Object.keys(valFlat).forEach((key) => {
            if (!(key in extFlat)) {
              overrides[key] = { value: valFlat[key], status: "corrected" };
            }
          });

          // We'll apply overrides after extracted is set via the normal useEffect,
          // but we need to set the map directly here since we have all the data.
          const m = flattenExtracted(ext, overrides);
          // For corrected fields, preserve originalValue from extFlat
          Object.keys(m).forEach((key) => {
            if (m[key].status === "corrected" && extFlat[key]) {
              m[key].originalValue = extFlat[key];
            }
            // Reviewer-added fields: originalValue = "" (no original)
            if (m[key].status === "corrected" && !extFlat[key]) {
              m[key].originalValue = "";
            }
          });
          setFields(m);
          // Clear extracted so the normal flatten useEffect doesn't overwrite
          setExtracted(null);
          // Re-set extracted for NoteViewer (keep it for rendering)
          setExtracted(ext);
        }
      });
    }
  }, [noteId, location.state]); // eslint-disable-line react-hooks/exhaustive-deps

  // Flatten extracted JSON into FieldMap (only for fresh loads without validation)
  useEffect(() => {
    if (!extracted || reReviewBanner) return;
    const m = flattenExtracted(extracted);
    setFields(m);
  }, [extracted, reReviewBanner]);

  // Scroll active card into view when activeKey changes
  useEffect(() => {
    if (activeKey && cardRefs.current[activeKey]) {
      cardRefs.current[activeKey]!.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [activeKey]);

  // Activate a field (from span click or card hover)
  const handleActivate = useCallback((key: string) => {
    if (deactivateTimeout.current) clearTimeout(deactivateTimeout.current);
    setActiveKey(key);
  }, []);

  // Deactivate after 200ms debounce (prevents flicker when moving cursor to a button)
  const handleDeactivate = useCallback(() => {
    deactivateTimeout.current = setTimeout(() => setActiveKey(null), 200);
  }, []);

  const handleFieldChange = useCallback((key: string, value: string, status: FieldStatus) => {
    setFields((prev) => ({
      ...prev,
      [key]: { ...prev[key], value, status },
    }));
  }, []);

  function handleAddField(key: string, value: string) {
    setFields((prev) => ({ ...prev, [key]: { value, originalValue: "", status: "corrected" } }));
  }

  const handleSave = useCallback(async (overallStatus: "accepted" | "corrected") => {
    if (!noteIdState || !extracted) return;
    setSaving(true); setError(null);
    try {
      const validated = JSON.parse(JSON.stringify(extracted));
      const removedMedIndices = new Set<number>();
      Object.entries(fields).forEach(([key, { status }]) => {
        if (key.startsWith("med.") && status === "removed") {
          removedMedIndices.add(parseInt(key.split(".")[1]));
        }
      });
      Object.entries(fields).forEach(([key, { value, status }]) => {
        const [section, ...rest] = key.split(".");
        if (status === "removed") {
          if (section === "vitals") delete validated.vitals[rest[0]];
          else if (section === "instr") delete validated.instructions[rest[0]];
          else if (section === "meta") delete validated.metadata[rest[0]];
        } else {
          if (section === "vitals" && validated.vitals[rest[0]]) {
            validated.vitals[rest[0]].value = value;
          } else if (section === "instr" && validated.instructions[rest[0]]) {
            validated.instructions[rest[0]].value = value;
          } else if (section === "meta" && validated.metadata[rest[0]]) {
            validated.metadata[rest[0]].value = value;
          } else if (section === "med") {
            const idx = parseInt(rest[0]);
            const field = rest[1] as string;
            if (!removedMedIndices.has(idx) && validated.medications[idx]) {
              (validated.medications[idx] as Record<string, string>)[field] = value;
            }
          }
        }
      });
      validated.medications = validated.medications.filter(
        (_: unknown, i: number) => !removedMedIndices.has(i)
      );
      const result = await api.validate({
        note_id: noteIdState,
        validated_json: validated,
        status: overallStatus,
        review_duration_ms: Date.now() - startTime.current,
      });
      setSaved(true);
      bumpQueue();

      // F: Save & Next
      if (result.next_pending_id !== null) {
        setSaveFlash("Saved — loading next note…");
        setTimeout(() => {
          navigate(`/review/${result.next_pending_id}`);
        }, 800);
      } else {
        setSaveFlash(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [noteIdState, extracted, fields, bumpQueue, navigate]);

  // E: Keyboard shortcuts
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      // Disable when an input/textarea/select is focused
      const tag = (document.activeElement as HTMLElement)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;

      if (e.key === "a" || e.key === "A") {
        if (activeKey && fields[activeKey]?.status === "pending") {
          handleFieldChange(activeKey, fields[activeKey].value, "accepted");
        }
      }
      if (e.key === "e" || e.key === "E") {
        if (activeKey) {
          setEditingKey(activeKey);
        }
      }
      if (e.key === "r" || e.key === "R") {
        if (activeKey && fields[activeKey]) {
          handleFieldChange(activeKey, fields[activeKey].value, "removed");
        }
      }
      if (e.key === "Escape") {
        setActiveKey(null);
      }
      if (e.key === "Tab") {
        e.preventDefault();
        const keys = Object.keys(fields);
        if (keys.length === 0) return;
        if (!activeKey) {
          handleActivate(keys[0]);
        } else {
          const idx = keys.indexOf(activeKey);
          const next = e.shiftKey ? keys[idx - 1] : keys[idx + 1];
          if (next) handleActivate(next);
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        handleSave(hasCorrected ? "corrected" : "accepted");
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [activeKey, fields, handleFieldChange, handleActivate, handleSave]); // hasCorrected is derived below

  // H: Unsaved changes warning
  useEffect(() => {
    const isDirty = Object.values(fields).some((f) => f.status !== "pending") && !saved;
    function handler(e: BeforeUnloadEvent) {
      if (isDirty) { e.preventDefault(); e.returnValue = ""; }
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [fields, saved]);

  if (!extracted) {
    return (
      <div className="h-full bg-slate-50 flex items-center justify-center text-slate-400 text-sm">
        Loading...
      </div>
    );
  }

  const hasCorrected = Object.values(fields).some((f) => f.status === "corrected" || f.status === "removed");
  const correctedCount = Object.values(fields).filter((f) => f.status === "corrected" || f.status === "removed").length;
  const acceptedCount = Object.values(fields).filter((f) => f.status === "accepted").length;
  const pendingCount = Object.values(fields).filter((f) => f.status === "pending").length;

  // D: Progress bar
  const totalFields = Object.keys(fields).length;
  const reviewedCount = totalFields - pendingCount; // accepted + corrected + removed
  const progressPct = totalFields > 0 ? Math.round((reviewedCount / totalFields) * 100) : 0;

  return (
    <div className="h-full bg-slate-50 flex flex-col overflow-hidden">
      {/* Review top bar */}
      <header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <span className="font-semibold text-sm tracking-wide">Reviewer</span>
        </div>
        {/* D: Progress indicator */}
        <div className="flex items-center gap-3 flex-1 mx-6">
          <span className="text-slate-400 text-[11px] whitespace-nowrap">
            {reviewedCount} of {totalFields} fields reviewed
          </span>
          <div className="flex-1 h-1 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-slate-400 rounded-full transition-all duration-300"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="text-slate-500">&#x23F1; {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}</span>
          {source && (
            <span className={`px-2 py-0.5 rounded border text-[10px] uppercase tracking-wider font-medium
              ${source === "ocr"
                ? "bg-slate-900 text-sky-400 border-cyan-800"
                : source === "pdf"
                  ? "bg-blue-950 text-blue-400 border-blue-800"
                  : "bg-slate-700 text-slate-400 border-slate-600"}`}>
              {source}
            </span>
          )}
          <span className="text-slate-600 text-[10px]">v{extracted.pipeline_version}</span>
        </div>
      </header>

      {/* E: Keyboard shortcut hint strip */}
      <div className="hidden md:flex bg-slate-900 text-slate-500 text-[10px] px-6 py-1 gap-4 flex-shrink-0 select-none">
        <span><kbd className="font-mono text-slate-400">A</kbd> Accept</span>
        <span className="text-slate-700">·</span>
        <span><kbd className="font-mono text-slate-400">E</kbd> Edit</span>
        <span className="text-slate-700">·</span>
        <span><kbd className="font-mono text-slate-400">R</kbd> Remove</span>
        <span className="text-slate-700">·</span>
        <span><kbd className="font-mono text-slate-400">Tab</kbd> Next</span>
        <span className="text-slate-700">·</span>
        <span><kbd className="font-mono text-slate-400">⌘S</kbd> Save</span>
      </div>

      {/* G: Re-review banner */}
      {reReviewBanner && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 text-amber-700 text-[11px] flex items-center gap-2 flex-shrink-0">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="7" stroke="#d97706" strokeWidth="1.2" />
            <path d="M8 5v4M8 11v.5" stroke="#d97706" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          Previously reviewed — you can re-review and save again.
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Left: NoteViewer */}
        <div className="w-1/2 border-r border-slate-200 flex flex-col overflow-hidden bg-white">
          {/* Legend */}
          <div className="px-4 py-1.5 border-b border-slate-100 bg-slate-50 flex gap-4 flex-shrink-0">
            {[
              { label: "vitals", color: "bg-blue-400" },
              { label: "meds", color: "bg-green-400" },
              { label: "instructions", color: "bg-amber-400" },
              { label: "metadata", color: "bg-violet-400" },
            ].map(({ label, color }) => (
              <span key={label} className="flex items-center gap-1.5 text-[10px] text-slate-500">
                <span className={`w-2 h-2 rounded-sm ${color} opacity-70`} />
                {label}
              </span>
            ))}
          </div>
          <NoteViewer
            rawText={rawText}
            extracted={extracted}
            activeKey={activeKey}
            onSpanClick={handleActivate}
          />
        </div>

        {/* Right: Field cards */}
        <div className="w-1/2 flex flex-col overflow-hidden bg-slate-50">
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
            {CATEGORIES.map((cat) => {
              const prefix = CATEGORY_PREFIX[cat];
              const catFields = Object.entries(fields).filter(([k]) => k.startsWith(prefix));
              return (
                <section key={cat}>
                  <h3 className="text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 mb-2 px-1">
                    {CATEGORY_DISPLAY[cat]}
                  </h3>
                  <div className="space-y-1.5">
                    {catFields.map(([k, f]) => (
                      <div
                        key={k}
                        ref={(el) => { cardRefs.current[k] = el; }}
                        onMouseEnter={() => handleActivate(k)}
                        onMouseLeave={handleDeactivate}
                      >
                        <FieldEditor
                          label={k.replace(prefix, "").replace(/^\d+\./, "")}
                          value={f.value}
                          originalValue={f.originalValue}
                          status={f.status}
                          category={getCategoryFromKey(k)}
                          isActive={activeKey === k}
                          onActivate={() => handleActivate(k)}
                          onChange={(v, s) => handleFieldChange(k, v, s)}
                          triggerEdit={editingKey === k}
                          onEditTriggered={() => setEditingKey(null)}
                        />
                      </div>
                    ))}
                    <AddFieldRow
                      category={cat}
                      existingKeys={Object.keys(fields)}
                      onAdd={handleAddField}
                    />
                  </div>
                </section>
              );
            })}
          </div>

          {/* Footer */}
          <div className="border-t border-slate-200 px-4 py-2.5 bg-white flex items-center justify-between flex-shrink-0">
            <div className="flex items-center gap-1.5 text-[11px] bg-slate-50 border border-slate-100 rounded-md px-3 py-1">
              <span className="text-amber-600 font-medium">{correctedCount} corrected</span>
              <span className="text-slate-300">|</span>
              <span className="text-green-600 font-medium">{acceptedCount} accepted</span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-400">{pendingCount} pending</span>
            </div>
            <div className="flex items-center gap-2">
              {error && <p className="text-red-500 text-xs mr-2">{error}</p>}
              {saveFlash && <p className="text-blue-500 text-xs mr-2">{saveFlash}</p>}
              {/* F: All notes reviewed state */}
              {saved && !saveFlash ? (
                <div className="flex items-center gap-3">
                  <p className="text-green-600 text-xs">All notes reviewed!</p>
                  <a href="/history" className="text-xs text-blue-600 hover:underline">History</a>
                  <a href="/metrics" className="text-xs text-blue-600 hover:underline">Metrics</a>
                </div>
              ) : (
                <>
                  <button
                    onClick={() => handleSave("accepted")}
                    disabled={saving || saved}
                    className="px-4 py-1.5 border border-green-200 text-green-700 bg-green-50 rounded-md text-sm font-medium hover:bg-green-100 disabled:opacity-50"
                  >
                    Accept all
                  </button>
                  <button
                    onClick={() => handleSave("corrected")}
                    disabled={saving || !hasCorrected || saved}
                    className="px-4 py-1.5 bg-blue-600 text-white rounded-md text-sm font-semibold hover:bg-blue-700 disabled:opacity-50"
                  >
                    {saving ? "Saving..." : "Save corrections"}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
