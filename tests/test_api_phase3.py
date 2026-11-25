"""Phase 3 backend API integration tests (upload -> mock OCR -> detail -> MD/PDF export)."""

import io
import time
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

import backend.main as main_mod
from backend.config import Settings
from backend.database import Database


def _create_sample_pdf_bytes() -> bytes:
    doc = pymupdf.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 120), "COVER SHEET\nRoll: CSE234002", fontsize=16)

    img = Image.new("RGB", (800, 1100), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([80, 100, 720, 460], outline="black", width=2)
    draw.text((100, 140), "Q1 Handwritten Answer", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    p2 = doc.new_page(width=800, height=1100)
    p2.insert_image(pymupdf.Rect(0, 0, 800, 1100), stream=buf.getvalue())

    out = doc.tobytes()
    doc.close()
    return out


def test_fastapi_pen_to_print_upload_and_exports(tmp_path: Path, monkeypatch) -> None:
    test_settings = Settings(
        database_path=str(tmp_path / "api_test.db"),
        storage_dir=str(tmp_path / "uploads"),
        mock_modal=True,
        mock_gemini=True,
    )
    test_db = Database(test_settings.db_path)
    monkeypatch.setattr(main_mod, "settings", test_settings)
    monkeypatch.setattr(main_mod, "db", test_db)

    client = TestClient(main_mod.app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    pdf_bytes = _create_sample_pdf_bytes()
    resp = client.post(
        "/api/submissions/upload",
        files={"files": ("CSE234002_datascience.pdf", pdf_bytes, "application/pdf")},
        data={"engine": "vlm", "mode": "hybrid", "skip_cover_page": "true"},
    )
    assert resp.status_code == 200
    created = resp.json()
    assert len(created) == 1
    sub_id = created[0]["submission_id"]
    assert created[0]["roll_number"] == "CSE234002"

    # Wait briefly for TestClient background task completion
    detail = None
    for _ in range(25):
        r = client.get(f"/api/submissions/{sub_id}")
        assert r.status_code == 200
        detail = r.json()
        if detail["submission"]["status"] in {"ocr_completed", "completed"}:
            break
        time.sleep(0.1)

    assert detail is not None
    assert detail["submission"]["status"] == "ocr_completed"
    assert len(detail["page_image_urls"]) == 1
    assert "| 1 - 5 | 3 | 20 | 60 |" in detail["clean_markdown"]

    # Page scan image endpoint
    page_resp = client.get(detail["page_image_urls"][0])
    assert page_resp.status_code == 200
    assert page_resp.headers["content-type"].startswith("image/png")

    # Markdown export endpoints
    md_clean = client.get(f"/api/submissions/{sub_id}/export-md?variant=clean")
    assert md_clean.status_code == 200
    assert "Shortcut" not in md_clean.text

    md_ann = client.get(f"/api/submissions/{sub_id}/export-md?variant=annotated")
    assert md_ann.status_code == 200
    assert "~~Shortcut~~" in md_ann.text

    # Edit markdown & re-export PDF
    upd = client.put(
        f"/api/submissions/{sub_id}/markdown",
        json={"clean_markdown": "# Edited Q1\nMean is 11.53.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"},
    )
    assert upd.status_code == 200

    pdf_resp = client.get(f"/api/submissions/{sub_id}/export-pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    with pymupdf.open(stream=pdf_resp.content, filetype="pdf") as rendered:
        assert "Edited Q1" in rendered[0].get_text()
