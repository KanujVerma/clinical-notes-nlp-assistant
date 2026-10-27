import { useState, useEffect } from "react";
import { api } from "../api/client";

export default function TranscriptionEditModal({
  isOpen,
  onClose,
  noteId,
  currentText,
  onRevisionCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  noteId: number;
  currentText: string;
  onRevisionCreated: (newRevisionId: string) => void;
}) {
  const [text, setText] = useState(currentText);
  const [reason, setReason] = useState("transcription_correction");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(currentText);
  }, [noteId, currentText]);

  if (!isOpen) return null;

  async function handleSave() {
    if (!text.trim()) return;
    try {
      setSaving(true);
      setError(null);
      const res = await api.appendNoteRevision(noteId, text, reason);
      onRevisionCreated(res.revision_id);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to create revision");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl text-slate-100 flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div>
            <h2 className="text-base font-bold text-white">Edit Document Transcription</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Creates a new immutable source revision and triggers re-extraction.
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            ✕
          </button>
        </div>

        {error && (
          <div className="mt-3 rounded bg-rose-950/50 border border-rose-800 p-2.5 text-xs text-rose-300">
            {error}
          </div>
        )}

        <div className="mt-4 flex-1 overflow-y-auto space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Source Text Content
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={12}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Revision Reason / Note
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Corrected misread OCR dosage"
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div className="rounded-lg bg-amber-950/30 border border-amber-800/60 p-3 text-xs text-amber-300">
            <strong>Important:</strong> Modifying the transcription invalidates prior completed reviews and requires a fresh verification pass.
          </div>
        </div>

        <div className="mt-5 flex justify-end space-x-3 pt-3 border-t border-slate-800">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-xs font-semibold text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !text.trim()}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-xs font-semibold text-white hover:bg-cyan-500 disabled:opacity-50 transition-colors"
          >
            {saving ? "Creating Revision…" : "Save New Revision"}
          </button>
        </div>
      </div>
    </div>
  );
}
