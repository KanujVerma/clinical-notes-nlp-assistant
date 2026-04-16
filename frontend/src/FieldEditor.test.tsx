// frontend/src/FieldEditor.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import FieldEditor from "./components/FieldEditor";

it("renders the field label and value", () => {
  render(<FieldEditor label="blood_pressure" value="120/80" status="pending" onChange={() => {}} />);
  expect(screen.getByText("blood_pressure")).toBeInTheDocument();
  expect(screen.getByText("120/80")).toBeInTheDocument();
});

it("calls onChange with corrected status after edit", () => {
  const onChange = vi.fn();
  render(<FieldEditor label="bp" value="120/80" status="pending" onChange={onChange} />);
  fireEvent.click(screen.getByText("edit"));
  const input = screen.getByDisplayValue("120/80");
  fireEvent.change(input, { target: { value: "130/85" } });
  fireEvent.click(screen.getByText("save"));
  expect(onChange).toHaveBeenCalledWith("130/85", "corrected");
});

it("calls onChange with removed status on remove", () => {
  const onChange = vi.fn();
  render(<FieldEditor label="bp" value="120/80" status="pending" onChange={onChange} />);
  fireEvent.click(screen.getByText("✕"));
  expect(onChange).toHaveBeenCalledWith("120/80", "removed");
});
