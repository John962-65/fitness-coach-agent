"""动作库数据契约测试：tools/validate.py 进 pytest（设计书 20.1）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from coach.exercises import library
from tools.validate import validate


def test_exercise_library_valid():
    assert validate() == []


def test_library_loaded_nonempty():
    assert len(library) >= 20


def test_plan_template_exercises_all_in_library():
    """槽位模板的 default 动作必须全部入库（R5：槽位式生成）"""
    from coach.plan import (BUSY_SLOTS, FULL_BODY_A, FULL_BODY_B,
                            PPL_ADVANCED_SLOTS, PPL_SLOTS)
    slots = [*BUSY_SLOTS, *FULL_BODY_A, *FULL_BODY_B,
             *[s for day in PPL_SLOTS.values() for s in day],
             *[s for day in PPL_ADVANCED_SLOTS.values() for s in day]]
    missing = [s["default"] for s in slots if not library.get(s["default"])]
    assert missing == []


def test_slot_defaults_match_pattern_and_primary():
    """槽位 default 必须匹配槽位的 pattern（和 primary 约束），防止模板与库漂移"""
    from coach.plan import (BUSY_SLOTS, FULL_BODY_A, FULL_BODY_B,
                            PPL_ADVANCED_SLOTS, PPL_SLOTS)
    slots = [*BUSY_SLOTS, *FULL_BODY_A, *FULL_BODY_B,
             *[s for day in PPL_SLOTS.values() for s in day],
             *[s for day in PPL_ADVANCED_SLOTS.values() for s in day]]
    bad = []
    for s in slots:
        ex = library.get(s["default"])
        if ex is None:
            continue
        muscles = set(ex.get("primary") or []) | set(ex.get("secondary") or [])
        if ex.get("pattern") != s["pattern"]:
            bad.append(f"{s['default']}: pattern {ex.get('pattern')} != {s['pattern']}")
        if s.get("primary") and not set(s["primary"]) & muscles:
            bad.append(f"{s['default']}: primary {s['primary']} 不匹配")
    assert bad == []
