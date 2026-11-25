"""Pen-to-Print Markdown (.md) and offline typeset PDF (.pdf) renderer."""

from __future__ import annotations

import base64
import html
import io
import re
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from shared.schemas import OCRDocumentResponse

STRUCK_PATTERN = re.compile(r"\[struck:\s*(.*?)\]", re.IGNORECASE | re.DOTALL)
UNCLEAR_PATTERN = re.compile(r"\[unclear:\s*([^/\]]+?)/([^\]]+?)\]", re.IGNORECASE)
DIAGRAM_TAG_PATTERN = re.compile(r"\[diagram:\s*(.*?)\]", re.IGNORECASE | re.DOTALL)
DISPLAY_MATH_RE = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")

LATEX_SYMBOLS = {
    r"\sum": "Σ",
    r"\prod": "Π",
    r"\infty": "∞",
    r"\leq": "≤",
    r"\le": "≤",
    r"\geq": "≥",
    r"\ge": "≥",
    r"\neq": "≠",
    r"\approx": "≈",
    r"\times": "×",
    r"\cdot": "·",
    r"\pm": "±",
    r"\rightarrow": "→",
    r"\to": "→",
    r"\leftarrow": "←",
    r"\Rightarrow": "⇒",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\sigma": "σ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\Delta": "Δ",
    r"\delta": "δ",
    r"\log": "log",
    r"\ln": "ln",
    r"\text": "",
    r"\mathrm": "",
}


def latex_to_readable_text(expr: str) -> str:
    """Convert common LaTeX tokens into clean ReportLab-safe math without missing glyphs."""
    text = expr.strip()
    # Unwrap \text{...} and \mathrm{...} BEFORE \frac so nested braces resolve cleanly
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\mathrm\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\bar\{([A-Za-z0-9])\}", lambda m: f"{m.group(1)}-bar", text)
    for _ in range(3):
        text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1) / (\2)", text)
    for k, v in LATEX_SYMBOLS.items():
        text = text.replace(k, v)
    text = re.sub(r"_\{([^{}]+)\}", r"_\1", text)
    text = re.sub(r"\^\{([^{}]+)\}", r"^\1", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s{2,}", " ", text).strip()


def save_diagram_crops(ocr: OCRDocumentResponse, crops_dir: str | Path) -> dict[str, Path]:
    """Persist cropped diagram/table PNGs from OCRDocumentResponse to disk."""
    out_dir = Path(crops_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    for page in ocr.pages:
        for region in page.regions:
            if region.crop_base64 and region.label in {"diagram", "table"}:
                crop_path = out_dir / f"{region.region_id}.png"
                crop_path.write_bytes(base64.b64decode(region.crop_base64))
                saved[region.region_id] = crop_path
    return saved


def build_markdown_variants(
    ocr: OCRDocumentResponse,
    crops_rel_dir: str = "crops",
) -> tuple[str, str]:
    """Produce (clean_markdown, annotated_markdown) from OCRDocumentResponse."""
    clean_pages: list[str] = []
    annotated_pages: list[str] = []

    for page in ocr.pages:
        raw = page.full_markdown.strip()
        if not raw and page.regions:
            raw = "\n\n".join(r.raw_text for r in page.regions if r.raw_text)

        # Clean Markdown: strip [struck: ...], pick primary [unclear: a/b] reading
        clean = STRUCK_PATTERN.sub("", raw)
        clean = UNCLEAR_PATTERN.sub(lambda m: m.group(1).strip(), clean)
        clean = re.sub(r"[ \t]{2,}", " ", clean)
        clean = re.sub(r"\n{3,}", "\n\n", clean).strip()

        # Annotated Markdown: keep strikethrough as ~~text~~ and retain [unclear: a/b]
        annotated = STRUCK_PATTERN.sub(lambda m: f"~~{m.group(1).strip()}~~", raw)
        annotated = re.sub(r"\n{3,}", "\n\n", annotated).strip()

        # Append inline links for extracted visual diagram crops on this page
        diagram_refs = [
            r for r in page.regions if r.crop_base64 and r.label == "diagram"
        ]
        if diagram_refs:
            links = "\n".join(
                f"![Diagram {r.region_id}]({crops_rel_dir}/{r.region_id}.png)"
                for r in diagram_refs
            )
            clean = f"{clean}\n\n{links}".strip()
            annotated = f"{annotated}\n\n{links}".strip()

        clean_pages.append(clean)
        annotated_pages.append(annotated)

    sep = "\n\n<!-- PAGE_BREAK -->\n\n"
    return sep.join(p for p in clean_pages if p), sep.join(p for p in annotated_pages if p)


def _format_inline_html(line: str) -> str:
    """Convert inline Markdown + math spans to ReportLab-safe Paragraph XML."""
    # Convert math tokens first before HTML escaping
    def _math_repl(match: re.Match[str]) -> str:
        readable = latex_to_readable_text(match.group(1))
        return f"@@MATH_START@@{readable}@@MATH_END@@"

    tmp = DISPLAY_MATH_RE.sub(_math_repl, line)
    tmp = INLINE_MATH_RE.sub(_math_repl, tmp)
    escaped = html.escape(tmp)

    escaped = escaped.replace("@@MATH_START@@", "<i><b>").replace("@@MATH_END@@", "</b></i>")
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    return escaped


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r"^\|?[\s:\-]+\|[\s:\-\|]*$", stripped))


def _parse_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def render_pen_to_print_pdf(
    markdown_text: str,
    output_pdf_path: str | Path,
    title: str = "Pen-to-Print Transcript",
    subtitle: str = "",
    crops_dir: Optional[str | Path] = None,
) -> Path:
    """Render clean Markdown (with tables, code blocks, math, and diagram crops) to A4 PDF."""
    out_path = Path(output_pdf_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, spaceAfter=4
    )
    sub_style = ParagraphStyle(
        "DocSub", parent=styles["Normal"], fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#444444"), spaceAfter=10
    )
    h1_style = ParagraphStyle(
        "H1", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, spaceBefore=10, spaceAfter=4
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=8, spaceAfter=3
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, spaceAfter=4
    )
    math_block_style = ParagraphStyle(
        "MathBlock",
        parent=styles["Normal"],
        fontName="Helvetica-BoldOblique",
        fontSize=10.5,
        leading=15,
        alignment=1,
        spaceBefore=5,
        spaceAfter=6,
    )
    code_style = ParagraphStyle(
        "CodeBlock",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=8.5,
        leading=11.5,
        leftIndent=10,
        backColor=colors.HexColor("#F4F4F5"),
    )
    cell_style = ParagraphStyle(
        "TableCell", parent=styles["Normal"], fontName="Helvetica", fontSize=8.8, leading=11.5
    )

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    usable_w = A4[0] - 36 * mm
    story: list = [Paragraph(html.escape(title), title_style)]
    if subtitle:
        story.append(Paragraph(html.escape(subtitle), sub_style))

    lines = markdown_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            story.append(Spacer(1, 4))
            i += 1
            continue

        if stripped == "<!-- PAGE_BREAK -->":
            story.append(PageBreak())
            i += 1
            continue

        if stripped == "---":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#CBD5E1")))
            story.append(Spacer(1, 6))
            i += 1
            continue

        # Fenced code/pseudocode block
        if stripped.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            story.append(Preformatted("\n".join(code_lines), code_style))
            story.append(Spacer(1, 5))
            continue

        # Display math block $$ ... $$
        if stripped.startswith("$$"):
            math_lines = [stripped[2:]]
            if stripped.endswith("$$") and len(stripped) > 4:
                expr = stripped[2:-2]
                i += 1
            else:
                i += 1
                while i < len(lines) and "$$" not in lines[i]:
                    math_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    math_lines.append(lines[i].replace("$$", ""))
                    i += 1
                expr = " ".join(math_lines)
            story.append(Paragraph(html.escape(latex_to_readable_text(expr)), math_block_style))
            continue

        # Markdown Table
        if "|" in stripped and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            headers = _parse_table_row(stripped)
            i += 2
            rows = [headers]
            while i < len(lines) and "|" in lines[i].strip() and lines[i].strip():
                rows.append(_parse_table_row(lines[i]))
                i += 1
            col_count = max(len(r) for r in rows)
            norm_rows = [
                [Paragraph(_format_inline_html(c), cell_style) for c in (r + [""] * (col_count - len(r)))]
                for r in rows
            ]
            col_w = usable_w / float(max(1, col_count))
            tbl = Table(norm_rows, colWidths=[col_w] * col_count, repeatRows=1)
            tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#94A3B8")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(tbl)
            story.append(Spacer(1, 6))
            continue

        # Embedded Markdown image: ![alt](path)
        img_match = re.match(r"^!\[(.*?)\]\((.*?)\)$", stripped)
        if img_match:
            alt_text, rel_path = img_match.group(1), img_match.group(2)
            resolved = Path(rel_path)
            if not resolved.is_absolute() and crops_dir:
                resolved = Path(crops_dir).parent / rel_path
                if not resolved.exists():
                    resolved = Path(crops_dir) / Path(rel_path).name
            if resolved.exists():
                with PILImage.open(resolved) as pil_im:
                    iw, ih = pil_im.size
                scale = min(usable_w / float(max(1, iw)), (85 * mm) / float(max(1, ih)), 1.0)
                story.append(RLImage(str(resolved), width=iw * scale, height=ih * scale))
                story.append(Paragraph(f"<i>{html.escape(alt_text)}</i>", sub_style))
                story.append(Spacer(1, 5))
            i += 1
            continue

        # Headings
        if stripped.startswith("### "):
            story.append(Paragraph(_format_inline_html(stripped[4:]), h2_style))
        elif stripped.startswith("## "):
            story.append(Paragraph(_format_inline_html(stripped[3:]), h2_style))
        elif stripped.startswith("# "):
            story.append(Paragraph(_format_inline_html(stripped[2:]), h1_style))
        elif stripped.startswith(("- ", "* ")):
            story.append(Paragraph(f"&bull; {_format_inline_html(stripped[2:])}", body_style))
        else:
            story.append(Paragraph(_format_inline_html(stripped), body_style))
        i += 1

    doc.build(story)
    return out_path
