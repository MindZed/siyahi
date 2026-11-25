"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Eye, EyeOff, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { apiUrl } from "@/lib/api";
import type { OCRDocumentResponse, RegionRef } from "@/types/schemas";

interface ScanViewerProps {
  pageImageUrls: string[];
  ocr?: OCRDocumentResponse | null;
  activeQuestionRegions?: RegionRef[];
  selectedRegionId?: string | null;
  onSelectRegion?: (regionId: string) => void;
}

const BOX_STYLES: Record<string, { stroke: string; fill: string }> = {
  text: { stroke: "#2563EB", fill: "rgba(37, 99, 235, 0.08)" },
  title: { stroke: "#2563EB", fill: "rgba(37, 99, 235, 0.12)" },
  formula: { stroke: "#D97706", fill: "rgba(217, 119, 6, 0.12)" },
  table: { stroke: "#D97706", fill: "rgba(217, 119, 6, 0.12)" },
  diagram: { stroke: "#DC2626", fill: "rgba(220, 38, 38, 0.12)" },
};

export function ScanViewer({
  pageImageUrls,
  ocr,
  activeQuestionRegions = [],
  selectedRegionId,
  onSelectRegion,
}: ScanViewerProps) {
  const [pageIdx, setPageIdx] = useState(0);
  const [zoom, setZoom] = useState(1.0);
  const [showBoxes, setShowBoxes] = useState(true);

  useEffect(() => {
    if (activeQuestionRegions.length > 0) {
      const targetPage = activeQuestionRegions[0].page_number - 1;
      if (targetPage >= 0 && targetPage < pageImageUrls.length) {
        setPageIdx(targetPage);
      }
    }
  }, [activeQuestionRegions, pageImageUrls.length]);

  const currentPageNum = pageIdx + 1;
  const pageOcr = ocr?.pages.find((p) => p.page_number === currentPageNum);
  const activeIds = new Set(
    activeQuestionRegions
      .filter((r) => r.page_number === currentPageNum)
      .map((r) => r.region_id)
  );

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setPageIdx((i) => Math.max(0, i - 1))}
            disabled={pageIdx === 0}
            className="rounded border border-slate-200 bg-white p-1 text-slate-700 hover:bg-slate-100 disabled:opacity-40"
            title="Previous Page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="px-1.5 text-xs font-semibold text-slate-700">
            Page {pageImageUrls.length > 0 ? currentPageNum : 0} / {pageImageUrls.length}
          </span>
          <button
            type="button"
            onClick={() => setPageIdx((i) => Math.min(pageImageUrls.length - 1, i + 1))}
            disabled={pageIdx >= pageImageUrls.length - 1}
            className="rounded border border-slate-200 bg-white p-1 text-slate-700 hover:bg-slate-100 disabled:opacity-40"
            title="Next Page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(0.5, Number((z - 0.15).toFixed(2))))}
            className="rounded border border-slate-200 bg-white p-1 text-slate-700 hover:bg-slate-100"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <span className="w-11 text-center text-xs font-mono text-slate-700">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(2.5, Number((z + 0.15).toFixed(2))))}
            className="rounded border border-slate-200 bg-white p-1 text-slate-700 hover:bg-slate-100"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1.0)}
            className="rounded border border-slate-200 bg-white p-1 text-slate-700 hover:bg-slate-100"
            title="Reset Zoom"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setShowBoxes((v) => !v)}
            className={`ml-1 inline-flex items-center gap-1 rounded border px-2 py-1 text-xs font-medium ${
              showBoxes
                ? "border-blue-300 bg-blue-50 text-blue-700"
                : "border-slate-200 bg-white text-slate-600"
            }`}
          >
            {showBoxes ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            Boxes
          </button>
        </div>
      </div>

      {/* Legend */}
      {showBoxes && (
        <div className="flex items-center gap-4 border-b border-slate-100 bg-white px-3 py-1.5 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm border border-blue-600 bg-blue-100" />
            Text
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm border border-amber-600 bg-amber-100" />
            Table / Formula
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm border border-red-600 bg-red-100" />
            Diagram Crop
          </span>
        </div>
      )}

      {/* Scrollable Scan Canvas */}
      <div className="flex-1 overflow-auto bg-slate-100 p-3">
        {pageImageUrls.length === 0 ? (
          <div className="flex h-64 items-center justify-center text-sm text-slate-500">
            No anonymized page scans available yet.
          </div>
        ) : (
          <div
            className="relative mx-auto origin-top-left bg-white shadow"
            style={{ width: `${Math.round(zoom * 100)}%` }}
          >
            <img
              src={apiUrl(pageImageUrls[pageIdx])}
              alt={`Anonymized scan page ${currentPageNum}`}
              className="block h-auto w-full select-none"
            />
            {showBoxes && pageOcr && (
              <svg
                viewBox={`0 0 ${pageOcr.width} ${pageOcr.height}`}
                className="pointer-events-auto absolute inset-0 h-full w-full"
              >
                {pageOcr.regions.map((region) => {
                  const [x1, y1, x2, y2] = region.bbox;
                  const style = BOX_STYLES[region.label] || BOX_STYLES.text;
                  const isHighlighted =
                    selectedRegionId === region.region_id || activeIds.has(region.region_id);

                  return (
                    <g
                      key={region.region_id}
                      onClick={() => onSelectRegion?.(region.region_id)}
                      className="cursor-pointer"
                    >
                      <rect
                        x={x1}
                        y={y1}
                        width={Math.max(1, x2 - x1)}
                        height={Math.max(1, y2 - y1)}
                        fill={style.fill}
                        stroke={style.stroke}
                        strokeWidth={isHighlighted ? 5 : 2.5}
                        strokeDasharray={isHighlighted ? undefined : "8 4"}
                      />
                      <rect
                        x={x1}
                        y={Math.max(0, y1 - 24)}
                        width={Math.max(95, region.label.length * 10 + 42)}
                        height={24}
                        rx={4}
                        fill={style.stroke}
                      />
                      <text
                        x={x1 + 6}
                        y={Math.max(16, y1 - 7)}
                        fill="#FFFFFF"
                        fontSize={14}
                        fontWeight={600}
                      >
                        {region.label} ({Math.round(region.confidence * 100)}%)
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
