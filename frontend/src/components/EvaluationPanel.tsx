"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, History, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import type {
  AuditOverrideRecord,
  EvaluationReport,
  QuestionEvaluation,
  RegionRef,
} from "@/types/schemas";

interface EvaluationPanelProps {
  submissionId: string;
  evaluation?: EvaluationReport | null;
  questionRegionMap: Record<string, RegionRef[]>;
  overrides: AuditOverrideRecord[];
  activeQuestionNo: string | null;
  onSelectQuestion: (questionNo: string) => void;
  onUpdated: () => void;
}

export function EvaluationPanel({
  submissionId,
  evaluation,
  questionRegionMap,
  overrides,
  activeQuestionNo,
  onSelectQuestion,
  onUpdated,
}: EvaluationPanelProps) {
  const activeQ: QuestionEvaluation | undefined = evaluation?.questions.find(
    (q) => q.question_no === activeQuestionNo
  );

  const [overrideMarks, setOverrideMarks] = useState<string>("");
  const [overrideNote, setOverrideNote] = useState<string>("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (activeQ) {
      setOverrideMarks(String(activeQ.final_marks));
      setOverrideNote(activeQ.override_note || "");
    }
  }, [activeQ]);

  const handleOverride = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeQ) return;
    setSaving(true);
    try {
      await api.overrideQuestion(
        submissionId,
        activeQ.question_no,
        Number(overrideMarks),
        overrideNote
      );
      onUpdated();
    } finally {
      setSaving(false);
    }
  };

  // Standalone Pen-to-Print View (No Exam Rubric attached yet)
  if (!evaluation) {
    const keys = Object.keys(questionRegionMap);
    return (
      <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
          <h2 className="text-sm font-bold text-slate-900">
            Pen-to-Print Sections &amp; Regions
          </h2>
          <p className="text-xs text-slate-500">
            Standalone transcription mode (AI Grader disabled for this script).
          </p>
        </div>

        <div className="flex-1 space-y-3 overflow-auto p-4">
          {keys.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 p-4 text-xs text-slate-500">
              No segmented regions yet.
            </div>
          ) : (
            keys.map((qNo) => {
              const refs = questionRegionMap[qNo] || [];
              const selected = activeQuestionNo === qNo;
              return (
                <button
                  key={qNo}
                  type="button"
                  onClick={() => onSelectQuestion(qNo)}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selected
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-white text-slate-800 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold">{qNo}</span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[11px] ${
                        selected ? "bg-slate-700 text-slate-100" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {refs.length} regions
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Score Summary Header */}
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Total Score
            </div>
            <div className="text-xl font-bold text-slate-900">
              {evaluation.total_final_marks} / {evaluation.total_max_marks}
            </div>
          </div>
          <a
            href={api.exportCsvUrl(evaluation.exam_id)}
            className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
          >
            <Download className="h-3.5 w-3.5" />
            CSV
          </a>
        </div>

        {/* Question Selector Tabs */}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {evaluation.questions.map((q) => {
            const isActive = q.question_no === activeQuestionNo;
            return (
              <button
                key={q.question_no}
                type="button"
                onClick={() => onSelectQuestion(q.question_no)}
                className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold ${
                  isActive
                    ? "bg-slate-900 text-white"
                    : q.needs_human_review
                    ? "border border-amber-300 bg-amber-50 text-amber-900"
                    : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
                }`}
              >
                {q.question_no}: {q.final_marks}/{q.max_marks}
                {q.needs_human_review && <AlertTriangle className="h-3 w-3 text-amber-600" />}
              </button>
            );
          })}
        </div>
      </div>

      {/* Active Question Criteria & Override */}
      <div className="flex-1 space-y-4 overflow-auto p-4">
        {activeQ && (
          <>
            {activeQ.needs_human_review && (
              <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
                <div className="flex items-center gap-1.5 font-bold">
                  <ShieldAlert className="h-4 w-4 text-amber-700" />
                  NEEDS HUMAN REVIEW (Spread Δŷ = {activeQ.mark_spread_delta})
                </div>
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  {activeQ.review_reasons.map((reason, idx) => (
                    <li key={idx}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="space-y-2.5">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Criterion Audit Breakdown
              </div>
              {activeQ.criteria_breakdown.map((crit) => (
                <div
                  key={crit.criterion_id}
                  className="rounded-lg border border-slate-200 bg-slate-50/70 p-3 text-xs"
                >
                  <div className="flex items-center justify-between font-bold text-slate-900">
                    <span>{crit.criterion_id}</span>
                    <span>
                      {crit.awarded_points} / {crit.max_points}
                    </span>
                  </div>
                  {crit.student_quote && (
                    <div className="mt-1.5 rounded border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] text-slate-700">
                      &ldquo;{crit.student_quote}&rdquo;{" "}
                      <span
                        className={`ml-1 inline-flex items-center gap-0.5 font-sans font-semibold ${
                          crit.quote_verified ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {crit.quote_verified ? (
                          <>
                            <CheckCircle2 className="h-3 w-3" /> Verified
                          </>
                        ) : (
                          "Unverified Quote"
                        )}
                      </span>
                    </div>
                  )}
                  <p className="mt-1.5 text-slate-600">{crit.reason}</p>
                </div>
              ))}
            </div>

            {/* 1-Click Teacher Override */}
            <form
              onSubmit={handleOverride}
              className="space-y-2.5 rounded-lg border border-slate-200 bg-slate-50 p-3"
            >
              <div className="text-xs font-bold text-slate-800">
                Professor Confirm / Override ({activeQ.question_no})
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step="0.5"
                  min={0}
                  max={activeQ.max_marks}
                  value={overrideMarks}
                  onChange={(e) => setOverrideMarks(e.target.value)}
                  className="w-24 rounded border border-slate-300 bg-white px-2.5 py-1.5 text-sm font-bold"
                />
                <span className="text-xs text-slate-500">/ {activeQ.max_marks}</span>
              </div>
              <input
                value={overrideNote}
                onChange={(e) => setOverrideNote(e.target.value)}
                placeholder="Optional override rationale..."
                className="w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
              />
              <button
                type="submit"
                disabled={saving}
                className="w-full rounded-lg bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Confirm / Override Mark"}
              </button>
            </form>
          </>
        )}

        {overrides.length > 0 && (
          <div className="space-y-1.5 border-t border-slate-200 pt-3">
            <div className="flex items-center gap-1 text-xs font-bold text-slate-500">
              <History className="h-3.5 w-3.5" />
              Audit Override Log
            </div>
            {overrides.map((ovr) => (
              <div key={ovr.override_id} className="rounded border border-slate-200 p-2 text-[11px]">
                <strong>{ovr.question_no}</strong>: {ovr.previous_marks} &rarr;{" "}
                <strong>{ovr.new_marks}</strong>
                {ovr.teacher_note && <div className="text-slate-600">{ovr.teacher_note}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
