"""动作库校验器（设计书 20.1）：字段格式、别名唯一、替代/退阶 id 闭合

可独立运行：python3 tools/validate.py；也被 test_exercises.py 调用进 pytest。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent / "exercises"

REQUIRED = {
    "id": str, "name": str, "aliases": list, "pattern": str,
    "primary": list, "equipment": list, "location": list,
    "level_min": str, "joint_stress": dict, "track_e1rm": bool,
    "substitutes": list, "status": str,
}
PATTERNS = {"squat", "hinge", "lunge", "h_push", "v_push", "h_pull", "v_pull",
            "isolation", "core", "carry"}
LEVELS = {"beginner", "intermediate", "advanced"}
JOINTS = {"knee", "lumbar", "shoulder", "wrist"}


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    files = sorted(root.glob("*.yaml"))
    if not files:
        return [f"动作库为空：{root}"]

    docs: dict[str, dict] = {}
    for path in files:
        try:
            docs[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{path.name}: YAML 解析失败 {e}")

    for stem, d in docs.items():
        if not isinstance(d, dict):
            errors.append(f"{stem}: 顶层必须是 dict")
            continue
        for field, typ in REQUIRED.items():
            if field not in d:
                errors.append(f"{stem}: 缺字段 {field}")
            elif not isinstance(d[field], typ):
                errors.append(f"{stem}: {field} 类型应为 {typ.__name__}")
        if d.get("id") != stem:
            errors.append(f"{stem}: id 字段 {d.get('id')!r} 与文件名不一致")
        if d.get("pattern") not in PATTERNS:
            errors.append(f"{stem}: pattern 非法 {d.get('pattern')!r}")
        if d.get("level_min") not in LEVELS:
            errors.append(f"{stem}: level_min 非法 {d.get('level_min')!r}")
        for joint, v in (d.get("joint_stress") or {}).items():
            if joint not in JOINTS or not isinstance(v, int) or not 0 <= v <= 3:
                errors.append(f"{stem}: joint_stress.{joint} 应为 0-3，实际 {v!r}")
        for rel in ("substitutes", "regressions", "progressions"):
            for ref in d.get(rel) or []:
                if ref not in docs:
                    errors.append(f"{stem}: {rel} 引用了不存在的 id {ref!r}")
        if d.get("status") not in ("draft", "approved"):
            errors.append(f"{stem}: status 非法 {d.get('status')!r}")

    seen: dict[str, str] = {}
    for stem, d in docs.items():
        for a in [d.get("name"), *(d.get("aliases") or [])]:
            key = "".join(str(a).split()).lower()
            if key in seen and seen[key] != stem:
                errors.append(f"别名冲突：{a!r} 同时属于 {seen[key]} 和 {stem}")
            seen[key] = stem
    return errors


if __name__ == "__main__":
    errs = validate()
    if errs:
        print("\n".join(f"❌ {e}" for e in errs))
        sys.exit(1)
    print(f"✅ 动作库校验通过（{len(list(ROOT.glob('*.yaml')))} 个动作）")
