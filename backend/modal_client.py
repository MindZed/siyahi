"""Async HTTP client for Modal OCR endpoints with Rule-1 separation and MOCK_MODAL support."""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Literal

import httpx
from PIL import Image
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import Settings
from shared.schemas import (
    LayoutRegion,
    OCRDocumentResponse,
    OCRPageImage,
    OCRRequest,
    PageOCR,
    PreprocessedPage,
    UnclearSpan,
)


def _encode_image_file(path: str | Path) -> tuple[str, int, int]:
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        w, h = rgb.size
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=90, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii"), w, h


def _crop_region_b64(path: str | Path, bbox: list[int]) -> str:
    with Image.open(path) as img:
        x1, y1, x2, y2 = bbox
        crop = img.crop((x1, y1, x2, y2)).convert("RGB")
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_ocr_request(
    submission_id: str,
    pages: list[PreprocessedPage],
    mode: Literal["hybrid", "strict_regions", "whole_page"] = "hybrid",
    enable_sensitivity_sampling: bool = False,
    k_samples: int = 3,
) -> OCRRequest:
    """Build strict Rule-1 OCR payload containing ONLY anonymized page images."""
    encoded_pages: list[OCRPageImage] = []
    for p in pages:
        b64, w, h = _encode_image_file(p.image_path)
        encoded_pages.append(
            OCRPageImage(
                page_number=p.page_number,
                width=w,
                height=h,
                image_base64=b64,
            )
        )
    return OCRRequest(
        submission_id=submission_id,
        pages=encoded_pages,
        mode=mode,
        enable_sensitivity_sampling=enable_sensitivity_sampling,
        k_samples=k_samples,
    )


def _build_mock_ocr_response(
    submission_id: str,
    pages: list[PreprocessedPage],
    engine: str,
) -> OCRDocumentResponse:
    """Deterministic offline OCR fixture exercising tables, math, tags, and crops."""
    start = time.perf_counter()
    page_outputs: list[PageOCR] = []

    for idx, p in enumerate(pages, start=1):
        w, h = p.width, p.height
        if idx == 1:
            raw_md = (
                "## Q1\n"
                "In order to make a class continuous, subtract 0.5 from lower limit and add 0.5 to upper limit.\n\n"
                "| Class | Class Mark ($x_i$) | $f_i$ | $f_i x_i$ |\n"
                "| --- | --- | --- | --- |\n"
                "| 1 - 5 | 3 | 20 | 60 |\n"
                "| 6 - 10 | 8 | 50 | 400 |\n"
                "| 11 - 15 | 13 | 46 | 598 |\n\n"
                "Simple Mean ([struck: Shortcut] Direct Method):\n\n"
                "$$\\text{Mean}(\\bar{x}) = \\frac{\\sum f_i x_i}{\\sum f_i} = \\frac{1730}{150} = [unclear: 11.53/11.58]$$\n"
            )
            clean_md = (
                "## Q1\n"
                "In order to make a class continuous, subtract 0.5 from lower limit and add 0.5 to upper limit.\n\n"
                "| Class | Class Mark ($x_i$) | $f_i$ | $f_i x_i$ |\n"
                "| --- | --- | --- | --- |\n"
                "| 1 - 5 | 3 | 20 | 60 |\n"
                "| 6 - 10 | 8 | 50 | 400 |\n"
                "| 11 - 15 | 13 | 46 | 598 |\n\n"
                "Simple Mean ( Direct Method):\n\n"
                "$$\\text{Mean}(\\bar{x}) = \\frac{\\sum f_i x_i}{\\sum f_i} = \\frac{1730}{150} = 11.53$$"
            )
            table_bbox = [int(w * 0.08), int(h * 0.08), int(w * 0.92), int(h * 0.48)]
            text_bbox = [int(w * 0.08), int(h * 0.50), int(w * 0.92), int(h * 0.92)]
            regions = [
                LayoutRegion(
                    region_id=f"p{idx}_r1",
                    label="table",
                    confidence=0.94,
                    bbox=table_bbox,
                    raw_text="| Class | Class Mark ($x_i$) | $f_i$ | $f_i x_i$ |",
                    clean_active_text="| Class | Class Mark ($x_i$) | $f_i$ | $f_i x_i$ |",
                    crop_base64=_crop_region_b64(p.image_path, table_bbox),
                ),
                LayoutRegion(
                    region_id=f"p{idx}_r2",
                    label="text",
                    confidence=0.91,
                    bbox=text_bbox,
                    raw_text=raw_md,
                    clean_active_text=clean_md,
                    unclear_spans=[
                        UnclearSpan(raw_tag="[unclear: 11.53/11.58]", alternatives=["11.53", "11.58"])
                    ],
                    struck_spans=["Shortcut"],
                ),
            ]
        else:
            diag_bbox = [int(w * 0.12), int(h * 0.12), int(w * 0.88), int(h * 0.45)]
            raw_md = (
                f"## Q{idx}\n"
                f"Divide and Conquer breaks a problem into subproblems.\n\n"
                f"[diagram: Tree splitting P into SP1 and SP2, each into SSP1 and SSP2]\n\n"
                f"Time complexity: $T(n) = 2T(n/2) + n = O(n \\log n)$.\n"
            )
            clean_md = raw_md
            regions = [
                LayoutRegion(
                    region_id=f"p{idx}_r1",
                    label="diagram",
                    confidence=0.89,
                    bbox=diag_bbox,
                    raw_text="[diagram: Tree splitting P into SP1 and SP2, each into SSP1 and SSP2]",
                    clean_active_text="[diagram: Tree splitting P into SP1 and SP2, each into SSP1 and SSP2]",
                    crop_base64=_crop_region_b64(p.image_path, diag_bbox),
                ),
                LayoutRegion(
                    region_id=f"p{idx}_r2",
                    label="text",
                    confidence=0.90,
                    bbox=[int(w * 0.08), int(h * 0.48), int(w * 0.92), int(h * 0.90)],
                    raw_text=raw_md,
                    clean_active_text=clean_md,
                ),
            ]

        page_outputs.append(
            PageOCR(
                page_number=idx,
                width=w,
                height=h,
                full_markdown=raw_md,
                regions=regions,
            )
        )

    return OCRDocumentResponse(
        submission_id=submission_id,
        engine_used=f"mock-{engine}",
        processing_time_sec=round(time.perf_counter() - start, 4),
        pages=page_outputs,
    )


class ModalOCRClient:
    """Async client calling Modal OCR microservices or local mock fixture."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=15),
        reraise=True,
    )
    async def _post_ocr(self, url: str, request_payload: OCRRequest) -> OCRDocumentResponse:
        headers = {
            "Authorization": f"Bearer {self.settings.modal_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=480.0, follow_redirects=True) as client:
            resp = await client.post(url, json=request_payload.model_dump(), headers=headers)
            if resp.status_code >= 500 or resp.status_code == 429:
                resp.raise_for_status()
            resp.raise_for_status()
            return OCRDocumentResponse.model_validate(resp.json())

    async def transcribe(
        self,
        submission_id: str,
        pages: list[PreprocessedPage],
        engine: Literal["vlm", "paddle_trocr"] = "vlm",
        mode: Literal["hybrid", "strict_regions", "whole_page"] = "hybrid",
        enable_sensitivity_sampling: bool = False,
        k_samples: int = 3,
    ) -> OCRDocumentResponse:
        """Send anonymized page images to Modal (or local mock if MOCK_MODAL=true)."""
        if self.settings.mock_modal:
            return _build_mock_ocr_response(submission_id, pages, engine)

        url = (
            self.settings.modal_ocr_baseline_url
            if engine == "paddle_trocr"
            else self.settings.modal_ocr_vlm_url
        )
        if not url or "<your-workspace>" in url:
            raise ValueError(f"Modal endpoint URL for engine='{engine}' is not configured in .env")

        ocr_req = build_ocr_request(
            submission_id=submission_id,
            pages=pages,
            mode=mode,
            enable_sensitivity_sampling=enable_sensitivity_sampling,
            k_samples=k_samples,
        )
        return await self._post_ocr(url, ocr_req)
