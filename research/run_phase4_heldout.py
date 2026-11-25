"""Single-shot frozen evaluation runner on the 15 untouched Held-Out scripts."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from research.run_phase2_dev import evaluate_benchmark_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Run single-shot Phase 4 Held-Out evaluation (15 scripts).")
    parser.add_argument("--dataset", required=True, help="Path to benchmark JSON records.")
    parser.add_argument("--split", required=True, help="Path to split.json.")
    parser.add_argument("--out", default="./data/phase4_heldout_results.json")
    args = parser.parse_args()

    split = json.loads(Path(args.split).read_text(encoding="utf-8"))
    heldout_ids = set(split["heldout_student_ids"])
    all_records = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    heldout_records = [r for r in all_records if str(r["student_id"]) in heldout_ids]

    res = asyncio.run(evaluate_benchmark_records(heldout_records))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"Saved Held-Out results ({len(heldout_records)} answers) -> {args.out}")


if __name__ == "__main__":
    main()
