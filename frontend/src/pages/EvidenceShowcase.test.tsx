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
};

function renderPage() {
  return render(<MemoryRouter><EvidenceShowcase /></MemoryRouter>);
}

describe("EvidenceShowcase", () => {
  beforeEach(() => vi.resetAllMocks());

  it("labels the real OCR baseline and never invents local model results", async () => {
    vi.mocked(api.getPublicShowcaseEvidence).mockResolvedValue(example as never);
    renderPage();
    expect(await screen.findByText("Recorded Tesseract OCR baseline")).toBeInTheDocument();
    expect(screen.getByText("3.83%")).toBeInTheDocument();
    expect(screen.getByText("27.14%")).toBeInTheDocument();
    expect(screen.getByText("11/11")).toBeInTheDocument();
    expect(screen.getByText(/No reviewed local-model recordings are published/i)).toBeInTheDocument();
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
