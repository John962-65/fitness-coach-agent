"""计划生成与定级逻辑单元测试（含 R0 新增：安全记录/健康筛查注意项）"""
from coach.plan import assess_level, generate_plan, plan_to_text


def mk(**over):
    p = {
        "basic": {"weight_kg": 80, "gender": "男", "age": 28, "height_cm": 178},
        "experience": {"training_years": 0, "level": "beginner", "big3": {},
                       "recent_layoff_weeks": 0},
        "goal": {"primary": "muscle_gain"},
        "conditions": {"injuries": [], "injuries_collected": True},
        "resources": {"location": "gym", "days_per_week": 4, "session_minutes": 60},
    }
    for section, values in over.items():
        p[section].update(values)
    return p


# ---- 定级 ----

def test_assess_level_by_big3():
    assert assess_level(mk(experience={"big3": {"squat": 130}})) == "advanced"
    assert assess_level(mk(experience={"big3": {"squat": 90}})) == "intermediate"
    assert assess_level(mk(experience={"big3": {"squat": 50}})) == "beginner"


def test_assess_level_by_years():
    assert assess_level(mk(experience={"training_years": 5})) == "advanced"
    assert assess_level(mk(experience={"training_years": 2})) == "intermediate"
    assert assess_level(mk()) == "beginner"


# ---- 忙碌计划 ----

def test_busy_plan():
    busy = generate_plan(mk(experience={"big3": {"squat": 130}},
                            resources={"days_per_week": 1}))
    assert "忙碌" in busy["template"]
    assert len(busy["schedule"]) == 1
    assert any("超级组" in n for n in busy["notes"])
    busy2 = generate_plan(mk(experience={"big3": {"squat": 130}},
                             resources={"days_per_week": 2}))
    assert len(busy2["schedule"]) == 2


# ---- 老炮 / 新手模板 ----

def test_advanced_plan():
    adv = generate_plan(mk(experience={"big3": {"squat": 130}}))
    assert "老炮周期化" in adv["template"]
    assert any("RPE" in (e.get("note") or "")
               for d in adv["schedule"] for e in d["exercises"])
    assert any("递减组" in n for n in adv["notes"])


def test_beginner_plan():
    nov = generate_plan(mk(experience={"big3": {"squat": 50}}))
    assert "新手全身" in nov["template"]


# ---- 停训 ramp ----

def test_layoff_ramp():
    lay = generate_plan(mk(experience={"big3": {"squat": 130},
                                      "recent_layoff_weeks": 3}))
    assert "复训 ramp" in lay["template"]
    assert any("70%" in n for n in lay["notes"])
    assert "停训 3 周" in lay["notes"][0]


# ---- 伤病剔除 ----

def test_injury_exclusion():
    inj = generate_plan(mk(conditions={"injuries": ["膝"], "injuries_collected": True},
                           experience={"big3": {"squat": 130}}))
    names = [e["name"] for d in inj["schedule"] for e in d["exercises"]]
    assert "杠铃深蹲" not in names
    assert any("剔除" in n for n in inj["notes"])


# ---- R0-S3：安全记录接入计划 ----

def test_open_pain_flag_adds_caution_note():
    p = mk(conditions={
        "injuries": [], "injuries_collected": True,
        "pain_flags": [{"at": "2026-09-26T10:00:00", "text": "胸闷", "kw": "胸闷",
                        "tier": "emergency", "mode": "block", "status": "open"}],
    })
    plan = generate_plan(p)
    assert any("安全记录" in n and "胸闷" in n for n in plan["notes"])


def test_resolved_pain_flag_no_note():
    p = mk(conditions={
        "injuries": [], "injuries_collected": True,
        "pain_flags": [{"at": "2026-09-26T10:00:00", "text": "胸闷", "kw": "胸闷",
                        "tier": "emergency", "mode": "block", "status": "resolved"}],
    })
    plan = generate_plan(p)
    assert not any("安全记录" in n for n in plan["notes"])


# ---- R0-S5：健康筛查接入计划 ----

def test_positive_health_screen_adds_note():
    p = mk(conditions={
        "injuries": [], "injuries_collected": True,
        "health_screen_collected": True,
        "health_screen": {"heart": "高血压", "medication": "无"},
    })
    plan = generate_plan(p)
    assert any("健康筛查" in n and "高血压" in n for n in plan["notes"])


# ---- PAR-Q 阳性 + 医生未放行 → 医疗降级（2026-09-29） ----

def test_parq_positive_without_clearance_waits_for_permission():
    """阳性且尚无明确许可：暂停自动处方，不用低强度替代医疗评估。"""
    p = mk(experience={"big3": {"squat": 130}},  # 老炮也一样降级
           conditions={
               "injuries": [], "injuries_collected": True,
               "health_screen_collected": True,
               "health_screen": {"heart": "冠心病史", "medication": "无"},
           })
    plan = generate_plan(p)
    assert plan["medical_status"] == "pending" and plan["schedule"] == []
    assert "老炮周期化" not in plan["template"]
    text = plan_to_text(plan)
    assert "RPE 9" not in text and "冲击" not in text
    assert any("放行" in n for n in plan["notes"])


def test_parq_limited_clearance_does_not_unlock_normal_plan():
    """仅允许中等强度不等于允许 RPE 9；有限许可不自动生成力量处方。"""
    p = mk(experience={"big3": {"squat": 130}},
           conditions={
               "injuries": [], "injuries_collected": True,
               "health_screen_collected": True,
               "health_screen": {"heart": "高血压",
                                 "clearance": "医生允许中等强度运动"},
           })
    plan = generate_plan(p)
    assert plan["medical_status"] == "limited" and plan["schedule"] == []
    assert "RPE 9" not in plan_to_text(plan)
    assert any("健康筛查" in n for n in plan["notes"])  # 注意项保留


def test_parq_clearance_wu_is_not_clearance():
    """clearance 填"无"只是没有限制记录，不等于放行 → 仍降级"""
    p = mk(experience={"big3": {"squat": 130}},
           conditions={
               "injuries": [], "injuries_collected": True,
               "health_screen_collected": True,
               "health_screen": {"heart": "冠心病史", "clearance": "无"},
           })
    plan = generate_plan(p)
    assert plan["medical_status"] == "pending" and plan["schedule"] == []


def test_clean_health_screen_no_note():
    p = mk(conditions={
        "injuries": [], "injuries_collected": True,
        "health_screen_collected": True,
        "health_screen": {"heart": "无", "medication": "无"},
    })
    plan = generate_plan(p)
    assert not any("健康筛查" in n for n in plan["notes"])


def test_is_positive_negative_phrasings():
    """阴性回答的各种写法都不能算阳性（评测抓到"没问题"被误判降级）"""
    from coach.profile import _is_positive
    for neg in ("无", "没有", "没问题", "正常", "没事", "没怀孕", "都正常",
                "都没问题", "无异常", "否", "没有心脏病", "心脏血压都正常",
                "身体健康", "一切正常", "不适用（男性）", "不适用",
                "未怀孕、未备孕", "无心血管疾病史、无高血压",
                "身体健康，无心血管疾病史/高血压"):
        assert not _is_positive(neg), neg
    for pos in ("高血压", "冠心病史", "在吃降压药", "心电图不正常",
                "医生嘱咐限制运动", "怀孕 3 个月"):
        assert _is_positive(pos), pos


def test_healthy_user_not_medical_downgraded():
    """健康筛查全阴（各种阴性写法）→ 不触发医疗降级"""
    p = mk(experience={"big3": {"squat": 130}},
           conditions={
               "injuries": [], "injuries_collected": True,
               "health_screen_collected": True,
               "health_screen": {"heart": "没问题", "medication": "没吃药",
                                 "clearance": "医生没说过不让运动"},
           })
    plan = generate_plan(p)
    assert "医疗降级" not in plan["template"]


# ---- 输出渲染 ----

def test_plan_to_text():
    adv = generate_plan(mk(experience={"big3": {"squat": 130}}))
    text = plan_to_text(adv)
    assert "定级：老炮" in text
    assert "杠铃平板卧推" in text


# ---- R5：槽位式填充（用户数据驱动 + 伤病同模式替代 + P1 排日） ----

def _states(rows):
    from datetime import datetime
    out = []
    for ex_id, kw in rows:
        r = {"exercise_id": ex_id, "updated_at": datetime.now().isoformat()}
        r.update(kw)
        out.append(r)
    return out


def test_injury_substitutes_same_pattern():
    """膝伤：深蹲被剔除后，蹲槽位只在已审核动作里找替代；
    已审核蹲类全是膝压 ≥2 时槽位诚实留空并说明，不用未审核 draft 凑数"""
    adv = mk(experience={"big3": {"squat": 130}},
             conditions={"injuries": ["膝"], "injuries_collected": True})
    plan = generate_plan(adv)
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    assert "杠铃深蹲" not in names
    whys = [e.get("why", "") for d in plan["schedule"] for e in d["exercises"]]
    # 要么换到同模式替代，要么槽位暂缺并在 notes 里说明
    assert any("不可用" in w or "换" in w for w in whys) \
        or any("暂缺" in n for n in plan["notes"])


def test_injured_user_never_gets_draft_exercises():
    """2026-09-29：有伤病时 draft 动作一律不入选（其关节压力是 LLM 估的、未审核）"""
    from coach.exercises import library
    adv = mk(experience={"big3": {"squat": 130}},
             conditions={"injuries": ["膝"], "injuries_collected": True})
    plan = generate_plan(adv)
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    drafts = {ex["name"] for ex in library.all() if ex.get("status") != "approved"}
    assert not (set(names) & drafts), f"伤病用户计划混入未审核动作: {set(names) & drafts}"


def test_unknown_injury_part_disclosed_not_guessed():
    """"大腿后侧拉伤"不映射任何关节：不静默删深蹲（旧版"腿→knee"误映射），
    而是明确告知用户这个部位处理不了"""
    adv = mk(experience={"big3": {"squat": 130}},
             conditions={"injuries": ["大腿后侧拉伤"], "injuries_collected": True})
    plan = generate_plan(adv)
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    assert "杠铃深蹲" in names  # 不映射 knee，深蹲不应被误删
    assert any("处理不了" in n for n in plan["notes"])


def test_elbow_injury_disclosed_no_data():
    """肘伤：库里没有肘部压力数据 → 明确告知，不过滤动作也不装死"""
    adv = mk(experience={"big3": {"squat": 130}},
             conditions={"injuries": ["肘"], "injuries_collected": True})
    plan = generate_plan(adv)
    assert any("处理不了" in n or "暂无压力数据" in n for n in plan["notes"])


def test_no_injury_draft_still_available():
    """无伤病时 draft 动作照常可用（居家用户的自重/哑铃动作都在 draft）"""
    plan = generate_plan(mk(resources={"location": "home", "days_per_week": 4}))
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    assert names, "无伤病居家计划不应为空"


def test_avoid_status_excludes_and_substitutes():
    """用户明确 avoid 的动作不出现在计划里，且槽位有替代"""
    states = _states([("barbell_bench_press", {"status": "avoid", "evidence": "先不练这个"})])
    plan = generate_plan(mk(), exercise_states=states)
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    assert "杠铃平板卧推" not in names
    whys = " ".join(e.get("why", "") for d in plan["schedule"] for e in d["exercises"])
    assert "先不练" in whys or "换" in whys


def test_discomfort_drives_substitution():
    """对默认动作报过不适 → 换成替代动作并解释"""
    states = _states([("barbell_bench_press", {"discomfort": "肩前侧不适", "evidence": "卧推肩膀疼"})])
    plan = generate_plan(mk(), exercise_states=states)
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    assert "杠铃平板卧推" not in names
    assert any("不适" in e.get("why", "")
               for d in plan["schedule"] for e in d["exercises"])


def test_six_day_no_consecutive_leg_days():
    """P1：每周 6 练的推拉蹲，蹲日不连续"""
    plan = generate_plan(mk(experience={"big3": {"squat": 130}},
                            resources={"days_per_week": 6}))
    days = [d["day"] for d in plan["schedule"] if d["focus"] == "蹲"]
    week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    idx = sorted(week.index(d) for d in days)
    assert all(b - a >= 2 for a, b in zip(idx, idx[1:]))


def test_choices_deterministic():
    """同输入两次生成，计划完全一致（确定性）"""
    import json
    a = json.dumps(generate_plan(mk()), ensure_ascii=False, sort_keys=True)
    b = json.dumps(generate_plan(mk()), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_home_user_gets_plan_with_reasons():
    """居家用户：杠铃动作被场地过滤，应有可用的自重/哑铃替代与解释"""
    plan = generate_plan(mk(experience={"big3": {"squat": 130}},
                            resources={"location": "home",
                                       "days_per_week": 4}))
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    assert names, "居家计划不应为空"
    assert "杠铃深蹲" not in names and "杠铃平板卧推" not in names
    whys = " ".join(e.get("why", "") for d in plan["schedule"] for e in d["exercises"])
    assert "不可用" in whys or "换" in whys
