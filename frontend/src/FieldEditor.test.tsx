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
