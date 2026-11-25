"""Pluggable LLM grader providers (Gemini, OpenAI-compatible, and offline Mock)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.config import Settings
from backend.database import Database
from shared.schemas import CriterionEvaluation, ExamRubric, QuestionRubric, RubricCriterion


class _LLMGradeOutput(BaseModel):
    criteria: list[CriterionEvaluation] = Field(default_factory=list)


class GraderProvider(ABC):
    """Abstract interface allowing any LLM backend to serve as the rubric grader."""

    provider_name: str = "base"

    @abstractmethod
    async def draft_rubric(
        self,
        exam_id: str,
        subject: str,
        title: str,
        question_paper_text: str,
        model_answer_text: str,
    ) -> ExamRubric:
        """Convert question paper + model answer text into a structured ExamRubric."""

    @abstractmethod
    async def grade_question(
        self,
        question_rubric: QuestionRubric,
        clean_active_text: str,
    ) -> list[CriterionEvaluation]:
        """Grade clean active student text strictly at T=0.0 per rubric criterion."""


def _make_cache_key(model_name: str, question_rubric: QuestionRubric, clean_active_text: str) -> str:
    payload = json.dumps(
        {
            "model": model_name,
            "rubric": question_rubric.model_dump(),
            "text": clean_active_text.strip(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _grading_prompt(question_rubric: QuestionRubric, clean_active_text: str) -> str:
    criteria_json = json.dumps([c.model_dump() for c in question_rubric.criteria], indent=2)
    return (
        "You are a strict, fair university exam rubric evaluator.\n"
        "Evaluate ONLY the student's active text below against each atomic criterion.\n"
        "Rules:\n"
        "1. Award points between 0 and criterion.max_points.\n"
        "2. For every criterion with awarded_points > 0, provide an EXACT verbatim `student_quote` "
        "copied directly from the student's active text.\n"
        "3. Do NOT invent or assume missing steps.\n\n"
        f"Question {question_rubric.question_no} ({question_rubric.max_marks} marks): "
        f"{question_rubric.question_text}\n\n"
        f"Rubric Criteria JSON:\n{criteria_json}\n\n"
        f"Student Clean Active Text:\n\"\"\"\n{clean_active_text}\n\"\"\"\n\n"
        'Return JSON matching {"criteria": [{"criterion_id": str, "max_points": float, '
        '"awarded_points": float, "student_quote": str|null, "quote_verified": false, "reason": str}]}.'
    )


def _draft_rubric_prompt(
    exam_id: str,
    subject: str,
    title: str,
    question_paper_text: str,
    model_answer_text: str,
) -> str:
    return (
        "Extract a structured grading rubric JSON from the Question Paper and Model Answer.\n"
        f"Use exam_id='{exam_id}', subject='{subject}', title='{title}', is_locked=false.\n"
        "Break each question into atomic RubricCriterion objects with expected_keywords, "
        "accepted_alternatives, partial_credit_rule, and requires_diagram.\n\n"
        f"QUESTION PAPER:\n{question_paper_text[:12000]}\n\n"
        f"MODEL ANSWER:\n{model_answer_text[:12000]}"
    )


class GeminiGraderProvider(GraderProvider):
    """Google Gemini API provider using google-genai with rate-limit backoff & caching."""

    provider_name = "gemini"

    def __init__(self, settings: Settings, db: Optional[Database] = None) -> None:
        self.settings = settings
        self.db = db
        self._last_call_ts = 0.0

    async def _throttle(self) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()
        elapsed = now - self._last_call_ts
        delay = self.settings.gemini_min_delay_sec - elapsed
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_call_ts = loop.time()

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2.0, min=2.0, max=24.0),
        reraise=True,
    )
    def _call_sync(self, prompt: str, response_schema: Any) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.settings.gemini_api_key)
        resp = client.models.generate_content(
            model=self.settings.grader_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )
        return resp.text or "{}"

    async def draft_rubric(
        self,
        exam_id: str,
        subject: str,
        title: str,
        question_paper_text: str,
        model_answer_text: str,
    ) -> ExamRubric:
        await self._throttle()
        prompt = _draft_rubric_prompt(exam_id, subject, title, question_paper_text, model_answer_text)
        raw = await asyncio.to_thread(self._call_sync, prompt, ExamRubric)
        return ExamRubric.model_validate_json(raw)

    async def grade_question(
        self,
        question_rubric: QuestionRubric,
        clean_active_text: str,
    ) -> list[CriterionEvaluation]:
        cache_key = _make_cache_key(self.settings.grader_model, question_rubric, clean_active_text)
        if self.db:
            cached = self.db.get_cached_grader_response(cache_key)
            if cached:
                return _LLMGradeOutput.model_validate_json(cached).criteria

        await self._throttle()
        prompt = _grading_prompt(question_rubric, clean_active_text)
        raw = await asyncio.to_thread(self._call_sync, prompt, _LLMGradeOutput)
        parsed = _LLMGradeOutput.model_validate_json(raw)
        if self.db:
            self.db.set_cached_grader_response(cache_key, self.settings.grader_model, parsed.model_dump_json())
        return parsed.criteria


class OpenAICompatibleGraderProvider(GraderProvider):
    """Generic OpenAI-compatible provider (OpenAI, OpenRouter, Groq, Ollama, vLLM)."""

    provider_name = "openai_compatible"

    def __init__(self, settings: Settings, db: Optional[Database] = None) -> None:
        self.settings = settings
        self.db = db

    async def _chat_json(self, prompt: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=self.settings.gemini_api_key or "EMPTY",
            base_url=self.settings.grader_base_url or None,
        )
        resp = await client.chat.completions.create(
            model=self.settings.grader_model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or "{}"

    async def draft_rubric(
        self,
        exam_id: str,
        subject: str,
        title: str,
        question_paper_text: str,
        model_answer_text: str,
    ) -> ExamRubric:
        prompt = _draft_rubric_prompt(exam_id, subject, title, question_paper_text, model_answer_text)
        raw = await self._chat_json(prompt)
        return ExamRubric.model_validate_json(raw)

    async def grade_question(
        self,
        question_rubric: QuestionRubric,
        clean_active_text: str,
    ) -> list[CriterionEvaluation]:
        cache_key = _make_cache_key(self.settings.grader_model, question_rubric, clean_active_text)
        if self.db:
            cached = self.db.get_cached_grader_response(cache_key)
            if cached:
                return _LLMGradeOutput.model_validate_json(cached).criteria

        raw = await self._chat_json(_grading_prompt(question_rubric, clean_active_text))
        parsed = _LLMGradeOutput.model_validate_json(raw)
        if self.db:
            self.db.set_cached_grader_response(cache_key, self.settings.grader_model, parsed.model_dump_json())
        return parsed.criteria


class MockGraderProvider(GraderProvider):
    """Deterministic offline rubric grader for tests and API-free development."""

    provider_name = "mock"

    async def draft_rubric(
        self,
        exam_id: str,
        subject: str,
        title: str,
        question_paper_text: str,
        model_answer_text: str,
    ) -> ExamRubric:
        # Parse simple Q1 / Q2 lines if present, otherwise return a sensible 2-question template
        q_matches = re.findall(r"(?:^|\n)\s*(Q\d+)\s*[:.\-]?\s*(.+)", question_paper_text, re.IGNORECASE)
        questions: list[QuestionRubric] = []
        if q_matches:
            for q_no, q_text in q_matches[:8]:
                q_norm = q_no.upper()
                words = [w.strip(".,:;()").lower() for w in model_answer_text.split() if len(w) > 4][:4]
                questions.append(
                    QuestionRubric(
                        question_no=q_norm,
                        question_text=q_text.strip(),
                        max_marks=5.0,
                        question_type="short_answer",
                        criteria=[
                            RubricCriterion(
                                criterion_id=f"{q_norm}_C1",
                                description=f"Addresses core concept for {q_norm}",
                                max_points=5.0,
                                expected_keywords=words or ["concept"],
                                accepted_alternatives=[],
                                partial_credit_rule="Proportional credit by matched keywords",
                                requires_diagram="diagram" in q_text.lower(),
                            )
                        ],
                    )
                )
        else:
            questions = [
                QuestionRubric(
                    question_no="Q1",
                    question_text=question_paper_text.strip()[:160] or "Question 1",
                    max_marks=5.0,
                    question_type="numerical",
                    criteria=[
                        RubricCriterion(
                            criterion_id="Q1_C1",
                            description="Correct intermediate steps and final value",
                            max_points=5.0,
                            expected_keywords=["mean", "11.53"],
                            accepted_alternatives=["1730/150"],
                            partial_credit_rule="Half credit for partial formula",
                            requires_diagram=False,
                        )
                    ],
                )
            ]

        return ExamRubric(
            exam_id=exam_id,
            subject=subject,
            title=title,
            total_marks=round(sum(q.max_marks for q in questions), 2),
            is_locked=False,
            questions=questions,
        )

    async def grade_question(
        self,
        question_rubric: QuestionRubric,
        clean_active_text: str,
    ) -> list[CriterionEvaluation]:
        lower_text = clean_active_text.lower()
        results: list[CriterionEvaluation] = []
        for crit in question_rubric.criteria:
            candidates = crit.expected_keywords + crit.accepted_alternatives
            if not candidates:
                matched_quote = clean_active_text[:80].strip() or None
                awarded = crit.max_points if matched_quote else 0.0
                results.append(
                    CriterionEvaluation(
                        criterion_id=crit.criterion_id,
                        max_points=crit.max_points,
                        awarded_points=awarded,
                        student_quote=matched_quote,
                        quote_verified=False,
                        reason="Mock evaluation based on non-empty answer." if awarded else "No answer provided.",
                    )
                )
                continue

            hits: list[str] = []
            for kw in candidates:
                if kw.lower() in lower_text:
                    hits.append(kw)

            if not hits:
                results.append(
                    CriterionEvaluation(
                        criterion_id=crit.criterion_id,
                        max_points=crit.max_points,
                        awarded_points=0.0,
                        student_quote=None,
                        quote_verified=False,
                        reason=f"Missing expected concepts: {', '.join(crit.expected_keywords)}",
                    )
                )
            else:
                ratio = min(1.0, len(hits) / max(1, len(crit.expected_keywords)))
                awarded = round(crit.max_points * ratio * 2.0) / 2.0
                # Find verbatim snippet around first matched keyword
                idx = lower_text.find(hits[0].lower())
                start = max(0, idx - 20)
                end = min(len(clean_active_text), idx + len(hits[0]) + 35)
                quote = clean_active_text[start:end].strip()
                results.append(
                    CriterionEvaluation(
                        criterion_id=crit.criterion_id,
                        max_points=crit.max_points,
                        awarded_points=min(crit.max_points, awarded),
                        student_quote=quote,
                        quote_verified=False,
                        reason=f"Matched concepts ({', '.join(hits)}) in active transcript.",
                    )
                )
        return results


def get_grader_provider(settings: Settings, db: Optional[Database] = None) -> GraderProvider:
    """Instantiate the configured variable LLM grader provider."""
    provider = settings.grader_provider.strip().lower()
    if provider == "mock" or (
        provider == "gemini"
        and (
            settings.mock_gemini
            or not settings.gemini_api_key
            or "replace-with" in settings.gemini_api_key
        )
    ):
        return MockGraderProvider()
    if provider == "openai_compatible":
        return OpenAICompatibleGraderProvider(settings, db=db)
    return GeminiGraderProvider(settings, db=db)
