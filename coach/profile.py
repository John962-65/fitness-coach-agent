"""用户档案辅助：摘要生成 + patch 深合并"""
from __future__ import annotations

import copy
import re

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
# 阴性开头措辞："没问题/正常/没怀孕/未孕/都无"等都是阴性回答——
# 注意"不"不在其中（"心电图不正常"必须是阳性）
_NEGATIVE_PREFIX_RE = re.compile(
    r"^(?:无|没有|没|未|否|正常|没问题|没事儿?|无异常|都正常|都没问题|都无|"
    r"挺好|良好|健康|都好|一切正常)"
)
# 混合句的句首健康陈述："身体健康，无心血管疾病史/高血压"
_HEALTHY_OPENING_RE = re.compile(r"^(?:身体|健康|一切|平时|目前)")
_NEGATED_TAIL_RE = re.compile(r"[,，、/]\s*无")


def _is_positive(v) -> bool:
    """健康筛查项是否为阳性（用户报了具体情况）。

    LLM 会把阴性回答提炼成各种写法——否定开头（无/没/未）、阴性结尾
    （都正常/没问题）、"不适用（男性）"、以及"身体健康，无心血管疾病史"
    这类健康陈述+否定列举的混合句，都是阴性；其余从严按阳性处理
    （安全场景宁可多提示一句，也不漏掉真阳性）。
    """
    if isinstance(v, bool):
        return v
    s = str(v).strip()
    if s in _NEGATIVE_VALUES:
        return False
    if _NEGATIVE_PREFIX_RE.match(s):
        return False
    # "心脏血压都正常/心肺没问题"：以阴性词结尾且不含"不"（"不正常"必须阳性）
    if s.endswith(("正常", "没问题", "没事", "无恙", "健康")) and "不" not in s:
        return False
    # "不适用（男性）/无需回答"：PAR-Q 里对性别不适用项的填法
    if "不适用" in s or "无需" in s:
        return False
    if s.startswith("有"):
        return True  # 规范填法"有：高血压"
    # "身体健康，无心血管疾病史/高血压"：句首健康陈述 + 后半否定列举
    if _HEALTHY_OPENING_RE.match(s) and _NEGATED_TAIL_RE.search(s):
        return False
    return True


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
    "goal": {"primary", "phase", "target"},
    "conditions": {"injuries", "injuries_evidence",
                   "health_screen", "health_screen_evidence"},
    "resources": {"location", "days_per_week", "session_minutes"},
    "nutrition": {"meals_per_day", "sleep_hours"},
}


def merge_patch(profile: dict, patch: dict) -> tuple[dict, dict]:
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

    def _merge(dst: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                _merge(dst[k], v)
            else:
                dst[k] = v

    for section, value in clean.items():
        _merge(merged.setdefault(section, {}), value)

    conditions = merged.setdefault("conditions", {})
    if "injuries" in clean.get("conditions", {}):
        conditions["injuries_collected"] = True
    if "health_screen" in clean.get("conditions", {}):
        conditions["health_screen_collected"] = True
    return merged, {"dropped": dropped, "warnings": warnings}
