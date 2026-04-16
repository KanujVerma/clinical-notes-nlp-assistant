// frontend/src/types.ts

export interface FieldValue {
  value: string;
  span: [number, number];
  source: "regex" | "medspacy" | "section" | "fallback";
  confidence: number;
}

export interface Medication {
  name: string;
  dose: string;
  route: string;
  frequency: string;
  span: [number, number];
  source: string;
  confidence: number;
}

export interface Instructions {
  discharge_instructions?: FieldValue;
  follow_up?: FieldValue;
  return_precautions?: FieldValue;
}

export interface Vitals {
  blood_pressure?: FieldValue;
  heart_rate?: FieldValue;
  temperature?: FieldValue;
  respiratory_rate?: FieldValue;
  oxygen_saturation?: FieldValue;
  weight?: FieldValue;
}

export interface Metadata {
  patient_name?: FieldValue;
  date_of_service?: FieldValue;
  provider_name?: FieldValue;
}

export interface ExtractionResult {
  pipeline_version: string;
  vitals: Vitals;
  medications: Medication[];
  instructions: Instructions;
  metadata: Metadata;
}

export interface NoteListItem {
  id: number;
  filename: string | null;
  source: string;
  created_at: string;
  status: "pending" | "accepted" | "corrected";
  correction_count: number;
}

export interface NoteDetail {
  id: number;
  filename: string | null;
  raw_text: string;
  source: string;
  created_at: string;
  extracted_json: ExtractionResult | null;
  pipeline_version: string | null;
  validation: {
    status: string;
    validated_json: ExtractionResult;
    correction_count: number;
    review_duration_ms: number | null;
  } | null;
}

export interface MetricsResponse {
  eval: {
    run_at: string;
    pipeline_version: string;
    overall: { precision: number; recall: number; f1: number };
    by_category: Record<string, { precision: number; recall: number; f1: number }>;
    per_note: Array<{ note: string; vitals_f1: number; medications_f1: number; instructions_f1: number; metadata_f1: number }>;
  } | null;
  db_stats: {
    by_status: Array<{ status: string; count: number; avg_corrections: number; avg_review_ms: number }>;
    correction_rates?: {
      by_category: Record<string, { reviewed: number; corrected: number; rate: number }>;
      by_field: Record<string, { reviewed: number; corrected: number; rate: number }>;
    };
  };
}

export interface QueueNote {
  id: number;
  filename: string | null;
  source: string;
  created_at: string;
}

export interface QueueResponse {
  notes: QueueNote[];
  count: number;
}
