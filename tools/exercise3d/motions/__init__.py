"""动作脚本注册表：exercise_id → 模块（build() → motion 文档）。"""
from __future__ import annotations

from importlib import import_module

from ..rig import Rig  # noqa: F401  确保 import 路径可用

_REGISTRY = {
    "barbell_back_squat": "squat",
    "barbell_bench_press": "bench_press",
    "deadlift": "deadlift",
    "barbell_row": "barbell_row",
    "dumbbell_shoulder_press": "db_shoulder_press",
}


def _load():
    mods = {}
    for ex_id, mod_name in _REGISTRY.items():
        mods[ex_id] = import_module(f".{mod_name}", package=__name__)
    return mods


MOTIONS = _load()
