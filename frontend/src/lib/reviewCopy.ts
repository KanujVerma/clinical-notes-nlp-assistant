const FIELD_NAMES: Record<string, string> = {
  blood_pressure: "Blood pressure",
  heart_rate: "Heart rate",
  oxygen_saturation: "Oxygen saturation",
  respiratory_rate: "Respiratory rate",
  temperature: "Temperature",
  weight: "Weight",
  name: "Name",
  dose: "Dose",
  route: "Route",
  frequency: "Frequency",
  qualifier: "Qualifier",
  duration: "Duration",
  patient_name: "Patient",
  date_of_service: "Date of service",
  provider: "Clinician",
};

const TEXT_ONLY_METHODS = new Set(["text_utf8", "text_render"]);

export function displayFieldName(raw: string): string {
  const bare = raw
    .replace(/^(metadata|vitals|medications|instructions)\./, "")
    .replace(/^\d+\./, "");
  const last = bare.split(".").pop() || bare;
  return FIELD_NAMES[last] || FIELD_NAMES[bare] || last.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function statusLabel(status: string): string {
  if (status === "pending") return "Not checked";
  if (status === "accepted") return "Accepted";
  if (status === "corrected") return "Edited";
  if (status === "removed") return "Removed";
  return status;
}

export function hasOriginalPageImage(pages: { acquisition_method?: string }[]): boolean {
  if (pages.length === 0) return false;
  return pages.some((page) => !TEXT_ONLY_METHODS.has(page.acquisition_method || ""));
}

export function acquisitionLabel(method?: string): string {
  if (method === "text_utf8" || method === "text_render") return "Pasted text";
  if (method === "native_pdf") return "PDF";
  if (method === "tesseract_ocr") return "Text from image";
  if (method === "binary_asset" || method === "image" || method === "uploaded_image") return "Image";
  return "Source";
}

export function formatRunWhen(iso?: string | null): string {
  if (!iso) return "Undated run";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Undated run";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatF1(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return value.toFixed(3);
}
