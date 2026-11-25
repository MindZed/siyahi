"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { EvaluationPanel } from "@/components/EvaluationPanel";
import { ScanViewer } from "@/components/ScanViewer";
import { TranscriptEditor } from "@/components/TranscriptEditor";
import { api } from "@/lib/api";
import type { SubmissionDetailResponse } from "@/types/schemas";

export default function ReviewDeskPage() {
  const params = useParams<{ submissionId: string }>();
  const submissionId = params.submissionId;

  const [detail, setDetail] = useState<SubmissionDetailResponse | null>(null);
  const [activeQuestionNo, setActiveQuestionNo] = useState<string | null>(null);
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
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
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        {error}
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex h-64 items-center justify-center gap-2 text-sm text-slate-600">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading 3-Pane Pen-to-Print Review Desk...
      </div>
    );
  }

  const activeRegions = activeQuestionNo
    ? detail.question_region_map[activeQuestionNo] || []
    : [];
  const activeEvalQ = detail.evaluation?.questions.find(
    (q) => q.question_no === activeQuestionNo
  );

  return (
    <div className="space-y-4">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <Link
            href="/upload"
            className="inline-flex items-center gap-1 rounded border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Queue
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold text-slate-900">
                {detail.submission.roll_number}
              </span>
              <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600">
                {detail.submission.submission_id}
              </span>
              <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                {detail.submission.status}
              </span>
            </div>
            <div className="text-xs text-slate-500">
              {detail.submission.original_filename} &middot; Engine: {detail.submission.engine_used}
            </div>
          </div>
        </div>
      </div>

      {/* 3-Pane Pen-to-Print Split Workspace (40% / 30% / 30%) */}
      <div className="grid h-[calc(100vh-190px)] min-h-[620px] grid-cols-1 gap-4 lg:grid-cols-10">
        <div className="h-full min-h-[420px] lg:col-span-4">
          <ScanViewer
            pageImageUrls={detail.page_image_urls}
            ocr={detail.ocr}
            activeQuestionRegions={activeRegions}
            selectedRegionId={selectedRegionId}
            onSelectRegion={setSelectedRegionId}
          />
        </div>

        <div className="h-full min-h-[420px] lg:col-span-3">
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

        <div className="h-full min-h-[420px] lg:col-span-3">
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
