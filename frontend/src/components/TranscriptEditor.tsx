"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, Edit3, Eye, FileDown, Save, Sparkles } from "lucide-react";
import { api, apiUrl } from "@/lib/api";
import type { OCRDocumentResponse } from "@/types/schemas";

interface TranscriptEditorProps {
  submissionId: string;
  cleanMarkdown: string;
  annotatedMarkdown: string;
  ocr?: OCRDocumentResponse | null;
  activeQuestionNo?: string | null;
  activeQuestionTranscript?: string | null;
  hasEvaluation?: boolean;
  onSaved?: () => void;
  onRegradeQuestion?: (questionNo: string, editedText: string) => Promise<void>;
}

const TOKEN_SPLIT_RE = /(\[struck:\s*.*?\]|\[unclear:\s*[^/\]]+?\/[^\]]+?\]|\[diagram:\s*.*?\])/gi;

export function TranscriptEditor({
  submissionId,
  cleanMarkdown,
  annotatedMarkdown,
  ocr,
  activeQuestionNo,
  activeQuestionTranscript,
  hasEvaluation = false,
  onSaved,
  onRegradeQuestion,
}: TranscriptEditorProps) {
  const [viewMode, setViewMode] = useState<"forensic" | "clean" | "edit">("forensic");
  const [draftMarkdown, setDraftMarkdown] = useState(cleanMarkdown);
  const [draftQuestionText, setDraftQuestionText] = useState(activeQuestionTranscript || "");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    setDraftMarkdown(cleanMarkdown);
  }, [cleanMarkdown]);

  useEffect(() => {
    setDraftQuestionText(activeQuestionTranscript || "");
  }, [activeQuestionTranscript, activeQuestionNo]);

  const diagramCropMap = useMemo(() => {
    const map: Record<string, string> = {};
    ocr?.pages.forEach((p) => {
      p.regions.forEach((r) => {
        if (r.crop_base64 && r.label === "diagram") {
          map[r.region_id] = `/api/submissions/${submissionId}/crops/${r.region_id}.png`;
        }
      });
    });
    return map;
  }, [ocr, submissionId]);

  const rawForensicSource = useMemo(() => {
    if (activeQuestionTranscript) return activeQuestionTranscript;
    if (ocr && ocr.pages.length > 0) {
      return ocr.pages.map((p) => p.full_markdown).join("\n\n---\n\n");
    }
    return annotatedMarkdown || cleanMarkdown;
  }, [activeQuestionTranscript, ocr, annotatedMarkdown, cleanMarkdown]);

  const handleResolveUnclear = (rawTag: string, chosen: string) => {
    const updated = draftMarkdown.includes(rawTag)
      ? draftMarkdown.replace(rawTag, chosen)
      : draftMarkdown;
    setDraftMarkdown(updated);
    if (activeQuestionTranscript && draftQuestionText.includes(rawTag)) {
      setDraftQuestionText((prev) => prev.replace(rawTag, chosen));
    }
    setViewMode("edit");
    setFeedback(`Resolved "${rawTag}" -> "${chosen}". Save to update PDF / re-grade.`);
  };

  const handleSaveMarkdown = async () => {
    setSaving(true);
    setFeedback(null);
    try {
      await api.updateMarkdown(submissionId, draftMarkdown, annotatedMarkdown);
      setFeedback("Saved Markdown and regenerated Pen-to-Print PDF.");
      onSaved?.();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "Failed to save Markdown");
    } finally {
      setSaving(false);
    }
  };

  const handleRegrade = async () => {
    if (!activeQuestionNo || !onRegradeQuestion) return;
    setSaving(true);
    setFeedback(null);
    try {
      await onRegradeQuestion(activeQuestionNo, draftQuestionText);
      setFeedback(`Re-graded ${activeQuestionNo} with updated transcript.`);
      onSaved?.();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "Re-grade failed");
    } finally {
      setSaving(false);
    }
  };

  const renderForensicTokens = (text: string) => {
    const parts = text.split(TOKEN_SPLIT_RE);
    return parts.map((part, idx) => {
      if (/^\[struck:/i.test(part)) {
        const inner = part.replace(/^\[struck:\s*/i, "").replace(/\]$/, "");
        return (
          <span
            key={idx}
            className="mx-0.5 inline-block rounded bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700 line-through"
            title="Crossed-out text (excluded from active grading)"
          >
            {inner}
          </span>
        );
      }
      if (/^\[unclear:/i.test(part)) {
        const inner = part.replace(/^\[unclear:\s*/i, "").replace(/\]$/, "");
        const alts = inner.split("/").map((s) => s.trim());
        return (
          <span
            key={idx}
            className="mx-0.5 inline-flex flex-wrap items-center gap-1 rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-xs font-semibold text-amber-900"
          >
            <span>?</span>
            {alts.map((alt, ai) => (
              <button
                key={ai}
                type="button"
                onClick={() => handleResolveUnclear(part, alt)}
                className="min-h-[28px] rounded bg-white px-2 py-0.5 text-[11px] hover:bg-amber-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
                title={`Click to pick "${alt}"`}
              >
                {alt}
              </button>
            ))}
          </span>
        );
      }
      if (/^\[diagram:/i.test(part)) {
        const desc = part.replace(/^\[diagram:\s*/i, "").replace(/\]$/, "");
        return (
          <span
            key={idx}
            className="my-2 block rounded-lg border border-red-200 bg-red-50/50 p-2.5 text-xs text-red-900"
          >
            <strong>Diagram Detected:</strong> {desc}
          </span>
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Header & Exports */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setViewMode("forensic")}
            className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 sm:min-h-[36px] ${
              viewMode === "forensic"
                ? "bg-[#1E293B] text-white"
                : "text-[#475569] hover:bg-slate-200"
            }`}
          >
            <Eye className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Forensic</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode("clean")}
            className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 sm:min-h-[36px] ${
              viewMode === "clean"
                ? "bg-[#1E293B] text-white"
                : "text-[#475569] hover:bg-slate-200"
            }`}
          >
            <span>Clean .MD</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode("edit")}
            className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 sm:min-h-[36px] ${
              viewMode === "edit"
                ? "bg-[#1E293B] text-white"
                : "text-[#475569] hover:bg-slate-200"
            }`}
          >
            <Edit3 className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Edit</span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <a
            href={api.exportMdUrl(submissionId, "clean")}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-semibold text-[#1E293B] hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 sm:min-h-[36px]"
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            <span>.MD</span>
          </a>
          <a
            href={api.exportPdfUrl(submissionId)}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-lg bg-[#2563EB] px-3 text-xs font-semibold text-white hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 sm:min-h-[36px]"
          >
            <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
            <span>.PDF</span>
          </a>
        </div>
      </div>

      {feedback && (
        <div className="border-b border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
          {feedback}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-auto p-3.5 sm:p-4">
        {viewMode === "forensic" && (
          <div className="space-y-4">
            {activeQuestionNo && (
              <div className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-[#334155]">
                Showing Transcript for {activeQuestionNo}
              </div>
            )}
            <div className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-[#0F172A]">
              {rawForensicSource ? (
                renderForensicTokens(rawForensicSource)
              ) : (
                <span className="text-[#475569]">OCR transcript pending...</span>
              )}
            </div>

            {Object.keys(diagramCropMap).length > 0 && (
              <div className="space-y-2 border-t border-slate-200 pt-3">
                <div className="text-xs font-bold uppercase tracking-wider text-[#475569]">
                  Extracted Diagram Crops
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {Object.entries(diagramCropMap).map(([rid, url]) => (
                    <div key={rid} className="rounded-lg border border-slate-200 p-2.5">
                      <div className="mb-1 font-mono text-[11px] text-[#475569]">{rid}</div>
                      <img
                        src={apiUrl(url)}
                        alt={`Diagram crop ${rid}`}
                        className="max-h-48 w-auto rounded border border-slate-100"
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {viewMode === "clean" && (
          <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-[#0F172A]">
            {cleanMarkdown || "No clean Markdown generated yet."}
          </pre>
        )}

        {viewMode === "edit" && (
          <div className="flex h-full flex-col gap-3">
            {hasEvaluation && activeQuestionNo ? (
              <>
                <label className="text-xs font-semibold text-[#334155]">
                  Editing Transcript for {activeQuestionNo}
                </label>
                <textarea
                  value={draftQuestionText}
                  onChange={(e) => setDraftQuestionText(e.target.value)}
                  className="min-h-[240px] flex-1 rounded-lg border border-slate-300 p-3 font-mono text-xs leading-relaxed text-[#0F172A] focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                />
                <button
                  type="button"
                  disabled={saving}
                  onClick={handleRegrade}
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[#2563EB] px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 disabled:opacity-50"
                >
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  <span>{saving ? "Re-Grading..." : `Save Edit & Re-Grade ${activeQuestionNo}`}</span>
                </button>
              </>
            ) : (
              <>
                <label className="text-xs font-semibold text-[#334155]">
                  Edit Full Pen-to-Print Markdown
                </label>
                <textarea
                  value={draftMarkdown}
                  onChange={(e) => setDraftMarkdown(e.target.value)}
                  className="min-h-[280px] flex-1 rounded-lg border border-slate-300 p-3 font-mono text-xs leading-relaxed text-[#0F172A] focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/20"
                />
                <button
                  type="button"
                  disabled={saving}
                  onClick={handleSaveMarkdown}
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[#2563EB] px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 disabled:opacity-50"
                >
                  <Save className="h-4 w-4" aria-hidden="true" />
                  <span>{saving ? "Saving..." : "Save Markdown & Regenerate PDF"}</span>
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
