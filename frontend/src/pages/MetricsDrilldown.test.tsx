import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MetricsDrilldown from "./MetricsDrilldown";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: { getMetricDrilldown: vi.fn() },
}));

function renderRoute(query: string) {
  return render(
    <MemoryRouter initialEntries={["/metrics/drilldown?" + query]}>
      <Routes>
        <Route path="/metrics/drilldown" element={<MetricsDrilldown />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MetricsDrilldown current evidence navigation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("links a scoped issue to the exact note and issue drawer", async () => {
    vi.mocked(api.getMetricDrilldown).mockResolvedValue({
      kind: "issues",
      title: "Warning issues (open)",
      count_returned: 1,
      has_more: false,
      max_rows: 50,
      contains_raw_source: false,
      current_binding_only: true,
      rows: [{
        kind: "issue",
        note_id: 42,
        source_revision_id: "rev-42",
        extraction_id: "ext-42",
        issue_id: "11111111-1111-1111-1111-111111111111",
        label: "SYNTHETIC_CANARY",
        severity: "warning",
        detail: "Source review recommended",
      }],
    });
    renderRoute("kind=issues&severity=warning&state=open");
    expect(await screen.findByRole("heading", { name: "Warning issues (open)" })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Inspect source and evidence for note 42/ });
    expect(link).toHaveAttribute("href", "/review/42?issue=11111111-1111-1111-1111-111111111111");
    expect(screen.getByText("Source review recommended")).toBeInTheDocument();
    expect(screen.queryByText(/raw patient/i)).toBeNull();
    expect(api.getMetricDrilldown).toHaveBeenCalledWith({
      kind: "issues", severity: "warning", state: "open",
    });
  });

  it("deep links a corrected field while excluding raw values", async () => {
    vi.mocked(api.getMetricDrilldown).mockResolvedValue({
      kind: "corrections",
      title: "Corrected field: vitals.blood_pressure",
      count_returned: 1,
      has_more: false,
      max_rows: 50,
      contains_raw_source: false,
      current_binding_only: true,
      rows: [{
        kind: "corrections", note_id: 12,
        source_revision_id: "rev", extraction_id: "ext",
        review_event_id: "event-123", field_path: "vitals.blood_pressure",
        label: "Reviewed Corrected", detail: "1 changed field group",
      }],
    });
    renderRoute("kind=corrections&field=vitals.blood_pressure");
    expect(await screen.findByRole("heading", { name: /Corrected field: vitals.blood_pressure/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Inspect source and evidence for note 12/ }))
      .toHaveAttribute("href", "/review/12?field=vitals.blood_pressure");
  });

  it("renders an accessible empty state when no current notes match", async () => {
    vi.mocked(api.getMetricDrilldown).mockResolvedValue({
      kind: "issues", title: "No current warning", rows: [], count_returned: 0,
      has_more: false, max_rows: 50, current_binding_only: true,
      contains_raw_source: false,
    });
    renderRoute("kind=issues&severity=warning");
    expect(await screen.findByText("No current records match this filter.")).toBeInTheDocument();
  });
});
