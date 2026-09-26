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


def test_clean_health_screen_no_note():
    p = mk(conditions={
        "injuries": [], "injuries_collected": True,
        "health_screen_collected": True,
        "health_screen": {"heart": "无", "medication": "无"},
    })
    plan = generate_plan(p)
    assert not any("健康筛查" in n for n in plan["notes"])


# ---- 输出渲染 ----

def test_plan_to_text():
    adv = generate_plan(mk(experience={"big3": {"squat": 130}}))
    text = plan_to_text(adv)
    assert "定级：老炮" in text
    assert "杠铃平板卧推" in text
