"""FastAPI backend orchestrator: preprocessing, Modal OCR, Pen-to-Print exports, and grading."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Literal, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.database import Database
from backend.document_renderer import (
    build_markdown_variants,
    render_pen_to_print_pdf,
    save_diagram_crops,
)
from backend.modal_client import ModalOCRClient
from backend.pdf_processor import generate_anonymous_submission_id, parse_submission_filename, preprocess_submission
from backend.question_segmenter import segment_ocr_document
from shared.schemas import (
    EvaluationReport,
    ExamRubric,
    OCRDocumentResponse,
    OverrideRequest,
    RegradeRequest,
    SubmissionDetailResponse,
    SubmissionSummary,
)

settings: Settings = get_settings()
db = Database(settings.db_path)

app = FastAPI(
    title="Siyahi — Auditable Handwritten Exam Grading & Pen-to-Print API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UpdateMarkdownRequest(BaseModel):
    clean_markdown: str
    annotated_markdown: Optional[str] = None


def _get_submission_storage(submission_id: str) -> Path:
    return settings.upload_dir / submission_id


async def _run_submission_pipeline(
    submission_id: str,
    input_file_path: Path,
    original_filename: str,
    exam_id: Optional[str],
    engine: Literal["vlm", "paddle_trocr"],
    mode: Literal["hybrid", "strict_regions", "whole_page"],
    skip_cover_page: bool,
    enable_sensitivity_sampling: bool,
) -> None:
    """Background pipeline: local PII preprocess -> Modal OCR -> MD/PDF -> optional evaluation."""
    try:
        db.update_submission_pages_and_status(submission_id, status="preprocessing")
        prep = await asyncio.to_thread(
            preprocess_submission,
            input_path=input_file_path,
            storage_dir=settings.upload_dir,
            submission_id=submission_id,
            original_filename=original_filename,
            dpi=settings.pdf_render_dpi,
            skip_cover_page=skip_cover_page,
            auto_split_spreads=settings.auto_split_spreads,
            header_mask_pct=settings.header_mask_pct,
        )
        page_paths = [p.image_path for p in prep.pages]
        db.update_submission_pages_and_status(
            submission_id, status="ocr_running", page_image_paths=page_paths
        )

        client = ModalOCRClient(settings)
        ocr_resp = await client.transcribe(
            submission_id=submission_id,
            pages=prep.pages,
            engine=engine,
            mode=mode,
            enable_sensitivity_sampling=enable_sensitivity_sampling,
        )

        sub_dir = _get_submission_storage(submission_id)
        crops_dir = sub_dir / "crops"
        save_diagram_crops(ocr_resp, crops_dir)

        clean_md, annotated_md = build_markdown_variants(
            ocr_resp,
            crops_rel_dir=f"/api/submissions/{submission_id}/crops",
        )
        # Render PDF locally with filesystem crop paths
        pdf_md, _ = build_markdown_variants(ocr_resp, crops_rel_dir="crops")
        pdf_path = sub_dir / f"{submission_id}_pen_to_print.pdf"
        await asyncio.to_thread(
            render_pen_to_print_pdf,
            pdf_md,
            pdf_path,
            title=f"{prep.roll_number} — {prep.subject}",
            subtitle=f"Submission {submission_id} | Engine: {ocr_resp.engine_used}",
            crops_dir=crops_dir,
        )

        db.save_ocr_result(
            submission_id=submission_id,
            ocr=ocr_resp,
            clean_markdown=clean_md,
            annotated_markdown=annotated_md,
            status="ocr_completed",
        )

        # If linked to a locked exam rubric, run Phase 4 evaluator if available
        if exam_id:
            rubric = db.get_exam(exam_id)
            if rubric and rubric.is_locked:
                try:
                    from backend.evaluator import evaluate_submission  # Phase 4

                    db.update_submission_pages_and_status(submission_id, status="grading")
                    report = await evaluate_submission(
                        submission_id=submission_id,
                        roll_number=prep.roll_number,
                        rubric=rubric,
                        ocr=ocr_resp,
                        settings=settings,
                        db=db,
                    )
                    db.save_evaluation_result(submission_id, report, status="completed")
                except ImportError:
                    # Phase 4 evaluator not yet installed; keep ocr_completed cleanly
                    pass
    except Exception as exc:
        db.update_submission_pages_and_status(submission_id, status=f"failed: {str(exc)[:180]}")


@app.get("/api/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "mock_modal": settings.mock_modal,
        "grader_provider": settings.grader_provider,
        "grader_model": settings.grader_model,
        "mock_gemini": settings.mock_gemini,
    }


# ---------------------------------------------------------------------------
# Exam & Rubric Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/exams")
def list_exams() -> list[dict]:
    return db.list_exams()


@app.get("/api/exams/{exam_id}", response_model=ExamRubric)
def get_exam(exam_id: str) -> ExamRubric:
    rubric = db.get_exam(exam_id)
    if not rubric:
        raise HTTPException(status_code=404, detail="Exam not found.")
    return rubric


@app.post("/api/exams", response_model=ExamRubric)
def save_exam(rubric: ExamRubric) -> ExamRubric:
    return db.save_exam(rubric)


@app.post("/api/exams/draft-rubric", response_model=ExamRubric)
async def draft_rubric_endpoint(
    subject: str = Form(...),
    title: str = Form(...),
    question_paper: UploadFile = File(...),
    model_answer: UploadFile = File(...),
) -> ExamRubric:
    try:
        from backend.rubric_builder import draft_rubric_from_uploads
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="Rubric builder (Phase 4) not yet enabled.") from exc

    qp_bytes = await question_paper.read()
    ma_bytes = await model_answer.read()
    return await draft_rubric_from_uploads(
        subject=subject,
        title=title,
        question_paper_bytes=qp_bytes,
        question_paper_name=question_paper.filename or "question_paper.pdf",
        model_answer_bytes=ma_bytes,
        model_answer_name=model_answer.filename or "model_answer.pdf",
        settings=settings,
    )


@app.get("/api/exams/{exam_id}/submissions", response_model=list[SubmissionSummary])
def list_exam_submissions(exam_id: str) -> list[SubmissionSummary]:
    return db.list_submissions(exam_id=exam_id)


@app.get("/api/exams/{exam_id}/export-csv")
def export_exam_csv(exam_id: str) -> Response:
    try:
        from backend.exporter import build_exam_gradebook_csv
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="Gradebook CSV exporter (Phase 4) not yet enabled.") from exc

    rubric = db.get_exam(exam_id)
    if not rubric:
        raise HTTPException(status_code=404, detail="Exam not found.")
    submissions = db.list_submissions(exam_id=exam_id)
    reports: list[EvaluationReport] = []
    for sub in submissions:
        raw = db.get_submission_raw(sub.submission_id)
        if raw and raw.get("evaluation_json"):
            reports.append(EvaluationReport.model_validate_json(raw["evaluation_json"]))

    csv_content = build_exam_gradebook_csv(rubric, reports)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{exam_id}_gradebook.csv"'},
    )


# ---------------------------------------------------------------------------
# Submission Upload, OCR, Pen-to-Print Exports & Review Desk
# ---------------------------------------------------------------------------

@app.get("/api/submissions", response_model=list[SubmissionSummary])
def list_all_submissions() -> list[SubmissionSummary]:
    return db.list_submissions()


@app.post("/api/submissions/upload", response_model=list[SubmissionSummary])
async def upload_submissions(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    exam_id: Optional[str] = Form(default=None),
    engine: Literal["vlm", "paddle_trocr"] = Form(default="vlm"),
    mode: Literal["hybrid", "strict_regions", "whole_page"] = Form(default="hybrid"),
    skip_cover_page: bool = Form(default=True),
    enable_sensitivity_sampling: bool = Form(default=False),
) -> list[SubmissionSummary]:
    clean_exam_id = exam_id.strip() if exam_id and exam_id.strip() else None
    if clean_exam_id and not db.get_exam(clean_exam_id):
        raise HTTPException(status_code=404, detail=f"Exam '{clean_exam_id}' not found.")

    created: list[SubmissionSummary] = []
    for upload in files:
        filename = upload.filename or "submission.pdf"
        roll_number, _ = parse_submission_filename(filename)
        sub_id = generate_anonymous_submission_id()
        sub_dir = _get_submission_storage(sub_id)
        sub_dir.mkdir(parents=True, exist_ok=True)
        dest_path = sub_dir / f"source{Path(filename).suffix.lower() or '.pdf'}"
        content = await upload.read()
        dest_path.write_bytes(content)

        summary = db.create_submission(
            submission_id=sub_id,
            roll_number=roll_number,
            original_filename=filename,
            engine_used=engine,
            exam_id=clean_exam_id,
            status="queued",
        )
        created.append(summary)
        background_tasks.add_task(
            _run_submission_pipeline,
            sub_id,
            dest_path,
            filename,
            clean_exam_id,
            engine,
            mode,
            skip_cover_page,
            enable_sensitivity_sampling,
        )

    return created


@app.get("/api/submissions/{submission_id}", response_model=SubmissionDetailResponse)
def get_submission_detail(submission_id: str) -> SubmissionDetailResponse:
    raw = db.get_submission_raw(submission_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Submission not found.")

    summary = db.get_submission_summary(submission_id)
    assert summary is not None

    page_paths: list[str] = json.loads(raw.get("page_image_paths_json") or "[]")
    page_urls = [
        f"/api/submissions/{submission_id}/pages/{i}"
        for i in range(1, len(page_paths) + 1)
    ]

    ocr_obj = OCRDocumentResponse.model_validate_json(raw["ocr_json"]) if raw.get("ocr_json") else None
    eval_obj = (
        EvaluationReport.model_validate_json(raw["evaluation_json"])
        if raw.get("evaluation_json")
        else None
    )

    question_region_map = {}
    if ocr_obj:
        expected = [q.question_no for q in eval_obj.questions] if eval_obj else None
        _, question_region_map = segment_ocr_document(ocr_obj, expected_questions=expected)

    overrides = db.list_audit_overrides(submission_id)
    return SubmissionDetailResponse(
        submission=summary,
        page_image_urls=page_urls,
        ocr=ocr_obj,
        evaluation=eval_obj,
        question_region_map=question_region_map,
        clean_markdown=raw.get("clean_markdown") or "",
        annotated_markdown=raw.get("annotated_markdown") or "",
        overrides=overrides,
    )


@app.get("/api/submissions/{submission_id}/pages/{page_number}")
def get_submission_page_image(submission_id: str, page_number: int) -> FileResponse:
    raw = db.get_submission_raw(submission_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Submission not found.")
    page_paths: list[str] = json.loads(raw.get("page_image_paths_json") or "[]")
    if page_number < 1 or page_number > len(page_paths):
        raise HTTPException(status_code=404, detail="Page image not found.")
    img_path = Path(page_paths[page_number - 1])
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Page image missing on disk.")
    return FileResponse(str(img_path), media_type="image/png")


@app.get("/api/submissions/{submission_id}/crops/{filename}")
def get_submission_crop_image(submission_id: str, filename: str) -> FileResponse:
    safe_name = Path(filename).name
    crop_path = _get_submission_storage(submission_id) / "crops" / safe_name
    if not crop_path.exists():
        raise HTTPException(status_code=404, detail="Crop image not found.")
    return FileResponse(str(crop_path), media_type="image/png")


@app.put("/api/submissions/{submission_id}/markdown")
async def update_submission_markdown(
    submission_id: str,
    payload: UpdateMarkdownRequest,
) -> dict:
    raw = db.get_submission_raw(submission_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Submission not found.")

    ocr_obj = (
        OCRDocumentResponse.model_validate_json(raw["ocr_json"])
        if raw.get("ocr_json")
        else OCRDocumentResponse(submission_id=submission_id, engine_used="manual", processing_time_sec=0.0, pages=[])
    )
    annotated = payload.annotated_markdown if payload.annotated_markdown is not None else raw.get("annotated_markdown", "")
    db.save_ocr_result(
        submission_id=submission_id,
        ocr=ocr_obj,
        clean_markdown=payload.clean_markdown,
        annotated_markdown=annotated,
        status=raw["status"],
    )

    sub_dir = _get_submission_storage(submission_id)
    crops_dir = sub_dir / "crops"
    pdf_md = re.sub(
        rf"/api/submissions/{re.escape(submission_id)}/crops/",
        "crops/",
        payload.clean_markdown,
    )
    pdf_path = sub_dir / f"{submission_id}_pen_to_print.pdf"
    await asyncio.to_thread(
        render_pen_to_print_pdf,
        pdf_md,
        pdf_path,
        title=f"{raw['roll_number']} — {raw['original_filename']}",
        subtitle="Pen-to-Print Verified Export",
        crops_dir=crops_dir,
    )
    return {"status": "saved", "submission_id": submission_id}


@app.get("/api/submissions/{submission_id}/export-md")
def export_submission_markdown(
    submission_id: str,
    variant: Literal["clean", "annotated"] = Query(default="clean"),
) -> PlainTextResponse:
    raw = db.get_submission_raw(submission_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Submission not found.")
    content = raw.get("annotated_markdown") if variant == "annotated" else raw.get("clean_markdown")
    filename = f"{raw['roll_number']}_{variant}.md"
    return PlainTextResponse(
        content=content or "",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/submissions/{submission_id}/export-pdf")
async def export_submission_pdf(submission_id: str) -> FileResponse:
    raw = db.get_submission_raw(submission_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Submission not found.")
    sub_dir = _get_submission_storage(submission_id)
    pdf_path = sub_dir / f"{submission_id}_pen_to_print.pdf"
    if not pdf_path.exists():
        clean_md = raw.get("clean_markdown") or ""
        pdf_md = re.sub(
            rf"/api/submissions/{re.escape(submission_id)}/crops/",
            "crops/",
            clean_md,
        )
        await asyncio.to_thread(
            render_pen_to_print_pdf,
            pdf_md,
            pdf_path,
            title=f"{raw['roll_number']} — {raw['original_filename']}",
            subtitle="Pen-to-Print Export",
            crops_dir=sub_dir / "crops",
        )
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"{raw['roll_number']}_pen_to_print.pdf",
    )


@app.post("/api/submissions/{submission_id}/regrade/{question_no}", response_model=EvaluationReport)
async def regrade_question_endpoint(
    submission_id: str,
    question_no: str,
    payload: RegradeRequest,
) -> EvaluationReport:
    try:
        from backend.evaluator import regrade_single_question
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="Evaluator (Phase 4) not yet enabled.") from exc

    raw = db.get_submission_raw(submission_id)
    if not raw or not raw.get("exam_id"):
        raise HTTPException(status_code=404, detail="Exam-linked submission not found.")
    rubric = db.get_exam(raw["exam_id"])
    if not rubric:
        raise HTTPException(status_code=404, detail="Exam rubric not found.")
    if not raw.get("evaluation_json"):
        raise HTTPException(status_code=400, detail="Submission has not been graded yet.")

    report = EvaluationReport.model_validate_json(raw["evaluation_json"])
    updated_report = await regrade_single_question(
        report=report,
        rubric=rubric,
        question_no=question_no,
        edited_transcript=payload.edited_transcript,
        teacher_note=payload.teacher_note,
        settings=settings,
        db=db,
    )
    db.save_evaluation_result(submission_id, updated_report, status="completed")
    return updated_report


@app.patch("/api/submissions/{submission_id}/override/{question_no}", response_model=EvaluationReport)
def override_question_endpoint(
    submission_id: str,
    question_no: str,
    payload: OverrideRequest,
) -> EvaluationReport:
    raw = db.get_submission_raw(submission_id)
    if not raw or not raw.get("evaluation_json"):
        raise HTTPException(status_code=404, detail="Graded submission not found.")

    report = EvaluationReport.model_validate_json(raw["evaluation_json"])
    target_q = next((q for q in report.questions if q.question_no == question_no), None)
    if not target_q:
        raise HTTPException(status_code=404, detail=f"Question '{question_no}' not found in report.")

    clamped = min(max(0.0, payload.new_marks), target_q.max_marks)
    prev_marks = target_q.final_marks
    target_q.final_marks = clamped
    target_q.teacher_overridden = True
    target_q.override_note = payload.teacher_note
    target_q.needs_human_review = False

    report.total_final_marks = round(sum(q.final_marks for q in report.questions), 2)
    report.needs_review_count = sum(1 for q in report.questions if q.needs_human_review)

    db.add_audit_override(
        submission_id=submission_id,
        question_no=question_no,
        previous_marks=prev_marks,
        new_marks=clamped,
        teacher_note=payload.teacher_note,
    )
    db.save_evaluation_result(submission_id, report, status="completed")
    return report
