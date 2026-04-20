// frontend/src/FieldEditor.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import FieldEditor from "./components/FieldEditor";

it("renders the field label and value", () => {
  render(<FieldEditor label="blood_pressure" value="120/80" status="pending" category="vitals" isActive={true} onActivate={vi.fn()} onChange={() => {}} />);
  expect(screen.getByText("blood_pressure")).toBeInTheDocument();
  expect(screen.getByText("120/80")).toBeInTheDocument();
});

it("calls onChange with corrected status after edit", () => {
  const onChange = vi.fn();
  render(<FieldEditor label="bp" value="120/80" status="pending" category="vitals" isActive={true} onActivate={vi.fn()} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: /edit/i }));
  const input = screen.getByDisplayValue("120/80");
  fireEvent.change(input, { target: { value: "130/85" } });
  fireEvent.click(screen.getByText("save"));
  expect(onChange).toHaveBeenCalledWith("130/85", "corrected");
});

it("calls onChange with removed status on remove", () => {
  const onChange = vi.fn();
  render(<FieldEditor label="bp" value="120/80" status="pending" category="vitals" isActive={true} onActivate={vi.fn()} onChange={onChange} />);
  fireEvent.click(screen.getByText("✕"));
  expect(onChange).toHaveBeenCalledWith("120/80", "removed");
});

it("shows action buttons when isActive is true", () => {
  render(
    <FieldEditor
      label="bp"
      value="138/88"
      status="pending"
      category="vitals"
      isActive={true}
      onActivate={vi.fn()}
      onChange={vi.fn()}
    />
  );
  expect(screen.getByRole("button", { name: /accept/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /edit/i })).toBeInTheDocument();
});

it("renders value text when isActive is false", () => {
  render(
    <FieldEditor
      label="bp"
      value="138/88"
      status="pending"
      category="vitals"
      isActive={false}
      onActivate={vi.fn()}
      onChange={vi.fn()}
    />
  );
  expect(screen.getByTestId("field-value")).toHaveTextContent("138/88");
});

it("shows accepted state with no action buttons", () => {
  render(
    <FieldEditor
      label="bp"
      value="138/88"
      status="accepted"
      category="vitals"
      isActive={false}
      onActivate={vi.fn()}
      onChange={vi.fn()}
    />
  );
  expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
  expect(screen.getByText(/accepted/)).toBeInTheDocument();
});

describe("ExplainerTrigger integration", () => {
  it("renders explainer trigger for medication name when in dictionary", () => {
    render(
      <FieldEditor
        label="medication"
        value="metformin"
        status="pending"
        category="med"
        isActive={true}
        onActivate={vi.fn()}
        onChange={vi.fn()}
        explainerKind="medication"
      />
    );
    expect(screen.getByRole("button", { name: /show explanation/i })).toBeInTheDocument();
  });

  it("renders explainer trigger for unknown medication (AI fallback, hasDictionaryEntry=false)", () => {
    render(
      <FieldEditor
        label="medication"
        value="unknowndrug"
        status="pending"
        category="med"
        isActive={true}
        onActivate={vi.fn()}
        onChange={vi.fn()}
        explainerKind="medication"
      />
    );
    expect(screen.queryByRole("button", { name: /show explanation/i })).toBeInTheDocument();
  });

  it("renders explainer trigger for frequency field with BID", () => {
    render(
      <FieldEditor
        label="frequency"
        value="BID"
        status="pending"
        category="med"
        isActive={true}
        onActivate={vi.fn()}
        onChange={vi.fn()}
        explainerKind="abbreviation"
      />
    );
    expect(screen.getByRole("button", { name: /show explanation/i })).toBeInTheDocument();
  });

  it("renders no explainer trigger when explainerKind is not set", () => {
    render(
      <FieldEditor
        label="medication"
        value="metformin"
        status="pending"
        category="med"
        isActive={true}
        onActivate={vi.fn()}
        onChange={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: /show explanation/i })).not.toBeInTheDocument();
  });
});
