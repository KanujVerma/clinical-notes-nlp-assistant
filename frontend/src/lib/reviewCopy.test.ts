import { describe, expect, it } from "vitest";
import { medicationIsMentionOnly, visibleFieldKeys } from "./reviewCopy";

describe("visibleFieldKeys", () => {
  const fields = {
    "med.1.name": { status: "accepted" },
    "med.1.dose": { status: "pending" },
    "med.2.name": { status: "accepted" },
    "med.2.dose": { status: "accepted" },
    "vitals.heart_rate": { status: "pending" },
  };

  it("keeps the medication name beside a remaining detail", () => {
    expect(visibleFieldKeys(fields, "remaining")).toEqual([
      "med.1.name",
      "med.1.dose",
      "vitals.heart_rate",
    ]);
  });

  it("does not call a medication mention-only when a filtered detail still exists", () => {
    expect(medicationIsMentionOnly(fields, "1")).toBe(false);
    expect(medicationIsMentionOnly({ "med.3.name": { status: "pending" } }, "3")).toBe(true);
  });
});
