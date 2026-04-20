export interface AbbreviationExplanation {
  abbreviation: string;  // display form (e.g. "BID")
  expansion: string;     // plain English expansion
  category: 'frequency' | 'route' | 'qualifier' | 'vital';
}

export const CLINICAL_ABBREVIATIONS: Record<string, AbbreviationExplanation> = {
  bid: {
    abbreviation: "BID",
    expansion: "Twice daily",
    category: "frequency",
  },
  tid: {
    abbreviation: "TID",
    expansion: "Three times daily",
    category: "frequency",
  },
  qid: {
    abbreviation: "QID",
    expansion: "Four times daily",
    category: "frequency",
  },
  q4h: {
    abbreviation: "q4h",
    expansion: "Every 4 hours",
    category: "frequency",
  },
  q6h: {
    abbreviation: "q6h",
    expansion: "Every 6 hours",
    category: "frequency",
  },
  q8h: {
    abbreviation: "q8h",
    expansion: "Every 8 hours",
    category: "frequency",
  },
  q12h: {
    abbreviation: "q12h",
    expansion: "Every 12 hours",
    category: "frequency",
  },
  q24h: {
    abbreviation: "q24h",
    expansion: "Every 24 hours (once daily)",
    category: "frequency",
  },
  qhs: {
    abbreviation: "qhs",
    expansion: "Every night at bedtime",
    category: "frequency",
  },
  qam: {
    abbreviation: "qam",
    expansion: "Every morning",
    category: "frequency",
  },
  qpm: {
    abbreviation: "qpm",
    expansion: "Every evening",
    category: "frequency",
  },
  qd: {
    abbreviation: "QD",
    expansion: "Once daily",
    category: "frequency",
  },
  prn: {
    abbreviation: "PRN",
    expansion: "As needed",
    category: "qualifier",
  },
  po: {
    abbreviation: "PO",
    expansion: "By mouth (orally)",
    category: "route",
  },
  iv: {
    abbreviation: "IV",
    expansion: "Intravenous (into the vein)",
    category: "route",
  },
  im: {
    abbreviation: "IM",
    expansion: "Intramuscular (into the muscle)",
    category: "route",
  },
  sq: {
    abbreviation: "SQ",
    expansion: "Subcutaneous (under the skin)",
    category: "route",
  },
  sl: {
    abbreviation: "SL",
    expansion: "Sublingual (under the tongue)",
    category: "route",
  },
  pr: {
    abbreviation: "PR",
    expansion: "Per rectum (rectally)",
    category: "route",
  },
  oral: {
    abbreviation: "oral",
    expansion: "By mouth (orally)",
    category: "route",
  },
  inhaled: {
    abbreviation: "inhaled",
    expansion: "By inhalation — breathed into the lungs",
    category: "route",
  },
  inhalation: {
    abbreviation: "inhalation",
    expansion: "By inhalation — breathed into the lungs",
    category: "route",
  },
  topical: {
    abbreviation: "topical",
    expansion: "Applied directly to the skin or mucosal surface",
    category: "route",
  },
  transdermal: {
    abbreviation: "transdermal",
    expansion: "Absorbed through the skin (patch or gel)",
    category: "route",
  },
  intranasal: {
    abbreviation: "intranasal",
    expansion: "Administered into the nasal passages",
    category: "route",
  },
  ophthalmic: {
    abbreviation: "ophthalmic",
    expansion: "Applied to or around the eye",
    category: "route",
  },
  otic: {
    abbreviation: "otic",
    expansion: "Applied into or around the ear canal",
    category: "route",
  },
  rectal: {
    abbreviation: "rectal",
    expansion: "Administered via the rectum",
    category: "route",
  },
  subcutaneous: {
    abbreviation: "subcutaneous",
    expansion: "Injected under the skin",
    category: "route",
  },
  sublingual: {
    abbreviation: "sublingual",
    expansion: "Dissolved under the tongue",
    category: "route",
  },
  subq: {
    abbreviation: "subq",
    expansion: "Subcutaneous — injected under the skin",
    category: "route",
  },
};
