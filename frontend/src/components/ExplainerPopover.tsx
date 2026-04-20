import { useEffect, useRef } from 'react';
import type { MedicationExplanation } from '../data/medicationExplanations';
import type { AbbreviationExplanation } from '../data/clinicalAbbreviations';

interface ExplainerPopoverProps {
  top: number;
  left: number;
  medication?: MedicationExplanation;
  abbreviations?: AbbreviationExplanation[];
  onClose: () => void;
}

export default function ExplainerPopover({
  top,
  left,
  medication,
  abbreviations,
  onClose,
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
      className="fixed z-50 max-w-[280px] bg-white border border-slate-200 rounded-lg shadow-lg p-3"
      style={{ top, left }}
    >
      {/* Header row: term name + close button */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="font-semibold text-sm text-slate-800">{termName}</span>
        <button
          aria-label="Close"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 leading-none shrink-0"
        >
          ×
        </button>
      </div>

      {/* Medication rows */}
      {medication && (
        <div className="flex flex-col gap-1 mb-2">
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
      {abbreviations && abbreviations.length > 0 && (
        <div className="flex flex-col gap-1 mb-2">
          {abbreviations.map((abbrev) => (
            <div key={abbrev.abbreviation} className="flex gap-2 text-xs">
              <span className="text-slate-500 shrink-0">{abbrev.abbreviation}</span>
              <span className="text-slate-800">{abbrev.expansion}</span>
            </div>
          ))}
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-[10px] italic text-slate-500">
        Informational only — not medical advice.
      </p>
    </div>
  );
}
