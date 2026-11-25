"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Download,
  Lock,
  SlidersHorizontal,
} from "lucide-react";
import { UploadDropzone } from "@/components/UploadDropzone";
import { api } from "@/lib/api";
import type { ExamListItem, HealthStatus } from "@/types/schemas";

export default function HomePage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [exams, setExams] = useState<ExamListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.listExams()])
      .then(([h, e]) => {
        setHealth(h);
        setExams(e);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="space-y-6">
      {/* Top Hero */}
      <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Siyahi — Pen-to-Print Handwriting &amp; Exam Desk
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Upload handwritten PDFs or scans to extract clean Markdown &amp; typeset PDFs, inspect
            every stroke side-by-side, and optionally run pluggable AI rubric grading.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {health && (
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
              {health.mock_modal ? "Mock OCR" : "Modal L4: Qwen3.5-9B"} &middot;{" "}
              {health.grader_provider}
            </span>
          )}
          <Link
            href="/setup"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            <SlidersHorizontal className="h-4 w-4" />
            Exam Setup
          </Link>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Backend connection error: {error}
        </div>
      )}

      {/* Primary Upload + Live Queue + Instant MD/PDF Result Workspace */}
      <UploadDropzone />

      {/* Configured Exams Summary */}
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900">Configured Exam Rubrics</h2>
          <Link
            href="/setup"
            className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline"
          >
            Manage Rubrics <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        {exams.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 py-5 text-center text-xs text-slate-500">
            No exam rubrics configured yet — standalone Pen-to-Print conversion works right above,
            or create a rubric in <strong>Exam Setup</strong>.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {exams.map((ex) => (
              <div
                key={ex.exam_id}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-3"
              >
                <div>
                  <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-900">
                    <span>{ex.title}</span>
                    {ex.is_locked && <Lock className="h-3.5 w-3.5 text-slate-700" />}
                  </div>
                  <div className="text-xs text-slate-500">
                    {ex.subject} &middot; {ex.total_marks} marks &middot; {ex.submission_count} scripts
                  </div>
                </div>
                <a
                  href={api.exportCsvUrl(ex.exam_id)}
                  className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100"
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
  );
}
