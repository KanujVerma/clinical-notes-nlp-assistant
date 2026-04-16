// frontend/src/components/NoteViewer.tsx
import { ExtractionResult } from "../types";

interface Span {
  start: number;
  end: number;
  category: "vitals" | "medications" | "instructions" | "metadata";
  fieldKey: string;  // matches FieldMap key: "vitals.bp", "med.0.name", "instr.follow_up", "meta.patient_name"
  label: string;     // human-readable, for title attribute
}

const CAT_BG: Record<string, string> = {
  vitals:       "bg-blue-100 text-blue-900",
  medications:  "bg-green-100 text-green-900",
  instructions: "bg-amber-100 text-amber-900",
  metadata:     "bg-violet-100 text-violet-900",
};

const CAT_BORDER_B: Record<string, string> = {
  vitals:       "border-blue-500",
  medications:  "border-green-500",
  instructions: "border-amber-400",
  metadata:     "border-violet-400",
};

const CAT_RING: Record<string, string> = {
  vitals:       "ring-blue-400",
  medications:  "ring-green-400",
  instructions: "ring-amber-300",
  metadata:     "ring-violet-400",
};

const SECTION_LABEL: Record<string, string> = {
  metadata:     "METADATA",
  vitals:       "VITALS",
  medications:  "MEDICATIONS",
  instructions: "INSTRUCTIONS",
};

function collectSpans(extracted: ExtractionResult): Span[] {
  const spans: Span[] = [];

  Object.entries(extracted.vitals).forEach(([k, v]) => {
    if (v?.span) spans.push({
      start: v.span[0], end: v.span[1],
      category: "vitals", fieldKey: `vitals.${k}`, label: k,
    });
  });

  extracted.medications.forEach((m, i) => {
    if (m?.span) spans.push({
      start: m.span[0], end: m.span[1],
      category: "medications", fieldKey: `med.${i}.name`, label: m.name,
    });
  });

  Object.entries(extracted.instructions).forEach(([k, v]) => {
    if (v?.span) spans.push({
      start: v.span[0], end: v.span[1],
      category: "instructions", fieldKey: `instr.${k}`, label: k,
    });
  });

  Object.entries(extracted.metadata).forEach(([k, v]) => {
    if (v?.span) spans.push({
      start: v.span[0], end: v.span[1],
      category: "metadata", fieldKey: `meta.${k}`, label: k,
    });
  });

  return spans.sort((a, b) => a.start - b.start);
}

interface Props {
  rawText: string;
  extracted: ExtractionResult;
  activeKey: string | null;
  onSpanClick: (fieldKey: string) => void;
}

export default function NoteViewer({ rawText, extracted, activeKey, onSpanClick }: Props) {
  const spans = collectSpans(extracted);
  const parts: React.JSX.Element[] = [];
  const seenCategories = new Set<string>();
  let pos = 0;

  for (const span of spans) {
    // Insert section divider on first occurrence of each category (in document order)
    if (!seenCategories.has(span.category)) {
      seenCategories.add(span.category);
      parts.push(
        <div key={`section-${span.category}`} className="border-t border-slate-100 mt-3 pt-2 mb-1">
          <span className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-400">
            {SECTION_LABEL[span.category]}
          </span>
        </div>
      );
    }

    // Plain text before this span
    if (span.start > pos) {
      parts.push(<span key={`text-${pos}`}>{rawText.slice(pos, span.start)}</span>);
    }

    // Highlighted span
    if (span.end > span.start) {
      const isActive = activeKey === span.fieldKey;
      parts.push(
        <mark
          key={`mark-${span.start}`}
          title={`${span.category}: ${span.label}`}
          onClick={() => onSpanClick(span.fieldKey)}
          className={[
            "rounded px-0.5 border-b-2 cursor-pointer transition-all duration-150",
            CAT_BG[span.category],
            CAT_BORDER_B[span.category],
            isActive ? `ring-2 ring-offset-0 ${CAT_RING[span.category]} font-semibold` : "",
          ].join(" ")}
        >
          {rawText.slice(span.start, span.end)}
        </mark>
      );
      pos = span.end;
    }
  }

  // Remaining text after last span
  if (pos < rawText.length) {
    parts.push(<span key="text-end">{rawText.slice(pos)}</span>);
  }

  return (
    <div className="h-full overflow-y-auto px-5 py-3.5 font-mono text-[11.5px] leading-[2] text-slate-900 whitespace-pre-wrap">
      {parts}
    </div>
  );
}
