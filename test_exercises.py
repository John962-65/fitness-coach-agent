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
    """现有计划模板用到的动作必须全部入库（R2 路线图：模板约 25 个动作）"""
    from coach.plan import (BUSY_FULL, FULL_BODY_A, FULL_BODY_B, PPL,
                            PPL_ADVANCED)
    names = set()
    for tpl in (FULL_BODY_A, FULL_BODY_B, BUSY_FULL):
        names.update(e["name"] for e in tpl)
    for day in (*PPL.values(), *PPL_ADVANCED.values()):
        names.update(e["name"] for e in day)
    missing = [n for n in sorted(names) if not library.normalize(n)[0]]
    assert missing == []
