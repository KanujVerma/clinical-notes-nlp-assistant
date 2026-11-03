import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EvidenceShowcase from "./EvidenceShowcase";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: { getPublicShowcaseEvidence: vi.fn() },
}));

const example = {
  schema_version: "1",
  synthetic_only: true,
  ready_for_clinical_use: false,
  notice: "Synthetic-only sample",
  baseline: {
    status: "recorded_real_tesseract",
    model: "Tesseract",
    engine_version: "5.5.2",
    manifest_sha256: "a".repeat(64),
    case_count: 3,
    cer_micro: 0.038265,
    wer_micro: 0.271428,
    critical_token_hits: 11,
    critical_token_total: 11,
    limitations: "Not clinical validation",
    cases: [{
      case_id: "synthetic_print_decimal",
      source_sha256: "b".repeat(64),
      source_type: "printed_decimal",
      transcription: "Hold Warfarin 2.5 mg PO daily.",
      cer: 0.01,
      wer: 0.02,
      critical_tokens: [{ token: "2.5 mg", recognized: true }],
    }],
  },
  recorded_ai: {
    status: "not_recorded",
    models: [],
    message: "No approved AI recordings",
  },
  frozen_benchmark: {
    dataset_role: "frozen_printed_synthetic_image_benchmark",
    case_count: 24,
    attempted_cases: 24,
    valid_predictions: 24,
    exclusions: 0,
    medication_support: 23,
    vital_support: 5,
    manifest_sha256: "c".repeat(64),
    evidence_zip_sha256: "d".repeat(64),
    source_document: "docs/validation/PR8_REAL_THREE_ARM_RESULTS.md",
    matcher: "source_occurrence_first_bounded_assignment",
    raw_recordings_published: false as const,
    not_clinical_validation: true as const,
    limitations: "Not clinical validation",
    arms: [{
      id: "tesseract",
      label: "Tesseract 5.5.2 + parser",
      medication_tp: 11,
      medication_fp: 3,
      medication_fn: 12,
      medication_precision: 11 / 14,
      medication_recall: 11 / 23,
      medication_f1: 22 / 37,
      vital_tp: 4,
      vital_fp: 0,
      vital_fn: 1,
      vital_f1: 8 / 9,
      ocr_cer: 124 / 2896,
      ocr_wer: 164 / 494,
      ocr_available: true,
      critical_hits: 42,
      critical_total: 55,
    }, {
      id: "qwen3_vl",
      label: "Qwen3-VL 4B direct",
      medication_tp: 15,
      medication_fp: 8,
      medication_fn: 8,
      medication_precision: 15 / 23,
      medication_recall: 15 / 23,
      medication_f1: 30 / 46,
      vital_tp: 0,
      vital_fp: 7,
      vital_fn: 5,
      vital_f1: 0,
      ocr_cer: null,
      ocr_wer: null,
      ocr_available: false,
      critical_hits: null,
      critical_total: null,
    }],
    documented_failure_examples: [
      { case_id: "h21", arm: "qwen3_vl", summary: "Omitted PRN." },
    ],
  },
};

function renderPage() {
  return render(<MemoryRouter><EvidenceShowcase /></MemoryRouter>);
}

describe("EvidenceShowcase", () => {
  beforeEach(() => vi.resetAllMocks());

  it("labels the real OCR baseline and never invents local model results", async () => {
    vi.mocked(api.getPublicShowcaseEvidence).mockResolvedValue(example as never);
    renderPage();
    expect(await screen.findByText("Three OCR examples")).toBeInTheDocument();
    expect(screen.getByText("3.83%")).toBeInTheDocument();
    expect(screen.getByText("27.14%")).toBeInTheDocument();
    expect(screen.getByText("11/11")).toBeInTheDocument();
    expect(screen.getByText(/No reviewed local-model recordings are published/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "24-image comparison" })).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
    expect(screen.getByText("Not applicable")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open review queue" })).toHaveAttribute("href", "/queue");
  });

  it("shows curator-approved model proposals separately without calling inference", async () => {
    vi.mocked(api.getPublicShowcaseEvidence).mockResolvedValue({
      ...example,
      recorded_ai: {
        status: "recorded_model_proposals_unverified",
        message: "Still requires independent source review",
        models: [{
          adapter: "glm_ocr",
          model_digest: "sha256:" + "c".repeat(64),
          cases: [{
            case_id: "synthetic_print_decimal",
            source_sha256: "b".repeat(64),
            transcription: "Hold Warfarin 2.5 mg",
          }],
        }],
      },
    } as never);
    renderPage();
    expect(await screen.findByText(/Still requires independent source review/)).toBeInTheDocument();
    expect(screen.getByText("glm-ocr")).toBeInTheDocument();
    expect(screen.queryByText(/No reviewed local-model recordings are published/)).toBeNull();
  });

  it("reports unavailable evidence without showing invented stats", async () => {
    vi.mocked(api.getPublicShowcaseEvidence).mockRejectedValue(new Error("Evidence unavailable"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("Evidence unavailable");
    expect(screen.queryByText("11/11")).toBeNull();
  });
});
