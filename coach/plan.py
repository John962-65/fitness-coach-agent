"""计划生成：槽位式填充（设计书 18.2 / 20.5，R5）

计划 = 博主方法论定骨架（槽位）+ 档案定参数 + 用户数据做个体校准。

槽位 {role, pattern, primary?, default}：role 定组次处方，pattern 定动作模式，
default 是模板默认动作。填槽三步（全部确定性代码，LLM 只负责讲解）：
  1. 硬过滤：场地器械 / level_min / 伤病对应关节压力 / 用户 avoid
  2. 默认优先：默认动作可用就用它（计划稳定）；用户对它报过不适、或它被过滤
     时才替换为打分最高的可用动作
  3. 记录选择理由（why）：替换原因、偏好、发力感——Agent 能讲清楚为什么这样排

伤病从"删掉动作"变成"同模式替代"：腰伤删硬拉，槽位自动落到同 hinge 模式的
替代动作上；没有安全替代时才留空并说明（不再默默练空或静默删掉）。

定级逻辑不变（assess_level：三大项体重倍数 → 训练年限，不采信自述）。
"""
from __future__ import annotations

import copy

from .exercises import library as exercise_lib
from .programming import estimate_minutes, fit_time_budget
from .medical import training_permission
from .profile import _is_positive, open_pain_flags

LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}
PATTERN_LABEL = {
    "squat": "蹲", "hinge": "髋铰链", "lunge": "单侧蹲",
    "h_push": "水平推", "v_push": "垂直推",
    "h_pull": "水平拉", "v_pull": "垂直拉", "isolation": "孤立",
    "core": "核心", "carry": "负重行走",
}
# 伤病描述 → 关节（joint_stress 的 key）；阈值：压力 ≥2 的动作避开
# 注意：没有"腿"这种笼统映射（旧版"腿→knee"会让大腿后侧拉伤的用户被删深蹲、
# 却保留罗马尼亚硬拉）；映射不了的部位会明确告知用户"处理不了"
JOINT_KEYWORDS = {"腰": "lumbar", "下背": "lumbar", "背": "lumbar",
                  "膝": "knee",
                  "肩": "shoulder", "腕": "wrist", "肘": "elbow", "髋": "hip"}
INJURY_STRESS_THRESHOLD = 2

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


# ---- 槽位定义（骨架来自现有模板，default 全部在动作库内） ----

def _slot(role, pattern, default, sets, reps, note="", primary=None):
    return {"role": role, "pattern": pattern, "primary": primary,
            "default": default, "sets": sets, "reps": reps, "note": note}

BUSY_SLOTS = [
    _slot("main", "squat", "barbell_back_squat", 3, "5-8"),
    _slot("main", "h_push", "barbell_bench_press", 3, "6-10"),
    _slot("secondary", "v_pull", "lat_pulldown", 3, "8-12"),
    _slot("main", "hinge", "romanian_deadlift", 2, "8-10"),
    _slot("secondary", "v_push", "overhead_press", 2, "8-12"),
]
FULL_BODY_A = [
    _slot("main", "squat", "barbell_back_squat", 5, "5"),
    _slot("main", "h_push", "barbell_bench_press", 5, "5"),
    _slot("main", "h_pull", "barbell_row", 5, "5"),
]
FULL_BODY_B = [
    _slot("main", "squat", "barbell_back_squat", 5, "5"),
    _slot("main", "v_push", "overhead_press", 5, "5"),
    _slot("main", "hinge", "romanian_deadlift", 3, "8"),
]
PPL_SLOTS = {
    "推": [
        _slot("main", "h_push", "barbell_bench_press", 4, "8-12"),
        _slot("secondary", "h_push", "incline_bench_press", 3, "8-12"),
        _slot("secondary", "v_push", "overhead_press", 3, "8-12"),
        _slot("accessory", "isolation", "lateral_raise", 3, "12-15",
              primary=["side_delt"]),
    ],
    "拉": [
        _slot("main", "hinge", "deadlift", 4, "6-10"),
        _slot("secondary", "h_pull", "seated_row", 4, "10-12"),
        _slot("secondary", "v_pull", "lat_pulldown", 3, "10-12"),
        _slot("accessory", "isolation", "barbell_curl", 3, "10-15",
              primary=["biceps"]),
    ],
    "蹲": [
        _slot("main", "squat", "barbell_back_squat", 4, "8-12"),
        _slot("secondary", "squat", "leg_press", 3, "10-15"),
        _slot("accessory", "isolation", "lying_leg_curl", 3, "12-15",
              primary=["hamstrings"]),
        _slot("accessory", "isolation", "standing_calf_raise", 3, "12-15",
              primary=["calves"]),
    ],
}
PPL_ADVANCED_SLOTS = {
    "推": [
        _slot("main", "h_push", "barbell_bench_press", 4, "5-8",
              note="RPE 8，第 3 周加重"),
        _slot("secondary", "h_push", "incline_bench_press", 3, "8-10", note="RPE 8"),
        _slot("secondary", "v_push", "overhead_press", 3, "6-10", note="RPE 8"),
        _slot("accessory", "isolation", "lateral_raise", 3, "12-20",
              note="最后一组递减组", primary=["side_delt"]),
    ],
    "拉": [
        _slot("main", "hinge", "deadlift", 3, "3-6", note="RPE 8-9，周期化加重"),
        _slot("secondary", "v_pull", "weighted_pull_up", 3, "6-10", note="RPE 8"),
        _slot("secondary", "h_pull", "seated_row", 3, "10-12", note="顶峰收缩 1 秒"),
        _slot("accessory", "h_pull", "face_pull", 3, "15-20",
              note="后束+肩袖健康", primary=["rear_delt"]),
    ],
    "蹲": [
        _slot("main", "squat", "barbell_back_squat", 4, "5-8",
              note="RPE 8，周期化加重"),
        _slot("secondary", "hinge", "romanian_deadlift", 3, "8-10",
              note="腘绳肌主导"),
        _slot("secondary", "lunge", "bulgarian_split_squat", 3, "8-12/侧",
              note="单侧纠正"),
        _slot("accessory", "isolation", "lying_leg_curl", 3, "12-15",
              primary=["hamstrings"]),
    ],
}


# ---- 用户数据与伤病 ----

def _states_by_id(exercise_states) -> dict:
    return {s["exercise_id"]: s for s in (exercise_states or [])
            if isinstance(s, dict) and s.get("exercise_id")}


def _injured_joints(injuries: list) -> tuple[set, list[str]]:
    """伤病描述 → (可映射的关节集合, 无法处理的原始描述列表)。

    映射不了（如"大腿后侧拉伤"）或有映射但库内无该关节压力数据（肘/髋）
    的部位不静默乱猜，交给调用方明确告知用户。
    """
    joints, unknown = set(), []
    for inj in injuries or []:
        text = str(inj).strip()
        if not text:
            continue
        matched = [joint for kw, joint in JOINT_KEYWORDS.items() if kw in text]
        if matched:
            joints.update(matched)
        else:
            unknown.append(text)
    return joints, unknown


def _joints_without_data(joints: set) -> set:
    """approved 动作里没有任何非零压力值的关节（如 elbow/hip）——
    这些关节的伤我们"处理不了"，必须明确告知用户，而不是假装过滤过"""
    has_data = set()
    for ex in exercise_lib.all():
        if ex.get("status") != "approved":
            continue
        for j, v in (ex.get("joint_stress") or {}).items():
            if v:
                has_data.add(j)
    return {j for j in joints if j not in has_data}


def _hard_exclude(ex: dict, profile: dict, states: dict,
                  joints: set, approved_only: bool) -> str | None:
    """返回排除原因；None = 通过。顺序：avoid > 未审核 > 伤病 > 场地器械 > 水平"""
    st = states.get(ex["id"]) or {}
    if st.get("status") == "avoid":
        return "你说过先不练它"
    # 2026-09-29：有伤病时只用已审核动作——draft 的 joint_stress 是 LLM 估的、
    # 未经发起人审核，不能拿它决定伤病用户练什么
    if approved_only and ex.get("status") != "approved":
        return "关节压力数据未经审核，有伤病时不选用"
    level = assess_level(profile)
    if LEVEL_ORDER.get(level, 0) < LEVEL_ORDER.get(ex.get("level_min", "beginner"), 0):
        return f"动作门槛高于当前水平（{ex.get('level_min')} 起）"
    loc = (profile.get("resources", {}) or {}).get("location", "gym")
    if loc not in (ex.get("location") or []):
        return f"场地不匹配（需要 {'/'.join(ex.get('location') or [])}）"
    for joint in joints:
        if (ex.get("joint_stress") or {}).get(joint, 0) >= INJURY_STRESS_THRESHOLD:
            return f"{joint} 压力高（{joint} 有伤）"
    return None


def _score(ex: dict, slot: dict, states: dict, day_muscles: set) -> float:
    st = states.get(ex["id"]) or {}
    score = 0.0
    score += 2.0 * (st.get("preference") or 0)
    score += 1.0 * (st.get("feel") or 0)
    if st.get("discomfort"):
        score -= 1.5
    if slot["role"] == "main" and ex.get("track_e1rm"):
        score += 1.0
    if slot["role"] != "main" and ex.get("fatigue") == "high":
        score -= 0.75
    if slot["primary"]:
        overlap = set(slot["primary"]) & (set(ex.get("primary") or [])
                                          | set(ex.get("secondary") or []))
        if not overlap:
            score -= 2.0  # 不满足槽位目标肌群，重罚
    else:
        overlap = (set(ex.get("primary") or []) | set(ex.get("secondary") or [])) & day_muscles
        if overlap and slot["role"] != "main":
            score -= 0.75  # 同一天肌群重复（多样性）
    return score


def _fill_slot(slot: dict, profile: dict, states: dict, day_muscles: set,
               joints: set, approved_only: bool) -> tuple[dict | None, str]:
    """返回 (动作条目 or None, why)。过滤后无人可选返回 (None, 原因)。"""
    level = assess_level(profile)
    candidates = []
    for ex in exercise_lib.all():
        if ex.get("pattern") != slot["pattern"]:
            continue
        if slot["primary"] and not (set(slot["primary"])
                                    & (set(ex.get("primary") or [])
                                       | set(ex.get("secondary") or []))):
            continue
        reason = _hard_exclude(ex, profile, states, joints, approved_only)
        if reason:
            continue
        candidates.append(ex)
    if not candidates:
        return None, f"{PATTERN_LABEL.get(slot['pattern'], slot['pattern'])}模式无安全替代"

    default = exercise_lib.get(slot["default"])
    picked, why = None, ""
    st_default = states.get(slot["default"]) or {}
    best = max(candidates, key=lambda ex: (_score(ex, slot, states, day_muscles), ex["id"]))
    keep_default = (default in candidates and not st_default.get("discomfort")
                    and _score(default, slot, states, day_muscles) + 0.5
                    >= _score(best, slot, states, day_muscles))
    if keep_default:
        picked = default
        why = f"{PATTERN_LABEL.get(slot['pattern'], slot['pattern'])}模式主推"
    else:
        best = max(candidates,
                   key=lambda ex: (_score(ex, slot, states, day_muscles), ex["id"]))
        picked = best
        parts = []
        if slot["default"] != best["id"]:
            why_default = (_hard_exclude(default, profile, states, joints, approved_only)
                           if default else "不在库中")
            if default and default not in candidates:
                parts.append(f"默认的{default['name']}不可用（{why_default}），"
                             f"换成同模式的{best['name']}")
            elif st_default.get("discomfort"):
                parts.append(f"你说过{default['name']}有不适"
                             f"（{st_default['discomfort']}），换成{best['name']}")
            else:
                parts.append(f"按你的数据选了{best['name']}")
        if (states.get(best["id"]) or {}).get("preference"):
            p = states[best["id"]]["preference"]
            parts.append(f"偏好{'+' if p > 0 else ''}{p}")
        if (states.get(best["id"]) or {}).get("feel"):
            parts.append(f"发力感 {states[best['id']]['feel']}/3")
        why = "；".join(parts) or f"{PATTERN_LABEL.get(slot['pattern'], slot['pattern'])}模式主推"

    entry = {"exercise_id": picked["id"], "name": picked["name"], "role": slot["role"],
             "sets": slot["sets"], "reps": slot["reps"]}
    if slot.get("note"):
        entry["note"] = slot["note"]
    entry["why"] = why
    return entry, why


def _day_names(days: int) -> list[str]:
    """P1：按一周日历均匀展开，不再出现连续两个蹲日"""
    week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    if days >= 7:
        return week
    idx = sorted({round(i * 7 / days) for i in range(days)})
    return [week[i] for i in idx]


def generate_plan(profile: dict, exercise_states=None) -> dict:
    e = profile.get("experience", {})
    r = profile.get("resources", {})
    g = profile.get("goal", {})
    c = profile.get("conditions", {})

    level = assess_level(profile)
    days = r.get("days_per_week") or 3
    minutes = max(0, int(r.get("session_minutes", 60)))
    layoff = e.get("recent_layoff_weeks") or 0
    injuries = "、".join(c.get("injuries") or [])
    states = _states_by_id(exercise_states)

    notes: list[str] = ["每次训练先热身 5-10 分钟，主力动作从小重量组开始"]
    permission = training_permission(profile)
    if not permission.allows_prescription:
        return {
            "template": "（医疗暂停）等待明确训练许可",
            "level": level, "days_per_week": days, "schedule": [],
            "medical_status": permission.status,
            "medical_evidence": permission.evidence,
            "notes": [f"健康筛查：{permission.reason}；"
                      + "、".join(str(v) for k, v in (c.get("health_screen") or {}).items()
                                if k != "clearance" and _is_positive(v)),
                      f"医嘱原话：{permission.evidence or '尚无明确放行'}",
                      "暂停自动训练处方不等于诊断。请与医疗专业人员确认活动范围；"
                      "拿到明确许可后可提出恢复计划，确认后再执行。"],
        }
    joints, unknown_injuries = _injured_joints(c.get("injuries"))
    no_data_joints = _joints_without_data(joints)
    joints -= no_data_joints
    # 有可用伤病关节时，筛选只信任已审核动作（draft 的关节压力未经发起人审核）
    approved_only = bool(joints)
    inj_names = []
    for joint in joints:
        for ex in exercise_lib.all():
            if ex.get("status") != "approved":
                continue
            if (ex.get("joint_stress") or {}).get(joint, 0) >= INJURY_STRESS_THRESHOLD \
                    and ex["name"] not in inj_names:
                inj_names.append(ex["name"])
    if inj_names:
        notes.append(f"因伤病（{injuries}）已剔除动作：{'、'.join(inj_names)}"
                     "，计划里已换成同模式替代")
    # 无法处理的部位（映射不了，或库内无该关节压力数据）：明确告知，不静默乱猜
    cant_handle = list(unknown_injuries)
    if no_data_joints:
        cant_handle.append("、".join(sorted(no_data_joints)) + "（该部位暂无压力数据）")
    if cant_handle:
        notes.append(
            f"⚠️ 伤病部位（{'、'.join(cant_handle)}）我暂时还处理不了："
            "没有可靠的关节压力数据，就不替你乱猜。请告诉我哪些动作会引发不适，"
            "我会按你的反馈逐个避开；这些部位的训练请先咨询医生或康复师"
        )

    open_flags = open_pain_flags(profile)
    if open_flags:
        kws = "、".join(
            f.get("kw", "?") if isinstance(f, dict) else f[:10] for f in open_flags
        )
        notes.append(
            f"⚠️ 有未确认的安全记录（{kws}）：确认无恙前避免力竭、大重量与独自训练"
        )
    hs = c.get("health_screen") or {}
    positives = [v for k, v in hs.items() if k != "clearance" and _is_positive(v)]
    if c.get("health_screen_collected") and positives:
        notes.append(
            f"⚠️ 健康筛查有需要关注项（{'、'.join(str(p)[:15] for p in positives)}）："
            "遵循已经确认的运动许可；如健康状态变化请及时更新"
        )
    if g.get("primary") == "fat_loss":
        notes.append("减脂期保持训练强度以保肌肉，热量缺口控制在 10-25%")

    # ---- 模板与槽位选择 ----
    if days <= 2:
        cycle_slots, day_focus = BUSY_SLOTS, "全身（高强度复合）"
        template = "忙碌高效全身计划（低频次高刺激）"
        notes += [
            "每周 1-2 练时，单次训练质量必须拉满：复合动作为主，60 分钟内完成",
            "建议用拮抗超级组压缩时间（如卧推+下拉交替做）",
            "进步指标看主力动作重量/RPE，不追求单次容量",
        ]
        day_slots = [cycle_slots for _ in range(max(days, 1))]
        names = [f"第 {i + 1} 练" for i in range(max(days, 1))]
    elif level == "beginner":
        ab = [FULL_BODY_A, FULL_BODY_B]
        day_slots = [ab[i % 2] for i in range(min(days, 3))]
        names = _day_names(min(days, 3))
        day_focus = ["全身 A", "全身 B"] * 2
        template = "新手全身 A/B（线性进阶：成功完成则下次上肢 +2.5kg、下肢 +5kg）"
    elif level == "intermediate":
        cycle = ["推", "拉", "蹲"]
        day_slots = [PPL_SLOTS[cycle[i % 3]] for i in range(days)]
        names = _day_names(days)
        day_focus = [cycle[i % 3] for i in range(days)]
        template = "三分化推拉蹲（4 周周期：力量 2 周 → 容量 1 周 → 卸载 1 周）"
    else:
        cycle = ["推", "拉", "蹲"]
        day_slots = [PPL_ADVANCED_SLOTS[cycle[i % 3]] for i in range(days)]
        names = _day_names(days)
        day_focus = [cycle[i % 3] for i in range(days)]
        template = "老炮周期化三分化（RPE 驱动 + 高级技术）"
        notes += [
            "第 1-2 周：RPE 8（每组留 2 次余量）；第 3 周：RPE 9 冲击；第 4 周卸载",
            "孤立动作最后一组用递减组；主力动作按周加重 2.5kg",
            "监控恢复：晨起静息心率升高 5+ 或持续疲劳 → 提前卸载",
        ]

    schedule = []
    for i, slots in enumerate(day_slots):
        picked, muscles = [], set()
        focus = day_focus[i] if isinstance(day_focus, list) else day_focus
        for slot in slots:
            entry, _why = _fill_slot(slot, profile, states, muscles,
                                     joints, approved_only)
            if entry is None:
                suffix = ("（已审核动作中没有更安全的选项，宁可空着也不用未审核的数据凑数）"
                          if approved_only else "")
                notes.append(f"⚠️ {names[i]}的{PATTERN_LABEL.get(slot['pattern'], slot['pattern'])}"
                             f"类动作暂缺：{_why}{suffix}")
                continue
            # 记录当日已覆盖肌群（多样性打分用）
            ex = exercise_lib.get(_id_of(entry["name"])) or {}
            muscles |= set(ex.get("primary") or [])
            picked.append(entry)
        picked, time_changes = fit_time_budget(picked, minutes)
        if time_changes:
            notes.append(f"{names[i]}（{minutes}分钟预算）：" + "；".join(time_changes))
        schedule.append({"day": names[i], "focus": focus, "exercises": picked,
                         "estimated_minutes": estimate_minutes(picked)})

    # 修复意见第 6 条后半（发起人 2026-10-11 整批授权，取决策清单建议项 B）：
    # 无伤病时处方域不锁 approved，但选中 draft 动作须在计划里明示其结构化属性未经审核
    draft_selected = []
    for day in schedule:
        for entry in day["exercises"]:
            ex = exercise_lib.get(_id_of(entry["name"])) or {}
            if ex.get("status") != "approved" and ex.get("name") not in draft_selected:
                draft_selected.append(ex.get("name") or entry["name"])
    if draft_selected:
        notes.append(
            "ℹ️ 以下动作的结构化属性（关节压力/替代关系）尚未经审核，"
            "伤病筛选未依赖其数据：" + "、".join(draft_selected))

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
        "medical_status": "allowed",
        "level": level,
        "days_per_week": days,
        "requested_days_per_week": days,
        "time_budget_minutes": minutes,
        # C2 目标版本绑定：计划记录它是在哪一版已确认目标下生成的（26.4 步骤⑤）
        "goal_version": int((g.get("version") or 0)),
        "schedule": schedule,
        "notes": notes,
    }


def regenerate_plan_preserve(profile: dict, exercise_states,
                             old_plan: dict | None, reason: str = "") -> dict:
    """整体重排计划（个性化闭环：反馈/伤病/场地/天数变化后）。

    重排时保留两类个体数据，不能每次重排都推倒重来：
    - 已有处方重量 weight_kg（按动作 id 匹配拷贝到新计划同名动作上）
    - 卸载周状态 deload（仍在有效期的卸载不因重排丢失）
    """
    old_plan = old_plan or {}
    effective = copy.deepcopy(profile)
    requested_days = (profile.get("resources") or {}).get("days_per_week") or 3
    prior_requested = old_plan.get("requested_days_per_week", old_plan.get("days_per_week"))
    actual_days = len(old_plan.get("schedule", []))
    if actual_days and requested_days == prior_requested:
        effective.setdefault("resources", {})["days_per_week"] = actual_days
    new = generate_plan(effective, exercise_states=exercise_states)
    new["requested_days_per_week"] = requested_days
    previous: dict[str, list[dict]] = {}
    for day in old_plan.get("schedule", []):
        for ex in day.get("exercises", []):
            ex_id = ex.get("exercise_id") or _id_of(ex.get("name", ""))
            if ex_id:
                previous.setdefault(ex_id, []).append(ex)
    time_changed = new.get("time_budget_minutes", 60) != old_plan.get("time_budget_minutes", 60)
    used = {}
    for day in new["schedule"]:
        for ex in day["exercises"]:
            ex_id = ex.get("exercise_id") or _id_of(ex["name"])
            prior = previous.get(ex_id)
            if not prior:
                continue
            i = used.get(ex_id, 0)
            saved = prior[min(i, len(prior) - 1)]
            used[ex_id] = i + 1
            fields = ["weight_kg"]
            if not time_changed and new.get("level") == old_plan.get("level"):
                fields += ["sets", "reps"]
            for field in fields:
                if saved.get(field) is not None:
                    ex[field] = saved[field]
        day["exercises"], changes = fit_time_budget(day["exercises"], new.get("time_budget_minutes", 60))
        day["estimated_minutes"] = estimate_minutes(day["exercises"])
        if changes:
            new["notes"].append("重排时间取舍：" + "；".join(changes))
    if old_plan.get("deload"):
        new["deload"] = copy.deepcopy(old_plan["deload"])
    new["adjust_action"] = "regenerate_plan"
    new["adjust_reason"] = reason
    return new


def _id_of(name: str) -> str:
    ex_id, _, _ = exercise_lib.normalize(name)
    return ex_id or ""


def plan_to_text(plan: dict) -> str:
    from datetime import date

    from .validate import round_half

    level_label = {
        "beginner": "新手", "intermediate": "进阶", "advanced": "老炮"
    }.get(plan.get("level", ""), plan.get("level", ""))
    lines = [f"模板：{plan.get('template', '自定义计划')}", f"定级：{level_label}", ""]
    deload = plan.get("deload") or {}
    until = deload.get("until", "")
    deload_active = bool(until) and until >= date.today().isoformat()
    factor = deload.get("factor", 0.5)
    for day in plan["schedule"]:
        lines.append(f"【{day['day']} · {day['focus']}】")
        if day.get("estimated_minutes") is not None:
            lines.append(f"  时间估算：约 {day['estimated_minutes']} 分钟（含热身与休息，非用时保证）")
        for ex in day["exercises"]:
            w = ex.get("weight_kg")
            if w and deload_active:
                wtext = f" {round_half(w * factor)}kg（卸载周，至 {until[5:]}）"
            elif w:
                wtext = f" {w}kg"
            else:
                wtext = ""
            note = f"（{ex['note']}）" if ex.get("note") else ""
            lines.append(
                f"  - {ex['name']}{wtext} {ex['sets']}组 × {ex['reps']}次{note}"
            )
            if ex.get("why") and ex["why"] != f"{PATTERN_LABEL.get('', '')}模式主推" \
                    and "主推" not in ex["why"]:
                lines.append(f"    · 为什么是它：{ex['why']}")
    lines.append("")
    lines += [f"· {n}" for n in plan.get("notes", [])]
    return "\n".join(lines)
