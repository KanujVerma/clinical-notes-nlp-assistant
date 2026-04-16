// frontend/src/components/NoteViewer.tsx
import { ExtractionResult } from "../types";

interface Span { start: number; end: number; category: string; label: string; }

const COLORS: Record<string, string> = {
  vitals: "bg-blue-100 text-blue-900",
  medications: "bg-green-100 text-green-900",
  instructions: "bg-amber-100 text-amber-900",
  metadata: "bg-purple-100 text-purple-900",
};

function collectSpans(extracted: ExtractionResult): Span[] {
  const spans: Span[] = [];
  Object.entries(extracted.vitals).forEach(([k, v]) => {
    if (v?.span) spans.push({ start: v.span[0], end: v.span[1], category: "vitals", label: k });
  });
  extracted.medications.forEach((m) => {
    if (m?.span) spans.push({ start: m.span[0], end: m.span[1], category: "medications", label: m.name });
  });
  Object.entries(extracted.instructions).forEach(([k, v]) => {
    if (v?.span) spans.push({ start: v.span[0], end: v.span[1], category: "instructions", label: k });
  });
  Object.entries(extracted.metadata).forEach(([k, v]) => {
    if (v?.span) spans.push({ start: v.span[0], end: v.span[1], category: "metadata", label: k });
  });
  return spans.sort((a, b) => a.start - b.start);
}

export default function NoteViewer({ rawText, extracted }: { rawText: string; extracted: ExtractionResult }) {
  const spans = collectSpans(extracted);
  const parts: JSX.Element[] = [];
  let pos = 0;

  for (const span of spans) {
    if (span.start > pos) {
      parts.push(<span key={`text-${pos}`}>{rawText.slice(pos, span.start)}</span>);
    }
    if (span.end > span.start) {
      const color = COLORS[span.category] || "bg-slate-100";
      parts.push(
        <mark key={`mark-${span.start}`} title={`${span.category}: ${span.label}`}
          className={`rounded px-0.5 ${color} cursor-help`}>
          {rawText.slice(span.start, span.end)}
        </mark>
      );
      pos = span.end;
    }
  }
  if (pos < rawText.length) {
    parts.push(<span key="text-end">{rawText.slice(pos)}</span>);
  }

  return (
    <div className="h-full overflow-y-auto p-4 font-mono text-sm whitespace-pre-wrap leading-relaxed text-slate-700">
      {parts}
    </div>
  );
}
