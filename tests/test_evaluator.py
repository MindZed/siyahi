"""Phase 4 tests: deterministic scoring, struck stripping, quote checking, Delta_y & overrides."""

import io
from pathlib import Path
import pymupdf
import pytest
from PIL import Image
from fastapi.testclient import TestClient

import backend.main as main_mod
from backend.config import Settings
from backend.database import Database
from backend.evaluator import (
    build_unclear_candidate_variants,
    evaluate_question,
    evaluate_submission,
    strip_struck_spans,
    verify_student_quote,
)
from backend.exporter import build_exam_gradebook_csv, build_printable_student_report_md
from backend.grader_provider import GraderProvider
from shared.schemas import (
    CriterionEvaluation,
    ExamRubric,
    LayoutRegion,
    OCRDocumentResponse,
    PageOCR,
    QuestionRubric,
    RubricCriterion,
    UnclearSpan,
)


class ScriptedGraderProvider(GraderProvider):
    """Deterministic fake provider simulating LLM outputs for edge-case verification."""

    async def draft_rubric(self, exam_id, subject, title, question_paper_text, model_answer_text):
        raise NotImplementedError

    async def grade_question(
        self, question_rubric: QuestionRubric, clean_active_text: str
    ) -> list[CriterionEvaluation]:
        lower = clean_active_text.lower()
        out: list[CriterionEvaluation] = []
        for c in question_rubric.criteria:
            if "11.53" in c.expected_keywords:
                if "11.53" in lower:
                    out.append(
                        CriterionEvaluation(
                            criterion_id=c.criterion_id,
                            max_points=c.max_points,
                            awarded_points=c.max_points,
                            student_quote="mean is 11.53",
                            quote_verified=False,
                            reason="Correct final answer.",
                        )
                    )
                else:
                    out.append(
                        CriterionEvaluation(
                            criterion_id=c.criterion_id,
                            max_points=c.max_points,
                            awarded_points=0.0,
                            student_quote=None,
                            quote_verified=False,
                            reason="Wrong numerical answer.",
                        )
                    )
            elif "increase" in c.expected_keywords:
                if "increase" in lower:
                    out.append(
                        CriterionEvaluation(
                            criterion_id=c.criterion_id,
                            max_points=c.max_points,
                            awarded_points=c.max_points,
                            student_quote="rate will increase",
                            quote_verified=False,
                            reason="Matches expected direction.",
                        )
                    )
                else:
                    out.append(
                        CriterionEvaluation(
                            criterion_id=c.criterion_id,
                            max_points=c.max_points,
                            awarded_points=0.0,
                            student_quote=None,
                            quote_verified=False,
                            reason="Opposite direction.",
                        )
                    )
            else:
                out.append(
                    CriterionEvaluation(
                        criterion_id=c.criterion_id,
                        max_points=c.max_points,
                        awarded_points=1.0,
                        student_quote="completely fabricated quote not in text",
                        quote_verified=False,
                        reason="Simulated hallucinated quote.",
                    )
                )
        return out


def test_struck_stripping_and_fuzzy_quote_verifier() -> None:
    raw = "The variance [struck: bias is always zero] causes overfitting."
    clean = strip_struck_spans(raw)
    assert "bias is always zero" not in clean
    assert clean == "The variance causes overfitting."

    assert verify_student_quote("variance causes overfitting", clean) is True
    assert verify_student_quote("completely unrelated phrase", clean) is False


@pytest.mark.asyncio
async def test_delta_y_sensitivity_and_deferral_triggers() -> None:
    provider = ScriptedGraderProvider()

    # Case 1: Ambiguous [unclear: increase/decrease] flips score from 2.0 -> 0.0 => Delta_y = 2.0
    q_rubric = QuestionRubric(
        question_no="Q1",
        question_text="What happens to variance as complexity grows?",
        max_marks=2.0,
        question_type="short_answer",
        criteria=[
            RubricCriterion(
                criterion_id="Q1_C1",
                description="States variance increases",
                max_points=2.0,
                expected_keywords=["increase"],
            )
        ],
    )
    variants = build_unclear_candidate_variants("The rate will [unclear: increase/decrease].")
    assert variants == ["The rate will increase.", "The rate will decrease."]

    q_eval = await evaluate_question(
        question_rubric=q_rubric,
        raw_transcript="The rate will [unclear: increase/decrease].",
        diagram_crops=[],
        provider=provider,
    )
    assert q_eval.ai_awarded_marks == 2.0
    assert q_eval.mark_spread_delta == 2.0
    assert q_eval.needs_human_review is True
    assert any("Mark Spread" in r for r in q_eval.review_reasons)
    assert q_eval.criteria_breakdown[0].quote_verified is True

    # Case 2: Crossed-out keyword MUST NOT receive points
    q_num = QuestionRubric(
        question_no="Q2",
        question_text="Find the mean.",
        max_marks=5.0,
        question_type="numerical",
        criteria=[
            RubricCriterion(
                criterion_id="Q2_C1",
                description="Final value 11.53",
                max_points=5.0,
                expected_keywords=["11.53"],
            )
        ],
    )
    q_eval_struck = await evaluate_question(
        question_rubric=q_num,
        raw_transcript="[struck: mean is 11.53] mean is 99.0",
        diagram_crops=[],
        provider=provider,
    )
    assert q_eval_struck.ai_awarded_marks == 0.0

    # Case 3: Unverified hallucinated quote flags needs_human_review
    q_hallucinated = QuestionRubric(
        question_no="Q3",
        question_text="Explain trees.",
        max_marks=4.0,
        question_type="long_answer",
        criteria=[
            RubricCriterion(
                criterion_id="Q3_C1",
                description="Mentions entropy",
                max_points=4.0,
                expected_keywords=["entropy"],
            )
        ],
    )
    q_eval_hall = await evaluate_question(
        question_rubric=q_hallucinated,
        raw_transcript="Decision trees split recursively.",
        diagram_crops=["ZmFrZQ=="],
        provider=provider,
    )
    assert q_eval_hall.needs_human_review is True
    assert q_eval_hall.criteria_breakdown[0].quote_verified is False
    assert any("Unverified student quote" in r for r in q_eval_hall.review_reasons)
    assert any("Diagram/Table" in r for r in q_eval_hall.review_reasons)


@pytest.mark.asyncio
async def test_full_evaluation_and_csv_report(tmp_path: Path) -> None:
    rubric = ExamRubric(
        exam_id="EXAM_MOCK",
        subject="datascience",
        title="Stats Quiz",
        total_marks=5.0,
        is_locked=True,
        questions=[
            QuestionRubric(
                question_no="Q1",
                question_text="Compute the mean.",
                max_marks=5.0,
                question_type="numerical",
                criteria=[
                    RubricCriterion(
                        criterion_id="Q1_C1",
                        description="States mean 11.53",
                        max_points=5.0,
                        expected_keywords=["mean", "11.53"],
                    )
                ],
            )
        ],
    )
    ocr = OCRDocumentResponse(
        submission_id="SUB_TEST1",
        engine_used="mock-vlm",
        processing_time_sec=0.5,
        pages=[
            PageOCR(
                page_number=1,
                width=800,
                height=1000,
                full_markdown="## Q1\nTherefore the mean is 11.53.",
                regions=[
                    LayoutRegion(
                        region_id="p1_r1",
                        label="text",
                        confidence=0.95,
                        bbox=[10, 10, 700, 300],
                        raw_text="## Q1\nTherefore the mean is 11.53.",
                        clean_active_text="Therefore the mean is 11.53.",
                    )
                ],
            )
        ],
    )
    settings = Settings(database_path=str(tmp_path / "d.db"), storage_dir=str(tmp_path / "u"), mock_gemini=True)
    report = await evaluate_submission("SUB_TEST1", "CSE234002", rubric, ocr, settings)
    assert report.total_ai_marks == 5.0
    assert report.total_final_marks == 5.0

    csv_text = build_exam_gradebook_csv(rubric, [report])
    assert "CSE234002" in csv_text
    assert "5.0" in csv_text

    md_report = build_printable_student_report_md(report)
    assert "CSE234002" in md_report
    assert "Verified" in md_report


def test_end_to_end_fastapi_exam_lock_grade_override_csv(tmp_path: Path, monkeypatch) -> None:
    import time

    test_settings = Settings(
        database_path=str(tmp_path / "e2e.db"),
        storage_dir=str(tmp_path / "uploads"),
        mock_modal=True,
        mock_gemini=True,
    )
    test_db = Database(test_settings.db_path)
    monkeypatch.setattr(main_mod, "settings", test_settings)
    monkeypatch.setattr(main_mod, "db", test_db)
    client = TestClient(main_mod.app)

    # 1. Draft rubric via /api/exams/draft-rubric
    draft_resp = client.post(
        "/api/exams/draft-rubric",
        data={"subject": "datascience", "title": "Stats Midterm"},
        files={
            "question_paper": ("qp.txt", b"Q1: Compute simple mean from grouped data", "text/plain"),
            "model_answer": ("ma.txt", b"Q1: mean = 11.53 using 1730/150", "text/plain"),
        },
    )
    assert draft_resp.status_code == 200
    rubric = draft_resp.json()
    rubric["is_locked"] = True
    lock_resp = client.post("/api/exams", json=rubric)
    assert lock_resp.status_code == 200
    exam_id = lock_resp.json()["exam_id"]

    # 2. Upload student PDF
    doc = pymupdf.open()
    doc.new_page(width=595, height=842).insert_text((72, 120), "COVER SHEET")
    img = Image.new("RGB", (800, 1100), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    doc.new_page(width=800, height=1100).insert_image(pymupdf.Rect(0, 0, 800, 1100), stream=buf.getvalue())
    pdf_bytes = doc.tobytes()
    doc.close()

    up = client.post(
        "/api/submissions/upload",
        files={"files": ("CSE234002_datascience.pdf", pdf_bytes, "application/pdf")},
        data={"exam_id": exam_id, "engine": "vlm"},
    )
    assert up.status_code == 200
    sub_id = up.json()[0]["submission_id"]

    detail = None
    for _ in range(30):
        r = client.get(f"/api/submissions/{sub_id}")
        detail = r.json()
        if detail["submission"]["status"] == "completed":
            break
        time.sleep(0.1)

    assert detail is not None
    assert detail["submission"]["status"] == "completed"
    assert detail["evaluation"] is not None

    # 3. Override mark + persist to audit_overrides
    ovr = client.patch(
        f"/api/submissions/{sub_id}/override/Q1",
        json={"new_marks": 4.5, "teacher_note": "Verified step visually"},
    )
    assert ovr.status_code == 200
    assert ovr.json()["total_final_marks"] == 4.5

    # 4. Regrade Q1 after transcript edit
    regrade = client.post(
        f"/api/submissions/{sub_id}/regrade/Q1",
        json={"edited_transcript": "Simple Mean = 11.53", "teacher_note": "Clarified digit"},
    )
    assert regrade.status_code == 200

    # 5. Export Class CSV
    csv_resp = client.get(f"/api/exams/{exam_id}/export-csv")
    assert csv_resp.status_code == 200
    assert "CSE234002" in csv_resp.text
