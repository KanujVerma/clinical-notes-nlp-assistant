import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import OperationalIssuesDrawer from "./OperationalIssuesDrawer";

vi.mock("../api/client", () => ({
  api: {
    getCapabilities: vi.fn(async () => ({ mode: "local" })),
    getIssues: vi.fn(async () => []),
    requestAiCandidates: vi.fn(async () => ({
      job_id: "synthetic-job-001",
      status: "queued",
      adapter: "text",
      source_revision_id: "revision-001",
    })),
    getJob: vi.fn(async () => ({
      id: "synthetic-job-001",
      kind: "ai_inference",
      status: "succeeded",
      progress: 1,
      result: { inference_run_id: "synthetic-inference-001" },
    })),
    getAiCandidates: vi.fn(async () => [{
      id: "synthetic-inference-001",
      source_revision_id: "revision-001",
      is_current: true,
      status: "completed",
      model_name: "qwen3-vl:4b",
      task_type: "semantic_candidates",
      candidates: { medications: [{ name: "Synthetic Drug" }] },
      discrepancies: [{
        type: "dose_discrepancy",
        medication: "Synthetic Drug",
        detail: "Model disagreed with rules on dose",
      }],
    }]),
  },
}));

describe("OperationalIssuesDrawer durable AI jobs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getCapabilities).mockResolvedValue({ mode: "local" } as never);
  });

  it("queues a source-bound job and polls its completed immutable result", async () => {
    render(
      <OperationalIssuesDrawer
        noteId={7}
        revisionId="revision-001"
        extractionId="extraction-001"
        isOpen={true}
        onToggle={() => {}}
      />,
    );

    const button = await screen.findByRole("button", { name: /Request Proposals/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(api.requestAiCandidates).toHaveBeenCalledTimes(1);
    });
    const call = vi.mocked(api.requestAiCandidates).mock.calls[0];
    expect(call[0]).toBe(7);
    expect(call[1]).toMatchObject({
      adapter: "text",
      source_revision_id: "revision-001",
      extraction_id: "extraction-001",
      page_number: 1,
    });
    expect(call[1].idempotency_key).toBeTruthy();

    expect(await screen.findByText(/Model disagreed with rules on dose/i)).toBeInTheDocument();
    expect(api.getJob).toHaveBeenCalledWith("synthetic-job-001");
    expect(api.getAiCandidates).toHaveBeenCalledWith(7);
    expect(await screen.findByText(/Unverified AI candidate output/i)).toBeInTheDocument();
  });

  it("shows and focuses a resolved current-bound issue without increasing open count", async () => {
    vi.mocked(api.getIssues).mockResolvedValueOnce([{
      id: "11111111-1111-1111-1111-111111111111",
      note_id: 7,
      source_revision_id: "revision-001",
      extraction_id: "extraction-001",
      issue_code: "SYNTHETIC_CANARY",
      status: "resolved",
      severity: "warning",
      safe_explanation: "Synthetic source discrepancy resolved after review.",
    }] as never);

    render(
      <OperationalIssuesDrawer
        noteId={7}
        revisionId="revision-001"
        extractionId="extraction-001"
        focusedIssueId="11111111-1111-1111-1111-111111111111"
        isOpen={true}
        onToggle={() => {}}
      />,
    );
    const selected = await screen.findByLabelText("Selected issue SYNTHETIC_CANARY");
    expect(selected).toBeVisible();
    expect(selected).toHaveFocus();
    expect(screen.getByText("Disposition: resolved")).toBeInTheDocument();
    expect(screen.queryByText("No open issues detected for this revision.")).not.toBeInTheDocument();
    expect(screen.queryByText("1 open")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
  });

  it("blocks local inference controls in hosted mode", async () => {
    vi.mocked(api.getCapabilities).mockResolvedValueOnce({ mode: "hosted_demo" } as never);
    render(
      <OperationalIssuesDrawer
        noteId={7}
        revisionId="revision-001"
        extractionId="extraction-001"
        isOpen={true}
        onToggle={() => {}}
      />,
    );
    expect(await screen.findByText(/Live AI disabled in hosted sandbox/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Request Proposals/i })).not.toBeInTheDocument();
  });
});
