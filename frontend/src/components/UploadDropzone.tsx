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

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleUpload}
        className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              Mode / Exam Link
            </label>
            <select
              value={selectedExamId}
              onChange={(e) => setSelectedExamId(e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
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
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              OCR Engine
            </label>
            <select
              value={engine}
              onChange={(e) => setEngine(e.target.value as "vlm" | "paddle_trocr")}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            >
              <option value="vlm">PP-DocLayoutV3 + Qwen3.5-9B (Primary)</option>
              <option value="paddle_trocr">PaddleOCR + TrOCR (Arm A Baseline)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
              Layout Strategy
            </label>
            <select
              value={mode}
              onChange={(e) =>
                setMode(e.target.value as "hybrid" | "whole_page" | "strict_regions")
              }
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            >
              <option value="hybrid">Hybrid (Whole-Page Flow + Diagram Crops)</option>
              <option value="whole_page">Whole-Page Markdown Only</option>
              <option value="strict_regions">Strict Region-by-Region</option>
            </select>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-6 text-sm text-slate-700">
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={skipCoverPage}
              onChange={(e) => setSkipCoverPage(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span>First page contains student details only (strip Page 1 PII)</span>
          </label>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={sensitivitySampling}
              onChange={(e) => setSensitivitySampling(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            <span>Enable K=3 ambiguity sampling on unclear regions</span>
          </label>
        </div>

        <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center transition hover:border-blue-400 hover:bg-blue-50/40">
          <UploadCloud className="h-9 w-9 text-slate-500" />
          <div className="mt-2 text-sm font-semibold text-slate-800">
            Select handwritten PDFs or images (e.g.,{" "}
            <span className="font-mono">CSE234002_datascience.pdf</span>)
          </div>
          <div className="mt-1 text-xs text-slate-500">
            Supports PDF, PNG, JPG. Roll numbers stay local; anonymized scans go to OCR.
          </div>
          <input
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.webp"
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
            className="hidden"
          />
          {files.length > 0 && (
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {files.map((f) => (
                <span
                  key={f.name}
                  className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white"
                >
                  {f.name}
                </span>
              ))}
            </div>
          )}
        </label>

        {error && (
          <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
            {error}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={uploading || files.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Uploading...
              </>
            ) : (
              "Process Scripts"
            )}
          </button>
        </div>
      </form>

      {/* Queue Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-5 py-3">
          <h2 className="text-sm font-bold text-slate-900">Submission Queue &amp; Exports</h2>
          {selectedExamId && (
            <a
              href={api.exportCsvUrl(selectedExamId)}
              className="inline-flex items-center gap-1.5 rounded border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100"
            >
              <Download className="h-3.5 w-3.5" />
              Export Class CSV
            </a>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-white text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Roll No / File</th>
                <th className="px-4 py-3">Pipeline Status</th>
                <th className="px-4 py-3">Score</th>
                <th className="px-4 py-3">Review Flags</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {submissions.map((sub) => {
                const isRunning = ["queued", "preprocessing", "ocr_running", "grading"].includes(
                  sub.status
                );
                return (
                  <tr key={sub.submission_id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <div className="font-semibold text-slate-900">{sub.roll_number}</div>
                      <div className="text-xs text-slate-500">
                        {sub.original_filename} &middot; {sub.submission_id}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {isRunning ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {sub.status}
                        </span>
                      ) : sub.status.startsWith("failed") ? (
                        <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-800">
                          {sub.status}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          {sub.status}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">
                      {sub.total_final_marks !== null && sub.total_final_marks !== undefined
                        ? `${sub.total_final_marks} (AI: ${sub.total_ai_marks})`
                        : "OCR Only"}
                    </td>
                    <td className="px-4 py-3">
                      {sub.needs_review_count > 0 ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                          <AlertTriangle className="h-3 w-3" />
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
                          className="rounded border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                        >
                          .MD
                        </a>
                        <a
                          href={api.exportPdfUrl(sub.submission_id)}
                          className="rounded border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                        >
                          .PDF
                        </a>
                        <Link
                          href={`/review/${sub.submission_id}`}
                          className="inline-flex items-center gap-1 rounded bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white hover:bg-slate-800"
                        >
                          <FileText className="h-3.5 w-3.5" />
                          Review
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {submissions.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-slate-500">
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
