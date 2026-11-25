"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  FileText,
  FileUp,
  Lock,
  SlidersHorizontal,
} from "lucide-react";
import { api } from "@/lib/api";
import type { ExamListItem, HealthStatus, SubmissionSummary } from "@/types/schemas";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [exams, setExams] = useState<ExamListItem[]>([]);
  const [submissions, setSubmissions] = useState<SubmissionSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.listExams(), api.listSubmissions()])
      .then(([h, e, s]) => {
        setHealth(h);
        setExams(e);
        setSubmissions(s);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Pen-to-Print &amp; Auditable Grading Overview
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Convert handwritten scripts into clean Markdown &amp; PDFs first, then run pluggable
            criterion-by-criterion grading with human-in-the-loop review.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Link
            href="/upload"
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
          >
            <FileUp className="h-4 w-4" />
            Upload Handwritten PDF
          </Link>
          <Link
            href="/setup"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            <SlidersHorizontal className="h-4 w-4" />
            Setup Exam Rubric
          </Link>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Backend unreachable ({error}). Start FastAPI with{" "}
          <code className="font-mono font-semibold">uvicorn backend.main:app --reload</code>.
        </div>
      )}

      {health && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              OCR Pipeline
            </div>
            <div className="mt-1 text-base font-bold text-slate-900">
              {health.mock_modal ? "Local Mock OCR" : "Modal L4 (Qwen3.5-9B)"}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Variable AI Grader
            </div>
            <div className="mt-1 text-base font-bold text-slate-900">
              {health.grader_provider} ({health.grader_model})
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Configured Exams
            </div>
            <div className="mt-1 text-2xl font-bold text-slate-900">{exams.length}</div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Processed Scripts
            </div>
            <div className="mt-1 text-2xl font-bold text-slate-900">{submissions.length}</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Submissions */}
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">Recent Script Transcriptions</h2>
            <Link
              href="/upload"
              className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline"
            >
              Upload More <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          {submissions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 py-10 text-center text-sm text-slate-500">
              No handwritten scripts uploaded yet. Go to <strong>Upload &amp; OCR</strong> to start.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {submissions.slice(0, 8).map((sub) => (
                <div key={sub.submission_id} className="flex items-center justify-between py-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{sub.roll_number}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">
                        {sub.submission_id}
                      </span>
                      {sub.needs_review_count > 0 ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                          <AlertTriangle className="h-3 w-3" />
                          {sub.needs_review_count} Review
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                          <CheckCircle2 className="h-3 w-3" />
                          {sub.status}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {sub.original_filename} &middot; {sub.engine_used}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <a
                      href={api.exportPdfUrl(sub.submission_id)}
                      className="inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                      title="Download Pen-to-Print PDF"
                    >
                      <Download className="h-3.5 w-3.5" />
                      PDF
                    </a>
                    <Link
                      href={`/review/${sub.submission_id}`}
                      className="inline-flex items-center gap-1 rounded bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white hover:bg-slate-800"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      Review
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Configured Exams */}
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-bold text-slate-900">Configured Exam Rubrics</h2>
            <Link
              href="/setup"
              className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline"
            >
              Create Exam <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          {exams.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 py-10 text-center text-sm text-slate-500">
              No exam rubrics yet. You can run standalone Pen-to-Print OCR anytime or set up a rubric in{" "}
              <strong>Exam Setup</strong>.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {exams.map((ex) => (
                <div key={ex.exam_id} className="flex items-center justify-between py-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{ex.title}</span>
                      {ex.is_locked && (
                        <span className="inline-flex items-center gap-1 rounded bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white">
                          <Lock className="h-3 w-3" />
                          Locked
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {ex.subject} &middot; {ex.question_count} questions &middot; {ex.total_marks} marks
                      &middot; {ex.submission_count} submissions
                    </div>
                  </div>
                  <a
                    href={api.exportCsvUrl(ex.exam_id)}
                    className="inline-flex items-center gap-1 rounded border border-slate-300 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    <Download className="h-3.5 w-3.5" />
                    CSV
                  </a>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
