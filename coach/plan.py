"""参数化计划生成（凯圣王式模板 + 系统定级）

定级逻辑（不采信用户自述，设计书第 11 章）：
- 有三大项数据 → 按体重倍数定级
- 无数据 → 按训练年限
计划选择：
- 停训 ≥2 周 → 复训 ramp（前 2 周强度 70%）
- 每周 ≤2 天 → 忙碌高效计划（复合动作 + 超级组）
- 新手 → 全身 A/B 线性进阶
- 进阶 → 三分化推拉蹲
- 老炮 → 周期化 + 高级技术（递减组/RPE）
"""
from __future__ import annotations

from .profile import _is_positive, open_pain_flags

FULL_BODY_A = [
    {"name": "杠铃深蹲", "sets": 5, "reps": "5"},
    {"name": "杠铃卧推", "sets": 5, "reps": "5"},
    {"name": "杠铃划船", "sets": 5, "reps": "5"},
]
FULL_BODY_B = [
    {"name": "杠铃深蹲", "sets": 5, "reps": "5"},
    {"name": "站姿推举", "sets": 5, "reps": "5"},
    {"name": "罗马尼亚硬拉", "sets": 3, "reps": "8"},
]
PPL = {
    "推": [
        {"name": "杠铃平板卧推", "sets": 4, "reps": "8-12"},
        {"name": "杠铃上斜卧推", "sets": 3, "reps": "8-12"},
        {"name": "站姿推举", "sets": 3, "reps": "8-12"},
        {"name": "侧平举", "sets": 3, "reps": "12-15"},
    ],
    "拉": [
        {"name": "硬拉", "sets": 4, "reps": "6-10"},
        {"name": "坐姿划船", "sets": 4, "reps": "10-12"},
        {"name": "高位下拉", "sets": 3, "reps": "10-12"},
        {"name": "杠铃弯举", "sets": 3, "reps": "10-15"},
    ],
    "蹲": [
        {"name": "杠铃深蹲", "sets": 4, "reps": "8-12"},
        {"name": "倒蹬", "sets": 3, "reps": "10-15"},
        {"name": "俯卧腿弯举", "sets": 3, "reps": "12-15"},
        {"name": "站姿提踵", "sets": 3, "reps": "12-15"},
    ],
}

# 老炮版：周期化 + RPE + 高级技术
PPL_ADVANCED = {
    "推": [
        {"name": "杠铃平板卧推", "sets": 4, "reps": "5-8", "note": "RPE 8，第 3 周加重"},
        {"name": "杠铃上斜卧推", "sets": 3, "reps": "8-10", "note": "RPE 8"},
        {"name": "站姿推举", "sets": 3, "reps": "6-10", "note": "RPE 8"},
        {"name": "侧平举", "sets": 3, "reps": "12-20", "note": "最后一组递减组"},
    ],
    "拉": [
        {"name": "硬拉", "sets": 3, "reps": "3-6", "note": "RPE 8-9，周期化加重"},
        {"name": "负重引体向上", "sets": 3, "reps": "6-10", "note": "RPE 8"},
        {"name": "坐姿划船", "sets": 3, "reps": "10-12", "note": "顶峰收缩 1 秒"},
        {"name": "面拉", "sets": 3, "reps": "15-20", "note": "后束+肩袖健康"},
    ],
    "蹲": [
        {"name": "杠铃深蹲", "sets": 4, "reps": "5-8", "note": "RPE 8，周期化加重"},
        {"name": "罗马尼亚硬拉", "sets": 3, "reps": "8-10", "note": "腘绳肌主导"},
        {"name": "保加利亚分腿蹲", "sets": 3, "reps": "8-12/侧", "note": "单侧纠正"},
        {"name": "俯卧腿弯举", "sets": 3, "reps": "12-15", "note": ""},
    ],
}

# 忙人版：每周 1-2 练，复合动作 + 拮抗超级组压缩时间
BUSY_FULL = [
    {"name": "杠铃深蹲", "sets": 3, "reps": "5-8"},
    {"name": "杠铃卧推", "sets": 3, "reps": "6-10"},
    {"name": "高位下拉", "sets": 3, "reps": "8-12"},
    {"name": "罗马尼亚硬拉", "sets": 2, "reps": "8-10"},
    {"name": "站姿推举", "sets": 2, "reps": "8-12"},
]

INJURY_EXCLUDE = {
    "腰": ["硬拉", "罗马尼亚硬拉", "杠铃划船"],
    "肩": ["站姿推举", "侧平举"],
    "膝": ["杠铃深蹲", "倒蹬", "保加利亚分腿蹲"],
    "腕": ["杠铃弯举"],
}


def assess_level(profile: dict) -> str:
    """系统定级：优先三大项体重倍数，其次训练年限"""
    e = profile.get("experience", {})
    b = profile.get("basic", {})
    big3 = e.get("big3") or {}
    bw = b.get("weight_kg") or 0
    squat = big3.get("squat") or 0

    if squat and bw:
        ratio = squat / bw
        if ratio >= 1.5:
            return "advanced"
        if ratio >= 1.0:
            return "intermediate"
        return "beginner"

    years = e.get("training_years") or 0
    if years >= 3:
        return "advanced"
    if years >= 1:
        return "intermediate"
    return "beginner"


def _filter(exercises: list[dict], excluded: list[str]) -> list[dict]:
    return [x for x in exercises if x["name"] not in excluded]


def _names_for(days: int) -> list[str]:
    base = ["周一", "周二", "周四", "周六", "周日", "周三"]
    return base[:days]


def generate_plan(profile: dict) -> dict:
    e = profile.get("experience", {})
    r = profile.get("resources", {})
    g = profile.get("goal", {})
    c = profile.get("conditions", {})

    level = assess_level(profile)
    days = r.get("days_per_week") or 3
    layoff = e.get("recent_layoff_weeks") or 0
    injuries = "、".join(c.get("injuries") or [])

    excluded: list[str] = []
    for key, moves in INJURY_EXCLUDE.items():
        if any(key in inj for inj in (c.get("injuries") or [])):
            excluded.extend(moves)

    notes: list[str] = ["每次训练先热身 5-10 分钟，主力动作从小重量组开始"]
    if excluded:
        notes.append(f"因伤病（{injuries}）已剔除动作：{'、'.join(excluded)}")
    open_flags = open_pain_flags(profile)
    if open_flags:
        kws = "、".join(
            f.get("kw", "?") if isinstance(f, dict) else f[:10] for f in open_flags
        )
        notes.append(
            f"⚠️ 有未确认的安全记录（{kws}）：确认无恙前避免力竭、大重量与独自训练"
        )
    hs = c.get("health_screen") or {}
    positives = [v for v in hs.values() if _is_positive(v)]
    if c.get("health_screen_collected") and positives:
        notes.append(
            f"⚠️ 健康筛查有需要关注项（{'、'.join(str(p)[:15] for p in positives)}）："
            "建议先咨询医生确认运动许可，初期保持中低强度"
        )
    if g.get("primary") == "fat_loss":
        notes.append("减脂期保持训练强度以保肌肉，热量缺口控制在 10-25%")

    # ---- 模板选择 ----
    if days <= 2:
        schedule = [
            {
                "day": f"第 {i + 1} 练",
                "focus": "全身（高强度复合）",
                "exercises": _filter(BUSY_FULL, excluded),
            }
            for i in range(max(days, 1))
        ]
        template = "忙碌高效全身计划（低频次高刺激）"
        notes += [
            "每周 1-2 练时，单次训练质量必须拉满：复合动作为主，60 分钟内完成",
            "建议用拮抗超级组压缩时间（如卧推+下拉交替做）",
            "进步指标看主力动作重量/RPE，不追求单次容量",
        ]
    elif level == "beginner":
        names = ["周一", "周三", "周五"]
        schedule = [
            {
                "day": names[i],
                "focus": "全身 A" if i % 2 == 0 else "全身 B",
                "exercises": _filter(
                    FULL_BODY_A if i % 2 == 0 else FULL_BODY_B, excluded
                ),
            }
            for i in range(min(days, 3))
        ]
        template = "新手全身 A/B（线性进阶：成功完成则下次上肢 +2.5kg、下肢 +5kg）"
    elif level == "intermediate":
        cycle = ["推", "拉", "蹲"]
        schedule = [
            {
                "day": day,
                "focus": cycle[i % 3],
                "exercises": _filter(PPL[cycle[i % 3]], excluded),
            }
            for i, day in enumerate(_names_for(days))
        ]
        template = "三分化推拉蹲（4 周周期：力量 2 周 → 容量 1 周 → 卸载 1 周）"
    else:
        cycle = ["推", "拉", "蹲"]
        schedule = [
            {
                "day": day,
                "focus": cycle[i % 3],
                "exercises": _filter(PPL_ADVANCED[cycle[i % 3]], excluded),
            }
            for i, day in enumerate(_names_for(days))
        ]
        template = "老炮周期化三分化（RPE 驱动 + 高级技术）"
        notes += [
            "第 1-2 周：RPE 8（每组留 2 次余量）；第 3 周：RPE 9 冲击；第 4 周卸载",
            "孤立动作最后一组用递减组；主力动作按周加重 2.5kg",
            "监控恢复：晨起静息心率升高 5+ 或持续疲劳 → 提前卸载",
        ]

    # ---- 停训复训 ramp ----
    if layoff >= 2:
        notes.insert(
            0,
            f"⚠️ 停训 {layoff} 周：第 1-2 周强度降为停训前的 70%，"
            "动作模式优先于重量，第 3 周恢复正常进阶",
        )
        template = "（复训 ramp）" + template

    return {
        "template": template,
        "level": level,
        "days_per_week": days,
        "schedule": schedule,
        "notes": notes,
    }


def plan_to_text(plan: dict) -> str:
    level_label = {
        "beginner": "新手", "intermediate": "进阶", "advanced": "老炮"
    }.get(plan.get("level", ""), plan.get("level", ""))
    lines = [f"模板：{plan['template']}", f"定级：{level_label}", ""]
    for day in plan["schedule"]:
        lines.append(f"【{day['day']} · {day['focus']}】")
        for ex in day["exercises"]:
            note = f"（{ex['note']}）" if ex.get("note") else ""
            lines.append(
                f"  - {ex['name']} {ex['sets']}组 × {ex['reps']}次{note}"
            )
    lines.append("")
    lines += [f"· {n}" for n in plan["notes"]]
    return "\n".join(lines)

