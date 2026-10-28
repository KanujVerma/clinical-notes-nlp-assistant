// frontend/src/utils/coordinates.test.ts
import { describe, it, expect } from "vitest";
import {
  validateBboxGeometry,
  transformBbox,
  checkSourceImageAgreement,
} from "./coordinates";

describe("validateBboxGeometry", () => {
  it("validates well-formed bounding box", () => {
    const res = validateBboxGeometry([10, 20, 50, 60], 100, 200);
    expect(res.isValid).toBe(true);
    expect(res.code).toBe("VALID");
  });

  it("rejects missing or incomplete geometry", () => {
    expect(validateBboxGeometry(null, 100, 100).code).toBe("MISSING_GEOMETRY");
    expect(validateBboxGeometry([10, 20], 100, 100).code).toBe("MISSING_GEOMETRY");
  });

  it("rejects degenerate box (x0 >= x1 or y0 >= y1)", () => {
    expect(validateBboxGeometry([50, 20, 10, 60], 100, 100).code).toBe("DEGENERATE_BOX");
  });

  it("rejects out of bounds geometry", () => {
    expect(validateBboxGeometry([10, 20, 150, 60], 100, 100).code).toBe("OUT_OF_BOUNDS");
  });
});

describe("transformBbox", () => {
  const pageW = 200;
  const pageH = 100;
  const bbox = [20, 10, 60, 40]; // w=40, h=30

  it("computes 0 degree normalized percentages correctly", () => {
    const t0 = transformBbox(bbox, pageW, pageH, 0);
    expect(t0.leftPct).toBe(10);   // (20/200)*100
    expect(t0.topPct).toBe(10);    // (10/100)*100
    expect(t0.widthPct).toBe(20);  // (40/200)*100
    expect(t0.heightPct).toBe(30); // (30/100)*100
    expect(t0.renderedWidth).toBe(200);
    expect(t0.renderedHeight).toBe(100);
  });

  it("computes 90 degree clockwise rotation correctly", () => {
    // renderedWidth=100, renderedHeight=200
    // x0_rot = 100 - 40 = 60; y0_rot = 20; w=30, h=40
    const t90 = transformBbox(bbox, pageW, pageH, 90);
    expect(t90.renderedWidth).toBe(100);
    expect(t90.renderedHeight).toBe(200);
    expect(t90.leftPct).toBe(60);  // (60/100)*100
    expect(t90.topPct).toBe(10);   // (20/200)*100
    expect(t90.widthPct).toBe(30); // (30/100)*100
    expect(t90.heightPct).toBe(20);// (40/200)*100
  });

  it("computes 180 degree rotation correctly", () => {
    const t180 = transformBbox(bbox, pageW, pageH, 180);
    expect(t180.leftPct).toBe(70); // ((200 - 60)/200)*100
    expect(t180.topPct).toBe(60);  // ((100 - 40)/100)*100
  });

  it("computes 270 degree rotation correctly", () => {
    const t270 = transformBbox(bbox, pageW, pageH, 270);
    expect(t270.leftPct).toBe(10); // (10/100)*100
    expect(t270.topPct).toBe(70);  // ((200 - 60)/200)*100
  });
});

describe("checkSourceImageAgreement", () => {
  const pageBoxes = [
    { bbox: [10, 10, 40, 25], text: "Lisinopril" },
    { bbox: [45, 10, 70, 25], text: "10mg" },
  ];

  it("identifies matching OCR text without asserting image truth", () => {
    const res = checkSourceImageAgreement("Lisinopril 10mg", [8, 8, 75, 28], pageBoxes, 100, 100);
    expect(res.agreement).toBe(true);
    expect(res.status).toBe("ocr_consistent_unverified");
  });

  it("identifies mismatching text as disagreement", () => {
    const res = checkSourceImageAgreement("Metformin 500mg", [8, 8, 75, 28], pageBoxes, 100, 100);
    expect(res.agreement).toBe(false);
    expect(res.status).toBe("disagreement");
    expect(res.reason).toContain("Disagreement");
  });

  it("catches decimal dosage mismatch (e.g. 2.5 vs 25 mg)", () => {
    const warfarinBoxes = [
      { bbox: [10, 10, 40, 25], text: "Warfarin" },
      { bbox: [45, 10, 70, 25], text: "25mg" },
    ];
    const res = checkSourceImageAgreement("Warfarin 2.5 mg", [8, 8, 75, 28], warfarinBoxes, 100, 100);
    expect(res.agreement).toBe(false);
    expect(res.status).toBe("disagreement");
    expect(res.reason).toContain("numeric value '2.5'");
  });

  it("flags leading decimal mismatch (.5 vs 5)", () => {
    const boxes = [
      { bbox: [10, 10, 40, 25], text: "Warfarin" },
      { bbox: [45, 10, 60, 25], text: "5" },
      { bbox: [65, 10, 80, 25], text: "mg" },
    ];
    const res = checkSourceImageAgreement("Warfarin .5 mg", [8, 8, 85, 28], boxes, 100, 100);
    expect(res.agreement).toBe(false);
    expect(res.status).toBe("disagreement");
    expect(res.reason).toContain("0.5");
  });

  it("flags compact dose mismatch (5mg vs 50mg)", () => {
    const boxes = [
      { bbox: [10, 10, 100, 25], text: "Take warfarin 50mg PO daily" },
    ];
    const res = checkSourceImageAgreement("Take warfarin 5mg PO daily", [8, 8, 105, 28], boxes, 200, 100);
    expect(res.agreement).toBe(false);
    expect(res.status).toBe("disagreement");
    expect(res.reason).toContain("5");
  });

  it("catches clinical polarity/negation difference", () => {
    const negBoxes = [
      { bbox: [10, 10, 40, 25], text: "Do" },
      { bbox: [45, 10, 70, 25], text: "not" },
      { bbox: [75, 10, 120, 25], text: "continue" },
      { bbox: [125, 10, 160, 25], text: "aspirin" },
    ];
    const res = checkSourceImageAgreement("Continue aspirin", [8, 8, 170, 28], negBoxes, 200, 100);
    expect(res.agreement).toBe(false);
    expect(res.status).toBe("disagreement");
    expect(res.reason).toContain("clinical polarity mismatch");
  });

  it("handles missing geometry gracefully", () => {
    const res = checkSourceImageAgreement("Lisinopril", null, pageBoxes, 100, 100);
    expect(res.agreement).toBe(false);
    expect(res.status).toBe("missing_geometry");
  });
});
