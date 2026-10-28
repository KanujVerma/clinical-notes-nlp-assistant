import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DocumentSourceViewer from "./DocumentSourceViewer";
import { ExtractionResult } from "../types";

vi.mock("../api/client", () => ({
  api: {
    getPageImageBlob: vi.fn(async () => new Blob(["synthetic-image"], { type: "image/png" })),
  },
}));

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:synthetic-authorized-source"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
});

const mockExtracted: ExtractionResult = {
  vitals: {
    bp: { value: "120/80", unit: "mmHg", span: [10, 20] } as any,
  },
  medications: [
    {
      id: "med_1",
      source_occurrence_id: "med_1",
      name: "Metformin",
      dose: "500 mg",
      span: [30, 45],
      page_number: 1,
      bbox: [50, 100, 200, 140],
    } as any,
    {
      id: "med_2",
      source_occurrence_id: "med_2",
      name: "Warfarin",
      dose: "5 mg",
      span: [60, 75],
      page_number: 2,
      // No bbox provided (missing geometry)
    } as any,
  ],
  instructions: {},
  metadata: {},
};

const mockPages = [
  {
    page_number: 1,
    width: 600,
    height: 800,
    boxes: [
      { bbox: [50, 100, 200, 140], text: "Metformin 500 mg" },
    ],
  },
  {
    page_number: 2,
    width: 600,
    height: 800,
    boxes: [],
  },
];

describe("DocumentSourceViewer", () => {
  it("renders document viewer with navigation and controls", async () => {
    render(
      <DocumentSourceViewer
        noteId={101}
        rawText="Raw clinical text sample"
        extracted={mockExtracted}
        pages={mockPages}
        activeKey={null}
        onSpanClick={vi.fn()}
      />
    );

    expect(screen.getByTestId("document-source-viewer")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByTestId("rotate-btn")).toHaveTextContent("↻ 0°");
    expect(await screen.findByTestId("document-page-image")).toBeInTheDocument();
  });

  it("toggles between document image and transcript text view", async () => {
    render(
      <DocumentSourceViewer
        noteId={101}
        rawText="Raw clinical text sample"
        extracted={mockExtracted}
        pages={mockPages}
        activeKey={null}
        onSpanClick={vi.fn()}
      />
    );

    // Click transcript toggle
    fireEvent.click(screen.getByTestId("toggle-view-transcript"));
    expect(screen.getByText("Raw clinical text sample")).toBeInTheDocument();
    expect(screen.queryByTestId("document-page-image")).not.toBeInTheDocument();

    // Click back to document view
    fireEvent.click(screen.getByTestId("toggle-view-document"));
    expect(await screen.findByTestId("document-page-image")).toBeInTheDocument();
  });

  it("navigates between pages using previous and next buttons", async () => {
    render(
      <DocumentSourceViewer
        noteId={101}
        rawText="Raw clinical text sample"
        extracted={mockExtracted}
        pages={mockPages}
        activeKey={null}
        onSpanClick={vi.fn()}
      />
    );

    const nextBtn = screen.getByTestId("page-next-btn");
    fireEvent.click(nextBtn);
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();

    const prevBtn = screen.getByTestId("page-prev-btn");
    fireEvent.click(prevBtn);
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  });

  it("rotates document page and updates rotation angle", async () => {
    render(
      <DocumentSourceViewer
        noteId={101}
        rawText="Raw clinical text sample"
        extracted={mockExtracted}
        pages={mockPages}
        activeKey={null}
        onSpanClick={vi.fn()}
      />
    );

    const rotateBtn = screen.getByTestId("rotate-btn");
    fireEvent.click(rotateBtn);
    expect(screen.getByTestId("rotate-btn")).toHaveTextContent("↻ 90°");

    fireEvent.click(rotateBtn);
    expect(screen.getByTestId("rotate-btn")).toHaveTextContent("↻ 180°");
  });

  it("renders bounding box overlay and responds to span click", async () => {
    const onSpanClick = vi.fn();
    render(
      <DocumentSourceViewer
        noteId={101}
        rawText="Raw clinical text sample"
        extracted={mockExtracted}
        pages={mockPages}
        activeKey="med.med_1.name"
        onSpanClick={onSpanClick}
      />
    );

    // Simulate image loaded
    fireEvent.load(await screen.findByTestId("document-page-image"));

    const overlayBox = screen.getByTestId("overlay-box-med.med_1.name");
    expect(overlayBox).toBeInTheDocument();
    fireEvent.click(overlayBox);
    expect(onSpanClick).toHaveBeenCalledWith("med.med_1.name");
  });

  it("displays missing geometry alert when active item lacks bounding box", async () => {
    render(
      <DocumentSourceViewer
        noteId={101}
        rawText="Raw clinical text sample"
        extracted={mockExtracted}
        pages={mockPages}
        activeKey="med.med_2.name"
        onSpanClick={vi.fn()}
      />
    );

    // Automatically navigated to Page 2 because med_2 is on page 2
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByTestId("missing-geometry-alert")).toBeInTheDocument();
    expect(screen.getByText(/Geometry unavailable/i)).toBeInTheDocument();
  });
});
