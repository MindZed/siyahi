"use client";

import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { RubricEditor } from "@/components/RubricEditor";
import { api } from "@/lib/api";
import type { ExamListItem } from "@/types/schemas";

export default function SetupPage() {
  const [exams, setExams] = useState<ExamListItem[]>([]);

  const refreshExams = () => {
    api.listExams().then(setExams).catch(() => {});
  };

  useEffect(() => {
    refreshExams();
  }, []);

  return (
    <div className="space-y-5 sm:space-y-6">
      <div className="space-y-1">
        <h1 className="text-xl font-bold tracking-tight text-[#0F172A] sm:text-2xl">
          Exam Setup &amp; Rubric Locking
        </h1>
        <p className="text-sm leading-relaxed text-[#475569]">
          Draft a rubric from Question Paper &amp; Model Answer (optional), customize atomic
          criteria and diagram requirements, then lock it before grading scripts.
        </p>
      </div>

      <RubricEditor onSaved={refreshExams} />

      {exams.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <h2 className="text-sm font-bold text-[#0F172A] sm:text-base">Saved Exams</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {exams.map((ex) => (
              <div
                key={ex.exam_id}
                className="rounded-lg border border-slate-200 bg-slate-50/70 p-3.5 text-xs"
              >
                <div className="flex items-center justify-between gap-2 font-bold text-[#0F172A]">
                  <span className="truncate">{ex.title}</span>
                  {ex.is_locked && (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded bg-[#1E293B] px-2 py-0.5 text-[10px] font-semibold text-white">
                      <Lock className="h-2.5 w-2.5" aria-hidden="true" />
                      Locked
                    </span>
                  )}
                </div>
                <div className="mt-1 truncate text-[#475569]">
                  <span className="font-mono">{ex.exam_id}</span> &middot; {ex.subject} &middot;{" "}
                  {ex.total_marks} marks
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
