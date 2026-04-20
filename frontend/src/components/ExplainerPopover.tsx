import { useEffect, useRef } from 'react';
import type { MedicationExplanation } from '../data/medicationExplanations';
import type { AbbreviationExplanation } from '../data/clinicalAbbreviations';

interface ExplainerPopoverProps {
  top: number;
  left: number;
  medication?: MedicationExplanation;
  abbreviations?: AbbreviationExplanation[];
  onClose: () => void;
  hasDictionaryEntry?: boolean;
  kind?: 'medication' | 'abbreviation';
  aiAvailable?: boolean;
  onRequestAi?: (kind: 'medication' | 'abbreviation', value: string, context?: object) => void;
}

export default function ExplainerPopover({
  top,
  left,
  medication,
  abbreviations,
  onClose,
  hasDictionaryEntry = true,
  kind,
  aiAvailable = false,
  onRequestAi,
}: ExplainerPopoverProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const handleMouseDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleMouseDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleMouseDown);
    };
  }, [onClose]);

  const termName = medication
    ? medication.name
    : abbreviations && abbreviations.length === 1
    ? abbreviations[0].abbreviation
    : 'Clinical Terms';

  return (
    <div
      ref={ref}
      data-testid="popover"
      className="fixed z-50 w-max max-w-[260px] bg-white border border-slate-200 rounded-lg shadow-lg p-2"
      style={{ top, left }}
    >
      {/* Header row: term name + close button */}
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="font-semibold text-sm text-slate-800">{termName}</span>
        <button
          aria-label="Close"
          onClick={onClose}
          className="text-slate-300 hover:text-slate-400 text-xs leading-none shrink-0 mt-px"
        >
          ×
        </button>
      </div>

      {/* Miss state: no built-in entry */}
      {!hasDictionaryEntry && (
        <p className="text-xs text-slate-500 italic mb-1.5">
          No built-in explanation available for this term.
        </p>
      )}

      {/* Medication rows */}
      {hasDictionaryEntry && medication && (
        <div className="flex flex-col gap-0.5 mb-1.5">
          <div className="flex gap-2 text-xs">
            <span className="text-slate-500 shrink-0">Description</span>
            <span className="text-slate-800">{medication.description}</span>
          </div>
          <div className="flex gap-2 text-xs">
            <span className="text-slate-500 shrink-0">Common use</span>
            <span className="text-slate-800">{medication.commonUse}</span>
          </div>
          <div className="flex gap-2 text-xs">
            <span className="text-slate-500 shrink-0">Drug class</span>
            <span className="text-slate-800">{medication.drugClass}</span>
          </div>
        </div>
      )}

      {/* Abbreviation rows */}
      {hasDictionaryEntry && abbreviations && abbreviations.length > 0 && (
        <div className="flex flex-col gap-0.5 mb-1.5">
          {abbreviations.map((abbrev) => (
            <div key={abbrev.abbreviation} className="flex gap-2 text-xs">
              <span className="text-slate-500 shrink-0">{abbrev.abbreviation}</span>
              <span className="text-slate-800">{abbrev.expansion}</span>
            </div>
          ))}
        </div>
      )}

      {/* Footer AI action row */}
      {kind && aiAvailable && onRequestAi && (
        <div className="mt-1.5 pt-1.5 border-t border-slate-100">
          {/* Medication hit: secondary action */}
          {kind === 'medication' && hasDictionaryEntry && (
            <button
              onClick={() => { onRequestAi(kind, termName ?? '', undefined); onClose(); }}
              className="text-[11px] text-slate-500 hover:text-slate-700 underline"
            >
              Explain in more detail →
            </button>
          )}
          {/* Any miss (either kind): primary action */}
          {!hasDictionaryEntry && (
            <button
              onClick={() => { onRequestAi(kind, termName ?? '', undefined); onClose(); }}
              className="text-[11px] bg-slate-700 text-white rounded px-2 py-0.5 hover:bg-slate-600"
            >
              Generate AI explanation
            </button>
          )}
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-[10px] italic text-slate-500">
        Informational only — not medical advice.
      </p>
    </div>
  );
}
