import { useState, useRef, useEffect } from 'react';
import { lookupMedication, lookupAbbreviations, isAbbreviationDenylisted } from '../lib/explainerLookup';
import ExplainerPopover from './ExplainerPopover';
import { useAiAvailable } from '../lib/aiStatus';
import { api } from '../api/client';
import type { AiExplanation } from '../lib/aiExplain';
import AIExplanationModal from './AIExplanationModal';

interface ExplainerTriggerProps {
  value: string;
  kind: 'medication' | 'abbreviation';
}

export default function ExplainerTrigger({ value, kind }: ExplainerTriggerProps) {
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const mountedRef = useRef(false);

  const aiAvailable = useAiAvailable();

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const [aiModal, setAiModal] = useState<{
    term: string;
    kind: 'medication' | 'abbreviation';
    context?: object;
  } | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiExplanation, setAiExplanation] = useState<AiExplanation | undefined>(undefined);
  const [aiError, setAiError] = useState<string | undefined>(undefined);

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

  const handleRequestAi = (kind: 'medication' | 'abbreviation', termValue: string) => {
    setPopoverPos(null);                  // close popover
    setAiModal({ term: termValue, kind });
    setAiLoading(true);
    setAiExplanation(undefined);
    setAiError(undefined);

    api.aiExplain({ kind, value: termValue, context: undefined })
      .then(r => {
        if (!mountedRef.current) return;
        setAiLoading(false);
        setAiExplanation(r.explanation);
      })
      .catch(e => {
        if (!mountedRef.current) return;
        setAiLoading(false);
        setAiError(e instanceof Error ? e.message : 'Could not generate explanation.');
      });
  };

  return (
    <span className="inline-flex items-center ml-0.5">
      <button
        ref={btnRef}
        onClick={handleClick}
        aria-label="Show explanation"
        data-testid="info-button"
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
          onRequestAi={handleRequestAi}
        />
      )}
      {aiModal && (
        <AIExplanationModal
          term={aiModal.term}
          loading={aiLoading}
          explanation={aiExplanation}
          error={aiError}
          onClose={() => {
            setAiModal(null);
            setAiLoading(false);
            setAiExplanation(undefined);
            setAiError(undefined);
          }}
        />
      )}
    </span>
  );
}
