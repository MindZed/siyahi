"""Isolated Modal baseline worker (Thesis Arm A): PaddleOCR line boxes + TrOCR handwritten."""

from __future__ import annotations

import base64
import io
import os
import time
from typing import Any

import modal

try:
    from fastapi import Header, HTTPException
except ImportError:  # pragma: no cover
    def Header(default: Any = None) -> Any:  # type: ignore[misc]
        return default

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)

APP_NAME = "exam-grader-ocr-baseline"
VOLUME_NAME = "exam-grader-weights"
SECRET_NAME = "exam-grader-secrets"

baseline_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("libgl1", "libglib2.0-0", "libgomp1")
    .pip_install(
        "paddlepaddle>=2.6.0",
        "paddleocr>=2.8.0",
        "transformers>=4.46.0",
        "torch>=2.4.0",
        "torchvision",
        "pillow>=10.4.0",
        "numpy<2.0.0",
        "fastapi[standard]>=0.115.0",
        "pydantic>=2.7.0",
    )
)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)


@app.cls(
    image=baseline_image,
    gpu="L4",
    min_containers=0,
    max_containers=1,
    scaledown_window=90,
    timeout=300,
    volumes={"/root/.cache/huggingface": volume},
    secrets=[modal.Secret.from_name(SECRET_NAME)],
)
class BaselineOCRService:
    """Thesis Arm A baseline: PaddleOCR line detector + TrOCR-large-handwritten."""

    @modal.enter()
    def load_models(self) -> None:
        from paddleocr import PaddleOCR
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        self.detector = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
        trocr_id = "microsoft/trocr-large-handwritten"
        self.processor = TrOCRProcessor.from_pretrained(trocr_id)
        self.trocr = VisionEncoderDecoderModel.from_pretrained(trocr_id).to("cuda")
        self.trocr.eval()

    @modal.fastapi_endpoint(method="POST")
    def transcribe_paddle_trocr(
        self,
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        import numpy as np
        import torch
        from PIL import Image

        expected_key = os.environ.get("MODAL_API_KEY", "")
        token = (authorization or "").replace("Bearer ", "").strip()
        if not expected_key or token != expected_key:
            raise HTTPException(status_code=401, detail="Invalid or missing Bearer token.")

        start = time.perf_counter()
        submission_id = str(payload["submission_id"])
        pages_out: list[dict[str, Any]] = []

        for page_item in payload.get("pages", []):
            page_num = int(page_item["page_number"])
            raw_bytes = base64.b64decode(page_item["image_base64"])
            pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            w, h = pil_img.size
            img_np = np.array(pil_img)

            det_res = self.detector.ocr(img_np, rec=False, cls=False)
            boxes = det_res[0] if det_res and det_res[0] else []

            # Sort detected lines top-to-bottom, left-to-right
            normalized_boxes: list[tuple[int, int, int, int]] = []
            for poly in boxes:
                xs = [int(pt[0]) for pt in poly]
                ys = [int(pt[1]) for pt in poly]
                x1, y1, x2, y2 = max(0, min(xs) - 4), max(0, min(ys) - 4), min(w, max(xs) + 4), min(h, max(ys) + 4)
                if x2 > x1 + 4 and y2 > y1 + 4:
                    normalized_boxes.append((x1, y1, x2, y2))
            normalized_boxes.sort(key=lambda b: (b[1] // 24, b[0]))

            regions: list[dict[str, Any]] = []
            lines: list[str] = []
            for idx, (x1, y1, x2, y2) in enumerate(normalized_boxes, start=1):
                line_crop = pil_img.crop((x1, y1, x2, y2))
                pixel_values = self.processor(images=line_crop, return_tensors="pt").pixel_values.to("cuda")
                with torch.no_grad():
                    generated_ids = self.trocr.generate(pixel_values, max_new_tokens=96)
                text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
                if text:
                    lines.append(text)
                regions.append(
                    {
                        "region_id": f"p{page_num}_r{idx}",
                        "label": "text",
                        "confidence": 0.85,
                        "bbox": [x1, y1, x2, y2],
                        "raw_text": text,
                        "clean_active_text": text,
                        "unclear_spans": [],
                        "struck_spans": [],
                        "crop_base64": None,
                    }
                )

            pages_out.append(
                {
                    "page_number": page_num,
                    "width": w,
                    "height": h,
                    "full_markdown": "\n".join(lines),
                    "regions": regions,
                }
            )

        return {
            "submission_id": submission_id,
            "engine_used": "PaddleOCR+TrOCR-large",
            "processing_time_sec": round(time.perf_counter() - start, 3),
            "pages": pages_out,
        }
