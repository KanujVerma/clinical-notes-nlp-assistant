import { useState, useRef } from 'react';
import { lookupMedication, lookupAbbreviations, isAbbreviationDenylisted } from '../lib/explainerLookup';
import ExplainerPopover from './ExplainerPopover';

interface ExplainerTriggerProps {
  value: string;
  kind: 'medication' | 'abbreviation';
  aiAvailable?: boolean;
  onRequestAi?: (kind: 'medication' | 'abbreviation', value: string, context?: object) => void;
}

export default function ExplainerTrigger({ value, kind, aiAvailable, onRequestAi }: ExplainerTriggerProps) {
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  // Run lookup
  const medEntry = kind === 'medication' ? lookupMedication(value) : null;
  const abbrevEntries = kind === 'abbreviation' ? lookupAbbreviations(value) : [];

  const hasDictionaryEntry = !!medEntry || abbrevEntries.length > 0;
  if (!hasDictionaryEntry) {
    if (kind === 'abbreviation' && isAbbreviationDenylisted(value)) {
      return null;  // suppress icon for obvious non-shorthand tokens
    }
    // medication misses and non-denylisted abbreviation misses: fall through and render icon
  }

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (popoverPos) {
      setPopoverPos(null); // toggle close
    } else {
      const rect = btnRef.current?.getBoundingClientRect();
      if (rect) {
        setPopoverPos({ top: rect.bottom + 4, left: rect.left });
      }
    }
  };

  return (
    <span className="inline-flex items-center ml-0.5">
      <button
        ref={btnRef}
        onClick={handleClick}
        aria-label="Show explanation"
        className="text-slate-400 hover:text-slate-600 cursor-pointer focus:outline-none"
      >
        {/* Info icon — inline SVG, 12px, stroke-current, matching project icon style */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      </button>
      {popoverPos && (
        <ExplainerPopover
          top={popoverPos.top}
          left={popoverPos.left}
          medication={medEntry ?? undefined}
          abbreviations={abbrevEntries.length > 0 ? abbrevEntries : undefined}
          onClose={() => setPopoverPos(null)}
          hasDictionaryEntry={hasDictionaryEntry}
          kind={kind}
          aiAvailable={aiAvailable}
          onRequestAi={onRequestAi}
        />
      )}
    </span>
  );
}
