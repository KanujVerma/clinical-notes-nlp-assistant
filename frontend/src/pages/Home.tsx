// frontend/src/pages/Home.tsx
import { useState, useRef } from "react";
import React from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function Home() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

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

  async function handleSubmitText() {
    if (!text.trim()) return;
    setLoading(true); setError(null);
    try {
      const { note_id, extracted_json } = await api.createNote(text);
      navigate("/review", { state: { note_id, extracted_json, raw_text: text } });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleFile(file: File) {
    setLoading(true); setError(null);
    try {
      const { note_id, extracted_json } = await api.uploadFile(file);
      // Fetch the note detail to get the raw_text (not part of extraction output)
      const detail = await api.getNoteDetail(note_id);
      navigate("/review", { state: { note_id, extracted_json, raw_text: detail.raw_text } });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  async function handleSeedDemo() {
    setLoading(true);
    try {
      const result = await api.seedDemo();
      alert(`Seeded: ${result.loaded} loaded, ${result.skipped} already existed. Check History.`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-slate-800 text-slate-100 px-6 py-2.5 flex items-center justify-between">
        <div>
          <span className="font-semibold text-sm tracking-wide">Clinical Notes NLP Assistant</span>
          <p className="text-xs text-slate-500 mt-0.5">Demo mode — all data is synthetic</p>
        </div>
        <nav className="flex gap-4 text-sm text-slate-400">
          <a href="/history" className="hover:text-slate-200 transition-colors">History</a>
          <a href="/metrics" className="hover:text-slate-200 transition-colors">Metrics</a>
        </nav>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center p-6 gap-6 max-w-3xl mx-auto w-full">
        <div className="text-center">
          <h2 className="text-2xl font-semibold text-slate-800">Extract structured data from a clinical note</h2>
          <p className="text-slate-500 mt-1">Paste note text, upload a .txt or .pdf file, or load a sample note.</p>
        </div>

        {/* Text area */}
        <textarea
          className="w-full h-48 border border-slate-300 rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 text-slate-900 leading-relaxed"
          placeholder="Paste clinical note text here..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`w-full border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors
            ${dragging ? "border-blue-400 bg-blue-50" : "border-slate-300 hover:border-blue-300"}`}
        >
          <p className="text-slate-500 text-sm">Drop a .txt, .pdf, or image file here, or click to browse</p>
          <input ref={fileRef} type="file" accept=".txt,.pdf,.png,.jpg,.jpeg,.tiff,.tif" className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
        </div>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <div className="flex gap-3 flex-wrap justify-center">
          <button onClick={handleSubmitText} disabled={!text.trim() || loading}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {loading ? "Processing..." : "Extract →"}
          </button>
          <button onClick={() => setText(SAMPLE_NOTE)}
            className="px-4 py-2 border border-slate-300 text-slate-600 rounded-lg text-sm hover:bg-slate-100">
            Load sample note
          </button>
          <button onClick={handleSeedDemo} disabled={loading}
            className="px-4 py-2 border border-slate-300 text-slate-500 rounded-lg text-sm hover:bg-slate-100">
            Seed demo data
          </button>
        </div>
      </main>
    </div>
  );
}
