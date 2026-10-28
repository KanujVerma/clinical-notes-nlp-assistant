// frontend/src/components/DocumentSourceViewer.tsx
import { useState, useEffect, useMemo, useRef } from "react";
import { ExtractionResult } from "../types";
import { transformBbox, validateBboxGeometry, checkSourceImageAgreement } from "../utils/coordinates";

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

const CAT_COLORS: Record<string, { bg: string; border: string; ring: string }> = {
  vitals: { bg: "bg-blue-500/20", border: "border-blue-500", ring: "ring-blue-400" },
  medications: { bg: "bg-green-500/20", border: "border-green-500", ring: "ring-green-400" },
  instructions: { bg: "bg-amber-500/20", border: "border-amber-500", ring: "ring-amber-400" },
  metadata: { bg: "bg-violet-500/20", border: "border-violet-500", ring: "ring-violet-400" },
};

export default function DocumentSourceViewer({
  noteId,
  rawText,
  extracted,
  pages = [],
  activeKey,
  onSpanClick,
}: Props) {
  const [viewMode, setViewMode] = useState<"document" | "transcript">("document");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [rotation, setRotation] = useState<number>(0);
  const [imageLoading, setImageLoading] = useState<boolean>(true);
  const [imageError, setImageError] = useState<string | null>(null);
  const prevActiveKey = useRef<string | null>(null);

  // Reset viewer state when changing notes
  useEffect(() => {
    setCurrentPage(1);
    setRotation(0);
    setImageLoading(true);
    setImageError(null);
    prevActiveKey.current = null;
  }, [noteId]);

  const totalPages = Math.max(1, pages.length);

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
          pageNumber: (v as any).page_number || 1,
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
          pageNumber: (m as any).page_number || 1,
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
          pageNumber: (v as any).page_number || 1,
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
          pageNumber: (v as any).page_number || 1,
          bbox: (v as any).bbox,
        });
      }
    });

    return items;
  }, [extracted]);

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

  const imageUrl = `/api/notes/${noteId}/pages/${currentPage}/image?rotation=${rotation}`;

  return (
    <div className="flex flex-col h-full bg-slate-900 border border-slate-700/60 rounded-xl overflow-hidden shadow-sm" data-testid="document-source-viewer">
      {/* Top Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 bg-slate-800/90 border-b border-slate-700 text-xs text-slate-200">
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg p-0.5 bg-slate-900/80 border border-slate-700">
            <button
              type="button"
              onClick={() => setViewMode("document")}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                viewMode === "document"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              data-testid="toggle-view-document"
            >
              Document Image
            </button>
            <button
              type="button"
              onClick={() => setViewMode("transcript")}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                viewMode === "transcript"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              data-testid="toggle-view-transcript"
            >
              Text Transcript
            </button>
          </div>

          {viewMode === "document" && (
            <span className="text-[11px] text-slate-400 px-2 py-0.5 rounded bg-slate-900 border border-slate-700">
              {currentPageMeta.acquisition_method || "original_asset"}
            </span>
          )}
        </div>

        {viewMode === "document" && (
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
              <span className="text-[11px] font-mono px-1">
                Page {currentPage} of {totalPages}
              </span>
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
      {viewMode === "document" && activeItem && activeGeometryStatus && (
        <div className="px-3 py-1.5 bg-slate-950 border-b border-slate-800 text-[11px]">
          {!activeGeometryStatus.hasGeometry ? (
            <div className="flex items-center gap-1.5 text-amber-400" data-testid="missing-geometry-alert">
              <span>⚠️</span>
              <span className="font-medium">Geometry unavailable:</span>
              <span className="text-slate-300">
                "{activeItem.label}" has text-only evidence; no bounding box geometry on page {currentPage}.
              </span>
            </div>
          ) : activeGeometryStatus.agreement && !activeGeometryStatus.agreement.agreement ? (
            <div className="flex items-center gap-1.5 text-amber-300" data-testid="source-disagreement-alert">
              <span>⚠️</span>
              <span className="font-semibold text-rose-400">Source/Image Disagreement:</span>
              <span className="text-slate-200">
                Transcript claims "{activeItem.quote}", but page OCR contains "{activeGeometryStatus.agreement.ocrText}".
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-emerald-400" data-testid="geometry-verified-badge">
              <span>✓</span>
              <span>Visual coordinate verified for "{activeItem.label}" on page {currentPage}.</span>
            </div>
          )}
        </div>
      )}

      {/* Main Content Area */}
      <div className="relative flex-1 overflow-auto p-4 flex items-center justify-center bg-slate-950">
        {viewMode === "transcript" ? (
          <div className="w-full h-full p-4 font-mono text-xs leading-relaxed text-slate-200 whitespace-pre-wrap overflow-y-auto">
            {rawText}
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
            <img
              src={imageUrl}
              alt={`Note ${noteId} Page ${currentPage}`}
              className="block max-w-full max-h-[75vh] object-contain rounded select-none"
              onLoad={() => setImageLoading(false)}
              onError={() => {
                setImageLoading(false);
                setImageError("Unable to render document page image.");
              }}
              data-testid="document-page-image"
            />

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
