// frontend/src/pages/OcrPreview.tsx
import { useState, useEffect } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { api } from "../api/client";

interface LocationState {
  rawText?: string;
  ocrConfidence?: number | null;
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.85 ? "bg-green-500" :
    confidence >= 0.7  ? "bg-amber-400" :
                         "bg-red-400";
  const label =
    confidence >= 0.85 ? "text-green-700" :
    confidence >= 0.7  ? "text-amber-700" :
                         "text-red-700";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-sm font-semibold w-10 text-right ${label}`}>{pct}%</span>
    </div>
  );
}

export default function OcrPreview() {
  const { noteId } = useParams<{ noteId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as LocationState;

  const [text, setText] = useState(state.rawText ?? "");
  const [confidence] = useState<number | null>(state.ocrConfidence ?? null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If arrived without state (e.g., direct URL), load from API
  useEffect(() => {
    if (!state.rawText && noteId) {
      api.getNoteDetail(Number(noteId))
        .then((d: any) => setText(d.raw_text ?? ""))
        .catch(() => setError("Failed to load note text."));
    }
  }, [noteId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleProceed() {
    if (!noteId || !text.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateNoteText(Number(noteId), text.trim());
      navigate(`/review/${noteId}`);
    } catch (e: any) {
      setError(e.message ?? "Failed to update text.");
      setSaving(false);
    }
  }

  function handleSkip() {
    navigate(`/review/${noteId}`);
  }

  const isLowConfidence = confidence !== null && confidence < 0.7;

  return (
    <div className="h-full overflow-auto bg-slate-50">
      <main className="max-w-3xl mx-auto p-6 space-y-5">
        {/* Header */}
        <div>
          <h1 className="text-xl font-semibold text-slate-800">OCR Preview</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Review and correct the extracted text before running the NLP pipeline.
          </p>
        </div>

        {/* Confidence indicator */}
        {confidence !== null && (
          <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                OCR Confidence
              </span>
            </div>
            <ConfidenceBar confidence={confidence} />
          </div>
        )}

        {/* Warning banner for low confidence */}
        {isLowConfidence && (
          <div className="flex gap-3 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
            <svg className="flex-shrink-0 mt-0.5 text-amber-500" width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 1.5L14.5 13H1.5L8 1.5Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
              <path d="M8 6v3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              <circle cx="8" cy="11" r="0.6" fill="currentColor"/>
            </svg>
            <p className="text-sm text-amber-800">
              OCR confidence is low — the extracted text may contain errors. Review and correct it before proceeding.
            </p>
          </div>
        )}

        {/* Editable text area */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Extracted Text
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={18}
            className="w-full border border-slate-300 rounded-lg p-3 font-mono text-sm resize-y focus:outline-none focus:ring-2 focus:ring-cyan-400 text-slate-900 leading-relaxed bg-white"
            placeholder="No text extracted."
          />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={handleProceed}
            disabled={saving || !text.trim()}
            className="px-5 py-2 bg-cyan-600 text-white rounded-lg text-sm font-medium hover:bg-cyan-700 disabled:opacity-50"
          >
            {saving ? "Re-extracting..." : "Proceed to Extraction →"}
          </button>
          <button
            onClick={handleSkip}
            disabled={saving}
            className="px-5 py-2 border border-slate-300 text-slate-600 rounded-lg text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            Skip to Review →
          </button>
        </div>
        <p className="text-xs text-slate-400">
          "Proceed" re-runs the NLP pipeline on your corrected text. "Skip" goes straight to review with the existing extraction.
        </p>
      </main>
    </div>
  );
}
