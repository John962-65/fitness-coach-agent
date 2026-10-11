"""用户档案辅助：摘要生成 + patch 深合并"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime

from .medical import screening_positive

_TIER_LABEL = {"emergency": "急症", "injury": "损伤", "yellow": "黄色"}


def open_pain_flags(profile: dict) -> list:
    """待跟进的安全记录（兼容早期纯文本格式）"""
    flags = profile.get("conditions", {}).get("pain_flags") or []
    return [
        f for f in flags
        if isinstance(f, str) or (isinstance(f, dict) and f.get("status") == "open")
    ]


def ensure_flag_ids(profile: dict) -> bool:
    """旧记录增量补 ID；不改变已有状态，不按显示顺序重新编号。"""
    flags = profile.setdefault("conditions", {}).setdefault("pain_flags", [])
    changed, seen = False, set()
    for i, flag in enumerate(flags):
        if isinstance(flag, str):
            flag = {"text": flag, "kw": flag, "status": "open"}
            flags[i] = flag
            changed = True
        if not isinstance(flag, dict):
            continue
        flag_id = flag.get("flag_id")
        if not isinstance(flag_id, str) or not flag_id or flag_id in seen:
            flag["flag_id"] = "flag-" + uuid.uuid4().hex
            changed = True
        seen.add(flag["flag_id"])
    return changed


def _flag_label(f) -> str:
    if isinstance(f, str):
        return f[:20]
    date = (f.get("at") or "")[:10]
    tier = _TIER_LABEL.get(f.get("tier"), f.get("tier", ""))
    return f"[{f.get('flag_id', '?')}] {f.get('kw', '?')}·{tier}·{date}"


def profile_summary(profile: dict) -> str:
    """生成给 LLM 看的档案摘要"""
    b = profile.get("basic", {})
    e = profile.get("experience", {})
    g = profile.get("goal", {})
    r = profile.get("resources", {})
    c = profile.get("conditions", {})

    open_flags = open_pain_flags(profile)
    if open_flags:
        flags_text = "；".join(_flag_label(f) for f in open_flags)
        flags_line = f"{len(open_flags)} 条待跟进（{flags_text}）"
    else:
        flags_line = "无"

    hs = c.get("health_screen") or {}
    positives = [f"{k}:{v}" for k, v in hs.items() if _is_positive(v)]
    hs_line = "、".join(positives) if positives else "无异常"

    return (
        f"用户：{b.get('name') or '未命名'}，{b.get('gender') or '?'}，"
        f"{b.get('age') or '?'}岁，{b.get('height_cm') or '?'}cm，"
        f"{b.get('weight_kg') or '?'}kg\n"
        f"水平：{e.get('level', 'beginner')}（训练 {e.get('training_years', 0)} 年）\n"
        f"目标：{g.get('primary') or '未定'}（阶段：{g.get('phase') or '未定'}）\n"
        f"条件：{r.get('location', 'gym')}，每周 {r.get('days_per_week') or '?'} 次，"
        f"每次 {r.get('session_minutes', 60)} 分钟\n"
        f"伤病：{(c.get('injuries') or ['无']) if c.get('injuries_collected') else '未采集'}；"
        f"健康筛查：{hs_line if c.get('health_screen_collected') else '未采集'}；"
        f"红旗记录：{flags_line}"
    )


def _is_positive(v) -> bool:
    """兼容调用点，健康筛查统一由医疗准入模块判断。"""
    return screening_positive(v)


# LLM 偶发自造字段时的归一化映射（安全网）
_ALIASES = {
    "basic": {"sex": "gender", "身高": "height_cm", "体重": "weight_kg",
              "年龄": "age", "姓名": "name"},
    "resources": {"days": "days_per_week", "frequency": "days_per_week"},
    "experience": {"years": "training_years"},
}

# G1：LLM 可写字段白名单；白名单外（含系统字段）一律拒绝并报告
_WRITABLE = {
    "basic": {"name", "age", "gender", "height_cm", "weight_kg"},
    "experience": {"training_years", "big3", "recent_layoff_weeks"},
    "goal": {"primary", "phase", "target", "secondary", "timeline"},
    "conditions": {"injuries", "injuries_evidence",
                   "health_screen", "health_screen_evidence"},
    "resources": {"location", "days_per_week", "session_minutes"},
    "nutrition": {"meals_per_day", "sleep_hours"},
}

# C1 收尾（26.2/26.4）：这些字段驱动处方与评价标准，已有确认值时被改写
# 不立即生效——先暂存并向用户澄清，经 confirm_profile_change 才落库。
HOLD_FIELDS = (
    "goal.primary", "goal.phase",
    "experience.training_years",
    "resources.days_per_week", "resources.session_minutes", "resources.location",
)

_HOLD_EMPTY = (None, "", 0, [])


def merge_patch(profile: dict, patch: dict,
                hold_fields: tuple = ()) -> tuple[dict, dict]:
    """把 LLM 提交的 patch 合并进档案。

    防线（设计书 17.2）：
    - D2：数字字段先强转（"130kg"→130，转不了丢弃）
    - 别名归一化（sex→gender 等）
    - G1：白名单外的 key 一律拒绝（onboarding_done / experience.level /
      pain_flags / *_collected 等系统字段只允许代码写）

    返回 (合并后档案, {"dropped": [...], "warnings": [...]})
    """
    from .validate import coerce_profile_patch

    merged = copy.deepcopy(profile)
    patch, warnings = coerce_profile_patch(patch)
    patch = copy.deepcopy(patch)

    for section, alias_map in _ALIASES.items():
        if isinstance(patch.get(section), dict):
            for old, new in alias_map.items():
                if old in patch[section]:
                    patch[section][new] = patch[section].pop(old)

    dropped: list[str] = []
    clean: dict[str, dict] = {}
    for section, value in patch.items():
        if section not in _WRITABLE:
            dropped.append(section)
            continue
        if not isinstance(value, dict):
            dropped.append(section)
            continue
        allowed = _WRITABLE[section]
        kept = {k: v for k, v in value.items() if k in allowed}
        for k in value:
            if k not in allowed:
                dropped.append(f"{section}.{k}")
        if kept:
            clean[section] = kept

    # C1 收尾：敏感字段"已有确认值 → 不同新值"时抽出不合并，交由确认流。
    # 旧值为空（首次采集）或值相同不算冲突，照常生效。
    held: list[dict] = []
    for path in hold_fields:
        section, key = path.split(".", 1)
        if section in clean and key in clean[section]:
            old = (profile.get(section) or {}).get(key)
            new = clean[section][key]
            if old not in _HOLD_EMPTY and old != new:
                held.append({"field": path, "old": old, "new": new})
                del clean[section][key]
                if not clean[section]:
                    del clean[section]

    def _merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _merge(dst[k], v)
            else:
                dst[k] = v

    # C1 记忆契约：字段被改写时留下旧值来历，供冲突澄清与更正追溯（26.2）。
    # 只记录"原字段存在且值变化"的情况；新字段无需历史。
    # _history 不在 _WRITABLE 白名单内，LLM 无法伪造或清空。
    for section, value in clean.items():
        dst = merged.setdefault(section, {})
        for k, v in value.items():
            if k in dst and dst[k] != v:
                merged.setdefault("_history", {})[f"{section}.{k}"] = {
                    "old": dst[k], "at": datetime.now().isoformat(timespec="seconds")}
        _merge(dst, value)

    conditions = merged.setdefault("conditions", {})
    if "injuries" in clean.get("conditions", {}):
        conditions["injuries_collected"] = True
    if "health_screen" in clean.get("conditions", {}):
        conditions["health_screen_collected"] = True
    return merged, {"dropped": dropped, "warnings": warnings, "held": held}
