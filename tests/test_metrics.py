"""Phase 5 tests: NMAE%, bootstrap CIs, QWK, Active/Literal CER & WER, Tag F1, split & robustness."""

import pytest

from backend.grader_provider import MockGraderProvider
from research.dataset_split import create_student_split
from research.metrics import (
    bootstrap_nmae_ci,
    compute_active_and_literal_cer_wer,
    compute_nmae_percent,
    compute_qwk,
    compute_tag_f1,
    paired_recognition_grade_shift,
)
from research.robustness import (
    inject_negation_drop,
    inject_numeric_and_directional_flips,
    measure_perturbation_mark_flips,
)
from shared.schemas import QuestionRubric, RubricCriterion


def test_stratified_zero_leakage_split() -> None:
    records = []
    for i in range(50):
        sid = f"CSE{i:03d}"
        stratum = "high" if i % 2 == 0 else "low"
        for q in ("Q1", "Q2", "Q3", "Q4"):
            records.append({"student_id": sid, "question_no": q, "stratum": stratum})

    split = create_student_split(records, dev_count=35, heldout_count=15, seed=42)
    assert split["dev_count"] == 35
    assert split["heldout_count"] == 15
    assert set(split["dev_student_ids"]).isdisjoint(set(split["heldout_student_ids"]))


def test_nmae_bootstrap_ci_and_qwk() -> None:
    student_ids = ["S1", "S1", "S2", "S2", "S3", "S3", "S4", "S4"]
    preds = [4.0, 5.0, 2.0, 3.0, 5.0, 1.0, 3.0, 4.0]
    trues = [4.0, 4.0, 2.5, 3.0, 4.5, 2.0, 3.0, 4.0]
    max_m = [5.0] * 8

    nmae = compute_nmae_percent(preds, trues, max_m)
    assert nmae == pytest.approx(7.5, abs=1e-4)

    boot = bootstrap_nmae_ci(student_ids, preds, trues, max_m, n_iterations=1000, seed=42)
    assert boot["nmae"] == pytest.approx(nmae, abs=1e-4)
    assert 0.0 <= boot["ci_low"] <= boot["nmae"] <= boot["ci_high"]

    qwk = compute_qwk(preds, trues, max_m)
    assert qwk > 0.7


def test_active_vs_literal_cer_wer_and_tag_f1() -> None:
    ref = "The variance [struck: old wrong bias] causes overfitting [diagram: tree]"
    # Pred matches active text cleanly even though struck text was slightly misread
    pred = "The variance [struck: old wrng bias] causes overfitting [diagram: tree]"
    res = compute_active_and_literal_cer_wer(pred, ref)
    assert res["active_cer"] == 0.0
    assert res["active_wer"] == 0.0
    assert res["literal_cer"] > 0.0

    struck_f1 = compute_tag_f1([pred, "clean text"], [ref, "clean text"], tag_type="struck")
    assert struck_f1["f1"] == 1.0
    diag_f1 = compute_tag_f1([pred, "clean text"], [ref, "clean text"], tag_type="diagram")
    assert diag_f1["f1"] == 1.0


def test_paired_recognition_grade_shift() -> None:
    shift = paired_recognition_grade_shift(
        arm_scores=[2.0, 4.0, 5.0, 1.0],
        control_scores=[4.0, 4.0, 3.0, 1.0],
        teacher_scores=[4.0, 4.0, 5.0, 2.0],
    )
    assert shift.worsened_pct == 25.0
    assert shift.improved_pct == 25.0
    assert shift.preserved_pct == 50.0


@pytest.mark.asyncio
async def test_synthetic_perturbations_and_mark_flips() -> None:
    dropped = inject_negation_drop("Gradient descent does not diverge here.")
    assert "not" not in dropped.lower()

    flipped = inject_numeric_and_directional_flips("Error will increase to 5.")
    assert "decrease" in flipped.lower()
    assert "6" in flipped

    rub = QuestionRubric(
        question_no="Q1",
        question_text="Does variance increase?",
        max_marks=4.0,
        question_type="short_answer",
        criteria=[
            RubricCriterion(
                criterion_id="Q1_C1",
                description="States variance increases",
                max_points=4.0,
                expected_keywords=["increase", "5"],
            )
        ],
    )
    summary = await measure_perturbation_mark_flips(
        rubrics=[rub],
        verified_transcripts=["Variance will increase to 5."],
        teacher_scores=[4.0],
        provider=MockGraderProvider(),
    )
    assert summary["numeric_direction_flip"]["mark_flip_rate"] == 100.0
