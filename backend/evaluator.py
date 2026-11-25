"""Deterministic rubric evaluator, verbatim quote verifier, and Delta_y sensitivity router."""

from __future__ import annotations

import itertools
import re
from typing import Optional

from rapidfuzz import fuzz

from backend.config import Settings
from backend.database import Database
from backend.grader_provider import GraderProvider, get_grader_provider
from backend.question_segmenter import SegmentedQuestion, segment_ocr_document
from shared.schemas import (
    CriterionEvaluation,
    EvaluationReport,
    ExamRubric,
    OCRDocumentResponse,
    QuestionEvaluation,
    QuestionRubric,
)

STRUCK_PATTERN = re.compile(r"\[struck:\s*(.*?)\]", re.IGNORECASE | re.DOTALL)
UNCLEAR_PATTERN = re.compile(r"\[unclear:\s*([^/\]]+?)/([^\]]+?)\]", re.IGNORECASE)


def strip_struck_spans(raw_text: str) -> str:
    """Remove [struck: ...] tags AND their enclosed crossed-out student text."""
    cleaned = STRUCK_PATTERN.sub("", raw_text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def normalize_for_quote_check(text: str) -> str:
    """Normalize whitespace and punctuation while preserving math symbols and digits."""
    lowered = text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def verify_student_quote(
    student_quote: Optional[str],
    clean_active_text: str,
    threshold: float = 85.0,
) -> bool:
    """Verify student_quote exists in clean_active_text with >=85% fuzzy overlap."""
    if not student_quote or not student_quote.strip():
        return False
    norm_quote = normalize_for_quote_check(student_quote)
    norm_source = normalize_for_quote_check(clean_active_text)
    if not norm_quote or not norm_source:
        return False
    if norm_quote in norm_source:
        return True
    score = fuzz.partial_ratio(norm_quote, norm_source)
    return float(score) >= threshold


def build_unclear_candidate_variants(raw_text: str, max_variants: int = 3) -> list[str]:
    """Expand [unclear: a/b] tags into up to `max_variants` unique clean active strings."""
    active_template = strip_struck_spans(raw_text)
    matches = list(UNCLEAR_PATTERN.finditer(active_template))
    if not matches:
        return [active_template]

    # Limit combinatorial explosion by expanding the first 3 unclear tags
    capped = matches[:3]
    options_per_match = [
        [m.group(1).strip(), m.group(2).strip()] for m in capped
    ]

    variants: list[str] = []
    for combo in itertools.product(*options_per_match):
        out = active_template
        for m, chosen in zip(capped, combo):
            out = out.replace(m.group(0), chosen, 1)
        # Resolve any remaining unclear tags beyond the first 3 to primary choice
        out = UNCLEAR_PATTERN.sub(lambda m: m.group(1).strip(), out)
        out = re.sub(r"[ \t]{2,}", " ", out).strip()
        if out not in variants:
            variants.append(out)
        if len(variants) >= max_variants:
            break
    return variants


def _finalize_criteria(
    raw_criteria: list[CriterionEvaluation],
    question_rubric: QuestionRubric,
    clean_active_text: str,
) -> tuple[list[CriterionEvaluation], float, list[str]]:
    """Clamp scores, verify student quotes in Python, and sum total deterministically."""
    by_id = {c.criterion_id: c for c in raw_criteria}
    final_criteria: list[CriterionEvaluation] = []
    warnings: list[str] = []

    for rub_c in question_rubric.criteria:
        c = by_id.get(rub_c.criterion_id)
        if c is None:
            final_criteria.append(
                CriterionEvaluation(
                    criterion_id=rub_c.criterion_id,
                    max_points=rub_c.max_points,
                    awarded_points=0.0,
                    student_quote=None,
                    quote_verified=False,
                    reason="Criterion omitted by grader; defaulted to 0.",
                )
            )
            continue

        awarded = round(min(max(0.0, float(c.awarded_points)), rub_c.max_points), 2)
        verified = verify_student_quote(c.student_quote, clean_active_text)
        if awarded > 0.0 and not verified:
            warnings.append(f"Unverified student quote on {rub_c.criterion_id}")

        final_criteria.append(
            CriterionEvaluation(
                criterion_id=rub_c.criterion_id,
                max_points=rub_c.max_points,
                awarded_points=awarded,
                student_quote=c.student_quote,
                quote_verified=verified,
                reason=c.reason,
            )
        )

    total = round(min(question_rubric.max_marks, sum(c.awarded_points for c in final_criteria)), 2)
    return final_criteria, total, warnings


async def evaluate_question(
    question_rubric: QuestionRubric,
    raw_transcript: str,
    diagram_crops: list[str],
    provider: GraderProvider,
) -> QuestionEvaluation:
    """Evaluate a single question with deterministic summation and Delta_y routing."""
    variants = build_unclear_candidate_variants(raw_transcript, max_variants=3)
    primary_clean = variants[0] if variants else strip_struck_spans(raw_transcript)

    if not primary_clean.strip():
        empty_criteria = [
            CriterionEvaluation(
                criterion_id=c.criterion_id,
                max_points=c.max_points,
                awarded_points=0.0,
                student_quote=None,
                quote_verified=False,
                reason="No active student response detected.",
            )
            for c in question_rubric.criteria
        ]
        needs_review = bool(diagram_crops)
        reasons = ["Diagram/Table crop detected — visual check required"] if diagram_crops else []
        return QuestionEvaluation(
            question_no=question_rubric.question_no,
            max_marks=question_rubric.max_marks,
            ai_awarded_marks=0.0,
            final_marks=0.0,
            raw_transcript=raw_transcript,
            clean_active_text="",
            mark_spread_delta=0.0,
            needs_human_review=needs_review,
            review_reasons=reasons,
            criteria_breakdown=empty_criteria,
            diagram_crops=diagram_crops,
        )

    raw_crit = await provider.grade_question(question_rubric, primary_clean)
    criteria_breakdown, primary_score, quote_warnings = _finalize_criteria(
        raw_crit, question_rubric, primary_clean
    )

    # Sensitivity Check across unclear alternatives (Delta_y)
    variant_scores = [primary_score]
    for alt_clean in variants[1:]:
        alt_raw = await provider.grade_question(question_rubric, alt_clean)
        _, alt_score, _ = _finalize_criteria(alt_raw, question_rubric, alt_clean)
        variant_scores.append(alt_score)

    mark_spread_delta = round(max(variant_scores) - min(variant_scores), 2)
    sensitivity_threshold = max(0.5, round(0.10 * question_rubric.max_marks, 2))

    review_reasons: list[str] = list(quote_warnings)
    if mark_spread_delta >= sensitivity_threshold:
        review_reasons.append(
            f"Mark Spread Δŷ = {mark_spread_delta} >= {sensitivity_threshold} on ambiguous text"
        )

    has_diagram = bool(diagram_crops) or "[diagram:" in raw_transcript.lower() or any(
        c.requires_diagram for c in question_rubric.criteria
    )
    if has_diagram and (diagram_crops or "[diagram:" in raw_transcript.lower()):
        review_reasons.append("Diagram/Table crop detected — verify visually")

    if (
        question_rubric.question_type == "short_answer"
        and question_rubric.max_marks <= 2.0
        and 0.0 < primary_score < question_rubric.max_marks
    ):
        review_reasons.append("Short-answer partial credit awarded — quick check recommended")

    return QuestionEvaluation(
        question_no=question_rubric.question_no,
        max_marks=question_rubric.max_marks,
        ai_awarded_marks=primary_score,
        final_marks=primary_score,
        raw_transcript=raw_transcript,
        clean_active_text=primary_clean,
        mark_spread_delta=mark_spread_delta,
        needs_human_review=len(review_reasons) > 0,
        review_reasons=review_reasons,
        criteria_breakdown=criteria_breakdown,
        diagram_crops=diagram_crops,
    )


async def evaluate_submission(
    submission_id: str,
    roll_number: str,
    rubric: ExamRubric,
    ocr: OCRDocumentResponse,
    settings: Settings,
    db: Optional[Database] = None,
    provider: Optional[GraderProvider] = None,
) -> EvaluationReport:
    """Segment an OCR document against a locked rubric and grade sequentially."""
    active_provider = provider or get_grader_provider(settings, db=db)
    expected_nos = [q.question_no for q in rubric.questions]
    segments, _ = segment_ocr_document(ocr, expected_questions=expected_nos)

    question_evals: list[QuestionEvaluation] = []
    for q_rubric in rubric.questions:
        seg: Optional[SegmentedQuestion] = segments.get(q_rubric.question_no)
        raw_transcript = seg.raw_transcript if seg else ""
        diagram_crops = seg.diagram_crops if seg else []
        q_eval = await evaluate_question(
            question_rubric=q_rubric,
            raw_transcript=raw_transcript,
            diagram_crops=diagram_crops,
            provider=active_provider,
        )
        question_evals.append(q_eval)

    return EvaluationReport(
        submission_id=submission_id,
        exam_id=rubric.exam_id,
        roll_number=roll_number,
        subject=rubric.subject,
        total_max_marks=round(sum(q.max_marks for q in rubric.questions), 2),
        total_ai_marks=round(sum(q.ai_awarded_marks for q in question_evals), 2),
        total_final_marks=round(sum(q.final_marks for q in question_evals), 2),
        needs_review_count=sum(1 for q in question_evals if q.needs_human_review),
        questions=question_evals,
    )


async def regrade_single_question(
    report: EvaluationReport,
    rubric: ExamRubric,
    question_no: str,
    edited_transcript: str,
    teacher_note: str,
    settings: Settings,
    db: Optional[Database] = None,
    provider: Optional[GraderProvider] = None,
) -> EvaluationReport:
    """Save a manual transcript edit and re-run deterministic grading for one question."""
    q_rubric = next((q for q in rubric.questions if q.question_no == question_no), None)
    if not q_rubric:
        raise ValueError(f"Question '{question_no}' not found in rubric '{rubric.exam_id}'.")

    existing_q = next((q for q in report.questions if q.question_no == question_no), None)
    prev_marks = existing_q.final_marks if existing_q else 0.0
    crops = existing_q.diagram_crops if existing_q else []

    active_provider = provider or get_grader_provider(settings, db=db)
    regraded = await evaluate_question(
        question_rubric=q_rubric,
        raw_transcript=edited_transcript,
        diagram_crops=crops,
        provider=active_provider,
    )
    regraded.override_note = teacher_note or "Re-graded after manual transcript edit"

    updated_questions = [
        regraded if q.question_no == question_no else q for q in report.questions
    ]
    if existing_q is None:
        updated_questions.append(regraded)

    if db:
        db.add_audit_override(
            submission_id=report.submission_id,
            question_no=question_no,
            previous_marks=prev_marks,
            new_marks=regraded.final_marks,
            edited_transcript=edited_transcript,
            teacher_note=regraded.override_note or "",
        )

    return EvaluationReport(
        submission_id=report.submission_id,
        exam_id=report.exam_id,
        roll_number=report.roll_number,
        subject=report.subject,
        total_max_marks=report.total_max_marks,
        total_ai_marks=round(sum(q.ai_awarded_marks for q in updated_questions), 2),
        total_final_marks=round(sum(q.final_marks for q in updated_questions), 2),
        needs_review_count=sum(1 for q in updated_questions if q.needs_human_review),
        questions=updated_questions,
    )
