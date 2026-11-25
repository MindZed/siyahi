"""Segments OCR output by Question Markers across pages and links bounding-box references."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from shared.schemas import OCRDocumentResponse, RegionRef, UnclearSpan

STRUCK_PATTERN = re.compile(r"\[struck:\s*(.*?)\]", re.IGNORECASE | re.DOTALL)
UNCLEAR_PATTERN = re.compile(r"\[unclear:\s*([^/\]]+?)/([^\]]+?)\]", re.IGNORECASE)

# Matches line-start markers like:
# "## Q1", "Q.1", "Q 2(a)", "Ans 2(b):", "Answer 3.", "Question 4(ii)"
QUESTION_MARKER_RE = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?:Question|Q\.?|Ans(?:wer)?\.?)\s*(\d+(?:\s*\([a-zA-Z0-9]+\))?)\s*[:.\-\)]*\s*(.*)$",
    re.IGNORECASE,
)


@dataclass
class SegmentedQuestion:
    """Aggregated raw/clean text, tags, and source bounding boxes for one question."""

    question_no: str
    raw_lines: list[str] = field(default_factory=list)
    region_refs: list[RegionRef] = field(default_factory=list)
    diagram_crops: list[str] = field(default_factory=list)
    unclear_spans: list[UnclearSpan] = field(default_factory=list)
    struck_spans: list[str] = field(default_factory=list)

    @property
    def raw_transcript(self) -> str:
        return "\n".join(self.raw_lines).strip()

    @property
    def clean_active_text(self) -> str:
        text = STRUCK_PATTERN.sub("", self.raw_transcript)
        text = UNCLEAR_PATTERN.sub(lambda m: m.group(1).strip(), text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def normalize_question_no(raw_num: str) -> str:
    """Canonicalize '2 (a)' or '1' into 'Q2(a)' or 'Q1'."""
    compact = re.sub(r"\s+", "", raw_num).lower()
    return f"Q{compact}"


def segment_ocr_document(
    ocr: OCRDocumentResponse,
    expected_questions: list[str] | None = None,
) -> tuple[dict[str, SegmentedQuestion], dict[str, list[RegionRef]]]:
    """Segment pages line-by-line into question blocks while preserving all text and crops."""
    segments: dict[str, SegmentedQuestion] = {}
    current_q = "UNASSIGNED"
    found_any_marker = False

    def _ensure_segment(q_no: str) -> SegmentedQuestion:
        if q_no not in segments:
            segments[q_no] = SegmentedQuestion(question_no=q_no)
        return segments[q_no]

    for page in ocr.pages:
        page_text = page.full_markdown.strip()
        if not page_text and page.regions:
            page_text = "\n\n".join(r.raw_text for r in page.regions if r.raw_text)

        page_questions_seen: list[str] = []
        for line in page_text.splitlines():
            match = QUESTION_MARKER_RE.match(line)
            if match:
                found_any_marker = True
                current_q = normalize_question_no(match.group(1))
                seg = _ensure_segment(current_q)
                if current_q not in page_questions_seen:
                    page_questions_seen.append(current_q)
                trailing = match.group(2).strip()
                if trailing:
                    seg.raw_lines.append(trailing)
            else:
                seg = _ensure_segment(current_q)
                if current_q not in page_questions_seen:
                    page_questions_seen.append(current_q)
                seg.raw_lines.append(line)

        # Link page region bounding boxes and diagram/table crops to active questions on the page
        target_q = page_questions_seen[-1] if page_questions_seen else current_q
        target_seg = _ensure_segment(target_q)
        for region in page.regions:
            ref = RegionRef(
                page_number=page.page_number,
                region_id=region.region_id,
                label=region.label,
                bbox=region.bbox,
            )
            # Deduplicate region refs per question
            if not any(
                r.page_number == ref.page_number and r.region_id == ref.region_id
                for r in target_seg.region_refs
            ):
                target_seg.region_refs.append(ref)

            if region.crop_base64 and region.label in {"diagram", "table"}:
                if region.crop_base64 not in target_seg.diagram_crops:
                    target_seg.diagram_crops.append(region.crop_base64)

            for u in region.unclear_spans:
                target_seg.unclear_spans.append(u)
            for s in region.struck_spans:
                target_seg.struck_spans.append(s)

    # If no Q1/Ans markers existed at all (e.g., pure study notes), rename UNASSIGNED -> FULL_DOCUMENT
    if not found_any_marker and "UNASSIGNED" in segments:
        doc_seg = segments.pop("UNASSIGNED")
        doc_seg.question_no = "FULL_DOCUMENT"
        segments["FULL_DOCUMENT"] = doc_seg

    # Ensure every expected rubric question exists (even if unanswered by the student)
    if expected_questions:
        for q_no in expected_questions:
            _ensure_segment(q_no)

    # Extract any tags directly from accumulated raw lines if region-level extraction missed them
    for seg in segments.values():
        raw = seg.raw_transcript
        for m in STRUCK_PATTERN.finditer(raw):
            val = m.group(1).strip()
            if val and val not in seg.struck_spans:
                seg.struck_spans.append(val)
        for m in UNCLEAR_PATTERN.finditer(raw):
            tag = m.group(0)
            if not any(u.raw_tag == tag for u in seg.unclear_spans):
                seg.unclear_spans.append(
                    UnclearSpan(raw_tag=tag, alternatives=[m.group(1).strip(), m.group(2).strip()])
                )

    region_map = {q_no: seg.region_refs for q_no, seg in segments.items()}
    return segments, region_map
