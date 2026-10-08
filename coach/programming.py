"""处方的时间预算估算：保留休息与热身，不用压缩安全余量来硬凑时长。"""
from __future__ import annotations

import copy
import math
import re

WARMUP_MINUTES = 8


def estimate_minutes(exercises: list[dict]) -> int:
    if not exercises:
        return 0
    total = float(WARMUP_MINUTES)
    for ex in exercises:
        numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(ex.get("reps", "8")))]
        reps = max(numbers or [8])
        rest = 2.0 if ex.get("role", "main") == "main" else 1.5
        sets = max(1, int(ex.get("sets", 1)))
        total += 1 + sets * (reps * 4 / 60 + rest)
    return math.ceil(total)


def fit_time_budget(exercises: list[dict], minutes: int) -> tuple[list[dict], list[str]]:
    selected = copy.deepcopy(exercises)
    changes = []
    rank = {"accessory": 0, "secondary": 1, "main": 2}
    while selected and estimate_minutes(selected) > minutes:
        reducible = [i for i, ex in enumerate(selected) if int(ex.get("sets", 1)) > 2]
        if reducible:
            idx = min(reducible, key=lambda i: (rank.get(selected[i].get("role", "main"), 2), -i))
            ex = selected[idx]
            ex["sets"] = int(ex["sets"]) - 1
            change = f"{ex['name']}减组以适应时间预算"
        else:
            idx = min(range(len(selected)), key=lambda i: (rank.get(selected[i].get("role", "main"), 2), -i))
            ex = selected.pop(idx)
            change = f"本次暂不安排{ex['name']}，保留其他重点动作与休息时间"
        if change not in changes:
            changes.append(change)
    if not selected:
        changes.append("给定时间不足以容纳热身与本方案，请延长时段或另行确认更短的方案")
    return selected, changes
