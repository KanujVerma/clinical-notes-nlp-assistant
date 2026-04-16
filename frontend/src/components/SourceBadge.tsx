// frontend/src/components/SourceBadge.tsx
const BADGE_STYLES: Record<string, string> = {
  txt:   "bg-slate-100 text-slate-600 border-slate-200",
  pdf:   "bg-blue-50 text-blue-600 border-blue-200",
  ocr:   "bg-slate-900 text-sky-400 border-cyan-800",
  paste: "bg-gray-100 text-gray-500 border-gray-200",
  demo:  "bg-purple-50 text-purple-600 border-purple-200",
};

export default function SourceBadge({ source }: { source: string }) {
  const style = BADGE_STYLES[source] ?? "bg-slate-100 text-slate-500 border-slate-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider border ${style}`}>
      {source}
    </span>
  );
}
