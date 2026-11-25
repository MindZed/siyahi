"""Synthetic perturbation runner measuring Mark Flip Rates under OCR noise."""

from __future__ import annotations

import random
import re
from typing import Sequence

from backend.evaluator import evaluate_question
from backend.grader_provider import GraderProvider
from research.metrics import compute_nmae_percent
from shared.schemas import QuestionRubric

NEGATION_WORDS = ("not", "never", "cannot", "can't", "no", "neither")
DIRECTION_SWAPS = {
    "increase": "decrease",
    "increases": "decreases",
    "decrease": "increase",
    "decreases": "increases",
    "higher": "lower",
    "lower": "higher",
}


def inject_character_swaps(text: str, rate: float = 0.02, seed: int = 42) -> str:
    """Randomly swap adjacent alphanumeric characters at `rate`."""
    rng = random.Random(seed)
    chars = list(text)
    n_swaps = max(1, int(len(chars) * rate)) if len(chars) >= 2 else 0
    indices = list(range(len(chars) - 1))
    rng.shuffle(indices)
    swapped = 0
    for idx in indices:
        if swapped >= n_swaps:
            break
        if chars[idx].isalnum() and chars[idx + 1].isalnum():
            chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
            swapped += 1
    return "".join(chars)


def inject_negation_drop(text: str) -> str:
    """Drop negation tokens ('not', 'never', 'cannot', 'no') to simulate silent OCR drops."""
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in NEGATION_WORDS) + r")\b\s*", re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", pattern.sub("", text)).strip()


def inject_numeric_and_directional_flips(text: str) -> str:
    """Flip directional terms and perturb digits to test mark-flip sensitivity."""
    def _swap_dir(m: re.Match[str]) -> str:
        word = m.group(0)
        repl = DIRECTION_SWAPS.get(word.lower(), word)
        return repl.capitalize() if word[0].isupper() else repl

    dir_pat = re.compile(r"\b(" + "|".join(DIRECTION_SWAPS.keys()) + r")\b", re.IGNORECASE)
    out = dir_pat.sub(_swap_dir, text)
    # Perturb digits by +1 mod 10
    out = re.sub(r"\d", lambda m: str((int(m.group(0)) + 1) % 10), out)
    return out


async def measure_perturbation_mark_flips(
    rubrics: Sequence[QuestionRubric],
    verified_transcripts: Sequence[str],
    teacher_scores: Sequence[float],
    provider: GraderProvider,
    flip_threshold_ratio: float = 0.25,
) -> dict[str, dict[str, float]]:
    """Run clean vs perturbed transcripts through the deterministic grader and compute flip rates."""
    clean_scores: list[float] = []
    max_marks = [r.max_marks for r in rubrics]

    for rub, txt in zip(rubrics, verified_transcripts):
        ev = await evaluate_question(rub, txt, [], provider)
        clean_scores.append(ev.ai_awarded_marks)

    perturbations = {
        "char_swap_2pct": [inject_character_swaps(t, 0.02) for t in verified_transcripts],
        "char_swap_5pct": [inject_character_swaps(t, 0.05) for t in verified_transcripts],
        "negation_drop": [inject_negation_drop(t) for t in verified_transcripts],
        "numeric_direction_flip": [inject_numeric_and_directional_flips(t) for t in verified_transcripts],
    }

    baseline_nmae = compute_nmae_percent(clean_scores, teacher_scores, max_marks)
    summary: dict[str, dict[str, float]] = {"baseline": {"nmae": baseline_nmae, "mark_flip_rate": 0.0}}

    for name, mod_texts in perturbations.items():
        p_scores: list[float] = []
        flips = 0
        for rub, clean_y, mod_txt in zip(rubrics, clean_scores, mod_texts):
            ev = await evaluate_question(rub, mod_txt, [], provider)
            p_scores.append(ev.ai_awarded_marks)
            if abs(ev.ai_awarded_marks - clean_y) >= rub.max_marks * flip_threshold_ratio:
                flips += 1
        nmae = compute_nmae_percent(p_scores, teacher_scores, max_marks)
        summary[name] = {
            "nmae": nmae,
            "delta_nmae": round(nmae - baseline_nmae, 4),
            "mark_flip_rate": round(100.0 * flips / max(1, len(rubrics)), 2),
        }

    return summary
