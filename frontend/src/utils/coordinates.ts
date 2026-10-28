// frontend/src/utils/coordinates.ts

export interface BboxOverlay {
  leftPct: number;
  topPct: number;
  widthPct: number;
  heightPct: number;
  renderedWidth: number;
  renderedHeight: number;
  rotation: number;
}

export interface ValidationResult {
  isValid: boolean;
  code: "VALID" | "MISSING_GEOMETRY" | "INVALID_GEOMETRY" | "DEGENERATE_BOX" | "OUT_OF_BOUNDS" | "INVALID_PAGE_DIMENSIONS";
  message?: string;
}

export interface AgreementResult {
  status: "verified" | "disagreement" | "missing_geometry" | "empty_box_ocr" | "missing_span_text";
  agreement: boolean;
  similarity: number;
  ocrText: string;
  spanText: string;
  reason?: string;
}

export function validateBboxGeometry(
  bbox: number[] | null | undefined,
  pageWidth: number,
  pageHeight: number
): ValidationResult {
  if (!bbox || !Array.isArray(bbox) || bbox.length !== 4) {
    return { isValid: false, code: "MISSING_GEOMETRY", message: "Bounding box geometry is missing or incomplete." };
  }

  const [x0, y0, x1, y1] = bbox;
  if (
    typeof x0 !== "number" || typeof y0 !== "number" ||
    typeof x1 !== "number" || typeof y1 !== "number" ||
    Number.isNaN(x0) || Number.isNaN(y0) || Number.isNaN(x1) || Number.isNaN(y1)
  ) {
    return { isValid: false, code: "INVALID_GEOMETRY", message: "Bounding box coordinates must be valid numbers." };
  }

  if (pageWidth <= 0 || pageHeight <= 0) {
    return { isValid: false, code: "INVALID_PAGE_DIMENSIONS", message: "Page dimensions must be strictly positive." };
  }

  if (x0 >= x1 || y0 >= y1) {
    return { isValid: false, code: "DEGENERATE_BOX", message: `Non-positive dimensions: [${x0}, ${y0}, ${x1}, ${y1}].` };
  }

  const tolerance = Math.max(2.0, Math.max(pageWidth, pageHeight) * 0.01);
  if (x0 < -tolerance || y0 < -tolerance || x1 > (pageWidth + tolerance) || y1 > (pageHeight + tolerance)) {
    return {
      isValid: false,
      code: "OUT_OF_BOUNDS",
      message: `Bounding box [${x0}, ${y0}, ${x1}, ${y1}] exceeds page dimensions [${pageWidth}, ${pageHeight}].`,
    };
  }

  return { isValid: true, code: "VALID" };
}

export function transformBbox(
  bbox: number[],
  pageWidth: number,
  pageHeight: number,
  rotation: number = 0,
  coordinateSystem: "top_left" | "bottom_left" = "top_left"
): BboxOverlay {
  const validation = validateBboxGeometry(bbox, pageWidth, pageHeight);
  if (!validation.isValid) {
    throw new Error(`${validation.code}: ${validation.message}`);
  }

  const [x0, rawY0, x1, rawY1] = bbox;
  let y0 = rawY0;
  let y1 = rawY1;

  // Convert bottom-left origin to top-left if needed
  if (coordinateSystem === "bottom_left") {
    const y0Tl = pageHeight - rawY1;
    const y1Tl = pageHeight - rawY0;
    y0 = Math.min(y0Tl, y1Tl);
    y1 = Math.max(y0Tl, y1Tl);
  }

  const rot = ((rotation % 360) + 360) % 360;
  if (![0, 90, 180, 270].includes(rot)) {
    throw new Error(`Unsupported rotation: ${rotation}. Must be a multiple of 90 degrees.`);
  }

  let leftPct = 0;
  let topPct = 0;
  let widthPct = 0;
  let heightPct = 0;
  let renderedWidth = pageWidth;
  let renderedHeight = pageHeight;

  if (rot === 0) {
    leftPct = (x0 / pageWidth) * 100.0;
    topPct = (y0 / pageHeight) * 100.0;
    widthPct = ((x1 - x0) / pageWidth) * 100.0;
    heightPct = ((y1 - y0) / pageHeight) * 100.0;
  } else if (rot === 90) {
    // 90 deg clockwise: (x, y) -> (pageHeight - y, x)
    renderedWidth = pageHeight;
    renderedHeight = pageWidth;
    const x0Rot = pageHeight - y1;
    const y0Rot = x0;
    const wRot = y1 - y0;
    const hRot = x1 - x0;
    leftPct = (x0Rot / renderedWidth) * 100.0;
    topPct = (y0Rot / renderedHeight) * 100.0;
    widthPct = (wRot / renderedWidth) * 100.0;
    heightPct = (hRot / renderedHeight) * 100.0;
  } else if (rot === 180) {
    renderedWidth = pageWidth;
    renderedHeight = pageHeight;
    const x0Rot = pageWidth - x1;
    const y0Rot = pageHeight - y1;
    const wRot = x1 - x0;
    const hRot = y1 - y0;
    leftPct = (x0Rot / renderedWidth) * 100.0;
    topPct = (y0Rot / renderedHeight) * 100.0;
    widthPct = (wRot / renderedWidth) * 100.0;
    heightPct = (hRot / renderedHeight) * 100.0;
  } else {
    // 270 deg clockwise: (x, y) -> (y, pageWidth - x)
    renderedWidth = pageHeight;
    renderedHeight = pageWidth;
    const x0Rot = y0;
    const y0Rot = pageWidth - x1;
    const wRot = y1 - y0;
    const hRot = x1 - x0;
    leftPct = (x0Rot / renderedWidth) * 100.0;
    topPct = (y0Rot / renderedHeight) * 100.0;
    widthPct = (wRot / renderedWidth) * 100.0;
    heightPct = (hRot / renderedHeight) * 100.0;
  }

  return {
    leftPct: Number(leftPct.toFixed(3)),
    topPct: Number(topPct.toFixed(3)),
    widthPct: Number(widthPct.toFixed(3)),
    heightPct: Number(heightPct.toFixed(3)),
    renderedWidth: Number(renderedWidth.toFixed(2)),
    renderedHeight: Number(renderedHeight.toFixed(2)),
    rotation: rot,
  };
}

export function checkSourceImageAgreement(
  spanText: string,
  bbox: number[] | null | undefined,
  pageBoxes: Array<{ bbox: number[]; text: string }>,
  pageWidth: number,
  pageHeight: number
): AgreementResult {
  if (!spanText || !spanText.trim()) {
    return {
      status: "missing_span_text",
      agreement: false,
      similarity: 0.0,
      ocrText: "",
      spanText: "",
      reason: "Span text is empty.",
    };
  }

  const val = validateBboxGeometry(bbox, pageWidth, pageHeight);
  if (!val.isValid) {
    return {
      status: "missing_geometry",
      agreement: false,
      similarity: 0.0,
      ocrText: "",
      spanText,
      reason: val.message,
    };
  }

  const [x0, y0, x1, y1] = bbox!;
  const tol = 3.0;
  const matchedWords: Array<{ top: number; left: number; text: string }> = [];

  for (const item of pageBoxes) {
    if (!item.bbox || item.bbox.length !== 4 || !item.text) continue;
    const cx = (item.bbox[0] + item.bbox[2]) / 2.0;
    const cy = (item.bbox[1] + item.bbox[3]) / 2.0;
    if (cx >= x0 - tol && cx <= x1 + tol && cy >= y0 - tol && cy <= y1 + tol) {
      matchedWords.push({ top: item.bbox[1], left: item.bbox[0], text: item.text.trim() });
    }
  }

  matchedWords.sort((a, b) => {
    const lineDiff = Math.round(a.top / 8.0) - Math.round(b.top / 8.0);
    return lineDiff !== 0 ? lineDiff : a.left - b.left;
  });

  const ocrText = matchedWords.map((w) => w.text).join(" ");
  if (!ocrText) {
    return {
      status: "empty_box_ocr",
      agreement: false,
      similarity: 0.0,
      ocrText: "",
      spanText,
      reason: "No OCR text found in bounding box.",
    };
  }

  // 1. Check exact numeric tokens (including decimals like 2.5 vs 25)
  const spanNumbers: string[] = spanText.match(/\b\d+(?:\.\d+)?\b/g) || [];
  const ocrNumbers: string[] = ocrText.match(/\b\d+(?:\.\d+)?\b/g) || [];
  for (const num of spanNumbers) {
    if (!ocrNumbers.includes(num)) {
      return {
        status: "disagreement",
        agreement: false,
        similarity: 0.0,
        ocrText,
        spanText,
        reason: `Disagreement: numeric value '${num}' in transcript not found in page OCR (${ocrNumbers.join(", ")}).`,
      };
    }
  }

  // 2. Check clinical negation polarity
  const negationTokens = new Set(["not", "no", "never", "discontinue", "discontinued", "stop", "stopped", "hold", "held"]);
  const spanWords = new Set((spanText.toLowerCase().match(/\b[a-z]+\b/g) || []).filter((w) => negationTokens.has(w)));
  const ocrWords = new Set((ocrText.toLowerCase().match(/\b[a-z]+\b/g) || []).filter((w) => negationTokens.has(w)));
  const spanNegList = Array.from(spanWords).sort().join(",");
  const ocrNegList = Array.from(ocrWords).sort().join(",");
  if (spanNegList !== ocrNegList) {
    return {
      status: "disagreement",
      agreement: false,
      similarity: 0.0,
      ocrText,
      spanText,
      reason: `Disagreement: clinical polarity mismatch (negation difference between transcript and page OCR).`,
    };
  }

  const cleanSpan = (spanText.toLowerCase().match(/[a-z0-9.]+/g) || []).join(" ");
  const cleanOcr = (ocrText.toLowerCase().match(/[a-z0-9.]+/g) || []).join(" ");

  let similarity = 0.0;
  if (cleanSpan === cleanOcr || cleanSpan.includes(cleanOcr) || cleanOcr.includes(cleanSpan)) {
    similarity = 1.0;
  } else {
    const setA = new Set(cleanSpan.split(" "));
    const setB = new Set(cleanOcr.split(" "));
    let intersection = 0;
    setA.forEach((token) => {
      if (setB.has(token)) intersection++;
    });
    const union = new Set([...setA, ...setB]).size || 1;
    similarity = Number((intersection / union).toFixed(3));
  }

  const agreement = similarity >= 0.6;
  return {
    status: agreement ? "verified" : "disagreement",
    agreement,
    similarity,
    ocrText,
    spanText,
    reason: agreement ? undefined : `Disagreement: span claims '${spanText}', but page OCR at box contains '${ocrText}'.`,
  };
}
