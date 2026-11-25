"""Local PDF/image ingestion, Pen-to-Print cleanup, and Rule-4 PII anonymization."""

import re
import uuid
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pymupdf
from PIL import Image

from shared.schemas import PreprocessedPage, PreprocessResult

SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
FILENAME_PATTERN = re.compile(r"^([A-Za-z0-9-]+)_([A-Za-z0-9_.-]+)$")


def parse_submission_filename(filename: str) -> tuple[str, str]:
    """Extract (roll_number, subject) from '<roll>_<subject>.pdf' locally."""
    stem = Path(filename).stem.strip()
    match = FILENAME_PATTERN.match(stem)
    if match:
        roll_number = match.group(1).strip()
        subject = match.group(2).strip().replace("_", " ")
        return roll_number, subject
    clean_stem = re.sub(r"[^A-Za-z0-9-]+", "_", stem).strip("_") or "UNKNOWN"
    return clean_stem, "general"


def generate_anonymous_submission_id() -> str:
    """Create an opaque submission ID containing zero student PII."""
    return f"SUB_{uuid.uuid4().hex[:8]}"


def _render_source_pages(input_path: Path, dpi: int) -> list[np.ndarray]:
    """Rasterize a PDF at `dpi` or load a single raster image as BGR numpy arrays."""
    suffix = input_path.suffix.lower()
    if suffix in SUPPORTED_IMAGE_EXTS:
        pil_img = Image.open(input_path).convert("RGB")
        return [cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)]

    if suffix != ".pdf":
        raise ValueError(f"Unsupported submission file format: {suffix}")

    zoom = dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    pages: list[np.ndarray] = []
    with pymupdf.open(str(input_path)) as doc:
        if len(doc) == 0:
            raise ValueError("Uploaded PDF has 0 pages.")
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 4:
                arr = arr[:, :, :3]
            pages.append(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
    return pages


def _split_dual_page_spread(image: np.ndarray) -> list[tuple[np.ndarray, bool]]:
    """Split landscape 2-page notebook spreads along the darkest center spine."""
    h, w = image.shape[:2]
    if w <= h * 1.25:
        return [(image, False)]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    x_start = int(w * 0.42)
    x_end = int(w * 0.58)
    center_band = gray[:, x_start:x_end]
    col_means = center_band.mean(axis=0)
    split_x = x_start + int(np.argmin(col_means))

    margin = max(8, int(w * 0.005))
    left = image[:, : max(1, split_x - margin)]
    right = image[:, min(w - 1, split_x + margin) :]
    return [(left, True), (right, True)]


def _trim_dark_borders(image: np.ndarray) -> np.ndarray:
    """Crop scanner/camera dark outer borders without clipping interior handwriting."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    non_black = gray > 28
    row_ratio = non_black.mean(axis=1)
    col_ratio = non_black.mean(axis=0)

    valid_rows = np.where(row_ratio > 0.15)[0]
    valid_cols = np.where(col_ratio > 0.15)[0]
    if len(valid_rows) < 20 or len(valid_cols) < 20:
        return image

    y1 = max(0, int(valid_rows[0]) - 4)
    y2 = min(h, int(valid_rows[-1]) + 5)
    x1 = max(0, int(valid_cols[0]) - 4)
    x2 = min(w, int(valid_cols[-1]) + 5)

    # Guard against over-aggressive cropping on nearly empty pages
    if (y2 - y1) < h * 0.4 or (x2 - x1) < w * 0.4:
        return image
    return image[y1:y2, x1:x2]


def _gentle_deskew(image: np.ndarray, max_angle_deg: float = 10.0) -> np.ndarray:
    """Correct small page skew using dominant horizontal text-line orientation."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=120,
        minLineLength=max(60, image.shape[1] // 8),
        maxLineGap=20,
    )
    if lines is None:
        return image

    angles: list[float] = []
    for line in lines.reshape(-1, 4):
        x1, y1, x2, y2 = line
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 20:
            continue
        angle = float(np.degrees(np.arctan2(dy, dx)))
        if abs(angle) <= max_angle_deg:
            angles.append(angle)

    if len(angles) < 3:
        return image

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.35:
        return image

    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    rot_mat = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    return cv2.warpAffine(
        image,
        rot_mat,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _normalize_illumination(image: np.ndarray) -> np.ndarray:
    """Level uneven paper shadows via LAB CLAHE while keeping soft ink gradients intact."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    l_eq = clahe.apply(l_chan)
    merged = cv2.merge((l_eq, a_chan, b_chan))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def _mask_top_header(image: np.ndarray, mask_pct: float) -> np.ndarray:
    """Optionally mask top header strip in white if student PII sits at top of a page."""
    if mask_pct <= 0.0:
        return image
    masked = image.copy()
    cut_y = int(masked.shape[0] * min(mask_pct, 0.4))
    masked[:cut_y, :] = 255
    return masked


def preprocess_submission(
    input_path: str | Path,
    storage_dir: str | Path,
    submission_id: Optional[str] = None,
    original_filename: Optional[str] = None,
    dpi: int = 300,
    skip_cover_page: bool = True,
    force_skip_single_page: bool = False,
    auto_split_spreads: bool = True,
    header_mask_pct: float = 0.0,
) -> PreprocessResult:
    """Ingest a student PDF/image, strip cover PII locally, clean pages, and save PNGs."""
    src = Path(input_path)
    filename = original_filename or src.name
    roll_number, subject = parse_submission_filename(filename)
    sub_id = submission_id or generate_anonymous_submission_id()

    raw_pages = _render_source_pages(src, dpi=dpi)
    raw_count = len(raw_pages)

    # Rule 4: First page is student details cover sheet only.
    cover_skipped = False
    if skip_cover_page and (raw_count > 1 or force_skip_single_page):
        raw_pages = raw_pages[1:]
        cover_skipped = True

    if not raw_pages:
        raise ValueError("No content pages remain after cover-page PII removal.")

    pages_dir = Path(storage_dir) / sub_id / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    processed_pages: list[PreprocessedPage] = []
    out_idx = 0
    for raw_img in raw_pages:
        trimmed = _trim_dark_borders(raw_img)
        halves = _split_dual_page_spread(trimmed) if auto_split_spreads else [(trimmed, False)]
        for half_img, was_split in halves:
            out_idx += 1
            cleaned = _normalize_illumination(_gentle_deskew(half_img))
            if out_idx == 1 and header_mask_pct > 0.0:
                cleaned = _mask_top_header(cleaned, header_mask_pct)

            out_path = pages_dir / f"page_{out_idx}.png"
            cv2.imwrite(str(out_path), cleaned)
            h, w = cleaned.shape[:2]
            processed_pages.append(
                PreprocessedPage(
                    page_number=out_idx,
                    image_path=str(out_path),
                    width=w,
                    height=h,
                    was_split_from_spread=was_split,
                )
            )

    return PreprocessResult(
        submission_id=sub_id,
        roll_number=roll_number,
        subject=subject,
        original_filename=filename,
        raw_page_count=raw_count,
        cover_page_skipped=cover_skipped,
        pages=processed_pages,
    )
