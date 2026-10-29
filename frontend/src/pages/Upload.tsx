// frontend/src/pages/Upload.tsx
import { useState, useEffect, useRef, useCallback } from "react";
import React from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useQueue } from "../context/QueueContext";

const SAMPLE_NOTE = `Patient: Sample Patient
Date of Service: 2025-01-15
Provider: Dr. Demo

Vitals: BP 130/82. HR 76 bpm. Temp 98.6F. RR 14. SpO2 98%. Wt 175 lbs.

Medications:
- lisinopril 10 mg PO daily
- metformin 500 mg PO BID

DISCHARGE INSTRUCTIONS:
Take all medications as prescribed.

FOLLOW UP:
Return to clinic in 2 weeks.

RETURN PRECAUTIONS:
Return to ER if chest pain or shortness of breath.`;

type FileStatus =
  | { phase: "queued" }
  | { phase: "uploading" }
  | { phase: "done"; noteId: number }
  | { phase: "error"; message: string };

interface FileEntry {
  file: File;
  status: FileStatus;
}

export default function Upload() {
  const navigate = useNavigate();
  const { bumpQueue } = useQueue();

  // Fail closed until the backend confirms whether arbitrary input is allowed.
  const [isHosted, setIsHosted] = useState(true);
  const [capabilitiesChecked, setCapabilitiesChecked] = useState(false);
  const [scenarios, setScenarios] = useState<Array<{ filename: string; title: string; sha256: string; has_issues: boolean; issues_count: number; snippet: string }>>([]);

  const [text, setText] = useState("");
  const [textLoading, setTextLoading] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);

  const [files, setFiles] = useState<FileEntry[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const cancelRef = useRef(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    api.getCapabilities()
      .then((caps) => {
        const hosted = caps.mode === "hosted_demo" || Boolean(caps.hosted_sandbox);
        setIsHosted(hosted);
        setCapabilitiesChecked(true);
        if (hosted) {
          api.getScenarios().then((res) => setScenarios(res.scenarios || []))
            .catch(() => setTextError("Could not load curated synthetic scenarios."));
        }
      })
      .catch(() => {
        setIsHosted(true);
        setCapabilitiesChecked(true);
        setTextError("Cannot confirm server capabilities. Free-text input is disabled.");
      });
  }, []);

  function showToast(msg: string) {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }

  async function handleSubmitText() {
    if (!capabilitiesChecked || isHosted || !text.trim()) return;
    setTextLoading(true);
    setTextError(null);
    try {
      const { note_id } = await api.createNote(text);
      navigate(`/review/${note_id}`);
    } catch (e: any) {
      setTextError(e.message);
    } finally {
      setTextLoading(false);
    }
  }

  async function handleSeedDemo() {
    if (!capabilitiesChecked) return;
    setTextLoading(true);
    try {
      const result = await api.seedDemo();
      bumpQueue();
      showToast(
        result.loaded > 0
          ? `Seeded ${result.loaded} note${result.loaded !== 1 ? "s" : ""} — opening queue…`
          : `${result.skipped} notes already exist`
      );
      if (result.loaded > 0) {
        setTimeout(() => navigate("/queue"), 1200);
      }
    } catch (e: any) {
      setTextError(e.message);
    } finally {
      setTextLoading(false);
    }
  }

  function addFiles(newFiles: File[]) {
    if (!capabilitiesChecked || isHosted) return;
    const entries: FileEntry[] = newFiles.map((f) => ({ file: f, status: { phase: "queued" } }));
    setFiles((prev) => [...prev, ...entries]);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const dropped = Array.from(e.dataTransfer.files);
    if (dropped.length) addFiles(dropped);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? []);
    if (selected.length) addFiles(selected);
    e.target.value = "";
  }

  const updateFileStatus = useCallback((idx: number, status: FileStatus) => {
    setFiles((prev) => prev.map((entry, i) => (i === idx ? { ...entry, status } : entry)));
  }, []);

  async function startUpload() {
    if (!capabilitiesChecked || isHosted) {
      setTextError("Uploads are unavailable until local mode is confirmed.");
      return { successCount: 0, failCount: 0, firstSuccessId: null, firstSuccessResult: null };
    }
    cancelRef.current = false;
    setUploading(true);

    // Find the absolute indices of queued files
    const queuedIndices = files
      .map((entry, i) => (entry.status.phase === "queued" ? i : -1))
      .filter((i) => i >= 0);

    let successCount = 0;
    let failCount = 0;
    let firstSuccessId: number | null = null;
    let firstSuccessResult: Awaited<ReturnType<typeof api.uploadFile>> | null = null;

    for (const idx of queuedIndices) {
      if (cancelRef.current) break;

      updateFileStatus(idx, { phase: "uploading" });
      try {
        const result = await api.uploadFile(files[idx].file);
        updateFileStatus(idx, { phase: "done", noteId: result.note_id });
        successCount++;
        if (firstSuccessId === null) {
          firstSuccessId = result.note_id;
          firstSuccessResult = result;
        }
      } catch (e: any) {
        updateFileStatus(idx, { phase: "error", message: e.message ?? "Upload failed" });
        failCount++;
      }
    }

    setUploading(false);
    if (successCount > 0 || failCount > 0) {
      bumpQueue();
    }
    return { successCount, failCount, firstSuccessId, firstSuccessResult };
  }

  // Track the first upload result for OCR-aware routing
  const [firstUploadResult, setFirstUploadResult] = useState<Awaited<ReturnType<typeof api.uploadFile>> | null>(null);

  // Summary derived from current files state
  const doneCount = files.filter((f) => f.status.phase === "done").length;
  const errorCount = files.filter((f) => f.status.phase === "error").length;
  const queuedCount = files.filter((f) => f.status.phase === "queued").length;
  const allFinished = files.length > 0 && queuedCount === 0 && !uploading;
  const firstSuccessNoteId = files.find(
    (f): f is FileEntry & { status: { phase: "done"; noteId: number } } =>
      f.status.phase === "done"
  )?.status.noteId ?? null;

  return (
    <div className="h-full overflow-auto bg-slate-50 flex flex-col">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-slate-800 text-slate-100 text-sm px-4 py-2.5 rounded-lg shadow-lg border border-slate-600 transition-opacity">
          {toast}
        </div>
      )}

      <main className="flex-1 flex flex-col items-center justify-center p-6 gap-6 max-w-3xl mx-auto w-full">
        {capabilitiesChecked && isHosted && (
          <div className="w-full bg-amber-50 border border-amber-300 rounded-lg p-3.5 text-sm text-amber-900">
            <div className="font-semibold mb-1 flex items-center gap-1.5">
              <span>Public Hosted Sandbox</span>
              <span className="text-[10px] bg-amber-200 text-amber-800 px-2 py-0.5 rounded-full font-mono uppercase font-bold tracking-wider">
                Curated Fixtures
              </span>
            </div>
            <p className="text-xs text-amber-800 leading-relaxed">
              Live arbitrary file uploads and free-text NLP runs are disabled to preserve resource boundaries. Explore the curated precomputed scenarios below or seed the demonstration dataset.
            </p>
          </div>
        )}

        <div className="text-center">
          <h2 className="text-2xl font-semibold text-slate-800">
            Extract structured data from a clinical note
          </h2>
          <p className="text-slate-500 mt-1">
            {isHosted
              ? "Select a curated clinical scenario or seed the showcase dataset."
              : "Paste note text, upload files (txt, pdf, or images), or load a sample note."}
          </p>
        </div>

        {/* Text area */}
        <textarea
          className={`w-full h-48 border border-slate-300 rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-cyan-400 text-slate-900 leading-relaxed ${
            isHosted ? "bg-slate-100 text-slate-500 cursor-not-allowed" : ""
          }`}
          placeholder={isHosted ? "Free-text input is restricted in hosted demo mode." : "Paste clinical note text here..."}
          value={text}
          disabled={isHosted}
          onChange={(e) => setText(e.target.value)}
        />

        {textError && <p className="text-red-500 text-sm w-full">{textError}</p>}

        <div className="flex gap-3 flex-wrap justify-center w-full">
          <button
            onClick={handleSubmitText}
            disabled={!capabilitiesChecked || !text.trim() || textLoading || isHosted}
            title={isHosted ? "Free-text extraction is disabled in the public sandbox" : undefined}
            className="px-6 py-2 bg-cyan-600 text-white rounded-lg text-sm font-medium hover:bg-cyan-700 disabled:opacity-50"
          >
            {textLoading ? "Processing..." : "Extract & Review →"}
          </button>
          {!isHosted && (
            <button
              onClick={() => setText(SAMPLE_NOTE)}
              className="px-4 py-2 border border-slate-300 text-slate-600 rounded-lg text-sm hover:bg-slate-100"
            >
              Load sample note
            </button>
          )}
          <button
            onClick={handleSeedDemo}
            disabled={textLoading || !capabilitiesChecked}
            className="px-4 py-2 bg-slate-800 text-white font-medium rounded-lg text-sm hover:bg-slate-700 disabled:opacity-50"
          >
            {isHosted ? "Seed Showcase Scenarios (10 Notes)" : "Seed demo data"}
          </button>
        </div>

        {/* Precomputed scenarios cards for hosted mode */}
        {isHosted && scenarios.length > 0 && (
          <div className="w-full bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-800 mb-2">
              Curated Showcase Scenarios ({scenarios.length})
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-60 overflow-y-auto pr-1">
              {scenarios.map((sc) => (
                <div
                  key={sc.filename}
                  className="p-2.5 border border-slate-200 rounded text-xs bg-slate-50 flex flex-col justify-between"
                >
                  <div className="font-semibold text-slate-800 mb-1 flex items-center justify-between">
                    <span>{sc.title}</span>
                    {sc.has_issues && (
                      <span className="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-medium">
                        {sc.issues_count} canary flag{sc.issues_count > 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                  <p className="text-slate-500 line-clamp-2 leading-relaxed">{sc.snippet}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Batch file drop zone (disabled in hosted mode) */}
        {!isHosted && (
        <div className="w-full">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => !uploading && fileRef.current?.click()}
            className={`w-full border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
              dragging
                ? "border-cyan-400 bg-cyan-50"
                : "border-slate-300 hover:border-cyan-300"
            } ${uploading ? "pointer-events-none opacity-60" : ""}`}
          >
            <p className="text-slate-500 text-sm">
              Drop files here, or click to browse
            </p>
            <p className="text-slate-400 text-xs mt-1">
              .txt · .pdf · .png · .jpg · .jpeg · .tiff · .tif — multiple files OK
            </p>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.pdf,.png,.jpg,.jpeg,.tiff,.tif"
              multiple
              className="hidden"
              onChange={handleFileInput}
            />
          </div>

          {/* File list */}
          {files.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {files.map((entry, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm px-3 py-2 bg-white border border-slate-200 rounded-md"
                >
                  <span className="text-slate-700 truncate max-w-[60%]">{entry.file.name}</span>
                  <span
                    className={`text-xs font-medium ml-2 ${
                      entry.status.phase === "done"
                        ? "text-green-600"
                        : entry.status.phase === "error"
                        ? "text-red-500"
                        : entry.status.phase === "uploading"
                        ? "text-cyan-500"
                        : "text-slate-400"
                    }`}
                  >
                    {entry.status.phase === "done" && "✓ done"}
                    {entry.status.phase === "error" && `✗ ${entry.status.message}`}
                    {entry.status.phase === "uploading" && "uploading..."}
                    {entry.status.phase === "queued" && "queued"}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Upload controls */}
          {files.length > 0 && !allFinished && (
            <div className="mt-3 flex gap-2">
              {!uploading ? (
                <button
                  onClick={async () => {
                    const { firstSuccessResult } = await startUpload();
                    if (firstSuccessResult) setFirstUploadResult(firstSuccessResult);
                  }}
                  className="px-5 py-2 bg-cyan-600 text-white rounded-lg text-sm font-medium hover:bg-cyan-700"
                >
                  Upload {queuedCount} file{queuedCount !== 1 ? "s" : ""}
                </button>
              ) : (
                <button
                  onClick={() => { cancelRef.current = true; }}
                  className="px-5 py-2 border border-slate-300 text-slate-600 rounded-lg text-sm hover:bg-slate-100"
                >
                  Cancel remaining
                </button>
              )}
              <button
                onClick={() => { setFiles([]); setFirstUploadResult(null); }}
                disabled={uploading}
                className="px-3 py-2 border border-slate-200 text-slate-400 rounded-lg text-sm hover:bg-slate-50 disabled:opacity-40"
              >
                Clear
              </button>
            </div>
          )}

          {/* Summary + Start Reviewing */}
          {allFinished && (
            <div className="mt-3 flex items-center gap-4">
              <p className="text-sm text-slate-600">
                {doneCount} uploaded{errorCount > 0 ? `, ${errorCount} failed` : ""}
              </p>
              {firstSuccessNoteId !== null && (
                <button
                  onClick={() => {
                    const r = firstUploadResult;
                    const isOcr = r?.source === "ocr";
                    const lowConf = isOcr && r?.ocr_confidence != null && r.ocr_confidence < 0.7;
                    if (lowConf && r) {
                      navigate(`/review/${r.note_id}/preview`, {
                        state: { rawText: r.raw_text, ocrConfidence: r.ocr_confidence },
                      });
                    } else {
                      navigate(`/review/${firstSuccessNoteId}`);
                    }
                  }}
                  className="px-5 py-2 bg-cyan-600 text-white rounded-lg text-sm font-medium hover:bg-cyan-700"
                >
                  Start Reviewing →
                </button>
              )}
              <button
                onClick={() => { setFiles([]); setFirstUploadResult(null); }}
                className="px-3 py-2 border border-slate-200 text-slate-400 rounded-lg text-sm hover:bg-slate-50"
              >
                Clear
              </button>
            </div>
          )}
        </div>
        )}
      </main>
    </div>
  );
}
