import { lookupMedication, lookupAbbreviations, isAbbreviationDenylisted } from './explainerLookup';

describe('lookupMedication', () => {
  it('returns entry for an exact lowercase match', () => {
    const result = lookupMedication('metformin');
    expect(result).not.toBeNull();
    expect(result?.name).toBe('Metformin');
  });

  it('is case-insensitive', () => {
    expect(lookupMedication('Metformin')).not.toBeNull();
    expect(lookupMedication('METFORMIN')).not.toBeNull();
  });

  it('returns null for an unknown drug', () => {
    expect(lookupMedication('unknowndrug')).toBeNull();
  });

  it('returns null for an empty string', () => {
    expect(lookupMedication('')).toBeNull();
  });
});

describe('lookupAbbreviations', () => {
  it('returns one entry for a single known abbreviation', () => {
    const result = lookupAbbreviations('BID');
    expect(result).toHaveLength(1);
    expect(result[0].abbreviation).toBe('BID');
  });

  it('returns multiple entries for a multi-token value', () => {
    const result = lookupAbbreviations('q6h PRN');
    expect(result).toHaveLength(2);
    expect(result.map(r => r.abbreviation)).toContain('q6h');
    expect(result.map(r => r.abbreviation)).toContain('PRN');
  });

  it('returns empty array for unrecognised tokens', () => {
    expect(lookupAbbreviations('2 tabs')).toHaveLength(0);
  });

  it('returns empty array for empty string', () => {
    expect(lookupAbbreviations('')).toHaveLength(0);
  });

  it('is case-insensitive', () => {
    expect(lookupAbbreviations('bid')).toHaveLength(1);
    expect(lookupAbbreviations('BID')).toHaveLength(1);
  });
});

describe('isAbbreviationDenylisted', () => {
  it('returns true for "daily"', () => {
    expect(isAbbreviationDenylisted('daily')).toBe(true);
  });

  it('returns true for "twice daily"', () => {
    expect(isAbbreviationDenylisted('twice daily')).toBe(true);
  });

  it('returns true for "2 tablets"', () => {
    expect(isAbbreviationDenylisted('2 tablets')).toBe(true);
  });

  it('returns true for "once a day"', () => {
    expect(isAbbreviationDenylisted('once a day')).toBe(true);
  });

  it('returns false for "BID"', () => {
    expect(isAbbreviationDenylisted('BID')).toBe(false);
  });

  it('returns false for "q6h"', () => {
    expect(isAbbreviationDenylisted('q6h')).toBe(false);
  });

  it('returns false for "with meals"', () => {
    expect(isAbbreviationDenylisted('with meals')).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(isAbbreviationDenylisted('')).toBe(false);
  });
});
