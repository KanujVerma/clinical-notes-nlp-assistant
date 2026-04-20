import { useEffect, useRef } from 'react';
import type { AiExplanation } from '../lib/aiExplain';

interface AIExplanationModalProps {
  term: string;
  loading: boolean;
  explanation?: AiExplanation;
  error?: string;
  onClose: () => void;
}

export default function AIExplanationModal({
  term,
  loading,
  explanation,
  error,
  onClose,
}: AIExplanationModalProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (cardRef.current && !cardRef.current.contains(e.target as Node)) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-slate-900/50 z-50"
      onMouseDown={handleBackdropClick}
    >
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        data-testid="modal"
        className="bg-white border border-slate-200 rounded-lg shadow-lg p-4 max-w-md w-[92vw]"
        onMouseDown={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <span className="font-semibold text-sm text-slate-800">{term}</span>
          <button
            aria-label="Close"
            onClick={onClose}
            className="text-slate-300 hover:text-slate-400 text-xs leading-none shrink-0 mt-px"
          >
            ×
          </button>
        </div>

        {/* Body */}
        {loading && (
          <p className="text-xs text-slate-500 animate-pulse">Generating explanation…</p>
        )}

        {!loading && error && (
          <p className="text-xs text-red-500">
            {error ?? 'Could not generate explanation. Please try again.'}
          </p>
        )}

        {!loading && !error && explanation && (
          <div className="flex flex-col gap-0.5 mb-1.5">
            <div className="flex gap-2 text-xs">
              <span className="text-slate-500 shrink-0">What it is</span>
              <span className="text-slate-800">{explanation.whatItIs}</span>
            </div>
            <div className="flex gap-2 text-xs">
              <span className="text-slate-500 shrink-0">Common use</span>
              <span className="text-slate-800">{explanation.commonUse}</span>
            </div>
            <div className="flex gap-2 text-xs">
              <span className="text-slate-500 shrink-0">Plain language</span>
              <span className="text-slate-800">{explanation.plainLanguage}</span>
            </div>
            {explanation.uncertainty && (
              <div className="flex gap-2 text-xs">
                <span className="text-slate-500 shrink-0">Context note</span>
                <span className="text-slate-800 italic">{explanation.uncertainty}</span>
              </div>
            )}
          </div>
        )}

        {/* Disclaimer */}
        <p className="text-[10px] italic text-slate-500">
          AI-generated explanation for informational review only — not medical advice.
        </p>
      </div>
    </div>
  );
}
