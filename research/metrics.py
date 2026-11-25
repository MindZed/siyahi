"""Statistical evaluation metrics: NMAE%, script-level bootstrap CIs, QWK, CER/WER, Tag F1."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sklearn.metrics import cohen_kappa_score

STRUCK_PATTERN = re.compile(r"\[struck:\s*(.*?)\]", re.IGNORECASE | re.DOTALL)
UNCLEAR_PATTERN = re.compile(r"\[unclear:\s*([^/\]]+?)/([^\]]+?)\]", re.IGNORECASE)
DIAGRAM_PATTERN = re.compile(r"\[diagram(?::\s*.*?)?\]", re.IGNORECASE | re.DOTALL)


def normalize_active_text(text: str) -> str:
    """Strip [struck: ...] completely and resolve [unclear: a/b] to primary reading `a`."""
    out = STRUCK_PATTERN.sub("", text)
    out = UNCLEAR_PATTERN.sub(lambda m: m.group(1).strip(), out)
    return re.sub(r"\s+", " ", out).strip()


def normalize_literal_text(text: str) -> str:
    """Keep struck-out words (strip only markup brackets) and resolve [unclear: a/b] to `a`."""
    out = STRUCK_PATTERN.sub(lambda m: m.group(1).strip(), text)
    out = UNCLEAR_PATTERN.sub(lambda m: m.group(1).strip(), out)
    return re.sub(r"\s+", " ", out).strip()


def _levenshtein(seq_a: Sequence[str], seq_b: Sequence[str]) -> int:
    m, n = len(seq_a), len(seq_b)
    if m == 0:
        return n
    if n == 0:
        return m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        ai = seq_a[i - 1]
        for j in range(1, n + 1):
            cost = 0 if ai == seq_b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[n]


def compute_cer_wer(pred: str, ref: str) -> tuple[float, float]:
    """Compute (CER, WER) on two already-normalized strings."""
    pred_chars = list(pred)
    ref_chars = list(ref)
    cer = _levenshtein(pred_chars, ref_chars) / float(max(1, len(ref_chars)))

    pred_words = pred.split()
    ref_words = ref.split()
    wer = _levenshtein(pred_words, ref_words) / float(max(1, len(ref_words)))
    return round(cer, 6), round(wer, 6)


def compute_active_and_literal_cer_wer(pred_raw: str, ref_raw: str) -> dict[str, float]:
    """Return Active-Text CER/WER (struck removed) and Literal-Text CER/WER (struck kept)."""
    act_cer, act_wer = compute_cer_wer(
        normalize_active_text(pred_raw), normalize_active_text(ref_raw)
    )
    lit_cer, lit_wer = compute_cer_wer(
        normalize_literal_text(pred_raw), normalize_literal_text(ref_raw)
    )
    return {
        "active_cer": act_cer,
        "active_wer": act_wer,
        "literal_cer": lit_cer,
        "literal_wer": lit_wer,
    }


def compute_tag_f1(
    pred_texts: Sequence[str],
    ref_texts: Sequence[str],
    tag_type: str = "struck",
) -> dict[str, float]:
    """Compute item-level Precision, Recall, and F1 for [struck] or [diagram] tag detection."""
    pattern = STRUCK_PATTERN if tag_type == "struck" else DIAGRAM_PATTERN
    tp = fp = fn = 0
    for p, r in zip(pred_texts, ref_texts):
        p_has = bool(pattern.search(p))
        r_has = bool(pattern.search(r))
        if p_has and r_has:
            tp += 1
        elif p_has and not r_has:
            fp += 1
        elif not p_has and r_has:
            fn += 1

    precision = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
    }


def compute_nmae_percent(
    pred_scores: Sequence[float],
    true_scores: Sequence[float],
    max_marks: Sequence[float],
) -> float:
    """Compute Normalized Mean Absolute Error (%) = (100/n) * sum(|y_hat - y| / M)."""
    if not pred_scores:
        return 0.0
    errors = [
        abs(float(yh) - float(y)) / float(m)
        for yh, y, m in zip(pred_scores, true_scores, max_marks)
        if m > 0
    ]
    if not errors:
        return 0.0
    return round(100.0 * float(np.mean(errors)), 4)


def bootstrap_nmae_ci(
    student_ids: Sequence[str],
    pred_scores: Sequence[float],
    true_scores: Sequence[float],
    max_marks: Sequence[float],
    n_iterations: int = 1000,
    seed: int = 42,
) -> dict[str, float]:
    """Compute NMAE% with student-script-level Bootstrap 95% Confidence Intervals."""
    by_student: dict[str, list[tuple[float, float, float]]] = {}
    for sid, yh, y, m in zip(student_ids, pred_scores, true_scores, max_marks):
        by_student.setdefault(str(sid), []).append((float(yh), float(y), float(m)))

    unique_sids = sorted(by_student.keys())
    if not unique_sids:
        return {"nmae": 0.0, "ci_low": 0.0, "ci_high": 0.0}

    point = compute_nmae_percent(pred_scores, true_scores, max_marks)
    rng = np.random.default_rng(seed)
    boot_vals: list[float] = []
    n_students = len(unique_sids)

    for _ in range(n_iterations):
        sampled_idx = rng.integers(0, n_students, size=n_students)
        s_yh: list[float] = []
        s_y: list[float] = []
        s_m: list[float] = []
        for idx in sampled_idx:
            for yh, y, m in by_student[unique_sids[int(idx)]]:
                s_yh.append(yh)
                s_y.append(y)
                s_m.append(m)
        boot_vals.append(compute_nmae_percent(s_yh, s_y, s_m))

    ci_low, ci_high = np.percentile(boot_vals, [2.5, 97.5])
    return {
        "nmae": round(point, 4),
        "ci_low": round(float(ci_low), 4),
        "ci_high": round(float(ci_high), 4),
    }


def compute_qwk(
    pred_scores: Sequence[float],
    true_scores: Sequence[float],
    max_marks: Sequence[float],
    bins: int = 10,
) -> float:
    """Compute Quadratic Weighted Kappa over normalized [0, bins] integer grades."""
    if len(pred_scores) < 2:
        return 0.0
    p_bins = [
        int(round(min(1.0, max(0.0, float(yh) / float(m))) * bins))
        for yh, m in zip(pred_scores, max_marks)
        if m > 0
    ]
    t_bins = [
        int(round(min(1.0, max(0.0, float(y) / float(m))) * bins))
        for y, m in zip(true_scores, max_marks)
        if m > 0
    ]
    if len(set(p_bins)) <= 1 and len(set(t_bins)) <= 1:
        return 1.0 if p_bins == t_bins else 0.0
    score = cohen_kappa_score(t_bins, p_bins, weights="quadratic")
    return 0.0 if np.isnan(score) else round(float(score), 4)


@dataclass
class PairedShiftResult:
    worsened_pct: float
    improved_pct: float
    preserved_pct: float
    total: int


def paired_recognition_grade_shift(
    arm_scores: Sequence[float],
    control_scores: Sequence[float],
    teacher_scores: Sequence[float],
    tol: float = 1e-6,
) -> PairedShiftResult:
    """Compare OCR-arm agreement with teacher marks vs Human-Verified Control."""
    total = len(teacher_scores)
    if total == 0:
        return PairedShiftResult(0.0, 0.0, 0.0, 0)

    worsened = improved = preserved = 0
    for arm_y, ctrl_y, teach_y in zip(arm_scores, control_scores, teacher_scores):
        arm_err = abs(float(arm_y) - float(teach_y))
        ctrl_err = abs(float(ctrl_y) - float(teach_y))
        if arm_err > ctrl_err + tol:
            worsened += 1
        elif arm_err + tol < ctrl_err:
            improved += 1
        else:
            preserved += 1

    return PairedShiftResult(
        worsened_pct=round(100.0 * worsened / total, 2),
        improved_pct=round(100.0 * improved / total, 2),
        preserved_pct=round(100.0 * preserved / total, 2),
        total=total,
    )
