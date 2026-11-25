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
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">
          Exam Setup &amp; Rubric Locking
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Draft a rubric from Question Paper &amp; Model Answer (optional), customize atomic
          criteria and diagram requirements, then lock it before grading scripts.
        </p>
      </div>

      <RubricEditor onSaved={refreshExams} />

      {exams.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold text-slate-900">Saved Exams</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {exams.map((ex) => (
              <div
                key={ex.exam_id}
                className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs"
              >
                <div className="flex items-center justify-between font-bold text-slate-900">
                  <span>{ex.title}</span>
                  {ex.is_locked && (
                    <span className="inline-flex items-center gap-1 rounded bg-slate-900 px-1.5 py-0.5 text-[10px] text-white">
                      <Lock className="h-2.5 w-2.5" />
                      Locked
                    </span>
                  )}
                </div>
                <div className="mt-1 text-slate-600">
                  {ex.exam_id} &middot; {ex.subject} &middot; {ex.total_marks} marks
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
