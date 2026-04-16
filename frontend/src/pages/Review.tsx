// frontend/src/pages/Review.tsx
import { useState, useEffect, useRef } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api } from "../api/client";
import { ExtractionResult } from "../types";
import NoteViewer from "../components/NoteViewer";
import FieldEditor, { FieldStatus } from "../components/FieldEditor";

type FieldState = { value: string; status: FieldStatus };
type FieldMap = Record<string, FieldState>;

export default function Review() {
  const location = useLocation();
  const { noteId } = useParams();
  const startTime = useRef(Date.now());

  const [rawText, setRawText] = useState<string>("");
  const [extracted, setExtracted] = useState<ExtractionResult | null>(null);
  const [noteIdState, setNoteIdState] = useState<number | null>(null);
  const [fields, setFields] = useState<FieldMap>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);

  // Elapsed timer
  useEffect(() => {
    const interval = setInterval(() => setElapsed(Math.floor((Date.now() - startTime.current) / 1000)), 1000);
    return () => clearInterval(interval);
  }, []);

  // Load data from navigation state or fetch
  useEffect(() => {
    const state = location.state as { note_id?: number; extracted_json?: ExtractionResult; raw_text?: string } | null;
    if (state?.extracted_json) {
      setRawText(state.raw_text ?? "");
      setExtracted(state.extracted_json);
      setNoteIdState(state.note_id ?? null);
    } else if (noteId) {
      api.getNoteDetail(Number(noteId)).then((d) => {
        setRawText(d.raw_text);
        setExtracted(d.extracted_json);
        setNoteIdState(d.id);
      });
    }
  }, [noteId, location.state]);

  // Flatten extracted JSON into editable fields
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

  function handleFieldChange(key: string, value: string, status: FieldStatus) {
    setFields((prev) => ({ ...prev, [key]: { value, status } }));
  }

  async function handleSave(overallStatus: "accepted" | "corrected") {
    if (!noteIdState || !extracted) return;
    setSaving(true); setError(null);
    try {
      const validated = JSON.parse(JSON.stringify(extracted));
      // Collect removed medication indices first
      const removedMedIndices = new Set<number>();
      Object.entries(fields).forEach(([key, { status }]) => {
        const parts = key.split(".");
        if (parts[0] === "med" && status === "removed") {
          removedMedIndices.add(parseInt(parts[1]));
        }
      });

      // Apply field edits
      Object.entries(fields).forEach(([key, { value, status }]) => {
        const [section, ...rest] = key.split(".");
        if (status === "removed") {
          if (section === "vitals") delete validated.vitals[rest[0]];
          else if (section === "instr") delete validated.instructions[rest[0]];
          else if (section === "meta") delete validated.metadata[rest[0]];
          // med removals handled by filter below
        } else {
          if (section === "vitals" && validated.vitals[rest[0]]) {
            validated.vitals[rest[0]].value = value;
          } else if (section === "instr" && validated.instructions[rest[0]]) {
            validated.instructions[rest[0]].value = value;
          } else if (section === "meta" && validated.metadata[rest[0]]) {
            validated.metadata[rest[0]].value = value;
          } else if (section === "med") {
            const idx = parseInt(rest[0]);
            const field = rest[1];
            if (!removedMedIndices.has(idx) && validated.medications[idx]) {
              (validated.medications[idx] as any)[field] = value;
            }
          }
        }
      });

      // Remove medications marked for deletion
      validated.medications = validated.medications.filter(
        (_: any, i: number) => !removedMedIndices.has(i)
      );

      await api.validate({
        note_id: noteIdState,
        validated_json: validated,
        status: overallStatus,
        review_duration_ms: Date.now() - startTime.current,
      });
      setSaved(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!extracted) return <div className="p-8 text-slate-400">Loading...</div>;

  const hasCorrected = Object.values(fields).some((f) => f.status === "corrected" || f.status === "removed");

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <a href="/" className="text-slate-400 hover:text-slate-600 text-sm">← Back</a>
          <h1 className="text-lg font-semibold text-slate-800">Reviewer</h1>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-400">Time: {Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,"0")}</span>
          <span className="text-slate-400 text-xs">pipeline v{extracted.pipeline_version}</span>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden" style={{ height: "calc(100vh - 57px)" }}>
        {/* Left: note viewer */}
        <div className="w-1/2 border-r border-slate-200 overflow-hidden flex flex-col">
          <div className="px-4 py-2 border-b border-slate-100 flex gap-3 text-xs">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-blue-100 inline-block"/>vitals</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-100 inline-block"/>medications</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-amber-100 inline-block"/>instructions</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-purple-100 inline-block"/>metadata</span>
          </div>
          <NoteViewer rawText={rawText} extracted={extracted} />
        </div>

        {/* Right: editable fields */}
        <div className="w-1/2 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Vitals */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Vitals</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("vitals.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace("vitals.", "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
            {/* Medications */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Medications</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("med.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace(/^med\.\d+\./, "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
            {/* Instructions */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Instructions</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("instr.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace("instr.", "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
            {/* Metadata */}
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Metadata</h3>
              <div className="space-y-2">
                {Object.entries(fields).filter(([k]) => k.startsWith("meta.")).map(([k, f]) => (
                  <FieldEditor key={k} label={k.replace("meta.", "")}
                    value={f.value} status={f.status}
                    onChange={(v, s) => handleFieldChange(k, v, s)} />
                ))}
              </div>
            </section>
          </div>

          {/* Footer actions */}
          <div className="border-t border-slate-200 p-4 flex items-center justify-between bg-white">
            {error && <p className="text-red-500 text-sm">{error}</p>}
            {saved && <p className="text-green-600 text-sm">Saved ✓</p>}
            <div className="flex gap-2 ml-auto">
              <button onClick={() => handleSave("accepted")} disabled={saving}
                className="px-4 py-2 border border-green-300 text-green-700 rounded text-sm hover:bg-green-50 disabled:opacity-50">
                Accept all
              </button>
              <button onClick={() => handleSave("corrected")} disabled={saving || !hasCorrected}
                className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                {saving ? "Saving..." : "Save corrections"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
