"""SQLite persistence layer for exams, anonymous submissions, overrides, and grader cache."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from shared.schemas import (
    AuditOverrideRecord,
    EvaluationReport,
    ExamRubric,
    OCRDocumentResponse,
    SubmissionSummary,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Lightweight SQLite repository enforcing atomic commits and foreign keys."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create required tables if they do not exist."""
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS exams (
                    exam_id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    title TEXT NOT NULL,
                    rubric_json TEXT NOT NULL,
                    is_locked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS submissions (
                    submission_id TEXT PRIMARY KEY,
                    exam_id TEXT NULL,
                    roll_number TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    engine_used TEXT NOT NULL DEFAULT 'vlm',
                    page_image_paths_json TEXT NOT NULL DEFAULT '[]',
                    ocr_json TEXT NULL,
                    evaluation_json TEXT NULL,
                    clean_markdown TEXT NOT NULL DEFAULT '',
                    annotated_markdown TEXT NOT NULL DEFAULT '',
                    total_ai_marks REAL NULL,
                    total_final_marks REAL NULL,
                    needs_review_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS audit_overrides (
                    override_id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL,
                    question_no TEXT NOT NULL,
                    previous_marks REAL NOT NULL,
                    new_marks REAL NOT NULL,
                    edited_transcript TEXT NULL,
                    teacher_note TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (submission_id) REFERENCES submissions(submission_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS grader_cache (
                    cache_key TEXT PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    # ------------------------------------------------------------------
    # Exam CRUD
    # ------------------------------------------------------------------

    def save_exam(self, rubric: ExamRubric) -> ExamRubric:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO exams (exam_id, subject, title, rubric_json, is_locked, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(exam_id) DO UPDATE SET
                    subject = excluded.subject,
                    title = excluded.title,
                    rubric_json = excluded.rubric_json,
                    is_locked = excluded.is_locked
                """,
                (
                    rubric.exam_id,
                    rubric.subject,
                    rubric.title,
                    rubric.model_dump_json(),
                    int(rubric.is_locked),
                    now,
                ),
            )
        return rubric

    def get_exam(self, exam_id: str) -> Optional[ExamRubric]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT rubric_json, is_locked FROM exams WHERE exam_id = ?",
                (exam_id,),
            ).fetchone()
        if not row:
            return None
        rubric = ExamRubric.model_validate_json(row["rubric_json"])
        rubric.is_locked = bool(row["is_locked"])
        return rubric

    def list_exams(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT e.exam_id, e.subject, e.title, e.rubric_json, e.is_locked, e.created_at,
                       COUNT(s.submission_id) AS submission_count
                FROM exams e
                LEFT JOIN submissions s ON s.exam_id = e.exam_id
                GROUP BY e.exam_id
                ORDER BY e.created_at DESC
                """
            ).fetchall()
        items = []
        for row in rows:
            rubric = ExamRubric.model_validate_json(row["rubric_json"])
            items.append(
                {
                    "exam_id": row["exam_id"],
                    "subject": row["subject"],
                    "title": row["title"],
                    "total_marks": rubric.total_marks,
                    "question_count": len(rubric.questions),
                    "is_locked": bool(row["is_locked"]),
                    "submission_count": row["submission_count"],
                    "created_at": row["created_at"],
                }
            )
        return items

    # ------------------------------------------------------------------
    # Submission CRUD
    # ------------------------------------------------------------------

    def create_submission(
        self,
        submission_id: str,
        roll_number: str,
        original_filename: str,
        engine_used: str = "vlm",
        exam_id: Optional[str] = None,
        status: str = "preprocessing",
        page_image_paths: Optional[list[str]] = None,
    ) -> SubmissionSummary:
        now = _utc_now()
        paths_json = json.dumps(page_image_paths or [])
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO submissions (
                    submission_id, exam_id, roll_number, original_filename,
                    status, engine_used, page_image_paths_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    submission_id,
                    exam_id,
                    roll_number,
                    original_filename,
                    status,
                    engine_used,
                    paths_json,
                    now,
                    now,
                ),
            )
        return self.get_submission_summary(submission_id)  # type: ignore[return-value]

    def update_submission_pages_and_status(
        self,
        submission_id: str,
        status: str,
        page_image_paths: Optional[list[str]] = None,
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            if page_image_paths is not None:
                conn.execute(
                    """
                    UPDATE submissions
                    SET status = ?, page_image_paths_json = ?, updated_at = ?
                    WHERE submission_id = ?
                    """,
                    (status, json.dumps(page_image_paths), now, submission_id),
                )
            else:
                conn.execute(
                    "UPDATE submissions SET status = ?, updated_at = ? WHERE submission_id = ?",
                    (status, now, submission_id),
                )

    def save_ocr_result(
        self,
        submission_id: str,
        ocr: OCRDocumentResponse,
        clean_markdown: str = "",
        annotated_markdown: str = "",
        status: str = "ocr_completed",
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE submissions
                SET ocr_json = ?,
                    engine_used = ?,
                    clean_markdown = ?,
                    annotated_markdown = ?,
                    status = ?,
                    updated_at = ?
                WHERE submission_id = ?
                """,
                (
                    ocr.model_dump_json(),
                    ocr.engine_used,
                    clean_markdown,
                    annotated_markdown,
                    status,
                    now,
                    submission_id,
                ),
            )

    def save_evaluation_result(
        self,
        submission_id: str,
        report: EvaluationReport,
        status: str = "completed",
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE submissions
                SET evaluation_json = ?,
                    total_ai_marks = ?,
                    total_final_marks = ?,
                    needs_review_count = ?,
                    status = ?,
                    updated_at = ?
                WHERE submission_id = ?
                """,
                (
                    report.model_dump_json(),
                    report.total_ai_marks,
                    report.total_final_marks,
                    report.needs_review_count,
                    status,
                    now,
                    submission_id,
                ),
            )

    def get_submission_raw(self, submission_id: str) -> Optional[dict]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_submission_summary(self, submission_id: str) -> Optional[SubmissionSummary]:
        row = self.get_submission_raw(submission_id)
        if not row:
            return None
        return SubmissionSummary(
            submission_id=row["submission_id"],
            exam_id=row["exam_id"],
            roll_number=row["roll_number"],
            original_filename=row["original_filename"],
            status=row["status"],
            engine_used=row["engine_used"],
            total_ai_marks=row["total_ai_marks"],
            total_final_marks=row["total_final_marks"],
            needs_review_count=row["needs_review_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_submissions(self, exam_id: Optional[str] = None) -> list[SubmissionSummary]:
        with self.connect() as conn:
            if exam_id:
                rows = conn.execute(
                    "SELECT * FROM submissions WHERE exam_id = ? ORDER BY created_at DESC",
                    (exam_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM submissions ORDER BY created_at DESC"
                ).fetchall()
        return [
            SubmissionSummary(
                submission_id=r["submission_id"],
                exam_id=r["exam_id"],
                roll_number=r["roll_number"],
                original_filename=r["original_filename"],
                status=r["status"],
                engine_used=r["engine_used"],
                total_ai_marks=r["total_ai_marks"],
                total_final_marks=r["total_final_marks"],
                needs_review_count=r["needs_review_count"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Audit Overrides & Grader Cache
    # ------------------------------------------------------------------

    def add_audit_override(
        self,
        submission_id: str,
        question_no: str,
        previous_marks: float,
        new_marks: float,
        edited_transcript: Optional[str] = None,
        teacher_note: str = "",
    ) -> AuditOverrideRecord:
        record = AuditOverrideRecord(
            override_id=f"OVR_{uuid.uuid4().hex[:10]}",
            submission_id=submission_id,
            question_no=question_no,
            previous_marks=previous_marks,
            new_marks=new_marks,
            edited_transcript=edited_transcript,
            teacher_note=teacher_note,
            timestamp=_utc_now(),
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_overrides (
                    override_id, submission_id, question_no, previous_marks,
                    new_marks, edited_transcript, teacher_note, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.override_id,
                    record.submission_id,
                    record.question_no,
                    record.previous_marks,
                    record.new_marks,
                    record.edited_transcript,
                    record.teacher_note,
                    record.timestamp,
                ),
            )
        return record

    def list_audit_overrides(self, submission_id: str) -> list[AuditOverrideRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_overrides WHERE submission_id = ? ORDER BY timestamp DESC",
                (submission_id,),
            ).fetchall()
        return [AuditOverrideRecord(**dict(r)) for r in rows]

    def get_cached_grader_response(self, cache_key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT response_json FROM grader_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return row["response_json"] if row else None

    def set_cached_grader_response(self, cache_key: str, model_name: str, response_json: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO grader_cache (cache_key, model_name, response_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (cache_key, model_name, response_json, _utc_now()),
            )
