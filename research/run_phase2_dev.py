"""CLI benchmark runner for Arms A, B, C + Human Control on the 35-Dev split."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from backend.config import get_settings
from backend.evaluator import evaluate_question
from backend.grader_provider import get_grader_provider
from research.metrics import (
    bootstrap_nmae_ci,
    compute_active_and_literal_cer_wer,
    compute_qwk,
    compute_tag_f1,
    paired_recognition_grade_shift,
)
from shared.schemas import QuestionRubric


async def evaluate_benchmark_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate benchmark fixture/dataset across Human Control, Arm A, Arm B, and Arm C."""
    settings = get_settings()
    provider = get_grader_provider(settings)

    student_ids = [str(r["student_id"]) for r in records]
    teacher_scores = [float(r["teacher_score"]) for r in records]
    max_marks = [float(r["max_marks"]) for r in records]

    arm_outputs: dict[str, list[float]] = {
        "human_control": [],
        "arm_a_paddle_trocr": [],
        "arm_b_qwen_vlm": [],
        "arm_c_e2e_vlm": [],
    }

    for r in records:
        rubric = QuestionRubric.model_validate(r["rubric"])
        ctrl_ev = await evaluate_question(rubric, r["human_transcript"], [], provider)
        arm_a_ev = await evaluate_question(rubric, r["arm_a_transcript"], [], provider)
        arm_b_ev = await evaluate_question(rubric, r["arm_b_transcript"], [], provider)
        arm_outputs["human_control"].append(ctrl_ev.ai_awarded_marks)
        arm_outputs["arm_a_paddle_trocr"].append(arm_a_ev.ai_awarded_marks)
        arm_outputs["arm_b_qwen_vlm"].append(arm_b_ev.ai_awarded_marks)
        arm_outputs["arm_c_e2e_vlm"].append(float(r.get("arm_c_score", arm_b_ev.ai_awarded_marks)))

    report: dict[str, Any] = {"arms": {}}
    ctrl_scores = arm_outputs["human_control"]

    for arm_name, scores in arm_outputs.items():
        ci = bootstrap_nmae_ci(student_ids, scores, teacher_scores, max_marks)
        qwk = compute_qwk(scores, teacher_scores, max_marks)
        shift = paired_recognition_grade_shift(scores, ctrl_scores, teacher_scores)
        report["arms"][arm_name] = {
            **ci,
            "qwk": qwk,
            "grade_shift_vs_control": {
                "worsened_pct": shift.worsened_pct,
                "improved_pct": shift.improved_pct,
                "preserved_pct": shift.preserved_pct,
            },
        }

    # Transcription quality for Arm A and Arm B
    for arm_key, field in [("arm_a_paddle_trocr", "arm_a_transcript"), ("arm_b_qwen_vlm", "arm_b_transcript")]:
        preds = [r[field] for r in records]
        refs = [r["human_transcript"] for r in records]
        cer_wer_list = [compute_active_and_literal_cer_wer(p, ref) for p, ref in zip(preds, refs)]
        report["arms"][arm_key]["ocr_metrics"] = {
            "mean_active_cer": round(sum(x["active_cer"] for x in cer_wer_list) / len(cer_wer_list), 4),
            "mean_active_wer": round(sum(x["active_wer"] for x in cer_wer_list) / len(cer_wer_list), 4),
            "mean_literal_cer": round(sum(x["literal_cer"] for x in cer_wer_list) / len(cer_wer_list), 4),
            "struck_tag_f1": compute_tag_f1(preds, refs, "struck")["f1"],
            "diagram_tag_f1": compute_tag_f1(preds, refs, "diagram")["f1"],
        }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 2 Dev Benchmark (35 scripts).")
    parser.add_argument("--dataset", required=True, help="Path to benchmark JSON records.")
    parser.add_argument("--split", required=True, help="Path to split.json.")
    parser.add_argument("--out", default="./data/phase2_dev_results.json")
    args = parser.parse_args()

    split = json.loads(Path(args.split).read_text(encoding="utf-8"))
    dev_ids = set(split["dev_student_ids"])
    all_records = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    dev_records = [r for r in all_records if str(r["student_id"]) in dev_ids]

    res = asyncio.run(evaluate_benchmark_records(dev_records))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"Saved Dev results ({len(dev_records)} answers) -> {args.out}")


if __name__ == "__main__":
    main()
