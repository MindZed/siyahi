"""Phase 2 tests: Modal mock OCR, Rule-1 payload, segmentation, and Pen-to-Print MD/PDF export."""

from pathlib import Path
import pymupdf
import pytest
from PIL import Image, ImageDraw

from backend.config import Settings
from backend.document_renderer import (
    build_markdown_variants,
    latex_to_readable_text,
    render_pen_to_print_pdf,
    save_diagram_crops,
)
from backend.modal_client import ModalOCRClient, build_ocr_request
from backend.pdf_processor import preprocess_submission
from backend.question_segmenter import segment_ocr_document


@pytest.mark.asyncio
async def test_mock_ocr_segmenter_and_pen_to_print_exports(tmp_path: Path) -> None:
    # Create a 3-page sample PDF (Page 1 = Cover PII, Pages 2-3 = handwritten pages)
    pdf_path = tmp_path / "CSE234002_datascience.pdf"
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 120), "COVER PAGE\nRoll: CSE234002", fontsize=16)

    for idx in (2, 3):
        img = Image.new("RGB", (800, 1100), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([80, 100, 720, 480], outline="black", width=2)
        draw.text((100, 130), f"Sample content page {idx}", fill="black")
        img_file = tmp_path / f"_src_{idx}.png"
        img.save(img_file)
        page = doc.new_page(width=800, height=1100)
        page.insert_image(pymupdf.Rect(0, 0, 800, 1100), filename=str(img_file))
    doc.save(str(pdf_path))
    doc.close()

    prep = preprocess_submission(
        input_path=pdf_path,
        storage_dir=tmp_path / "uploads",
        dpi=150,
        skip_cover_page=True,
    )
    assert prep.cover_page_skipped is True
    assert len(prep.pages) == 2

    # Verify Rule 1 OCRRequest builds without any rubric fields
    ocr_req = build_ocr_request(prep.submission_id, prep.pages)
    assert "rubric" not in ocr_req.model_dump()
    assert len(ocr_req.pages) == 2

    settings = Settings(
        database_path=str(tmp_path / "db.sqlite"),
        storage_dir=str(tmp_path / "uploads"),
        mock_modal=True,
    )
    client = ModalOCRClient(settings)
    ocr_resp = await client.transcribe(prep.submission_id, prep.pages)
    assert ocr_resp.submission_id == prep.submission_id
    assert len(ocr_resp.pages) == 2

    # Question segmentation
    segments, region_map = segment_ocr_document(ocr_resp, expected_questions=["Q1", "Q2"])
    assert "Q1" in segments and "Q2" in segments
    assert "Shortcut" not in segments["Q1"].clean_active_text
    assert len(segments["Q1"].unclear_spans) >= 1
    assert len(segments["Q2"].diagram_crops) == 1
    assert len(region_map["Q1"]) >= 1

    # Save crops + Markdown variants + Pen-to-Print PDF
    crops_dir = tmp_path / "uploads" / prep.submission_id / "crops"
    saved_crops = save_diagram_crops(ocr_resp, crops_dir)
    assert len(saved_crops) >= 1

    clean_md, annotated_md = build_markdown_variants(ocr_resp)
    assert "Shortcut" not in clean_md
    assert "~~Shortcut~~" in annotated_md
    assert "| 1 - 5 | 3 | 20 | 60 |" in clean_md

    out_pdf = tmp_path / "pen_to_print.pdf"
    render_pen_to_print_pdf(
        clean_md,
        out_pdf,
        title=f"{prep.roll_number} — {prep.subject}",
        subtitle="Pen-to-Print Verified Output",
        crops_dir=crops_dir,
    )
    assert out_pdf.exists()
    with pymupdf.open(str(out_pdf)) as rendered:
        assert len(rendered) >= 1
        extracted = "\n".join(page.get_text() for page in rendered)
        assert "1730" in extracted
        assert "Divide and Conquer" in extracted


def test_latex_to_readable_text() -> None:
    converted = latex_to_readable_text(r"\bar{x} = \frac{\sum f_i x_i}{\sum f_i}")
    assert "Σ" in converted
    assert "/" in converted
