"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ClipboardCheck, FileText, Loader2, ScanEye } from "lucide-react";
import { EvaluationPanel } from "@/components/EvaluationPanel";
import { ScanViewer } from "@/components/ScanViewer";
import { TranscriptEditor } from "@/components/TranscriptEditor";
import { api } from "@/lib/api";
import type { SubmissionDetailResponse } from "@/types/schemas";

type MobilePane = "scan" | "transcript" | "evaluation";

export default function ReviewDeskPage() {
  const params = useParams<{ submissionId: string }>();
  const submissionId = params.submissionId;

  const [detail, setDetail] = useState<SubmissionDetailResponse | null>(null);
  const [activeQuestionNo, setActiveQuestionNo] = useState<string | null>(null);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<MobilePane>("scan");
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(async () => {
    try {
      const data = await api.getSubmissionDetail(submissionId);
      setDetail(data);
      setActiveQuestionNo((prev) => {
        if (prev) return prev;
        if (data.evaluation && data.evaluation.questions.length > 0) {
          return data.evaluation.questions[0].question_no;
        }
        const keys = Object.keys(data.question_region_map);
        return keys.length > 0 ? keys[0] : null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load submission");
    }
  }, [submissionId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const handleRegradeQuestion = async (questionNo: string, editedText: string) => {
    await api.regradeQuestion(submissionId, questionNo, editedText, "Professor transcript edit");
    await loadDetail();
  };

  if (error) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm font-medium text-red-800"
      >
        {error}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex h-64 items-center justify-center gap-2 text-sm text-[#475569]">
        <Loader2 className="h-5 w-5 animate-spin text-[#2563EB]" aria-hidden="true" />
        <span>Loading Pen-to-Print Review Desk...</span>
      </div>
    );
  }

  const activeRegions = activeQuestionNo
    ? detail.question_region_map[activeQuestionNo] || []
    : [];
  const activeEvalQ = detail.evaluation?.questions.find(
    (q) => q.question_no === activeQuestionNo
  );

  const mobileTabs: { id: MobilePane; label: string; icon: typeof ScanEye }[] = [
    { id: "scan", label: "Scan", icon: ScanEye },
    { id: "transcript", label: "Transcript", icon: FileText },
    { id: "evaluation", label: detail.evaluation ? "Grade" : "Sections", icon: ClipboardCheck },
  ];

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm sm:px-4">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/upload"
            className="inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-[#1E293B] transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            <span>Queue</span>
          </Link>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span className="truncate text-sm font-bold text-[#0F172A] sm:text-base">
                {detail.submission.roll_number}
              </span>
              <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-[#475569]">
                {detail.submission.submission_id}
              </span>
              <span className="rounded bg-blue-50 px-2 py-0.5 text-[11px] font-semibold text-[#2563EB]">
                {detail.submission.status}
              </span>
            </div>
            <div className="mt-0.5 truncate text-xs text-[#475569]">
              {detail.submission.original_filename} &middot; Engine:{" "}
              {detail.submission.engine_used}
              {detail.submission.wall_time_sec !== null &&
                detail.submission.wall_time_sec !== undefined && (
                  <>
                    {" "}
                    &middot;{" "}
                    <span className="font-mono font-medium text-[#0F172A]">
                      {detail.submission.wall_time_sec.toFixed(2)}s
                    </span>{" "}
                    ({detail.submission.ocr_time_sec?.toFixed(2) ?? "?"}s GPU
                    {detail.submission.estimated_cost_usd !== null &&
                    detail.submission.estimated_cost_usd !== undefined
                      ? ` · $${detail.submission.estimated_cost_usd.toFixed(4)}`
                      : ""}
                    )
                  </>
                )}
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Segmented Pane Switcher (< lg) */}
      <div
        role="tablist"
        aria-label="Review desk views"
        className="grid grid-cols-3 gap-1.5 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm lg:hidden"
      >
        {mobileTabs.map(({ id, label, icon: Icon }) => {
          const active = mobilePane === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setMobilePane(id)}
              className={`inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                active
                  ? "bg-[#1E293B] text-white shadow-sm"
                  : "text-[#475569] hover:bg-slate-100 hover:text-[#0F172A]"
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{label}</span>
            </button>
          );
        })}
      </div>

      {/* 3-Pane Pen-to-Print Split Workspace (Tabbed on Mobile, 40/30/30 Split on Desktop) */}
      <div className="grid grid-cols-1 gap-4 lg:h-[calc(100vh-195px)] lg:min-h-[620px] lg:grid-cols-10">
        <div
          className={`${
            mobilePane === "scan" ? "block" : "hidden"
          } h-[68vh] min-h-[420px] lg:col-span-4 lg:block lg:h-full`}
        >
          <ScanViewer
            pageImageUrls={detail.page_image_urls}
            ocr={detail.ocr}
            activeQuestionRegions={activeRegions}
            selectedRegionId={selectedRegionId}
            onSelectRegion={setSelectedRegionId}
          />
        </div>

        <div
          className={`${
            mobilePane === "transcript" ? "block" : "hidden"
          } h-[68vh] min-h-[420px] lg:col-span-3 lg:block lg:h-full`}
        >
          <TranscriptEditor
            submissionId={detail.submission.submission_id}
            cleanMarkdown={detail.clean_markdown}
            annotatedMarkdown={detail.annotated_markdown}
            ocr={detail.ocr}
            activeQuestionNo={activeQuestionNo}
            activeQuestionTranscript={activeEvalQ?.raw_transcript || null}
            hasEvaluation={Boolean(detail.evaluation)}
            onSaved={loadDetail}
            onRegradeQuestion={handleRegradeQuestion}
          />
        </div>

        <div
          className={`${
            mobilePane === "evaluation" ? "block" : "hidden"
          } h-[68vh] min-h-[420px] lg:col-span-3 lg:block lg:h-full`}
        >
          <EvaluationPanel
            submissionId={detail.submission.submission_id}
            evaluation={detail.evaluation}
            questionRegionMap={detail.question_region_map}
            overrides={detail.overrides}
            activeQuestionNo={activeQuestionNo}
            onSelectQuestion={setActiveQuestionNo}
            onUpdated={loadDetail}
          />
        </div>
      </div>
    </div>
  );
}
