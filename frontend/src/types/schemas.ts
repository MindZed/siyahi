/**
 * TypeScript interfaces strictly mirroring shared/schemas.py.
 */

export type QuestionType =
  | "short_answer"
  | "long_answer"
  | "numerical"
  | "diagram_heavy";

export interface RubricCriterion {
  criterion_id: string;
  description: string;
  max_points: number;
  expected_keywords: string[];
  accepted_alternatives: string[];
  partial_credit_rule: string;
  requires_diagram: boolean;
}

export interface QuestionRubric {
  question_no: string;
  question_text: string;
  max_marks: number;
  question_type: QuestionType;
  criteria: RubricCriterion[];
}

export interface ExamRubric {
  exam_id: string;
  subject: string;
  title: string;
  total_marks: number;
  is_locked: boolean;
  questions: QuestionRubric[];
}

export interface ExamListItem {
  exam_id: string;
  subject: string;
  title: string;
  total_marks: number;
  question_count: number;
  is_locked: boolean;
  submission_count: number;
  created_at: string;
}

export interface UnclearSpan {
  raw_tag: string;
  alternatives: string[];
}

export interface LayoutRegion {
  region_id: string;
  label: string;
  confidence: number;
  bbox: [number, number, number, number];
  raw_text: string;
  clean_active_text: string;
  unclear_spans: UnclearSpan[];
  struck_spans: string[];
  crop_base64?: string | null;
}

export interface PageOCR {
  page_number: number;
  width: number;
  height: number;
  full_markdown: string;
  regions: LayoutRegion[];
}

export interface OCRDocumentResponse {
  submission_id: string;
  engine_used: string;
  processing_time_sec: number;
  pages: PageOCR[];
}

export interface RegionRef {
  page_number: number;
  region_id: string;
  label: string;
  bbox: [number, number, number, number];
}

export interface CriterionEvaluation {
  criterion_id: string;
  max_points: number;
  awarded_points: number;
  student_quote?: string | null;
  quote_verified: boolean;
  reason: string;
}

export interface QuestionEvaluation {
  question_no: string;
  max_marks: number;
  ai_awarded_marks: number;
  final_marks: number;
  raw_transcript: string;
  clean_active_text: string;
  mark_spread_delta: number;
  needs_human_review: boolean;
  review_reasons: string[];
  criteria_breakdown: CriterionEvaluation[];
  diagram_crops: string[];
  teacher_overridden: boolean;
  override_note?: string | null;
}

export interface EvaluationReport {
  submission_id: string;
  exam_id: string;
  roll_number: string;
  subject: string;
  total_max_marks: number;
  total_ai_marks: number;
  total_final_marks: number;
  needs_review_count: number;
  questions: QuestionEvaluation[];
}

export interface AuditOverrideRecord {
  override_id: string;
  submission_id: string;
  question_no: string;
  previous_marks: number;
  new_marks: number;
  edited_transcript?: string | null;
  teacher_note: string;
  timestamp: string;
}

export interface SubmissionSummary {
  submission_id: string;
  exam_id?: string | null;
  roll_number: string;
  original_filename: string;
  status: string;
  engine_used: string;
  page_count?: number;
  ocr_time_sec?: number | null;
  wall_time_sec?: number | null;
  estimated_cost_usd?: number | null;
  total_ai_marks?: number | null;
  total_final_marks?: number | null;
  needs_review_count: number;
  created_at: string;
  updated_at: string;
}

export interface SubmissionDetailResponse {
  submission: SubmissionSummary;
  page_image_urls: string[];
  ocr?: OCRDocumentResponse | null;
  evaluation?: EvaluationReport | null;
  question_region_map: Record<string, RegionRef[]>;
  clean_markdown: string;
  annotated_markdown: string;
  overrides: AuditOverrideRecord[];
}

export interface ModalUsageSummary {
  total_submissions: number;
  total_pages: number;
  total_ocr_time_sec: number;
  avg_ocr_time_sec: number;
  siyahi_gpu_cost_usd: number;
  modal_baseline_spent_usd: number;
  modal_total_bill_usd: number;
  modal_credit_limit_usd: number;
  modal_bill_percent: number;
  gpu_name: string;
  gpu_rate_per_hr: number;
}

export interface HealthStatus {
  status: string;
  mock_modal: boolean;
  grader_provider: string;
  grader_model: string;
  mock_gemini: boolean;
  usage?: ModalUsageSummary;
}
