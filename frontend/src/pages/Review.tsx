// frontend/src/pages/Review.tsx
import { useState, useEffect, useRef, useCallback } from "react";
import { useLocation, useParams, useNavigate, useBlocker } from "react-router-dom";
import { api } from "../api/client";
import { ExtractionResult, NoteDetail } from "../types";
import NoteViewer from "../components/NoteViewer";
import DocumentSourceViewer, { PageMetadata } from "../components/DocumentSourceViewer";
import FieldEditor, { FieldStatus, FieldCategory } from "../components/FieldEditor";
import TranscriptionEditModal from "../components/TranscriptionEditModal";
import OperationalIssuesDrawer from "../components/OperationalIssuesDrawer";
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
      const addMedId = `med_add_${crypto.randomUUID()}`;
      onAdd(`med.${addMedId}.name`, medName.trim());
      if (medDose.trim()) onAdd(`med.${addMedId}.dose`, medDose.trim());
      if (medRoute.trim()) onAdd(`med.${addMedId}.route`, medRoute.trim());
      if (medFreq.trim()) onAdd(`med.${addMedId}.frequency`, medFreq.trim());
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
    const medId = med.id || med.source_occurrence_id || `med_${i}`;
    const entries: [string, string][] = [
      [`med.${medId}.name`, med.name],
      ...(med.dose ? [[`med.${medId}.dose`, med.dose] as [string, string]] : []),
      ...(med.route ? [[`med.${medId}.route`, med.route] as [string, string]] : []),
      ...(med.frequency ? [[`med.${medId}.frequency`, med.frequency] as [string, string]] : []),
      ...(med.duration ? [[`med.${medId}.duration`, med.duration] as [string, string]] : []),
      ...(med.qualifier ? [[`med.${medId}.qualifier`, med.qualifier] as [string, string]] : []),
      ...(med.action ? [[`med.${medId}.action`, med.action] as [string, string]] : []),
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
  const evidenceParams = new URLSearchParams(location.search);
  const expectedEvidenceRevision = evidenceParams.get("source_revision_id");
  const expectedEvidenceExtraction = evidenceParams.get("extraction_id");
  const expectedEvidenceReview = evidenceParams.get("review_event_id");
  const evidenceLinkIsBound = Boolean(
    expectedEvidenceRevision || expectedEvidenceExtraction || expectedEvidenceReview
  );
  const evidenceBindingKey = String(noteId) + "|" + location.search;
  const requestedIssueId = evidenceParams.get("issue");
  const requestedRawField = new URLSearchParams(location.search).get("field");
  const requestedField = requestedRawField?.startsWith("instructions.")
    ? "instr." + requestedRawField.slice("instructions.".length)
    : requestedRawField?.startsWith("metadata.")
      ? "meta." + requestedRawField.slice("metadata.".length)
      : requestedRawField;
  const appliedDeepLinkRef = useRef<string | null>(null);
  const [evidenceBinding, setEvidenceBinding] = useState<{
    key: string; status: "current" | "stale" | "error";
  } | null>(null);
  const evidenceBindingIsCurrent = !evidenceLinkIsBound || (
    evidenceBinding?.key === evidenceBindingKey &&
    evidenceBinding.status === "current"
  );
  const navigate = useNavigate();
  const fromHistory = (location.state as any)?.from === "history";
  const startTime = useRef(Date.now());
  const { bumpQueue } = useQueue();

  const [isHosted, setIsHosted] = useState(false);
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
  const [isTranscriptionModalOpen, setIsTranscriptionModalOpen] = useState(false);
  const [isIssuesDrawerOpen, setIsIssuesDrawerOpen] = useState(false);
  const [currentRevisionId, setCurrentRevisionId] = useState<string | null>(null);
  const [currentRevisionNumber, setCurrentRevisionNumber] = useState<number>(1);
  const [currentExtractionId, setCurrentExtractionId] = useState<string | null>(null);
  const [currentSourceHash, setCurrentSourceHash] = useState<string | null>(null);
  const [lockVersion, setLockVersion] = useState<number>(0);
  const [reviewEventId, setReviewEventId] = useState<string | null>(null);
  const [openBlockersCount, setOpenBlockersCount] = useState<number>(0);
  const [categoryAck, setCategoryAck] = useState<Record<string, boolean>>({
    metadata: false,
    vitals: false,
    medications: false,
    instructions: false,
  });
  const [pages, setPages] = useState<PageMetadata[]>([]);
  const [leftPaneMode, setLeftPaneMode] = useState<"document" | "transcript">("document");

  const deactivateTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const hasLoadedReviewRef = useRef<boolean>(false);
  const pendingSubmissionRef = useRef<{
    idempotencyKey: string;
    reviewDurationMs: number;
    expectedHeadEventId: string | null;
    expectedLockVersion: number;
  } | null>(null);

  useEffect(() => {
    api.getCapabilities()
      .then((caps) => setIsHosted(caps.mode === "hosted_demo"))
      .catch(() => setError("Cannot verify server capabilities."));
  }, []);

  // Metrics URLs refer to a particular source/extraction/review snapshot.
  // They must never silently open whichever newer note happens to be current.
  // Key the response to the URL so an old successful verification cannot
  // briefly expose a different note while the next request is pending.
  useEffect(() => {
    if (!evidenceLinkIsBound) return;
    let active = true;
    if (!expectedEvidenceRevision || !expectedEvidenceExtraction || !noteId) {
      setEvidenceBinding({ key: evidenceBindingKey, status: "stale" });
      return () => { active = false; };
    }
    api.getNoteState(Number(noteId))
      .then((state) => {
        if (!active) return;
        const sameSnapshot = (
          state.current_source_revision_id === expectedEvidenceRevision &&
          state.current_extraction_id === expectedEvidenceExtraction &&
          (!expectedEvidenceReview || state.review_head?.event_id === expectedEvidenceReview)
        );
        setEvidenceBinding({
          key: evidenceBindingKey,
          status: sameSnapshot ? "current" : "stale",
        });
      })
      .catch(() => {
        if (active) setEvidenceBinding({ key: evidenceBindingKey, status: "error" });
      });
    return () => { active = false; };
  }, [
    noteId, evidenceBindingKey, evidenceLinkIsBound, expectedEvidenceRevision,
    expectedEvidenceExtraction, expectedEvidenceReview,
  ]);

  // Timer
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startTime.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  // Cleanup deactivate timeout on unmount
  useEffect(() => () => {
    if (deactivateTimeout.current) clearTimeout(deactivateTimeout.current);
  }, []);

  // Reset per-note UI state when navigating to a different note
  useEffect(() => {
    setSaved(false);
    setSaveFlash(null);
    setError(null);
    setReReviewBanner(false);
    setFields({});
    setActiveKey(null);
    setEditingKey(null);
    setCurrentRevisionId(null);
    setCurrentExtractionId(null);
    setCurrentSourceHash(null);
    setLockVersion(0);
    setReviewEventId(null);
    hasLoadedReviewRef.current = false;
    pendingSubmissionRef.current = null;
    setCategoryAck({
      metadata: false, vitals: false, medications: false, instructions: false,
    });
    startTime.current = Date.now();
  }, [noteId]);

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
      if (noteId) {
        const nid = Number(noteId);
        Promise.all([api.getNoteState(nid), api.getNoteSource(nid)])
          .then(([st, src]) => {
            if (st.raw_text) setRawText(st.raw_text);
            if (st.extracted_json) setExtracted(st.extracted_json);
            setCurrentRevisionId(st.current_source_revision_id ?? null);
            setCurrentExtractionId(st.current_extraction_id ?? null);
            setLockVersion(st.lock_version ?? 0);
            setReviewEventId(st.review_head?.event_id ?? null);
            setCurrentRevisionNumber(src.revision_number ?? 1);
            setCurrentSourceHash(src.sha256 ?? null);
            if (src.pages) setPages(src.pages);
          })
          .catch(() => setError("Cannot verify current source/extraction binding."));
      }
    } else if (noteId) {
      const nid = Number(noteId);
      api.getNoteState(nid).then((st) => {
        setCurrentRevisionId(st.current_source_revision_id ?? null);
        setCurrentExtractionId(st.current_extraction_id ?? null);
        if (st.lock_version !== undefined) setLockVersion(st.lock_version);
        setReviewEventId(st.review_head?.event_id ?? null);
      }).catch(() => {});

      api.getNoteSource(nid).then((src) => {
        if (src.revision_number) setCurrentRevisionNumber(src.revision_number);
        if (src.sha256) setCurrentSourceHash(src.sha256);
        if (src.pages) setPages(src.pages);
      }).catch(() => {});

      api.getNoteDetail(nid).then((d: NoteDetail) => {
        setRawText(d.raw_text);
        setExtracted(d.extracted_json);
        setNoteIdState(d.id);
        setSource(d.source ?? "");
        const loadedFrom = (location.state as any)?._loadedFrom;
        if (loadedFrom === "saveNext") {
          const name = d.filename ?? `Note #${d.id}`;
          setSaveFlash(`Loaded ${name}`);
          setTimeout(() => setSaveFlash(null), 2500);
        }

        // G: Re-review awareness
        const valSnapshot = d.review_head?.reviewed_snapshot || d.validation?.validated_json;
        if (valSnapshot && d.extracted_json) {
          const isDraft = d.review_head?.event_kind === "draft_saved";
          const itemDecs = d.review_head?.item_decisions || {};
          if (!isDraft) {
            setReReviewBanner(true);
          }
          // Offset timer by previous review duration
          if (d.validation?.review_duration_ms) {
            startTime.current = Date.now() - d.validation.review_duration_ms;
          }
          // Reconstruct per-field statuses
          const ext = d.extracted_json;
          const val = valSnapshot;
          const overrides: Record<string, { value: string; status: FieldStatus }> = {};

          // Build a flat map of validated fields
          const valFlat: Record<string, string> = {};
          Object.entries(val.vitals ?? {}).forEach(([k, v]) => { if (v) valFlat[`vitals.${k}`] = (v as any).value ?? v; });
          (val.medications ?? []).forEach((med: any, i: number) => {
            const medId = med.id || med.source_occurrence_id || `med_${i}`;
            valFlat[`med.${medId}.name`] = med.name;
            if (med.dose) valFlat[`med.${medId}.dose`] = med.dose;
            if (med.route) valFlat[`med.${medId}.route`] = med.route;
            if (med.frequency) valFlat[`med.${medId}.frequency`] = med.frequency;
            if (med.duration) valFlat[`med.${medId}.duration`] = med.duration;
            if (med.qualifier) valFlat[`med.${medId}.qualifier`] = med.qualifier;
            if (med.action) valFlat[`med.${medId}.action`] = med.action;
          });
          Object.entries(val.instructions ?? {}).forEach(([k, v]) => { if (v) valFlat[`instr.${k}`] = (v as any).value ?? v; });
          Object.entries(val.metadata ?? {}).forEach(([k, v]) => { if (v) valFlat[`meta.${k}`] = (v as any).value ?? v; });

          // Build flat map of extracted fields
          const extFlat: Record<string, string> = {};
          Object.entries(ext.vitals ?? {}).forEach(([k, v]) => { if (v) extFlat[`vitals.${k}`] = (v as any).value ?? v; });
          (ext.medications ?? []).forEach((med: any, i: number) => {
            const medId = med.id || med.source_occurrence_id || `med_${i}`;
            extFlat[`med.${medId}.name`] = med.name;
            if (med.dose) extFlat[`med.${medId}.dose`] = med.dose;
            if (med.route) extFlat[`med.${medId}.route`] = med.route;
            if (med.frequency) extFlat[`med.${medId}.frequency`] = med.frequency;
            if (med.duration) extFlat[`med.${medId}.duration`] = med.duration;
            if (med.qualifier) extFlat[`med.${medId}.qualifier`] = med.qualifier;
            if (med.action) extFlat[`med.${medId}.action`] = med.action;
          });
          Object.entries(ext.instructions ?? {}).forEach(([k, v]) => { if (v) extFlat[`instr.${k}`] = (v as any).value ?? v; });
          Object.entries(ext.metadata ?? {}).forEach(([k, v]) => { if (v) extFlat[`meta.${k}`] = (v as any).value ?? v; });

          // Diff extracted vs validated
          Object.keys(extFlat).forEach((key) => {
            const decObj = itemDecs[key];
            const explicitDec = typeof decObj === "string" ? decObj : decObj?.decision;
            if (explicitDec) {
              if (explicitDec === "accept") overrides[key] = { value: valFlat[key] ?? extFlat[key], status: "accepted" };
              else if (explicitDec === "edit") overrides[key] = { value: valFlat[key] ?? extFlat[key], status: "corrected" };
              else if (explicitDec === "remove") overrides[key] = { value: extFlat[key], status: "removed" };
              else overrides[key] = { value: extFlat[key], status: "pending" };
            } else if (isDraft) {
              overrides[key] = { value: extFlat[key], status: "pending" };
            } else if (!(key in valFlat)) {
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
          // Historical review additions are not present in the original
          // extraction, so flattenExtracted alone would silently lose them.
          for (const [key, value] of Object.entries(valFlat)) {
            if (!(key in extFlat)) {
              m[key] = { value, originalValue: "", status: "corrected" };
            }
          }
          hasLoadedReviewRef.current = true;
          setFields(m);
          // reReviewBanner or hasLoadedReviewRef guards the flatten useEffect below,
          // so setExtracted won't overwrite these restored draft or review statuses.
          setExtracted(ext);
        }
      });
    }
  }, [noteId, location.state]); // eslint-disable-line react-hooks/exhaustive-deps

  // Flatten extracted JSON into FieldMap (only for fresh loads without prior validation or draft)
  useEffect(() => {
    if (!extracted || reReviewBanner || hasLoadedReviewRef.current) return;
    const m = flattenExtracted(extracted);
    setFields(m);
  }, [extracted, reReviewBanner]);

  // A dashboard deep link must resolve only AFTER the actual bound note's
  // fields are loaded. Apply it once per URL so edits do not repeatedly steal
  // focus from the reviewer.
  useEffect(() => {
    const token = noteId + location.search;
    if (appliedDeepLinkRef.current === token) return;
    if (!evidenceBindingIsCurrent) return;
    if (requestedIssueId && /^[0-9a-f-]{36}$/i.test(requestedIssueId)) {
      setIsIssuesDrawerOpen(true);
    }
    if (requestedField && /^[a-zA-Z0-9_.-]{1,120}$/.test(requestedField)) {
      if (!Object.prototype.hasOwnProperty.call(fields, requestedField)) return;
      setActiveKey(requestedField);
    }
    appliedDeepLinkRef.current = token;
  }, [noteId, location.search, requestedIssueId, requestedField, fields, evidenceBindingIsCurrent]);

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

  // Deactivate handler (preserves active key for keyboard navigation and popover interaction)
  const handleDeactivate = useCallback(() => {
    // no-op: preserve activeKey until another card is activated or Escape is pressed
  }, []);

  const handleFieldChange = useCallback((key: string, value: string, status: FieldStatus) => {
    pendingSubmissionRef.current = null;
    setFields((prev) => {
      const previous = prev[key];
      if (status === "removed" && previous?.originalValue === "") {
        // Removing a not-yet-saved addition is an undo, not a removal of an
        // existing extracted field. Avoid submitting an invalid unknown ID.
        const next = { ...prev };
        if (key.startsWith("med.") && key.endsWith(".name")) {
          const prefix = `med.${key.split(".")[1]}.`;
          Object.keys(next).forEach((candidate) => {
            if (candidate.startsWith(prefix)) delete next[candidate];
          });
        } else {
          delete next[key];
        }
        return next;
      }
      const effectiveStatus =
        status === "accepted" &&
        previous?.originalValue !== undefined &&
        previous.originalValue !== "" &&
        value !== previous.originalValue
          ? "corrected"
          : status;
      return { ...prev, [key]: { ...previous, value, status: effectiveStatus } };
    });
  }, []);

  function handleAddField(key: string, value: string) {
    if (isHosted) {
      setError("Public demo permits curated review actions only.");
      return;
    }
    pendingSubmissionRef.current = null;
    setFields((prev) => ({ ...prev, [key]: { value, originalValue: "", status: "corrected" } }));
  }

  const handleSave = useCallback(async (_overallStatus: "accepted" | "corrected", fieldsOverride?: FieldMap) => {
    if (!noteIdState || !extracted) return;
    setSaving(true); setError(null);
    try {
      const effectiveFields = fieldsOverride || fields;
      const validated: ExtractionResult = JSON.parse(JSON.stringify(extracted));
      const medMap: Record<string, any> = {};
      (validated.medications || []).forEach((m: any, idx: number) => {
        const mid = m.id || m.source_occurrence_id || `med_${idx}`;
        m.id = mid;
        m.source_occurrence_id = mid;
        medMap[mid] = { ...m };
      });

      // Find medications whose name was removed (meaning the medication itself is removed)
      const removedMedIds = new Set<string>();
      Object.entries(effectiveFields).forEach(([key, { status }]) => {
        if (key.startsWith("med.") && status === "removed") {
          const parts = key.split(".");
          if (parts[2] === "name" || parts.length === 2) {
            removedMedIds.add(parts[1]);
          }
        }
      });

      // Handle additions for new medications
      Object.entries(effectiveFields).forEach(([key, { status }]) => {
        if (key.startsWith("med.") && (status === "accepted" || status === "corrected")) {
          const parts = key.split(".");
          const mid = parts[1];
          if (!medMap[mid] && !removedMedIds.has(mid)) {
            medMap[mid] = { id: mid, source_occurrence_id: mid, name: "" };
          }
        }
      });

      // Apply field updates
      Object.entries(effectiveFields).forEach(([key, { value, status }]) => {
        const [section, ...rest] = key.split(".");
        if (status === "removed") {
          if (section === "vitals") delete (validated.vitals as any)[rest[0]];
          else if (section === "instr") delete (validated.instructions as any)[rest[0]];
          else if (section === "meta") delete (validated.metadata as any)[rest[0]];
          else if (section === "med") {
            const mid = rest[0];
            const attr = rest[1];
            if (attr && attr !== "name" && medMap[mid]) {
              // Child attribute removal removes only that attribute, not the medication!
              delete medMap[mid][attr];
            }
          }
        } else {
          if (section === "vitals") {
            if (!(validated.vitals as any)[rest[0]]) (validated.vitals as any)[rest[0]] = { value };
            else (validated.vitals as any)[rest[0]].value = value;
          } else if (section === "instr") {
            if (!(validated.instructions as any)[rest[0]]) (validated.instructions as any)[rest[0]] = { value };
            else (validated.instructions as any)[rest[0]].value = value;
          } else if (section === "meta") {
            if (!(validated.metadata as any)[rest[0]]) (validated.metadata as any)[rest[0]] = { value };
            else (validated.metadata as any)[rest[0]].value = value;
          } else if (section === "med") {
            const mid = rest[0];
            const attr = rest[1];
            if (!removedMedIds.has(mid) && medMap[mid]) {
              medMap[mid][attr] = value;
            }
          }
        }
      });
      validated.medications = Object.values(medMap).filter((m: any) => !removedMedIds.has(m.id));

      const itemDecisions: Record<string, any> = {};
      const pendingFields: string[] = [];
      Object.entries(effectiveFields).forEach(([k, f]) => {
        if (f.status === "pending") {
          pendingFields.push(k);
        } else {
          let dec = "accept";
          if (f.originalValue === "") {
            dec = f.status === "removed" ? "remove" : "add";
          } else if (f.status === "corrected") {
            dec = "edit";
          } else if (f.status === "removed") {
            dec = "remove";
          } else if (f.status === "accepted") {
            dec = "accept";
          }
          const decObj: Record<string, any> = { decision: dec };
          if (dec === "edit" || dec === "add") {
            decObj.value = f.value;
          }
          if (dec === "add") {
            decObj.reason = "Reviewer clinical entry";
          }
          itemDecisions[k] = decObj;
        }
      });

      if (pendingFields.length > 0) {
        throw new Error(
          `Please resolve all pending fields before completing review. (${pendingFields.length} pending: ${pendingFields.slice(0, 3).join(", ")}${pendingFields.length > 3 ? "..." : ""})`
        );
      }

      // Rule A15: Check all 4 category completeness acknowledgments
      const missingAcks = (["metadata", "vitals", "medications", "instructions"] as const).filter(
        (cat) => !categoryAck[cat]
      );
      if (missingAcks.length > 0) {
        throw new Error(`Completeness must be acknowledged for all categories: ${missingAcks.join(", ")}`);
      }

      if (!currentExtractionId || !currentRevisionId || !currentSourceHash) {
        throw new Error("Source/extraction binding has not loaded. Retry when note details are available.");
      }

      let idempotencyKey: string;
      let reviewDurationMs: number;

      if (
        pendingSubmissionRef.current &&
        pendingSubmissionRef.current.expectedHeadEventId === (reviewEventId ?? null) &&
        pendingSubmissionRef.current.expectedLockVersion === lockVersion
      ) {
        idempotencyKey = pendingSubmissionRef.current.idempotencyKey;
        reviewDurationMs = pendingSubmissionRef.current.reviewDurationMs;
      } else {
        idempotencyKey = crypto.randomUUID();
        reviewDurationMs = Date.now() - startTime.current;
        pendingSubmissionRef.current = {
          idempotencyKey,
          reviewDurationMs,
          expectedHeadEventId: reviewEventId ?? null,
          expectedLockVersion: lockVersion,
        };
      }

      // A review must have exactly ONE authoritative write. Never follow an
      // immutable ReviewEvent with the old mutable /api/validate API.
      const revRes = await api.submitReview(currentExtractionId, {
        schema_version: "2.0.0",
        note_id: noteIdState,
        source_revision_id: currentRevisionId,
        extraction_id: currentExtractionId,
        source_hash: currentSourceHash,
        expected_lock_version: lockVersion,
        expected_head_event_id: reviewEventId ?? null,
        event_kind: "review_completed",
        item_decisions: itemDecisions,
        category_acknowledgments: categoryAck,
        reviewed_snapshot: validated,
        review_duration_ms: reviewDurationMs,
        idempotency_key: idempotencyKey,
      });

      if (!revRes?.event_id) {
        throw new Error("The server did not confirm a review event.");
      }
      pendingSubmissionRef.current = null;
      setReviewEventId(revRes.event_id);
      setLockVersion((v) => v + 1);
      const pendingQueue = await api.getQueue().catch(() => null);
      const nextPendingId = pendingQueue?.notes?.find((n) => n.id !== noteIdState)?.id ?? null;
      setSaved(true);
      bumpQueue();

      // F: Save & Next
      if (nextPendingId !== null) {
        setSaveFlash("Saved — loading next note…");
        setTimeout(() => {
          navigate(`/review/${nextPendingId}`, { state: { _loadedFrom: "saveNext" } });
        }, 800);
      } else {
        setSaveFlash(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [
    noteIdState,
    extracted,
    fields,
    bumpQueue,
    navigate,
    currentExtractionId,
    currentRevisionId,
    currentSourceHash,
    lockVersion,
    reviewEventId,
    categoryAck,
  ]);

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
        if (activeKey && !isHosted) {
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
      if (e.key === "c" || e.key === "C") {
        setCategoryAck((prev) => {
          const allChecked = Object.values(prev).every(Boolean);
          const nextVal = !allChecked;
          return { metadata: nextVal, vitals: nextVal, medications: nextVal, instructions: nextVal };
        });
      }
      if (e.key === "Tab") {
        const keys = Object.keys(fields);
        if (keys.length > 0) {
          if (!activeKey) {
            e.preventDefault();
            handleActivate(keys[0]);
          } else {
            const idx = keys.indexOf(activeKey);
            if (e.shiftKey) {
              if (idx > 0) {
                e.preventDefault();
                handleActivate(keys[idx - 1]);
              } else {
                setActiveKey(null);
              }
            } else {
              if (idx < keys.length - 1) {
                e.preventDefault();
                handleActivate(keys[idx + 1]);
              } else {
                e.preventDefault();
                setActiveKey(null);
                document.getElementById("ack-metadata")?.focus();
              }
            }
          }
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        handleSave(hasCorrected ? "corrected" : "accepted");
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [activeKey, fields, isHosted, handleFieldChange, handleActivate, handleSave]); // hasCorrected is derived below

  // H: Unsaved changes warning — blocks both in-app nav and browser-level unload
  const isDirty = Object.values(fields).some((f) => f.status !== "pending") && !saved;
  const blocker = useBlocker(isDirty);

  // Handle React Router in-app navigation block
  useEffect(() => {
    if (blocker.state === "blocked") {
      if (window.confirm("You have unsaved changes. Leave anyway?")) {
        blocker.proceed?.();
      } else {
        blocker.reset?.();
      }
    }
  }, [blocker]);

  // Handle browser-level navigation (tab close, page refresh)
  useEffect(() => {
    function handler(e: BeforeUnloadEvent) {
      if (isDirty) { e.preventDefault(); e.returnValue = ""; }
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  // Do not show a current note as evidence for a stale metric result.
  // Even if separate API calls loaded the new note first, this guard keeps
  // its source/fields/issue drawer hidden until bindings have been checked.
  if (evidenceLinkIsBound && !evidenceBindingIsCurrent) {
    const result = evidenceBinding?.key === evidenceBindingKey
      ? evidenceBinding.status : "checking";
    return (
      <main className="flex h-full items-center justify-center bg-slate-50 p-8">
        <div className="max-w-lg rounded-lg border border-amber-200 bg-white p-6">
          <h1 className="text-lg font-semibold text-slate-900">
            {result === "checking" ? "Checking source evidence…" : "Evidence link needs refreshing"}
          </h1>
          <p role={result === "checking" ? "status" : "alert"} className="mt-2 text-sm text-slate-700">
            {result === "checking"
              ? "Verifying the exact source revision, extraction and review event."
              : "The metric evidence no longer matches the current note, or cannot be verified. Return to the dashboard and reopen a current result."}
          </p>
          <button
            type="button"
            onClick={() => navigate("/metrics")}
            className="mt-4 rounded border border-cyan-700 px-3 py-2 text-sm font-medium text-cyan-800 hover:bg-cyan-50"
          >
            Return to metrics
          </button>
        </div>
      </main>
    );
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

  // D: Progress bar
  const totalFields = Object.keys(fields).length;
  const reviewedCount = totalFields - pendingCount; // accepted + corrected + removed
  const progressPct = totalFields > 0 ? Math.round((reviewedCount / totalFields) * 100) : 0;

  return (
    <div className="h-full bg-slate-50 flex flex-col overflow-hidden">
      {/* Review top bar */}
      <header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          {fromHistory && (
            <button
              onClick={() => navigate("/history")}
              className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1"
            >
              ← History
            </button>
          )}
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
          <button
            onClick={() => setIsIssuesDrawerOpen((o) => !o)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-semibold transition-colors"
          >
            <span>Issues</span>
            {openBlockersCount > 0 ? (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-rose-500 text-white">
                {openBlockersCount}
              </span>
            ) : null}
          </button>
          {reviewEventId && (
            <button
              onClick={async () => {
                try {
                  await api.downloadExport(reviewEventId);
                } catch (err: any) {
                  setError(err.message || "Failed to download export");
                }
              }}
              title="Download verified review bundle ZIP"
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-800 hover:bg-emerald-700 text-emerald-100 text-xs font-semibold transition-colors"
            >
              <span>Export ZIP</span>
            </button>
          )}
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
        {/* Left: Document Source & Evidence Viewer */}
        <div className="w-1/2 border-r border-slate-200 flex flex-col overflow-hidden bg-slate-900">
          {/* Header controls for Document vs Transcript view */}
          <div className="px-3 py-1.5 border-b border-slate-800 bg-slate-900/90 flex items-center justify-between gap-2 flex-shrink-0">
            <div className="inline-flex rounded-lg p-0.5 bg-slate-950 border border-slate-700">
              <button
                type="button"
                onClick={() => setLeftPaneMode("document")}
                className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors ${
                  leftPaneMode === "document"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                data-testid="leftpane-mode-document"
              >
                Document Viewer (PDF/Image)
              </button>
              <button
                type="button"
                onClick={() => setLeftPaneMode("transcript")}
                className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors ${
                  leftPaneMode === "transcript"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                data-testid="leftpane-mode-transcript"
              >
                Transcript Spans
              </button>
            </div>

            <button
              onClick={() => setIsTranscriptionModalOpen(true)}
              className="text-[11px] font-medium text-cyan-400 hover:text-cyan-300 underline"
            >
              Update Transcription (Rev {currentRevisionNumber})
            </button>
          </div>

          {leftPaneMode === "document" && noteIdState && extracted ? (
            <DocumentSourceViewer
              key={currentRevisionId || noteIdState}
              noteId={noteIdState}
              revisionId={currentRevisionId}
              rawText={rawText}
              extracted={extracted}
              pages={pages}
              activeKey={activeKey}
              onSpanClick={handleActivate}
            />
          ) : (
            <div className="flex-1 flex flex-col overflow-hidden bg-white">
              {/* Legend */}
              <div className="px-4 py-1.5 border-b border-slate-100 bg-slate-50 flex items-center gap-4 flex-shrink-0">
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
              {extracted && (
                <NoteViewer
                  rawText={rawText}
                  extracted={extracted}
                  activeKey={activeKey}
                  onSpanClick={handleActivate}
                />
              )}
            </div>
          )}
        </div>

        {/* Right: Field cards */}
        <div className="w-1/2 flex flex-col overflow-hidden bg-slate-50">
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
            {CATEGORIES.map((cat) => {
              const prefix = CATEGORY_PREFIX[cat];
              const catFields = Object.entries(fields).filter(([k]) => k.startsWith(prefix));

              // Medications: group fields by drug ID into visual containers
              if (cat === "med") {
                const drugIds = Array.from(
                  new Set(catFields.map(([k]) => k.split(".")[1]))
                );

                return (
                  <section key={cat}>
                    <h3 className="text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400 mb-2 px-1">
                      {CATEGORY_DISPLAY[cat]}
                    </h3>
                    <div className="space-y-2">
                      {drugIds.map((medId) => {
                        const drugFields = catFields.filter(([k]) => k.split(".")[1] === medId);
                        const nameEntry = drugFields.find(([k]) => k.endsWith(".name"));
                        const otherFields = drugFields.filter(([k]) => !k.endsWith(".name"));
                        const isMentionOnly = otherFields.length === 0;
                        return (
                          <div key={medId} className={`rounded-lg border overflow-hidden bg-white ${isMentionOnly ? "border-slate-200" : "border-green-100"}`}>
                            {/* Name row */}
                            {nameEntry && (
                              <div
                                ref={(el) => { cardRefs.current[nameEntry[0]] = el; }}
                                onMouseEnter={() => handleActivate(nameEntry[0])}
                                onMouseLeave={handleDeactivate}
                                className={otherFields.length > 0 ? "border-b border-green-100" : ""}
                              >
                                <FieldEditor
                                  allowEdit={!isHosted}
                                  key={`${currentRevisionId ?? "rev"}-${nameEntry[0]}`}
                                  label="name"
                                  value={nameEntry[1].value}
                                  originalValue={nameEntry[1].originalValue}
                                  status={nameEntry[1].status}
                                  category="med"
                                  isActive={activeKey === nameEntry[0]}
                                  onActivate={() => handleActivate(nameEntry[0])}
                                  onChange={(v, s) => handleFieldChange(nameEntry[0], v, s)}
                                  triggerEdit={editingKey === nameEntry[0]}
                                  onEditTriggered={() => setEditingKey(null)}
                                  explainerKind="medication"
                                />
                              </div>
                            )}
                            {/* Dose / route / frequency — indented */}
                            {otherFields.length > 0 && (
                              <div className="pl-3 border-l-2 border-green-200 ml-2 divide-y divide-green-50">
                                {otherFields.map(([k, f]) => (
                                  <div
                                    key={k}
                                    ref={(el) => { cardRefs.current[k] = el; }}
                                    onMouseEnter={() => handleActivate(k)}
                                    onMouseLeave={handleDeactivate}
                                  >
                                    <FieldEditor
                                  allowEdit={!isHosted}
                                      key={`${currentRevisionId ?? "rev"}-${k}`}
                                      label={k.split(".")[2]}
                                      value={f.value}
                                      originalValue={f.originalValue}
                                      status={f.status}
                                      category="med"
                                      isActive={activeKey === k}
                                      onActivate={() => handleActivate(k)}
                                      onChange={(v, s) => handleFieldChange(k, v, s)}
                                      triggerEdit={editingKey === k}
                                      onEditTriggered={() => setEditingKey(null)}
                                      explainerKind={
                                        ['route', 'frequency', 'qualifier'].includes(k.split(".")[2]) ? 'abbreviation'
                                        : undefined
                                      }
                                    />
                                  </div>
                                ))}
                              </div>
                            )}
                            {/* Mention-only strip */}
                            {isMentionOnly && (
                              <div className="px-3 py-1 flex items-center gap-1.5 bg-slate-50 border-t border-slate-100">
                                <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-400">mention only</span>
                                <span className="text-[9px] text-slate-300">— no dose or sig captured</span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {!isHosted && (
                      <AddFieldRow
                        category={cat}
                        existingKeys={Object.keys(fields)}
                        onAdd={handleAddField}
                      />
                    )}
                    </div>
                  </section>
                );
              }

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
                                  allowEdit={!isHosted}
                          key={`${currentRevisionId ?? "rev"}-${k}`}
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
                    {!isHosted && (
                      <AddFieldRow
                      category={cat}
                      existingKeys={Object.keys(fields)}
                      onAdd={handleAddField}
                    />
                    )}
                  </div>
                </section>
              );
            })}
          </div>

          {/* Category Completeness Acknowledgments Bar */}
          <div className="border-t border-slate-200 px-4 py-2 bg-slate-100 flex items-center justify-between flex-shrink-0 text-xs">
            <span className="font-semibold text-slate-700">Category Completeness:</span>
            <div className="flex items-center gap-4">
              {(["metadata", "vitals", "medications", "instructions"] as const).map((cat) => (
                <label key={cat} className="flex items-center gap-1.5 cursor-pointer text-slate-700 select-none">
                  <input
                    type="checkbox"
                    id={`ack-${cat}`}
                    data-testid={`ack-${cat}`}
                    checked={!!categoryAck[cat]}
                    onChange={(e) => setCategoryAck((prev) => ({ ...prev, [cat]: e.target.checked }))}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                  />
                  <span className="capitalize">{cat}</span>
                </label>
              ))}
            </div>
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
                  <p className="text-green-600 text-xs font-semibold">Review saved!</p>
                  {reviewEventId && (
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await api.downloadExport(reviewEventId);
                        } catch (e: any) {
                          setError(e.message || "Failed to download export");
                        }
                      }}
                      className="px-3 py-1 bg-emerald-600 text-white rounded text-xs font-semibold hover:bg-emerald-500 shadow-sm transition-colors"
                    >
                      Export ZIP
                    </button>
                  )}
                  <a href="/history" className="text-xs text-blue-600 hover:underline">History</a>
                  <a href="/metrics" className="text-xs text-blue-600 hover:underline">Metrics</a>
                </div>
              ) : (
                <>
                  {reviewEventId && (
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await api.downloadExport(reviewEventId);
                        } catch (e: any) {
                          setError(e.message || "Failed to download export");
                        }
                      }}
                      className="px-3 py-1.5 bg-emerald-600 text-white rounded-md text-xs font-bold hover:bg-emerald-500 shadow-sm transition-colors"
                    >
                      Export ZIP
                    </button>
                  )}
                  <button
                    onClick={() => {
                      const next: FieldMap = {};
                      Object.entries(fields).forEach(([k, f]) => {
                        next[k] = f.status === "pending" ? { ...f, status: "accepted" } : f;
                      });
                      setFields(next);
                      handleSave("accepted", next);
                    }}
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

      {/* Transcription Edit Modal */}
      {noteIdState && !isHosted && (
        <TranscriptionEditModal
          isOpen={isTranscriptionModalOpen}
          onClose={() => setIsTranscriptionModalOpen(false)}
          noteId={noteIdState}
          currentText={rawText}
          expectedRevisionId={currentRevisionId}
          expectedLockVersion={lockVersion}
          onRevisionCreated={(newRevId) => {
            setCurrentRevisionId(newRevId);
            setCurrentRevisionNumber((n) => n + 1);
            setReReviewBanner(false);
            hasLoadedReviewRef.current = false;
            setSaved(false);
            setCategoryAck({
              metadata: false, vitals: false, medications: false, instructions: false,
            });
            api.getNoteState(noteIdState).then((st) => {
              setRawText(st.raw_text);
              setExtracted(st.extracted_json);
              if (st.extracted_json) {
                setFields(flattenExtracted(st.extracted_json));
              }
              setLockVersion(st.lock_version);
              if (st.current_source_revision_id) setCurrentRevisionId(st.current_source_revision_id);
              if (st.current_extraction_id) setCurrentExtractionId(st.current_extraction_id);
              if (st.source_hash) setCurrentSourceHash(st.source_hash);
              setReviewEventId(null);
            });
            api.getNoteSource(noteIdState).then((src) => {
              if (src.sha256) setCurrentSourceHash(src.sha256);
              if (src.revision_number) setCurrentRevisionNumber(src.revision_number);
              if (src.pages) setPages(src.pages);
            }).catch(() => {});
          }}
        />
      )}

      {/* Operational Issues Drawer */}
      {noteIdState && (
        <OperationalIssuesDrawer
          noteId={noteIdState}
          revisionId={currentRevisionId}
          extractionId={currentExtractionId}
          focusedIssueId={requestedIssueId}
          isOpen={isIssuesDrawerOpen}
          onToggle={() => setIsIssuesDrawerOpen((o) => !o)}
          onIssuesUpdated={(blockers) => setOpenBlockersCount(blockers)}
        />
      )}
    </div>
  );
}
