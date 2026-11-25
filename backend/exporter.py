"""Class gradebook CSV and auditable per-student evaluation report exporter."""

from __future__ import annotations

import csv
import io

from shared.schemas import EvaluationReport, ExamRubric


def build_exam_gradebook_csv(rubric: ExamRubric, reports: list[EvaluationReport]) -> str:
    """Generate a clean class gradebook CSV across all evaluated submissions."""
    buf = io.StringIO()
    q_nos = [q.question_no for q in rubric.questions]
    header = [
        "roll_number",
        "submission_id",
        *q_nos,
        "total_ai_marks",
        "total_final_marks",
        "total_max_marks",
        "needs_review_count",
        "overridden_questions",
    ]
    writer = csv.writer(buf)
    writer.writerow(header)

    for rep in sorted(reports, key=lambda r: r.roll_number):
        by_q = {q.question_no: q for q in rep.questions}
        q_scores = [by_q[qn].final_marks if qn in by_q else "" for qn in q_nos]
        overridden = ",".join(q.question_no for q in rep.questions if q.teacher_overridden)
        writer.writerow(
            [
                rep.roll_number,
                rep.submission_id,
                *q_scores,
                rep.total_ai_marks,
                rep.total_final_marks,
                rep.total_max_marks,
                rep.needs_review_count,
                overridden,
            ]
        )

    return buf.getvalue()


def build_printable_student_report_md(report: EvaluationReport) -> str:
    """Generate an auditable Markdown evaluation report linking quotes to marks."""
    lines = [
        f"# Evaluation Report — {report.roll_number} ({report.subject})",
        "",
        f"- **Submission ID:** `{report.submission_id}`",
        f"- **Exam ID:** `{report.exam_id}`",
        f"- **Final Score:** {report.total_final_marks} / {report.total_max_marks} "
        f"(AI Score: {report.total_ai_marks})",
        f"- **Questions Flagged for Review:** {report.needs_review_count}",
        "",
    ]

    for q in report.questions:
        lines.append(f"## {q.question_no} — {q.final_marks} / {q.max_marks}")
        if q.needs_human_review:
            lines.append(f"- **Needs Human Review:** {', '.join(q.review_reasons)}")
        if q.teacher_overridden:
            lines.append(f"- **Teacher Override Note:** {q.override_note or 'Adjusted by professor'}")
        lines.append("")
        lines.append("**Clean Active Transcript:**")
        lines.append(f"> {q.clean_active_text or '(empty)'}")
        lines.append("")
        for c in q.criteria_breakdown:
            status = "Verified" if c.quote_verified else "Unverified"
            quote = f'`"{c.student_quote}"` ({status})' if c.student_quote else "No quote"
            lines.append(
                f"- **{c.criterion_id}** ({c.awarded_points}/{c.max_points}): {c.reason} | {quote}"
            )
        lines.append("")

    return "\n".join(lines)
