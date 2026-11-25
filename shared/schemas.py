"""Shared Pydantic v2 data contracts across modal_worker, backend, and research."""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Exam & Rubric Contracts
# ---------------------------------------------------------------------------

class RubricCriterion(BaseModel):
    """Atomic grading criterion within a question rubric."""

    criterion_id: str
    description: str
    max_points: float = Field(ge=0.0)
    expected_keywords: list[str] = Field(default_factory=list)
    accepted_alternatives: list[str] = Field(default_factory=list)
    partial_credit_rule: str = ""
    requires_diagram: bool = False


class QuestionRubric(BaseModel):
    """Rubric definition for a single exam question."""

    question_no: str
    question_text: str
    max_marks: float = Field(ge=0.0)
    question_type: Literal["short_answer", "long_answer", "numerical", "diagram_heavy"]
    criteria: list[RubricCriterion] = Field(default_factory=list)


class ExamRubric(BaseModel):
    """Complete subject exam rubric locked by the professor prior to grading."""

    exam_id: str
    subject: str
    title: str
    total_marks: float = Field(ge=0.0)
    is_locked: bool = False
    questions: list[QuestionRubric] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# OCR & Separation-Rule Contracts (Modal <-> Backend)
# ---------------------------------------------------------------------------

class UnclearSpan(BaseModel):
    """Ambiguous handwritten span tagged with plausible alternative readings."""

    raw_tag: str
    alternatives: list[str] = Field(default_factory=list)


class LayoutRegion(BaseModel):
    """Detected document layout region and its verbatim OCR transcription."""

    region_id: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[int]
    raw_text: str = ""
    clean_active_text: str = ""
    unclear_spans: list[UnclearSpan] = Field(default_factory=list)
    struck_spans: list[str] = Field(default_factory=list)
    crop_base64: Optional[str] = None

    @field_validator("bbox")
    @classmethod
    def validate_bbox_length(cls, value: list[int]) -> list[int]:
        if len(value) != 4:
            raise ValueError("bbox must contain exactly 4 integers: [x1, y1, x2, y2]")
        return value


class PageOCR(BaseModel):
    """Structured OCR output for a single anonymized script page."""

    page_number: int = Field(ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    full_markdown: str = ""
    regions: list[LayoutRegion] = Field(default_factory=list)


class OCRDocumentResponse(BaseModel):
    """Full structured OCR response returned by the Modal worker."""

    submission_id: str
    engine_used: str
    processing_time_sec: float = Field(ge=0.0)
    pages: list[PageOCR] = Field(default_factory=list)


class OCRPageImage(BaseModel):
    """Anonymized page image payload sent to the OCR worker."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    image_base64: str


class OCRRequest(BaseModel):
    """Strict Rule-1 request contract: never accepts question papers or rubrics."""

    model_config = ConfigDict(extra="forbid")

    submission_id: str
    pages: list[OCRPageImage] = Field(min_length=1)
    mode: Literal["hybrid", "strict_regions", "whole_page"] = "hybrid"
    enable_sensitivity_sampling: bool = False
    k_samples: int = Field(default=3, ge=1, le=5)


# ---------------------------------------------------------------------------
# Preprocessing & Segmentation Contracts
# ---------------------------------------------------------------------------

class PreprocessedPage(BaseModel):
    """Single anonymized 300 DPI page produced locally by pdf_processor."""

    page_number: int = Field(ge=1)
    image_path: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    was_split_from_spread: bool = False


class PreprocessResult(BaseModel):
    """Result of local PDF/image ingestion and PII anonymization."""

    submission_id: str
    roll_number: str
    subject: str
    original_filename: str
    raw_page_count: int = Field(ge=1)
    cover_page_skipped: bool = False
    pages: list[PreprocessedPage] = Field(default_factory=list)


class RegionRef(BaseModel):
    """Links a segmented question back to its exact page and bounding box."""

    page_number: int = Field(ge=1)
    region_id: str
    label: str
    bbox: list[int]


# ---------------------------------------------------------------------------
# Evaluation & Audit Contracts (Evaluator -> Dashboard)
# ---------------------------------------------------------------------------

class CriterionEvaluation(BaseModel):
    """Criterion-level evaluation grounded in a verbatim student quote."""

    criterion_id: str
    max_points: float = Field(ge=0.0)
    awarded_points: float = Field(ge=0.0)
    student_quote: Optional[str] = None
    quote_verified: bool = False
    reason: str = ""


class QuestionEvaluation(BaseModel):
    """Auditable evaluation for one segmented student answer."""

    question_no: str
    max_marks: float = Field(ge=0.0)
    ai_awarded_marks: float = Field(ge=0.0)
    final_marks: float = Field(ge=0.0)
    raw_transcript: str
    clean_active_text: str
    mark_spread_delta: float = Field(default=0.0, ge=0.0)
    needs_human_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    criteria_breakdown: list[CriterionEvaluation] = Field(default_factory=list)
    diagram_crops: list[str] = Field(default_factory=list)
    teacher_overridden: bool = False
    override_note: Optional[str] = None


class EvaluationReport(BaseModel):
    """Complete grading report for one student submission."""

    submission_id: str
    exam_id: str
    roll_number: str
    subject: str
    total_max_marks: float = Field(ge=0.0)
    total_ai_marks: float = Field(ge=0.0)
    total_final_marks: float = Field(ge=0.0)
    needs_review_count: int = Field(default=0, ge=0)
    questions: list[QuestionEvaluation] = Field(default_factory=list)


class AuditOverrideRecord(BaseModel):
    """Immutable audit log entry for a teacher mark override or transcript edit."""

    override_id: str
    submission_id: str
    question_no: str
    previous_marks: float
    new_marks: float
    edited_transcript: Optional[str] = None
    teacher_note: str = ""
    timestamp: str


class OverrideRequest(BaseModel):
    """Request payload for applying a one-click mark override."""

    new_marks: float = Field(ge=0.0)
    teacher_note: str = ""


class RegradeRequest(BaseModel):
    """Request payload for saving a manual transcript edit and re-evaluating."""

    edited_transcript: str
    teacher_note: str = ""


class SubmissionSummary(BaseModel):
    """Compact row displayed in upload queue and exam dashboards."""

    submission_id: str
    exam_id: Optional[str] = None
    roll_number: str
    original_filename: str
    status: str
    engine_used: str
    total_ai_marks: Optional[float] = None
    total_final_marks: Optional[float] = None
    needs_review_count: int = 0
    created_at: str
    updated_at: str


class SubmissionDetailResponse(BaseModel):
    """Full submission payload combining OCR, Pen-to-Print exports, and evaluation."""

    submission: SubmissionSummary
    page_image_urls: list[str] = Field(default_factory=list)
    ocr: Optional[OCRDocumentResponse] = None
    evaluation: Optional[EvaluationReport] = None
    question_region_map: dict[str, list[RegionRef]] = Field(default_factory=dict)
    clean_markdown: str = ""
    annotated_markdown: str = ""
    overrides: list[AuditOverrideRecord] = Field(default_factory=list)
