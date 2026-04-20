import { MEDICATION_EXPLANATIONS, MedicationExplanation } from '../data/medicationExplanations';
import { CLINICAL_ABBREVIATIONS, AbbreviationExplanation } from '../data/clinicalAbbreviations';

const ABBREVIATION_DENYLIST = new Set([
  'daily', 'once', 'twice', 'tablet', 'tablets', 'capsule', 'capsules',
]);

export function isAbbreviationDenylisted(value: string): boolean {
  if (!value.trim()) return false;
  const tokens = value.trim().split(/[\s/]+/);
  return tokens.some(token => {
    const normalized = token.toLowerCase().replace(/[.,;:]+$/, '');
    return ABBREVIATION_DENYLIST.has(normalized);
  });
}

export function lookupMedication(value: string): MedicationExplanation | null {
  if (!value) return null;
  return MEDICATION_EXPLANATIONS[value.toLowerCase().trim()] ?? null;
}

export function lookupAbbreviations(value: string): AbbreviationExplanation[] {
  if (!value.trim()) return [];
  const tokens = value.trim().split(/[\s/]+/);
  const results: AbbreviationExplanation[] = [];
  for (const token of tokens) {
    const key = token.toLowerCase().replace(/[.,;:]+$/, '');
    const entry = CLINICAL_ABBREVIATIONS[key];
    if (entry && !results.includes(entry)) {
      results.push(entry);
    }
  }
  return results;
}
