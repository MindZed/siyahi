"use client";

import { useState } from "react";
import { Lock, Plus, Sparkles, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ExamRubric, QuestionRubric, QuestionType } from "@/types/schemas";

interface RubricEditorProps {
  onSaved?: (rubric: ExamRubric) => void;
}

export function RubricEditor({ onSaved }: RubricEditorProps) {
  const [subject, setSubject] = useState("datascience");
  const [title, setTitle] = useState("Midterm Exam");
  const [qpFile, setQpFile] = useState<File | null>(null);
  const [maFile, setMaFile] = useState<File | null>(null);

  const [rubric, setRubric] = useState<ExamRubric>({
    exam_id: `EXAM_${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
    subject: "datascience",
    title: "Midterm Exam",
    total_marks: 5,
    is_locked: false,
    questions: [
      {
        question_no: "Q1",
        question_text: "Explain the method and calculate the mean from grouped data.",
        max_marks: 5,
        question_type: "numerical",
        criteria: [
          {
            criterion_id: "Q1_C1",
            description: "Correct class marks and frequency table computation",
            max_points: 2.5,
            expected_keywords: ["class mark", "1730", "150"],
            accepted_alternatives: ["midpoint"],
            partial_credit_rule: "1 mark for partial table setup",
            requires_diagram: false,
          },
          {
            criterion_id: "Q1_C2",
            description: "Correct final mean value (11.53)",
            max_points: 2.5,
            expected_keywords: ["11.53"],
            accepted_alternatives: ["1730/150"],
            partial_credit_rule: "1 mark for formula without final division",
            requires_diagram: false,
          },
        ],
      },
    ],
  });

  const [loadingDraft, setLoadingDraft] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const recomputeTotal = (questions: QuestionRubric[]) =>
    Number(questions.reduce((acc, q) => acc + Number(q.max_marks || 0), 0).toFixed(2));

  const handleDraftFromFiles = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!qpFile || !maFile) return;
    setLoadingDraft(true);
    setMessage(null);
    try {
      const fd = new FormData();
      fd.append("subject", subject);
      fd.append("title", title);
      fd.append("question_paper", qpFile);
      fd.append("model_answer", maFile);
      const drafted = await api.draftRubric(fd);
      setRubric(drafted);
      setMessage("AI drafted rubric below. Review criteria and click Lock Exam Rubric.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to draft rubric");
    } finally {
      setLoadingDraft(false);
    }
  };

  const handleSaveAndLock = async (lock: boolean) => {
    setSaving(true);
    setMessage(null);
    try {
      const payload: ExamRubric = {
        ...rubric,
        subject,
        title,
        total_marks: recomputeTotal(rubric.questions),
        is_locked: lock,
      };
      const saved = await api.saveExam(payload);
      setRubric(saved);
      setMessage(lock ? `Exam ${saved.exam_id} locked and saved.` : `Saved draft ${saved.exam_id}.`);
      onSaved?.(saved);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to save exam");
    } finally {
      setSaving(false);
    }
  };

  const addQuestion = () => {
    const nextNo = `Q${rubric.questions.length + 1}`;
    const updated: QuestionRubric[] = [
      ...rubric.questions,
      {
        question_no: nextNo,
        question_text: "",
        max_marks: 5,
        question_type: "short_answer",
        criteria: [
          {
            criterion_id: `${nextNo}_C1`,
            description: "Core concept explanation",
            max_points: 5,
            expected_keywords: [],
            accepted_alternatives: [],
            partial_credit_rule: "",
            requires_diagram: false,
          },
        ],
      },
    ];
    setRubric({ ...rubric, questions: updated, total_marks: recomputeTotal(updated) });
  };

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleDraftFromFiles}
        className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h2 className="text-base font-bold text-slate-900">
          1. Upload Question Paper &amp; Model Answer (Optional AI Draft)
        </h2>
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="block text-xs font-semibold text-slate-600">Subject Code</label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="e.g. datascience"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600">Exam Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              placeholder="e.g. Midterm Data Science"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600">
              Question Paper (PDF/TXT/Image)
            </label>
            <input
              type="file"
              onChange={(e) => setQpFile(e.target.files?.[0] || null)}
              className="mt-1 w-full text-xs text-slate-700"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600">
              Model Answer Script (PDF/TXT/Image)
            </label>
            <input
              type="file"
              onChange={(e) => setMaFile(e.target.files?.[0] || null)}
              className="mt-1 w-full text-xs text-slate-700"
            />
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={loadingDraft || !qpFile || !maFile}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-50 disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {loadingDraft ? "Drafting Rubric..." : "Draft Rubric with AI"}
          </button>
        </div>
      </form>

      {/* Interactive Rubric Card Editor */}
      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              2. Interactive Rubric Editor ({rubric.exam_id})
            </h2>
            <p className="text-xs text-slate-500">
              Total Marks: {recomputeTotal(rubric.questions)} &middot; Status:{" "}
              {rubric.is_locked ? "Locked" : "Draft"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={addQuestion}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Question
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => handleSaveAndLock(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              <Lock className="h-3.5 w-3.5" />
              {saving ? "Locking..." : "Lock Exam Rubric"}
            </button>
          </div>
        </div>

        {message && (
          <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
            {message}
          </div>
        )}

        <div className="space-y-4">
          {rubric.questions.map((q, qi) => (
            <div key={qi} className="rounded-lg border border-slate-200 bg-slate-50/60 p-4">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
                <input
                  value={q.question_no}
                  onChange={(e) => {
                    const next = [...rubric.questions];
                    next[qi] = { ...q, question_no: e.target.value };
                    setRubric({ ...rubric, questions: next });
                  }}
                  className="md:col-span-2 rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-bold"
                  placeholder="Q1"
                />
                <input
                  value={q.question_text}
                  onChange={(e) => {
                    const next = [...rubric.questions];
                    next[qi] = { ...q, question_text: e.target.value };
                    setRubric({ ...rubric, questions: next });
                  }}
                  className="md:col-span-5 rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
                  placeholder="Question prompt"
                />
                <select
                  value={q.question_type}
                  onChange={(e) => {
                    const next = [...rubric.questions];
                    next[qi] = { ...q, question_type: e.target.value as QuestionType };
                    setRubric({ ...rubric, questions: next });
                  }}
                  className="md:col-span-3 rounded border border-slate-300 bg-white px-2 py-1.5 text-xs"
                >
                  <option value="short_answer">short_answer</option>
                  <option value="long_answer">long_answer</option>
                  <option value="numerical">numerical</option>
                  <option value="diagram_heavy">diagram_heavy</option>
                </select>
                <div className="md:col-span-2 flex items-center gap-1.5">
                  <input
                    type="number"
                    step="0.5"
                    value={q.max_marks}
                    onChange={(e) => {
                      const next = [...rubric.questions];
                      next[qi] = { ...q, max_marks: Number(e.target.value) };
                      setRubric({
                        ...rubric,
                        questions: next,
                        total_marks: recomputeTotal(next),
                      });
                    }}
                    className="w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-xs font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => {
                      const next = rubric.questions.filter((_, idx) => idx !== qi);
                      setRubric({
                        ...rubric,
                        questions: next,
                        total_marks: recomputeTotal(next),
                      });
                    }}
                    className="rounded p-1 text-slate-400 hover:text-red-600"
                    title="Remove Question"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Criteria */}
              <div className="mt-3 space-y-2 pl-2">
                {q.criteria.map((c, ci) => (
                  <div
                    key={c.criterion_id}
                    className="grid grid-cols-1 gap-2 rounded border border-slate-200 bg-white p-2.5 md:grid-cols-12"
                  >
                    <input
                      value={c.description}
                      onChange={(e) => {
                        const next = [...rubric.questions];
                        const crit = [...q.criteria];
                        crit[ci] = { ...c, description: e.target.value };
                        next[qi] = { ...q, criteria: crit };
                        setRubric({ ...rubric, questions: next });
                      }}
                      className="md:col-span-5 rounded border border-slate-200 px-2 py-1 text-xs"
                      placeholder="Criterion description"
                    />
                    <input
                      value={c.expected_keywords.join(", ")}
                      onChange={(e) => {
                        const next = [...rubric.questions];
                        const crit = [...q.criteria];
                        crit[ci] = {
                          ...c,
                          expected_keywords: e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean),
                        };
                        next[qi] = { ...q, criteria: crit };
                        setRubric({ ...rubric, questions: next });
                      }}
                      className="md:col-span-4 rounded border border-slate-200 px-2 py-1 text-xs"
                      placeholder="Keywords (comma separated)"
                    />
                    <input
                      type="number"
                      step="0.5"
                      value={c.max_points}
                      onChange={(e) => {
                        const next = [...rubric.questions];
                        const crit = [...q.criteria];
                        crit[ci] = { ...c, max_points: Number(e.target.value) };
                        next[qi] = { ...q, criteria: crit };
                        setRubric({ ...rubric, questions: next });
                      }}
                      className="md:col-span-1 rounded border border-slate-200 px-2 py-1 text-xs font-mono"
                    />
                    <label className="md:col-span-2 flex items-center gap-1 text-[11px] text-slate-600">
                      <input
                        type="checkbox"
                        checked={c.requires_diagram}
                        onChange={(e) => {
                          const next = [...rubric.questions];
                          const crit = [...q.criteria];
                          crit[ci] = { ...c, requires_diagram: e.target.checked };
                          next[qi] = { ...q, criteria: crit };
                          setRubric({ ...rubric, questions: next });
                        }}
                      />
                      Diagram
                    </label>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
