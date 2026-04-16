// frontend/src/components/StatusBadge.tsx
const styles = {
  pending: "bg-slate-100 text-slate-600",
  accepted: "bg-green-100 text-green-700",
  corrected: "bg-amber-100 text-amber-700",
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = styles[status as keyof typeof styles] ?? styles.pending;
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>{status}</span>;
}
