import type {
  EvaluationReport,
  ExamListItem,
  ExamRubric,
  HealthStatus,
  SubmissionDetailResponse,
  SubmissionSummary,
} from "@/types/schemas";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...init,
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => fetchJson<HealthStatus>("/api/health"),

  listExams: () => fetchJson<ExamListItem[]>("/api/exams"),
  getExam: (examId: string) => fetchJson<ExamRubric>(`/api/exams/${examId}`),
  saveExam: (rubric: ExamRubric) =>
    fetchJson<ExamRubric>("/api/exams", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rubric),
    }),

  draftRubric: async (formData: FormData): Promise<ExamRubric> => {
    const res = await fetch(apiUrl("/api/exams/draft-rubric"), {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    return (await res.json()) as ExamRubric;
  },

  listSubmissions: (examId?: string) =>
    fetchJson<SubmissionSummary[]>(
      examId ? `/api/exams/${examId}/submissions` : "/api/submissions"
    ),

  uploadSubmissions: async (formData: FormData): Promise<SubmissionSummary[]> => {
    const res = await fetch(apiUrl("/api/submissions/upload"), {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    return (await res.json()) as SubmissionSummary[];
  },

  getSubmissionDetail: (submissionId: string) =>
    fetchJson<SubmissionDetailResponse>(`/api/submissions/${submissionId}`),

  updateMarkdown: (
    submissionId: string,
    cleanMarkdown: string,
    annotatedMarkdown?: string
  ) =>
    fetchJson<{ status: string; submission_id: string }>(
      `/api/submissions/${submissionId}/markdown`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clean_markdown: cleanMarkdown,
          annotated_markdown: annotatedMarkdown,
        }),
      }
    ),

  regradeQuestion: (
    submissionId: string,
    questionNo: string,
    editedTranscript: string,
    teacherNote = ""
  ) =>
    fetchJson<EvaluationReport>(
      `/api/submissions/${submissionId}/regrade/${encodeURIComponent(questionNo)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          edited_transcript: editedTranscript,
          teacher_note: teacherNote,
        }),
      }
    ),

  overrideQuestion: (
    submissionId: string,
    questionNo: string,
    newMarks: number,
    teacherNote: string
  ) =>
    fetchJson<EvaluationReport>(
      `/api/submissions/${submissionId}/override/${encodeURIComponent(questionNo)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          new_marks: newMarks,
          teacher_note: teacherNote,
        }),
      }
    ),

  exportMdUrl: (submissionId: string, variant: "clean" | "annotated" = "clean") =>
    apiUrl(`/api/submissions/${submissionId}/export-md?variant=${variant}`),

  exportPdfUrl: (submissionId: string) =>
    apiUrl(`/api/submissions/${submissionId}/export-pdf`),

  exportCsvUrl: (examId: string) =>
    apiUrl(`/api/exams/${examId}/export-csv`),
};
