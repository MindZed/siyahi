"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  UploadCloud,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ExamListItem, SubmissionSummary } from "@/types/schemas";

export function UploadDropzone() {
  const [exams, setExams] = useState<ExamListItem[]>([]);
  const [selectedExamId, setSelectedExamId] = useState<string>("");
  const [engine, setEngine] = useState<"vlm" | "paddle_trocr">("vlm");
  const [mode, setMode] = useState<"hybrid" | "whole_page" | "strict_regions">("hybrid");
  const [skipCoverPage, setSkipCoverPage] = useState(true);
  const [sensitivitySampling, setSensitivitySampling] = useState(false);

  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submissions, setSubmissions] = useState<SubmissionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [exList, subList] = await Promise.all([
        api.listExams(),
        api.listSubmissions(selectedExamId || undefined),
      ]);
      setExams(exList);
      setSubmissions(subList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queue");
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedExamId]);

  // Poll while any submission is still processing
  useEffect(() => {
    const active = submissions.some((s) =>
      ["queued", "preprocessing", "ocr_running", "grading"].includes(s.status)
    );
    if (!active) return;
    const timer = setInterval(() => {
      loadData();
    }, 2000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submissions, selectedExamId]);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      if (selectedExamId) fd.append("exam_id", selectedExamId);
      fd.append("engine", engine);
      fd.append("mode", mode);
      fd.append("skip_cover_page", String(skipCoverPage));
      fd.append("enable_sensitivity_sampling", String(sensitivitySampling));

      await api.uploadSubmissions(fd);
      setFiles([]);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const renderStatusBadge = (status: string) => {
    const isRunning = ["queued", "preprocessing", "ocr_running", "grading"].includes(status);
    if (isRunning) {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-[#2563EB]">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          {status}
        </span>
      );
    }
    if (status.startsWith("failed")) {
      return (
        <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-1 text-xs font-semibold text-red-800">
          {status}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        {status}
      </span>
    );
  };

  return (
    <div className="space-y-5 sm:space-y-6">
      <form
        onSubmit={handleUpload}
        className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <label
              htmlFor="exam-select"
              className="block text-xs font-semibold uppercase tracking-wider text-[#475569]"
            >
              Mode / Exam Link
            </label>
            <select
              id="exam-select"
              value={selectedExamId}
              onChange={(e) => setSelectedExamId(e.target.value)}
              className="mt-1.5 min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-[#0F172A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              <option value="">Pen-to-Print Only (No AI Grader)</option>
              {exams.map((ex) => (
                <option key={ex.exam_id} value={ex.exam_id}>
                  {ex.title} ({ex.subject}) {ex.is_locked ? "— Locked" : "— Draft"}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="ocr-engine"
              className="block text-xs font-semibold uppercase tracking-wider text-[#475569]"
            >
              OCR Engine
            </label>
            <select
              id="ocr-engine"
              value={engine}
              onChange={(e) => setEngine(e.target.value as "vlm" | "paddle_trocr")}
              className="mt-1.5 min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-[#0F172A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              <option value="vlm">PP-DocLayoutV3 + Qwen3.5-9B (Primary)</option>
              <option value="paddle_trocr">PaddleOCR + TrOCR (Arm A Baseline)</option>
            </select>
          </div>

          <div>
            <label
              htmlFor="layout-strategy"
              className="block text-xs font-semibold uppercase tracking-wider text-[#475569]"
            >
              Layout Strategy
            </label>
            <select
              id="layout-strategy"
              value={mode}
              onChange={(e) =>
                setMode(e.target.value as "hybrid" | "whole_page" | "strict_regions")
              }
              className="mt-1.5 min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-[#0F172A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              <option value="hybrid">Hybrid (Whole-Page Flow + Diagram Crops)</option>
              <option value="whole_page">Whole-Page Markdown Only</option>
              <option value="strict_regions">Strict Region-by-Region</option>
            </select>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 text-sm text-[#334155] sm:flex-row sm:flex-wrap sm:items-center sm:gap-6">
          <label className="inline-flex min-h-[44px] cursor-pointer items-center gap-2.5">
            <input
              type="checkbox"
              checked={skipCoverPage}
              onChange={(e) => setSkipCoverPage(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-[#2563EB] focus:ring-blue-600"
            />
            <span>First page contains student details only (strip Page 1 PII)</span>
          </label>
          <label className="inline-flex min-h-[44px] cursor-pointer items-center gap-2.5">
            <input
              type="checkbox"
              checked={sensitivitySampling}
              onChange={(e) => setSensitivitySampling(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-[#2563EB] focus:ring-blue-600"
            />
            <span>Enable K=3 ambiguity sampling on unclear regions</span>
          </label>
        </div>

        <label className="mt-4 flex min-h-[140px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/70 px-4 py-7 text-center transition-colors hover:border-[#2563EB] hover:bg-blue-50/40 focus-within:ring-2 focus-within:ring-blue-600 sm:px-6 sm:py-8">
          <UploadCloud className="h-9 w-9 text-[#475569]" aria-hidden="true" />
          <div className="mt-2.5 text-sm font-semibold text-[#0F172A]">
            Select handwritten PDFs or images (e.g.,{" "}
            <span className="font-mono text-xs sm:text-sm">CSE234002_datascience.pdf</span>)
          </div>
          <div className="mt-1 text-xs text-[#475569]">
            Supports PDF, PNG, JPG. Roll numbers stay local; anonymized scans go to OCR.
          </div>
          <input
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.webp"
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
            className="sr-only"
          />
          {files.length > 0 && (
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {files.map((f) => (
                <span
                  key={f.name}
                  className="rounded-full bg-[#1E293B] px-3 py-1 text-xs font-medium text-white"
                >
                  {f.name}
                </span>
              ))}
            </div>
          )}
        </label>

        {error && (
          <div
            role="alert"
            className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-800"
          >
            {error}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={uploading || files.length === 0}
            className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg bg-[#2563EB] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
          >
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                <span>Uploading...</span>
              </>
            ) : (
              <span>Process Scripts</span>
            )}
          </button>
        </div>
      </form>

      {/* Queue List (Mobile Cards + Desktop Table) */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3 sm:px-5">
          <h2 className="text-sm font-bold text-[#0F172A] sm:text-base">
            Submission Queue &amp; Exports
          </h2>
          {selectedExamId && (
            <a
              href={api.exportCsvUrl(selectedExamId)}
              className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-[#1E293B] hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Export Class CSV</span>
            </a>
          )}
        </div>

        {/* Mobile Card View (< md) */}
        <div className="divide-y divide-slate-100 md:hidden">
          {submissions.map((sub) => (
            <div key={sub.submission_id} className="space-y-3 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-bold text-[#0F172A]">{sub.roll_number}</div>
                  <div className="mt-0.5 truncate text-xs text-[#475569]">
                    {sub.original_filename} &middot;{" "}
                    <span className="font-mono">{sub.submission_id}</span>
                  </div>
                </div>
                {renderStatusBadge(sub.status)}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="font-mono font-medium text-[#334155]">
                  {sub.total_final_marks !== null && sub.total_final_marks !== undefined
                    ? `Score: ${sub.total_final_marks} (AI: ${sub.total_ai_marks})`
                    : "OCR Only"}
                </span>
                {sub.needs_review_count > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 font-semibold text-amber-800">
                    <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                    {sub.needs_review_count} Flagged
                  </span>
                )}
              </div>

              <div className="grid grid-cols-3 gap-2 pt-1">
                <a
                  href={api.exportMdUrl(sub.submission_id, "clean")}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-[#1E293B] hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                >
                  .MD
                </a>
                <a
                  href={api.exportPdfUrl(sub.submission_id)}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-[#1E293B] hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                >
                  .PDF
                </a>
                <Link
                  href={`/review/${sub.submission_id}`}
                  className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-[#1E293B] px-2.5 text-xs font-semibold text-white hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                >
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Review</span>
                </Link>
              </div>
            </div>
          ))}
          {submissions.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-[#475569]">
              No submissions in queue yet.
            </div>
          )}
        </div>

        {/* Desktop Table View (>= md) */}
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-white text-xs uppercase text-[#475569]">
              <tr>
                <th className="px-4 py-3">Roll No / File</th>
                <th className="px-4 py-3">Pipeline Status</th>
                <th className="px-4 py-3">Score</th>
                <th className="px-4 py-3">Review Flags</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {submissions.map((sub) => (
                <tr key={sub.submission_id} className="hover:bg-slate-50/70">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-[#0F172A]">{sub.roll_number}</div>
                    <div className="text-xs text-[#475569]">
                      {sub.original_filename} &middot;{" "}
                      <span className="font-mono">{sub.submission_id}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">{renderStatusBadge(sub.status)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-[#334155]">
                    {sub.total_final_marks !== null && sub.total_final_marks !== undefined
                      ? `${sub.total_final_marks} (AI: ${sub.total_ai_marks})`
                      : "OCR Only"}
                  </td>
                  <td className="px-4 py-3">
                    {sub.needs_review_count > 0 ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                        {sub.needs_review_count} Flagged
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <a
                        href={api.exportMdUrl(sub.submission_id, "clean")}
                        className="inline-flex min-h-[36px] items-center rounded-md border border-slate-200 px-2.5 py-1 text-xs font-semibold text-[#1E293B] hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                      >
                        .MD
                      </a>
                      <a
                        href={api.exportPdfUrl(sub.submission_id)}
                        className="inline-flex min-h-[36px] items-center rounded-md border border-slate-200 px-2.5 py-1 text-xs font-semibold text-[#1E293B] hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                      >
                        .PDF
                      </a>
                      <Link
                        href={`/review/${sub.submission_id}`}
                        className="inline-flex min-h-[36px] items-center gap-1.5 rounded-md bg-[#1E293B] px-3 py-1 text-xs font-semibold text-white hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                      >
                        <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Review</span>
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
              {submissions.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-[#475569]">
                    No submissions in queue yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
