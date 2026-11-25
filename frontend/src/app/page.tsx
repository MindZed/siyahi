"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Cpu,
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
    <div className="space-y-5 sm:space-y-6">
      {/* Top Hero */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] font-semibold text-blue-700">
                Pen-to-Print + Auditable Rubric Desk
              </span>
              {health && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-[#334155]">
                  <Cpu className="h-3.5 w-3.5 text-[#2563EB]" aria-hidden="true" />
                  {health.mock_modal ? "Mock OCR" : "Modal L4: Qwen3.5-9B"} &middot;{" "}
                  {health.grader_provider}
                </span>
              )}
            </div>
            <h1 className="text-xl font-bold tracking-tight text-[#0F172A] sm:text-2xl">
              Siyahi — Handwriting OCR &amp; Exam Desk
            </h1>
            <p className="max-w-3xl text-sm leading-relaxed text-[#475569]">
              Upload handwritten PDFs or camera scans to extract clean Markdown &amp; typeset PDFs,
              inspect every stroke side-by-side, and optionally run pluggable AI rubric grading.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/setup"
              className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-[#1E293B] transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 sm:w-auto"
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
              Exam Setup
            </Link>
          </div>
        </div>
      </section>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800"
        >
          Backend connection error: {error}
        </div>
      )}

      {/* Primary Upload + Live Queue + Instant MD/PDF Result Workspace */}
      <UploadDropzone />

      {/* Configured Exams Summary */}
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-bold text-[#0F172A] sm:text-base">
            Configured Exam Rubrics
          </h2>
          <Link
            href="/setup"
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-[#2563EB] hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
          >
            <span>Manage Rubrics</span>
            <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
        {exams.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-xs text-[#475569] sm:text-sm">
            No exam rubrics configured yet — standalone Pen-to-Print conversion works right above,
            or create a rubric in <strong className="text-[#0F172A]">Exam Setup</strong>.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {exams.map((ex) => (
              <div
                key={ex.exam_id}
                className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50/70 p-3.5"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 text-sm font-semibold text-[#0F172A]">
                    <span className="truncate">{ex.title}</span>
                    {ex.is_locked && (
                      <Lock className="h-3.5 w-3.5 shrink-0 text-[#1E293B]" aria-label="Locked" />
                    )}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-[#475569]">
                    {ex.subject} &middot; {ex.total_marks} marks &middot; {ex.submission_count}{" "}
                    scripts
                  </div>
                </div>
                <a
                  href={api.exportCsvUrl(ex.exam_id)}
                  className="inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-[#1E293B] transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>CSV</span>
                </a>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
