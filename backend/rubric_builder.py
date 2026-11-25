"""Drafts structured ExamRubric objects from Question Paper and Model Answer uploads."""

from __future__ import annotations

import uuid
from pathlib import Path

import pymupdf

from backend.config import Settings
from backend.grader_provider import GraderProvider, get_grader_provider
from shared.schemas import ExamRubric


def extract_document_text(file_bytes: bytes, filename: str) -> str:
    """Extract text locally from PDF or plain-text uploads."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        parts: list[str] = []
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc, start=1):
                txt = page.get_text("text").strip()
                if txt:
                    parts.append(f"--- Page {i} ---\n{txt}")
        return "\n\n".join(parts)
    try:
        return file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""


async def draft_rubric_from_uploads(
    subject: str,
    title: str,
    question_paper_bytes: bytes,
    question_paper_name: str,
    model_answer_bytes: bytes,
    model_answer_name: str,
    settings: Settings,
    provider: GraderProvider | None = None,
) -> ExamRubric:
    """Parse uploaded question paper + model answer into an editable draft ExamRubric."""
    qp_text = extract_document_text(question_paper_bytes, question_paper_name)
    ma_text = extract_document_text(model_answer_bytes, model_answer_name)
    exam_id = f"EXAM_{uuid.uuid4().hex[:8].upper()}"

    active_provider = provider or get_grader_provider(settings)
    rubric = await active_provider.draft_rubric(
        exam_id=exam_id,
        subject=subject.strip(),
        title=title.strip(),
        question_paper_text=qp_text,
        model_answer_text=ma_text,
    )
    rubric.exam_id = exam_id
    rubric.is_locked = False
    rubric.total_marks = round(sum(q.max_marks for q in rubric.questions), 2)
    return rubric
