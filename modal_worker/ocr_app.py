"""Modal.com serverless OCR worker: PP-DocLayoutV3 (CPU) + Qwen/Qwen3.5-9B (vLLM L4).

Cost & Isolation Safeguards:
- Dedicated App/Volume/Secret names so other Modal apps are untouched.
- min_containers=0, max_containers=1, scaledown_window=90 (1.5-min auto-off).
- Memory/GPU snapshot enabled for fast cold wakeups after auto-off.
- Enforces Separation Rule: never receives question papers or rubrics.
"""

from __future__ import annotations

import base64
import io
import os
import re
import time
from typing import Any

import modal

try:
    from fastapi import Header, HTTPException
except ImportError:  # pragma: no cover - local static inspection fallback
    def Header(default: Any = None) -> Any:  # type: ignore[misc]
        return default

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: str) -> None:
            super().__init__(detail)

APP_NAME = "exam-grader-ocr"
VOLUME_NAME = "exam-grader-weights"
SECRET_NAME = "exam-grader-secrets"

STRUCK_PATTERN = re.compile(r"\[struck:\s*(.*?)\]", re.IGNORECASE | re.DOTALL)
UNCLEAR_PATTERN = re.compile(r"\[unclear:\s*([^/\]]+?)/([^\]]+?)\]", re.IGNORECASE)

# Map PP-DocLayoutV3's 25 layout classes to canonical pipeline categories.
LAYOUT_CATEGORY_MAP = {
    "text": "text",
    "content": "text",
    "abstract": "text",
    "aside_text": "text",
    "reference": "text",
    "reference_content": "text",
    "vertical_text": "text",
    "footnote": "text",
    "vision_footnote": "text",
    "header": "text",
    "footer": "text",
    "number": "text",
    "doc_title": "title",
    "paragraph_title": "title",
    "figure_title": "title",
    "display_formula": "formula",
    "inline_formula": "formula",
    "formula_number": "formula",
    "algorithm": "text",
    "table": "table",
    "image": "diagram",
    "chart": "diagram",
    "header_image": "diagram",
    "footer_image": "diagram",
    "seal": "diagram",
}

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm==0.34.0",
        "transformers>=5.16.1,<5.23.0",
        "pillow>=10.4.0",
        "fastapi[standard]>=0.115.0",
        "pydantic>=2.7.0",
        "accelerate",
        "qwen-vl-utils",
        "hf-transfer",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_ENABLE_V1_MULTIPROCESSING": "0"})
    .add_local_python_source("modal_worker")
)

volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)


def _strip_struck_and_extract_tags(raw_text: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Remove [struck: ...] spans and parse [unclear: a/b] alternatives."""
    struck_spans = [m.group(1).strip() for m in STRUCK_PATTERN.finditer(raw_text) if m.group(1).strip()]
    without_struck = STRUCK_PATTERN.sub("", raw_text)

    unclear_spans: list[dict[str, Any]] = []
    for m in UNCLEAR_PATTERN.finditer(without_struck):
        alt1 = m.group(1).strip()
        alt2 = m.group(2).strip()
        unclear_spans.append({"raw_tag": m.group(0), "alternatives": [alt1, alt2]})

    clean_text = UNCLEAR_PATTERN.sub(lambda m: m.group(1).strip(), without_struck)
    clean_text = re.sub(r"[ \t]{2,}", " ", clean_text)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
    return clean_text, struck_spans, unclear_spans


def _pil_to_base64_png(pil_img: Any) -> str:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _resize_for_vlm(pil_img: Any, max_long_edge: int = 1280) -> Any:
    w, h = pil_img.size
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return pil_img
    scale = max_long_edge / float(long_edge)
    return pil_img.resize((max(1, int(w * scale)), max(1, int(h * scale))))


@app.cls(
    image=image,
    gpu="L40S",
    min_containers=0,
    max_containers=1,
    scaledown_window=90,
    timeout=300,
    startup_timeout=300,
    volumes={"/root/.cache/huggingface": volume},
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
class OCRService:
    """Two-stage layout + VLM handwriting OCR service."""

    @modal.enter(snap=True)
    def load_models(self) -> None:
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        # Run vLLM engine in-process cleanly for Modal serverless containers
        os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"

        self.layout_device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[OCRService] Loading PP-DocLayoutV3 on {self.layout_device}...")
        layout_id = "PaddlePaddle/PP-DocLayoutV3_safetensors"
        self.layout_processor = AutoImageProcessor.from_pretrained(layout_id)
        self.layout_model = AutoModelForObjectDetection.from_pretrained(layout_id).to(
            self.layout_device
        )
        self.layout_model.eval()

        vlm_id = os.environ.get("VLM_MODEL_ID", "Qwen/Qwen3.5-9B")
        self.model_id = vlm_id
        self.backend_engine = "vllm"
        self.llm = None
        self.hf_processor = None
        self.hf_model = None

        dummy = Image.new("RGB", (224, 224), "white")

        try:
            from vllm import LLM

            quantization = os.environ.get("VLM_QUANTIZATION", "fp8_per_tensor").strip() or None
            llm_kwargs: dict[str, Any] = {
                "model": vlm_id,
                "trust_remote_code": True,
                "max_model_len": 8192,
                "gpu_memory_utilization": 0.88,
                "enable_prefix_caching": True,
                "enforce_eager": False,
                "limit_mm_per_prompt": {"image": 1, "video": 0},
                "skip_mm_profiling": True,
                "mm_processor_kwargs": {"min_pixels": 200704, "max_pixels": 1003520},
                "max_num_seqs": 2,
            }
            if quantization and quantization.lower() != "none":
                llm_kwargs["quantization"] = quantization

            print("[OCRService] Initializing vLLM engine...")
            try:
                self.llm = LLM(**llm_kwargs)
            except Exception:
                llm_kwargs.pop("quantization", None)
                self.llm = LLM(**llm_kwargs)

            print("[OCRService] Running vLLM warmup image check...")
            self._run_vlm(dummy, "Read text.", temperature=0.0, max_tokens=8)
            print("[OCRService] vLLM ready!")
        except Exception as vllm_err:
            import gc
            print(f"[OCRService] vLLM init/image check failed ({vllm_err}); falling back to native transformers BF16.")
            if self.llm is not None:
                try:
                    engine = getattr(self.llm, "llm_engine", None)
                    if engine is not None and hasattr(engine, "engine_core"):
                        engine.engine_core.shutdown()
                except Exception:
                    pass
                del self.llm
                self.llm = None
                gc.collect()
                torch.cuda.empty_cache()

            from transformers import AutoConfig, AutoModelForImageTextToText, AutoProcessor

            self.backend_engine = "transformers"
            self.hf_processor = AutoProcessor.from_pretrained(vlm_id, trust_remote_code=True)
            hf_cfg = AutoConfig.from_pretrained(vlm_id, trust_remote_code=True)
            v_cfg = getattr(hf_cfg, "vision_config", None)
            if v_cfg is not None and not hasattr(v_cfg, "rope_parameters"):
                v_cfg.rope_parameters = {"rope_type": "default", "rope_theta": 10000.0}
            self.hf_model = AutoModelForImageTextToText.from_pretrained(
                vlm_id,
                config=hf_cfg,
                torch_dtype=torch.bfloat16,
                device_map="cuda:0",
                trust_remote_code=True,
            )
            self.hf_model.eval()
            self._run_vlm(dummy, "Read text.", temperature=0.0, max_tokens=8)

    def _run_vlm(
        self,
        pil_img: Any,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        from modal_worker.prompts import VERBATIM_OCR_SYSTEM_PROMPT

        resized = _resize_for_vlm(pil_img)

        if self.backend_engine == "vllm" and self.llm is not None:
            from vllm import SamplingParams

            messages = [
                {"role": "system", "content": VERBATIM_OCR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_pil", "image_pil": resized},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ]
            sampling = SamplingParams(
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=1.0 if temperature == 0.0 else 0.9,
            )
            outputs = self.llm.chat(
                messages=messages,
                sampling_params=sampling,
                chat_template_kwargs={"enable_thinking": False},
                use_tqdm=False,
            )
            return outputs[0].outputs[0].text.strip()

        import torch

        assert self.hf_processor is not None and self.hf_model is not None
        messages = [
            {"role": "system", "content": VERBATIM_OCR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": resized},
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]
        try:
            text_prompt = self.hf_processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            text_prompt = self.hf_processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        inputs = self.hf_processor(
            text=[text_prompt],
            images=[resized],
            padding=True,
            return_tensors="pt",
        )
        inputs = {k: v.to(self.hf_model.device) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_tokens,
            "do_sample": temperature > 0.0,
        }
        if temperature > 0.0:
            gen_kwargs["temperature"] = temperature
            gen_kwargs["top_p"] = 0.9
        with torch.no_grad():
            generated_ids = self.hf_model.generate(**inputs, **gen_kwargs)
        trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
        ]
        decoded = self.hf_processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        # Strip any residual <think>...</think> block if template didn't suppress it
        decoded = re.sub(r"<think>.*?</think>", "", decoded, flags=re.DOTALL).strip()
        return decoded

    def _detect_layout_regions(self, pil_img: Any) -> list[dict[str, Any]]:
        import torch

        inputs = self.layout_processor(images=pil_img, return_tensors="pt")
        inputs = {k: v.to(self.layout_device) for k, v in inputs.items() if isinstance(v, torch.Tensor)}
        with torch.no_grad():
            outputs = self.layout_model(**inputs)

        target_sizes = [pil_img.size[::-1]]
        results = self.layout_processor.post_process_object_detection(
            outputs,
            threshold=0.30,
            target_sizes=target_sizes,
        )
        if not results:
            return []

        result = results[0]
        w, h = pil_img.size
        detections: list[dict[str, Any]] = []
        for idx, (score_t, label_t, box_t) in enumerate(
            zip(result["scores"], result["labels"], result["boxes"])
        ):
            score = float(score_t.item())
            raw_label = str(self.layout_model.config.id2label[int(label_t.item())]).lower()
            canon_label = LAYOUT_CATEGORY_MAP.get(raw_label, "text")
            min_thresh = 0.30 if canon_label in {"diagram", "table", "formula"} else 0.38
            if score < min_thresh:
                continue

            x1, y1, x2, y2 = [int(round(v)) for v in box_t.tolist()]
            x1 = max(0, x1 - 12)
            y1 = max(0, y1 - 12)
            x2 = min(w, x2 + 12)
            y2 = min(h, y2 + 12)
            if x2 <= x1 + 4 or y2 <= y1 + 4:
                continue

            detections.append(
                {
                    "order": idx,
                    "raw_label": raw_label,
                    "label": canon_label,
                    "confidence": round(score, 4),
                    "bbox": [x1, y1, x2, y2],
                }
            )
        return detections

    def _transcribe_page(
        self,
        page_num: int,
        pil_img: Any,
        mode: str,
        enable_sensitivity: bool,
        k_samples: int,
    ) -> dict[str, Any]:
        from modal_worker.prompts import (
            PAGE_TRANSCRIPTION_USER_PROMPT,
            REGION_TRANSCRIPTION_USER_PROMPT,
        )

        w, h = pil_img.size
        t0 = time.perf_counter()
        detections = [] if mode == "whole_page" else self._detect_layout_regions(pil_img)
        t_layout = time.perf_counter() - t0

        regions: list[dict[str, Any]] = []
        full_markdown_parts: list[str] = []

        if mode in {"hybrid", "whole_page"} or not detections:
            # Whole-page pass preserves multi-column context, curly braces, and Pen-to-Print flow
            t1 = time.perf_counter()
            page_raw = self._run_vlm(pil_img, PAGE_TRANSCRIPTION_USER_PROMPT, temperature=0.0, max_tokens=2048)
            t_vlm = time.perf_counter() - t1
            print(f"[OCRService] page={page_num} layout={t_layout:.2f}s vlm={t_vlm:.2f}s chars={len(page_raw)}")
            page_clean, page_struck, page_unclear = _strip_struck_and_extract_tags(page_raw)

            if not detections:
                regions.append(
                    {
                        "region_id": f"p{page_num}_r1",
                        "label": "text",
                        "confidence": 1.0,
                        "bbox": [0, 0, w, h],
                        "raw_text": page_raw,
                        "clean_active_text": page_clean,
                        "unclear_spans": page_unclear,
                        "struck_spans": page_struck,
                        "crop_base64": None,
                    }
                )
            else:
                for i, det in enumerate(detections, start=1):
                    x1, y1, x2, y2 = det["bbox"]
                    crop = pil_img.crop((x1, y1, x2, y2))
                    crop_b64 = _pil_to_base64_png(crop) if det["label"] in {"diagram", "table"} else None
                    regions.append(
                        {
                            "region_id": f"p{page_num}_r{i}",
                            "label": det["label"],
                            "confidence": det["confidence"],
                            "bbox": det["bbox"],
                            "raw_text": page_raw if i == 1 else "",
                            "clean_active_text": page_clean if i == 1 else "",
                            "unclear_spans": page_unclear if i == 1 else [],
                            "struck_spans": page_struck if i == 1 else [],
                            "crop_base64": crop_b64,
                        }
                    )

            full_markdown = page_raw
        else:
            # Strict region-by-region transcription mode
            for i, det in enumerate(detections, start=1):
                x1, y1, x2, y2 = det["bbox"]
                crop = pil_img.crop((x1, y1, x2, y2))
                crop_b64 = _pil_to_base64_png(crop) if det["label"] in {"diagram", "table"} else None
                prompt = REGION_TRANSCRIPTION_USER_PROMPT.format(label=det["raw_label"])
                r_raw = self._run_vlm(crop, prompt, temperature=0.0, max_tokens=1200)
                r_clean, r_struck, r_unclear = _strip_struck_and_extract_tags(r_raw)

                if enable_sensitivity and r_unclear and k_samples > 1:
                    alt_readings: list[str] = []
                    for _ in range(k_samples):
                        sample = self._run_vlm(crop, prompt, temperature=0.35, max_tokens=1200)
                        s_clean, _, _ = _strip_struck_and_extract_tags(sample)
                        if s_clean and s_clean not in alt_readings:
                            alt_readings.append(s_clean)
                    if len(alt_readings) > 1:
                        r_unclear.append(
                            {
                                "raw_tag": f"[unclear: {'/'.join(alt_readings[:2])}]",
                                "alternatives": alt_readings[:3],
                            }
                        )

                regions.append(
                    {
                        "region_id": f"p{page_num}_r{i}",
                        "label": det["label"],
                        "confidence": det["confidence"],
                        "bbox": det["bbox"],
                        "raw_text": r_raw,
                        "clean_active_text": r_clean,
                        "unclear_spans": r_unclear,
                        "struck_spans": r_struck,
                        "crop_base64": crop_b64,
                    }
                )
                if r_raw:
                    full_markdown_parts.append(r_raw)

            full_markdown = "\n\n".join(full_markdown_parts)

        return {
            "page_number": page_num,
            "width": w,
            "height": h,
            "full_markdown": full_markdown,
            "regions": regions,
        }

    def _process_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        from PIL import Image

        start = time.perf_counter()
        submission_id = str(payload["submission_id"])
        mode = str(payload.get("mode", "hybrid"))
        enable_sensitivity = bool(payload.get("enable_sensitivity_sampling", False))
        k_samples = int(payload.get("k_samples", 3))

        pages_out: list[dict[str, Any]] = []
        for page_item in payload.get("pages", []):
            raw_bytes = base64.b64decode(page_item["image_base64"])
            pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            pages_out.append(
                self._transcribe_page(
                    page_num=int(page_item["page_number"]),
                    pil_img=pil_img,
                    mode=mode,
                    enable_sensitivity=enable_sensitivity,
                    k_samples=k_samples,
                )
            )

        return {
            "submission_id": submission_id,
            "engine_used": f"PP-DocLayoutV3+{self.model_id}",
            "processing_time_sec": round(time.perf_counter() - start, 3),
            "pages": pages_out,
        }

    @modal.method()
    def transcribe_rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        """RPC entrypoint for direct Modal client / smoke tests."""
        return self._process_payload(payload)

    @modal.fastapi_endpoint(method="POST")
    def transcribe_vlm(
        self,
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Authenticated HTTP endpoint receiving anonymized page PNGs only."""
        expected_key = os.environ.get("MODAL_API_KEY", "")
        token = (authorization or "").replace("Bearer ", "").strip()
        if not expected_key or token != expected_key:
            raise HTTPException(status_code=401, detail="Invalid or missing Bearer token.")

        forbidden = {"rubric", "question_paper", "model_answer", "exam_id", "questions"}
        if any(k in payload for k in forbidden):
            raise HTTPException(status_code=400, detail="Separation Rule violation: OCR endpoint accepts images only.")

        return self._process_payload(payload)


@app.local_entrypoint()
def smoke_test(image_path: str = "data/samples/stats_sample_1.jpg") -> None:
    """Stream live Modal container logs while testing a single handwritten image."""
    from pathlib import Path
    from PIL import Image

    raw_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    with Image.open(image_path) as im:
        w, h = im.size
    payload = {
        "submission_id": "SUB_SMOKE",
        "mode": "hybrid",
        "pages": [{"page_number": 1, "width": w, "height": h, "image_base64": raw_b64}],
    }
    res = OCRService().transcribe_rpc.remote(payload)
    print("Engine:", res["engine_used"], "Time:", res["processing_time_sec"])
    print(res["pages"][0]["full_markdown"])
