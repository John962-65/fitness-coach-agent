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


# ---------- K-A02 错挂处置的映射回归（2026-10-10 解除挂空时不触发旧断言，建卡时补） ----------

# 每条：(claims 文件, claim id, 期望的 exercises 映射)。None = 应保持空映射（解除错挂留池）。
_REMAP_EXPECTATIONS = [
    ("claims/ksw.yaml", "ksw-BV1we4y1J72N-0052", "t_bar_squat"),
    ("claims/ksw.yaml", "ksw-BV1we4y1J72N-0053", "t_bar_squat"),
    ("claims/ksw.yaml", "ksw-BV1we4y1J72N-0055", "t_bar_squat"),
    ("claims/ksw.yaml", "ksw-BV1we4y1J72N-0056", "t_bar_squat"),
    ("claims/ksw.yaml", "ksw-BV1we4y1J72N-0057", "t_bar_squat"),
    ("claims/ksw.yaml", "ksw-BV1we4y1J72N-0058", "t_bar_squat"),
    ("claims/tcy.yaml", "tcy-BV1FL2MBME3G-0002", "lying_db_external_rotation"),
    ("claims/tcy.yaml", "tcy-BV1FL2MBME3G-0005", "lying_db_external_rotation"),
    ("claims/tcy.yaml", "tcy-BV1FL2MBME3G-0008", "lying_db_external_rotation"),
    ("claims/tcy.yaml", "tcy-BV1utntzhE9a-0008", "rear_delt_fly"),
    ("claims/tcy.yaml", "tcy-BV1utntzhE9a-0013", "rear_delt_fly"),
    ("claims/ksw.yaml", "ksw-BV1MG4y1G76W-0047", "crunch"),
    ("claims/ksw.yaml", "ksw-BV1MG4y1G76W-0048", "crunch"),
    ("claims/ksw.yaml", "ksw-BV1MG4y1G76W-0050", "crunch"),
    ("claims/ksw.yaml", "ksw-BV1MG4y1G76W-0051", "crunch"),
    ("claims/ksw.yaml", "ksw-BV1MG4y1G76W-0052", "crunch"),
    ("claims/tcy.yaml", "tcy-BV1Ehn7zmEHN-0014", "reverse_back_extension"),
    ("claims/tcy.yaml", "tcy-BV1W1BFBKEdR-0005", "reverse_back_extension"),
    ("claims/tcy.yaml", "tcy-BV1W1BFBKEdR-0022", "reverse_back_extension"),
    ("claims/ksw.yaml", "ksw-BV1MG4y1G76W-0055", "back_extension"),
    ("claims/ksw.yaml", "ksw-BV1MG4y1G76W-0043", "bent_over_triceps_extension"),
    ("claims/tcy.yaml", "tcy-BV1hyWwzeETh-0006", "skull_crusher"),
    ("claims/ksw.yaml", "ksw-BV1A1s3zUEN6-0004", "overhead_squat_screen"),
    ("claims/tcy.yaml", "tcy-BV1QF4r6BE2S-0005", "band_scapular_upward_rotation"),
]


def test_claim_remap_after_k_a02_unmapping():
    """错挂解除后必须落到正确动作 id（或保持空），不许静默回退或挂空无人管。

    用行级扫描而非整体 YAML 解析（claims 文件大，避免拖慢测试套件）：
    定位 claim 条目后检查其 exercises 块内容。
    """
    from pathlib import Path
    root = Path(__file__).parent
    by_file = {}
    for f, cid, _ in _REMAP_EXPECTATIONS:
        by_file.setdefault(f, []).append(cid)
    texts = {f: (root / f).read_text(encoding="utf-8").splitlines() for f in by_file}
    for f, cid, expect in _REMAP_EXPECTATIONS:
        lines = texts[f]
        idx = next((i for i, ln in enumerate(lines)
                    if ln.strip() == f"- id: {cid}"), None)
        assert idx is not None, f"{cid} 不存在于 {f}"
        got = []
        in_ex = False
        for ln in lines[idx + 1: idx + 20]:
            s = ln.strip()
            if s == "exercises:":
                in_ex = True
                continue
            if in_ex:
                if s.startswith("- "):
                    got.append(s[2:].strip())
                else:
                    break
        assert got == ([expect] if expect else []), f"{cid} 映射为 {got}，期望 {expect}"
