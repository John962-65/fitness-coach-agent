"""用户档案辅助：摘要生成 + patch 深合并"""
from __future__ import annotations

import copy

_TIER_LABEL = {"emergency": "急症", "injury": "损伤", "yellow": "黄色"}


def open_pain_flags(profile: dict) -> list:
    """待跟进的安全记录（兼容早期纯文本格式）"""
    flags = profile.get("conditions", {}).get("pain_flags") or []
    return [
        f for f in flags
        if isinstance(f, str) or (isinstance(f, dict) and f.get("status") == "open")
    ]


def _flag_label(f) -> str:
    if isinstance(f, str):
        return f[:20]
    date = (f.get("at") or "")[:10]
    tier = _TIER_LABEL.get(f.get("tier"), f.get("tier", ""))
    return f"{f.get('kw', '?')}·{tier}·{date}"


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


_NEGATIVE_VALUES = {"", "无", "没有", "否", "无异常", "none", "None", "无。", "没有。"}


def _is_positive(v) -> bool:
    """健康筛查项是否为阳性（用户报了具体情况）"""
    if isinstance(v, bool):
        return v
    return str(v).strip() not in _NEGATIVE_VALUES


# LLM 偶发自造字段时的归一化映射（安全网）
_ALIASES = {
    "basic": {"sex": "gender", "身高": "height_cm", "体重": "weight_kg",
              "年龄": "age", "姓名": "name"},
    "resources": {"days": "days_per_week", "frequency": "days_per_week"},
    "experience": {"years": "training_years"},
}


def merge_patch(profile: dict, patch: dict) -> dict:
    """把 LLM 提交的 patch 深合并进档案（含字段别名归一化）"""
    merged = copy.deepcopy(profile)
    patch = copy.deepcopy(patch)

    for section, alias_map in _ALIASES.items():
        if isinstance(patch.get(section), dict):
            for old, new in alias_map.items():
                if old in patch[section]:
                    patch[section][new] = patch[section].pop(old)

    def _merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _merge(dst[k], v)
            else:
                dst[k] = v

    _merge(merged, patch)
    if "injuries" in patch.get("conditions", {}):
        merged["conditions"]["injuries_collected"] = True
    if "health_screen" in patch.get("conditions", {}):
        merged["conditions"]["health_screen_collected"] = True
    return merged
