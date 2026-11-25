"""Phase 1 tests: shared schemas, Separation Rule, SQLite CRUD, and PII preprocessing."""

from pathlib import Path
import pymupdf
import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from backend.database import Database
from backend.pdf_processor import parse_submission_filename, preprocess_submission
from shared.schemas import (
    CriterionEvaluation,
    EvaluationReport,
    ExamRubric,
    LayoutRegion,
    OCRDocumentResponse,
    OCRPageImage,
    OCRRequest,
    PageOCR,
    QuestionEvaluation,
    QuestionRubric,
    RubricCriterion,
    UnclearSpan,
)


def test_exam_rubric_and_evaluation_roundtrip() -> None:
    rubric = ExamRubric(
        exam_id="EXAM_DS_101",
        subject="datascience",
        title="Midterm Data Science",
        total_marks=10.0,
        is_locked=True,
        questions=[
            QuestionRubric(
                question_no="Q1",
                question_text="Define overfitting and bias-variance tradeoff.",
                max_marks=5.0,
                question_type="short_answer",
                criteria=[
                    RubricCriterion(
                        criterion_id="Q1_C1",
                        description="Mentions high variance / memorizing training noise",
                        max_points=2.5,
                        expected_keywords=["variance", "training noise"],
                        accepted_alternatives=["fits noise instead of signal"],
                        partial_credit_rule="1 mark for defining only one side",
                    )
                ],
            )
        ],
    )
    loaded = ExamRubric.model_validate_json(rubric.model_dump_json())
    assert loaded.exam_id == "EXAM_DS_101"
    assert loaded.is_locked is True
    assert loaded.questions[0].criteria[0].criterion_id == "Q1_C1"

    report = EvaluationReport(
        submission_id="SUB_12345678",
        exam_id="EXAM_DS_101",
        roll_number="CSE234002",
        subject="datascience",
        total_max_marks=5.0,
        total_ai_marks=2.5,
        total_final_marks=2.5,
        needs_review_count=1,
        questions=[
            QuestionEvaluation(
                question_no="Q1",
                max_marks=5.0,
                ai_awarded_marks=2.5,
                final_marks=2.5,
                raw_transcript="Overfitting happens when [struck: bias] variance is high.",
                clean_active_text="Overfitting happens when variance is high.",
                mark_spread_delta=0.0,
                needs_human_review=True,
                review_reasons=["Diagram detected"],
                criteria_breakdown=[
                    CriterionEvaluation(
                        criterion_id="Q1_C1",
                        max_points=2.5,
                        awarded_points=2.5,
                        student_quote="Overfitting happens when variance is high",
                        quote_verified=True,
                        reason="Matched variance concept.",
                    )
                ],
            )
        ],
    )
    assert EvaluationReport.model_validate_json(report.model_dump_json()).total_final_marks == 2.5


def test_separation_rule_blocks_rubric_fields_in_ocr_request() -> None:
    page = OCRPageImage(page_number=1, width=800, height=1000, image_base64="ZmFrZQ==")
    valid = OCRRequest(submission_id="SUB_abcd", pages=[page])
    assert valid.mode == "hybrid"

    with pytest.raises(ValidationError):
        OCRRequest(
            submission_id="SUB_abcd",
            pages=[page],
            rubric={"exam_id": "X"},  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        LayoutRegion(
            region_id="r1",
            label="text",
            confidence=0.9,
            bbox=[1, 2, 3],  # Invalid length
        )


def test_ocr_document_response_contract() -> None:
    doc = OCRDocumentResponse(
        submission_id="SUB_01",
        engine_used="PP-DocLayoutV3+Qwen3.5-9B",
        processing_time_sec=1.42,
        pages=[
            PageOCR(
                page_number=1,
                width=1200,
                height=1600,
                full_markdown="# Q1\nAnswer text",
                regions=[
                    LayoutRegion(
                        region_id="p1_r1",
                        label="text",
                        confidence=0.92,
                        bbox=[10, 20, 500, 300],
                        raw_text="[unclear: increase/decrease] rate",
                        clean_active_text="increase rate",
                        unclear_spans=[
                            UnclearSpan(
                                raw_tag="[unclear: increase/decrease]",
                                alternatives=["increase", "decrease"],
                            )
                        ],
                        struck_spans=[],
                    )
                ],
            )
        ],
    )
    assert doc.pages[0].regions[0].unclear_spans[0].alternatives == ["increase", "decrease"]


def test_database_crud_and_override_audit(tmp_path: Path) -> None:
    db = Database(tmp_path / "test_exam.db")
    rubric = ExamRubric(
        exam_id="EXAM_01",
        subject="ml",
        title="ML Quiz",
        total_marks=10.0,
        is_locked=True,
        questions=[],
    )
    db.save_exam(rubric)
    fetched_exam = db.get_exam("EXAM_01")
    assert fetched_exam is not None
    assert fetched_exam.is_locked is True

    sub = db.create_submission(
        submission_id="SUB_999",
        roll_number="CSE234002",
        original_filename="CSE234002_ml.pdf",
        exam_id="EXAM_01",
    )
    assert sub.status == "preprocessing"
    assert db.list_exams()[0]["submission_count"] == 1

    # Also ensure standalone Pen-to-Print submission works without exam_id
    standalone = db.create_submission(
        submission_id="SUB_STANDALONE",
        roll_number="CSE234003",
        original_filename="CSE234003_notes.pdf",
        exam_id=None,
    )
    assert standalone.exam_id is None

    ovr = db.add_audit_override(
        submission_id="SUB_999",
        question_no="Q1",
        previous_marks=2.0,
        new_marks=3.5,
        edited_transcript="Corrected formula",
        teacher_note="Formula reading verified visually",
    )
    overrides = db.list_audit_overrides("SUB_999")
    assert len(overrides) == 1
    assert overrides[0].override_id == ovr.override_id
    assert overrides[0].new_marks == 3.5

    db.set_cached_grader_response("hash_abc", "gemini-3-flash-preview", '{"ok": true}')
    assert db.get_cached_grader_response("hash_abc") == '{"ok": true}'


def _make_sample_pdf(pdf_path: Path) -> None:
    """Create a 3-page PDF: Page 1 = student cover PII, Page 2 = portrait answer, Page 3 = 2-page spread."""
    doc = pymupdf.open()

    # Page 1: Cover sheet (must be stripped locally)
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 120), "STUDENT COVER SHEET\nName: Alice\nRoll: CSE234002", fontsize=18)

    # Page 2: Single answer page image
    img2 = Image.new("RGB", (600, 800), "white")
    d2 = ImageDraw.Draw(img2)
    d2.text((40, 60), "Q1. Bias-variance tradeoff answer", fill="black")
    img2_path = pdf_path.parent / "_tmp_p2.png"
    img2.save(img2_path)
    p2 = doc.new_page(width=600, height=800)
    p2.insert_image(pymupdf.Rect(0, 0, 600, 800), filename=str(img2_path))

    # Page 3: Wide landscape 2-page spread with a dark center spine
    img3 = Image.new("RGB", (1400, 800), "white")
    d3 = ImageDraw.Draw(img3)
    d3.rectangle([695, 0, 705, 800], fill=(10, 10, 10))
    d3.text((60, 80), "Q2(a). Left spread page", fill="black")
    d3.text((780, 80), "Q2(b). Right spread page", fill="black")
    img3_path = pdf_path.parent / "_tmp_p3.png"
    img3.save(img3_path)
    p3 = doc.new_page(width=1400, height=800)
    p3.insert_image(pymupdf.Rect(0, 0, 1400, 800), filename=str(img3_path))

    doc.save(str(pdf_path))
    doc.close()


def test_filename_parser_and_cover_stripping_preprocessor(tmp_path: Path) -> None:
    roll, subj = parse_submission_filename("CSE234002_datascience.pdf")
    assert roll == "CSE234002"
    assert subj == "datascience"

    pdf_path = tmp_path / "CSE234002_datascience.pdf"
    _make_sample_pdf(pdf_path)

    result = preprocess_submission(
        input_path=pdf_path,
        storage_dir=tmp_path / "storage",
        dpi=150,
        skip_cover_page=True,
        auto_split_spreads=True,
    )
    assert result.roll_number == "CSE234002"
    assert result.subject == "datascience"
    assert result.raw_page_count == 3
    assert result.cover_page_skipped is True
    # Page 1 stripped; Page 2 -> 1 page; Page 3 spread -> 2 pages => 3 output pages total
    assert len(result.pages) == 3
    assert result.pages[0].was_split_from_spread is False
    assert result.pages[1].was_split_from_spread is True
    assert result.pages[2].was_split_from_spread is True
    for p in result.pages:
        assert Path(p.image_path).exists()
