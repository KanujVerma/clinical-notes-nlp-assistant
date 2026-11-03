import { render, screen, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Review from "./Review";
import { QueueProvider } from "../context/QueueContext";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    getCapabilities: vi.fn(async () => ({ mode: "local" })),
    getNoteState: vi.fn(async () => ({})),
    getNoteSource: vi.fn(async () => ({ revision_number: 1, sha256: "abc", pages: [] })),
    getIssues: vi.fn(async () => []),
  },
}));

const extracted = {
  vitals: { blood_pressure: { value: "120/80", span: [15, 21] } },
  medications: [],
  instructions: {},
  metadata: {},
};

function renderNarrowReview() {
  Element.prototype.scrollIntoView = () => {};
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;

  const router = createMemoryRouter(
    [{ path: "/review/:noteId", element: <Review /> }],
    {
      initialEntries: [{
        pathname: "/review/7",
        state: {
          note_id: 7,
          raw_text: "Blood pressure 120/80.",
          source: "text",
          extracted_json: extracted,
        },
      }],
    },
  );
  return render(
    <QueueProvider>
      <RouterProvider router={router} />
    </QueueProvider>,
  );
}

describe("Review field shortcuts on a narrow screen", () => {
  beforeEach(() => {
    vi.mocked(api.getCapabilities).mockClear();
  });

  it("ignores Accept and Tab while Source hides the fields, then applies them on Fields", async () => {
    renderNarrowReview();
    const checked = await screen.findByText("0 of 1 checked");
    expect(screen.getByRole("tab", { name: "Source" })).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(window, { key: "Tab" });
    fireEvent.keyDown(window, { key: "a" });
    expect(checked).toHaveTextContent("0 of 1 checked");

    fireEvent.click(screen.getByRole("tab", { name: "Fields" }));
    fireEvent.keyDown(window, { key: "Tab" });
    fireEvent.keyDown(window, { key: "a" });
    expect(checked).toHaveTextContent("1 of 1 checked");
  });
});
