// frontend/src/components/DocumentSourceViewer.tsx
import { useState, useEffect, useMemo, useRef, type ReactNode } from "react";
import { ExtractionResult } from "../types";
import { api } from "../api/client";
import { transformBbox, validateBboxGeometry, checkSourceImageAgreement } from "../utils/coordinates";
import { acquisitionLabel, hasOriginalPageImage } from "../lib/reviewCopy";

export interface PageMetadata {
  page_number: number;
  width: number;
  height: number;
  acquisition_method?: string;
  confidence?: number;
  start_offset?: number;
  end_offset?: number;
  boxes?: Array<{ bbox: number[]; text: string }>;
}

export interface Props {
  noteId: number;
  revisionId?: string | null;
  rawText: string;
  extracted: ExtractionResult;
  pages?: PageMetadata[];
  activeKey: string | null;
  onSpanClick: (fieldKey: string) => void;
}

interface EvidenceItem {
  fieldKey: string;
  category: "vitals" | "medications" | "instructions" | "metadata";
  label: string;
  quote?: string;
  span?: [number, number];
  pageNumber: number;
  bbox?: number[];
}

const TEXT_MARK: Record<EvidenceItem["category"], string> = {
  vitals: "bg-blue-100 text-blue-950",
  medications: "bg-green-100 text-green-950",
  instructions: "bg-amber-100 text-amber-950",
  metadata: "bg-violet-100 text-violet-950",
};

function renderTranscriptSpans(
  rawText: string,
  items: EvidenceItem[],
  activeKey: string | null,
  onSpanClick: (fieldKey: string) => void,
): ReactNode[] {
  const spans = items
    .filter((item): item is EvidenceItem & { span: [number, number] } => {
      if (!item.span) return false;
      const [start, end] = item.span;
      return start >= 0 && end > start && end <= rawText.length;
    })
    .sort((a, b) => a.span[0] - b.span[0] || a.span[1] - b.span[1]);

  const parts: ReactNode[] = [];
  let pos = 0;
  for (const item of spans) {
    const [start, end] = item.span;
    if (start < pos) continue;
    if (start > pos) {
      parts.push(<span key={`text-${pos}`}>{rawText.slice(pos, start)}</span>);
    }
    const isActive = activeKey === item.fieldKey;
    parts.push(
      <button
        key={`span-${item.fieldKey}-${start}`}
        type="button"
        data-testid={`source-span-${item.fieldKey}`}
        title={`${item.category}: ${item.label}`}
        onClick={() => onSpanClick(item.fieldKey)}
        className={`inline cursor-pointer rounded border-0 p-0 font-inherit ${TEXT_MARK[item.category]} ${isActive ? "font-semibold ring-2 ring-slate-700" : ""}`}
      >
        {rawText.slice(start, end)}
      </button>,
    );
    pos = end;
  }
  if (pos < rawText.length) {
    parts.push(<span key={`text-${pos}`}>{rawText.slice(pos)}</span>);
  }
  return parts;
}

const CAT_COLORS: Record<string, { bg: string; border: string; ring: string }> = {
  vitals: { bg: "bg-blue-500/20", border: "border-blue-500", ring: "ring-blue-400" },
  medications: { bg: "bg-green-500/20", border: "border-green-500", ring: "ring-green-400" },
  instructions: { bg: "bg-amber-500/20", border: "border-amber-500", ring: "ring-amber-400" },
  metadata: { bg: "bg-violet-500/20", border: "border-violet-500", ring: "ring-violet-400" },
};

export default function DocumentSourceViewer({
  noteId,
  revisionId,
  rawText,
  extracted,
  pages = [],
  activeKey,
  onSpanClick,
}: Props) {
  const originalImage = hasOriginalPageImage(pages);
  const [viewMode, setViewMode] = useState<"document" | "transcript">(originalImage ? "document" : "transcript");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [rotation, setRotation] = useState<number>(0);
  const [imageLoading, setImageLoading] = useState<boolean>(true);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const prevActiveKey = useRef<string | null>(null);

  // Reset viewer state when changing notes or revisions
  useEffect(() => {
    setViewMode(hasOriginalPageImage(pages) ? "document" : "transcript");
    setCurrentPage(1);
    setRotation(0);
    setImageLoading(true);
    setImageError(null);
    prevActiveKey.current = null;
  }, [noteId, revisionId, pages]);

  // Source binaries require authenticated API requests. Fetch a temporary
  // image blob, never encode the capability token in a URL or query string.
  // Cancel stale requests and revoke object URLs after page/rotation changes.
  useEffect(() => {
    if (viewMode !== "document") {
      setImageLoading(false);
      setImageUrl(null);
      return;
    }
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setImageLoading(true);
    setImageError(null);
    setImageUrl(null);
    api.getPageImageBlob(noteId, currentPage, rotation, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setImageUrl(objectUrl);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setImageError("Unable to load the authorized document image.");
          setImageLoading(false);
        }
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [noteId, currentPage, rotation, viewMode, revisionId, rawText]);

  const totalPages = Math.max(1, pages.length);

  // Helper to derive page number from explicit field property or character span against page offsets
  const resolvePageNumber = (span?: [number, number], explicitPage?: number): number => {
    if (explicitPage) return explicitPage;
    if (span && pages && pages.length > 0) {
      const found = pages.find(
        (p) => p.start_offset != null && p.end_offset != null && span[0] >= p.start_offset && span[0] < p.end_offset
      );
      if (found) return found.page_number;
    }
    return 1;
  };

  // Collect all visual evidence items from extraction
  const evidenceItems = useMemo<EvidenceItem[]>(() => {
    const items: EvidenceItem[] = [];

    // Vitals
    Object.entries(extracted.vitals || {}).forEach(([k, v]) => {
      if (v?.span) {
        items.push({
          fieldKey: `vitals.${k}`,
          category: "vitals",
          label: k,
          span: v.span,
          quote: String(v.value ?? ""),
          pageNumber: resolvePageNumber(v.span, (v as any).page_number),
          bbox: (v as any).bbox,
        });
      }
    });

    // Medications
    (extracted.medications || []).forEach((m, i) => {
      const medId = (m as any).id || (m as any).source_occurrence_id || `med_${i}`;
      if (m?.span) {
        items.push({
          fieldKey: `med.${medId}.name`,
          category: "medications",
          label: m.name,
          span: m.span,
          quote: m.name,
          pageNumber: resolvePageNumber(m.span, (m as any).page_number),
          bbox: (m as any).bbox,
        });
      }
    });

    // Instructions
    Object.entries(extracted.instructions || {}).forEach(([k, v]) => {
      if (v?.span) {
        items.push({
          fieldKey: `instr.${k}`,
          category: "instructions",
          label: k,
          span: v.span,
          quote: String(v.value ?? ""),
          pageNumber: resolvePageNumber(v.span, (v as any).page_number),
          bbox: (v as any).bbox,
        });
      }
    });

    // Metadata
    Object.entries(extracted.metadata || {}).forEach(([k, v]) => {
      if (v?.span) {
        items.push({
          fieldKey: `meta.${k}`,
          category: "metadata",
          label: k,
          span: v.span,
          quote: String(v.value ?? ""),
          pageNumber: resolvePageNumber(v.span, (v as any).page_number),
          bbox: (v as any).bbox,
        });
      }
    });

    return items;
  }, [extracted, pages]);

  // Navigate page when activeKey changes to an evidence item on another page
  useEffect(() => {
    if (activeKey && activeKey !== prevActiveKey.current) {
      prevActiveKey.current = activeKey;
      const activeItem = evidenceItems.find((item) => item.fieldKey === activeKey);
      if (activeItem && activeItem.pageNumber && activeItem.pageNumber !== currentPage) {
        setCurrentPage(activeItem.pageNumber);
      }
    } else if (!activeKey) {
      prevActiveKey.current = null;
    }
  }, [activeKey, evidenceItems, currentPage]);

  const activeItem = useMemo(() => {
    return evidenceItems.find((item) => item.fieldKey === activeKey);
  }, [activeKey, evidenceItems]);

  // Current page metadata
  const currentPageMeta = useMemo(() => {
    return pages.find((p) => p.page_number === currentPage) || {
      page_number: currentPage,
      width: 800,
      height: 1100,
      boxes: [],
    };
  }, [pages, currentPage]);

  // Check agreement & geometry for the active item on current page
  const activeGeometryStatus = useMemo(() => {
    if (!activeItem) return null;
    const bbox = activeItem.bbox;
    const geomValidation = validateBboxGeometry(bbox, currentPageMeta.width, currentPageMeta.height);
    if (!geomValidation.isValid) {
      return {
        hasGeometry: false,
        code: geomValidation.code,
        message: geomValidation.message,
        agreement: null,
      };
    }

    const agreement = checkSourceImageAgreement(
      activeItem.quote || activeItem.label,
      bbox,
      currentPageMeta.boxes || [],
      currentPageMeta.width,
      currentPageMeta.height
    );

    return {
      hasGeometry: true,
      code: "VALID",
      agreement,
    };
  }, [activeItem, currentPageMeta]);

  // Transform overlays for the current page
  const pageOverlays = useMemo(() => {
    const overlays: Array<{
      item: EvidenceItem;
      overlay: ReturnType<typeof transformBbox>;
      isActive: boolean;
    }> = [];

    evidenceItems.forEach((item) => {
      if (item.pageNumber !== currentPage || !item.bbox) return;
      const valid = validateBboxGeometry(item.bbox, currentPageMeta.width, currentPageMeta.height);
      if (!valid.isValid) return;

      try {
        const transformed = transformBbox(
          item.bbox,
          currentPageMeta.width,
          currentPageMeta.height,
          rotation
        );
        overlays.push({
          item,
          overlay: transformed,
          isActive: activeKey === item.fieldKey,
        });
      } catch {
        // Skip invalid bounding boxes gracefully
      }
    });

    return overlays;
  }, [evidenceItems, currentPage, currentPageMeta, rotation, activeKey]);

  const handleRotate = () => {
    setRotation((prev) => (prev + 90) % 360);
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-700/60 rounded-xl overflow-hidden shadow-sm" data-testid="document-source-viewer">
      {/* Top Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white border-b border-slate-200 text-sm text-slate-800">
        <div className="flex items-center gap-2">
          <span className="font-medium">Source note</span>
          {originalImage && (
            <div className="inline-flex rounded-lg p-0.5 bg-slate-100 border border-slate-200" role="tablist" aria-label="Source view">
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === "transcript"}
                onClick={() => setViewMode("transcript")}
                className={`px-3 py-1.5 rounded-md text-sm font-medium ${
                  viewMode === "transcript" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600"
                }`}
                data-testid="toggle-view-transcript"
              >
                Text
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={viewMode === "document"}
                onClick={() => setViewMode("document")}
                className={`px-3 py-1.5 rounded-md text-sm font-medium ${
                  viewMode === "document" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600"
                }`}
                data-testid="toggle-view-document"
              >
                Page image
              </button>
            </div>
          )}
          <span className="text-xs text-slate-500">{acquisitionLabel(currentPageMeta?.acquisition_method)}</span>
        </div>

        {viewMode === "document" && originalImage && (
          <div className="flex items-center gap-2">
            {/* Page Navigation */}
            <div className="flex items-center gap-1 bg-slate-900/80 px-2 py-0.5 rounded border border-slate-700">
              <button
                type="button"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="px-1.5 py-0.5 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
                data-testid="page-prev-btn"
                title="Previous page"
              >
                ◀
              </button>
              {totalPages > 1 && (
              <span className="text-xs px-1">
                Page {currentPage} of {totalPages}
              </span>
              )}
              <button
                type="button"
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="px-1.5 py-0.5 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
                data-testid="page-next-btn"
                title="Next page"
              >
                ▶
              </button>
            </div>

            {/* Rotation Control */}
            <button
              type="button"
              onClick={handleRotate}
              className="px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded text-[11px] font-medium transition-colors flex items-center gap-1"
              data-testid="rotate-btn"
              title="Rotate document 90° clockwise"
            >
              ↻ {rotation}°
            </button>
          </div>
        )}
      </div>

      {/* Warning/Alert banners for Geometry or Disagreement */}
      {viewMode === "document" && originalImage && activeItem && activeGeometryStatus && (!activeGeometryStatus.hasGeometry || (activeGeometryStatus.agreement && !activeGeometryStatus.agreement.agreement)) && (
        <div className="px-3 py-2 bg-amber-50 border-b border-amber-200 text-sm">
          {!activeGeometryStatus.hasGeometry ? (
            <div className="text-amber-950" data-testid="missing-geometry-alert" role="status">
              No image highlight is available for this field. Check the source text.
            </div>
          ) : activeGeometryStatus.agreement && !activeGeometryStatus.agreement.agreement ? (
            <div className="text-amber-950" data-testid="source-disagreement-alert" role="status">
              The source text and the page image do not say the same thing here. Source text: "{activeItem.quote}". Image text: "{activeGeometryStatus.agreement.ocrText}".
            </div>
          ) : null}
        </div>
      )}

      {/* Main Content Area */}
      <div className={`relative flex-1 overflow-auto flex ${viewMode === "document" && originalImage ? "items-center justify-center bg-slate-950 p-4" : "bg-white"}`}>
        {viewMode === "transcript" || !originalImage ? (
          <div className="w-full h-full overflow-y-auto bg-white px-6 py-5 text-[15px] leading-relaxed text-slate-900 whitespace-pre-wrap" data-testid="source-transcript">
            {renderTranscriptSpans(rawText, evidenceItems, activeKey, onSpanClick)}
          </div>
        ) : (
          <div className="relative max-w-full max-h-full inline-block shadow-2xl rounded border border-slate-800">
            {imageLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-slate-900/60 z-20 text-slate-300 text-xs">
                Rendering page image...
              </div>
            )}
            {imageError && (
              <div className="p-8 text-center text-rose-400 text-xs">
                {imageError}
              </div>
            )}
            {imageUrl && <img
              src={imageUrl}
              alt={`Note ${noteId} Page ${currentPage}`}
              className="block max-w-full max-h-[75vh] object-contain rounded select-none"
              onLoad={() => setImageLoading(false)}
              onError={() => {
                setImageLoading(false);
                setImageError("Unable to render document page image.");
              }}
              data-testid="document-page-image"
            />}

            {/* Bounding Box Highlights Overlay */}
            {!imageLoading && !imageError && (
              <div className="absolute inset-0 pointer-events-none" data-testid="bbox-overlay-container">
                {pageOverlays.map(({ item, overlay, isActive }) => {
                  const colors = CAT_COLORS[item.category] || CAT_COLORS.metadata;
                  return (
                    <div
                      key={`box-${item.fieldKey}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSpanClick(item.fieldKey);
                      }}
                      title={`${item.category}: ${item.label} (Click to inspect)`}
                      className={`absolute pointer-events-auto cursor-pointer rounded border-2 transition-all ${
                        colors.bg
                      } ${colors.border} ${
                        isActive ? `ring-4 ${colors.ring} scale-[1.02] z-10 shadow-lg font-bold` : "opacity-80 hover:opacity-100"
                      }`}
                      style={{
                        left: `${overlay.leftPct}%`,
                        top: `${overlay.topPct}%`,
                        width: `${overlay.widthPct}%`,
                        height: `${overlay.heightPct}%`,
                      }}
                      data-testid={`overlay-box-${item.fieldKey}`}
                    >
                      <span className="absolute -top-4 left-0 text-[9px] px-1 py-0.2 rounded bg-slate-900/90 text-white border border-slate-700 whitespace-nowrap">
                        {item.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
