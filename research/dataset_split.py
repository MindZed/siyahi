"""Stratified student-level 35 Dev / 15 Held-Out zero-leakage dataset split generator."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


def create_student_split(
    records: list[dict[str, Any]],
    dev_count: int = 35,
    heldout_count: int = 15,
    seed: int = 42,
    stratum_key: str = "stratum",
) -> dict[str, Any]:
    """Split student scripts strictly by student_id with stratification and zero overlap.

    Each record should have `student_id` (and optionally `stratum`).
    """
    unique_students: dict[str, str] = {}
    for rec in records:
        sid = str(rec["student_id"])
        if sid not in unique_students:
            unique_students[sid] = str(rec.get(stratum_key, "default"))

    total_students = len(unique_students)
    if total_students < 2:
        raise ValueError("Need at least 2 unique students to create a split.")

    if total_students != dev_count + heldout_count:
        ratio = dev_count / float(dev_count + heldout_count)
        dev_target = max(1, min(total_students - 1, round(total_students * ratio)))
    else:
        dev_target = dev_count

    by_stratum: dict[str, list[str]] = {}
    for sid, strat in unique_students.items():
        by_stratum.setdefault(strat, []).append(sid)

    rng = random.Random(seed)
    dev_ids: list[str] = []
    heldout_ids: list[str] = []

    for strat in sorted(by_stratum):
        group = sorted(by_stratum[strat])
        rng.shuffle(group)
        n_dev = round(len(group) * (dev_target / float(total_students)))
        dev_ids.extend(group[:n_dev])
        heldout_ids.extend(group[n_dev:])

    # Exact adjustment to hit dev_target cleanly
    while len(dev_ids) > dev_target and dev_ids:
        heldout_ids.append(dev_ids.pop())
    while len(dev_ids) < dev_target and len(heldout_ids) > 1:
        dev_ids.append(heldout_ids.pop())

    assert set(dev_ids).isdisjoint(set(heldout_ids)), "Leakage detected between dev and heldout!"

    return {
        "seed": seed,
        "total_students": total_students,
        "dev_count": len(dev_ids),
        "heldout_count": len(heldout_ids),
        "dev_student_ids": sorted(dev_ids),
        "heldout_student_ids": sorted(heldout_ids),
    }


def save_split(split: dict[str, Any], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(split, indent=2), encoding="utf-8")
    return path


def load_split(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
