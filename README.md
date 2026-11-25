# Siyahi — Pen-to-Print & Auditable Handwritten Exam Grading System

A **Pen-to-Print** handwritten script converter (`.md` and typeset `.pdf`) paired with a **pluggable, auditable AI rubric evaluation desk** built with Next.js, FastAPI, SQLite, and Modal.com serverless L4 GPUs.

## Core Architecture & Non-Negotiable Rules
1. **Pen-to-Print Core First:** 300 DPI PyMuPDF rasterization, dual-page spread splitting, deskewing, LAB illumination leveling, `PP-DocLayoutV3` layout detection, and `Qwen/Qwen3.5-9B` transcription into clean/annotated Markdown (`.md`) and offline typeset PDF (`.pdf`).
2. **Separation Rule:** The OCR worker (`modal_worker/ocr_app.py`) never receives Question Papers or Model Answers (`OCRRequest` enforces `extra="forbid"`).
3. **Local PII Anonymization:** Filenames (`<roll>_<subject>.pdf`) and Page-1 student detail cover sheets (`SKIP_COVER_PAGE=true`) are stripped locally before anonymized images leave your machine.
4. **Pluggable Variable AI Grader (`backend/grader_provider.py`):** Swap between `gemini` (`google-genai`, default `gemini-3-flash-preview`), `openai_compatible` (OpenAI / OpenRouter / Groq / local vLLM), or `mock`.
5. **Deterministic Verification & Uncertainty Routing (`backend/evaluator.py`):** Strips `[struck: ...]` spans, verifies verbatim `student_quote` overlap ($\ge 85\%$) and sums points in Python, computes Mark Spread ($\Delta \hat{y}$) across `[unclear: a/b]` variants, and flags ambiguous/diagram/short-answer partial-credit questions for human review.

## Quick Start (Local)

### 1. Backend (FastAPI)
```powershell
cd C:\seven\works\automated-exam-grader
.\.venv\Scripts\uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend (Next.js Dashboard)
```powershell
cd C:\seven\works\automated-exam-grader\frontend
npm run dev
```
Open `http://localhost:3000`:
- `/upload` — Upload handwritten PDFs/images, download `.md` / `.pdf`
- `/review/[submissionId]` — 3-pane Scan Viewer, `[struck]`/`[unclear]` Transcript Editor & Override Desk
- `/setup` — Draft & lock exam rubrics

### 3. Modal Serverless OCR Worker (Auto-Off in 90s)
- App: `exam-grader-ocr` (`min_containers=0`, `max_containers=1`, `scaledown_window=90`)
- Redeploy if modified: `modal deploy modal_worker/ocr_app.py`
- Offline development without GPU spend: set `MOCK_MODAL=true` in `.env`.

### 4. Tests & Research Harness
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```
- Research suite: `research/dataset_split.py`, `research/metrics.py`, `research/robustness.py`, `research/run_phase2_dev.py`, `research/run_phase4_heldout.py`.
