// frontend/src/pages/Review.tsx
import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ExtractionResult } from "../types";
import NoteViewer from "../components/NoteViewer";
import FieldEditor, { FieldStatus, FieldCategory } from "../components/FieldEditor";

type FieldState = { value: string; status: FieldStatus };
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

export default function Review() {
  const location = useLocation();
  const { noteId } = useParams();
  const startTime = useRef(Date.now());

  const [rawText, setRawText] = useState("");
  const [extracted, setExtracted] = useState<ExtractionResult | null>(null);
  const [noteIdState, setNoteIdState] = useState<number | null>(null);
  const [source, setSource] = useState("");
  const [fields, setFields] = useState<FieldMap>({});
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

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
      api.getNoteDetail(Number(noteId)).then((d) => {
        setRawText(d.raw_text);
        setExtracted(d.extracted_json);
        setNoteIdState(d.id);
        setSource(d.source ?? "");
      });
    }
  }, [noteId, location.state]);

  // Flatten extracted JSON into FieldMap
  useEffect(() => {
    if (!extracted) return;
    const m: FieldMap = {};
    Object.entries(extracted.vitals).forEach(([k, v]) => {
      if (v) m[`vitals.${k}`] = { value: v.value, status: "pending" };
    });
    extracted.medications.forEach((med, i) => {
      m[`med.${i}.name`] = { value: med.name, status: "pending" };
      if (med.dose) m[`med.${i}.dose`] = { value: med.dose, status: "pending" };
      if (med.route) m[`med.${i}.route`] = { value: med.route, status: "pending" };
      if (med.frequency) m[`med.${i}.frequency`] = { value: med.frequency, status: "pending" };
    });
    Object.entries(extracted.instructions).forEach(([k, v]) => {
      if (v) m[`instr.${k}`] = { value: v.value, status: "pending" };
    });
    Object.entries(extracted.metadata).forEach(([k, v]) => {
      if (v) m[`meta.${k}`] = { value: v.value, status: "pending" };
    });
    setFields(m);
  }, [extracted]);

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

  function handleFieldChange(key: string, value: string, status: FieldStatus) {
    setFields((prev) => ({ ...prev, [key]: { value, status } }));
  }

  function handleAddField(key: string, value: string) {
    setFields((prev) => ({ ...prev, [key]: { value, status: "corrected" } }));
  }

  async function handleSave(overallStatus: "accepted" | "corrected") {
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
      await api.validate({
        note_id: noteIdState,
        validated_json: validated,
        status: overallStatus,
        review_duration_ms: Date.now() - startTime.current,
      });
      setSaved(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

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

  return (
    <div className="h-full bg-slate-50 flex flex-col overflow-hidden">
      {/* Review top bar */}
      <header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <span className="font-semibold text-sm tracking-wide">Reviewer</span>
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
                          status={f.status}
                          category={getCategoryFromKey(k)}
                          isActive={activeKey === k}
                          onActivate={() => handleActivate(k)}
                          onChange={(v, s) => handleFieldChange(k, v, s)}
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
              {saved && <p className="text-green-600 text-xs mr-2">Saved &#x2713;</p>}
              <button
                onClick={() => handleSave("accepted")}
                disabled={saving}
                className="px-4 py-1.5 border border-green-200 text-green-700 bg-green-50 rounded-md text-sm font-medium hover:bg-green-100 disabled:opacity-50"
              >
                Accept all
              </button>
              <button
                onClick={() => handleSave("corrected")}
                disabled={saving || !hasCorrected}
                className="px-4 py-1.5 bg-blue-600 text-white rounded-md text-sm font-semibold hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save corrections"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
