export interface AiExplanation {
  whatItIs: string;
  commonUse: string;
  plainLanguage: string;
  uncertainty?: string;
}

export interface AiExplainRequest {
  kind: 'medication' | 'abbreviation';
  value: string;
  context?: {
    dose?: string;
    route?: string;
    frequency?: string;
    duration?: string;
    qualifier?: string;
    medicationName?: string;
  };
}

export interface AiExplainResponse {
  explanation: AiExplanation;
  modelUsed: string;
}

export interface AiStatusResponse {
  available: boolean;
}
