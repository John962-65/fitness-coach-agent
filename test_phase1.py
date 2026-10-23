"""Phase 1 测试：SQLite 四表 + Onboarding（含 PAR-Q 健康筛查）+ 计划生成 + 打卡落库"""
import tempfile
from pathlib import Path

from coach.agent import CoachAgent


def _mk(uid="p1_test"):
    tmp_db = Path(tempfile.mkdtemp()) / "test.db"
    agent = CoachAgent(user_id=uid, db_path=tmp_db)
    return agent, tmp_db


def test_four_tables_exist():
    agent, _ = _mk()
    tables = {
        r[0]
        for r in agent.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"users", "plans", "checkins", "messages"} <= tables


def test_onboarding_flow_with_health_screen():
    agent, _ = _mk()
    assert not agent.profile.get("onboarding_done")

    r = agent.chat("你好")
    assert len(r) > 0

    agent.chat("我叫阿明，男，28岁，178cm，85kg")
    assert agent.profile["basic"]["age"] == 28
    assert agent.profile["basic"]["gender"] == "男"
    assert agent.profile["basic"]["height_cm"] == 178
    assert agent.profile["basic"]["weight_kg"] == 85

    agent.chat("我想减脂，每周能练3天")
    assert agent.profile["goal"]["primary"] == "fat_loss"
    assert agent.profile["resources"]["days_per_week"] == 3

    # 各项都有明确回答后，才允许完成健康筛查。
    agent.chat("我没有任何伤病，没有心血管疾病或高血压，不适用怀孕，没有长期用药，医生没有限制运动")
    assert agent.profile["conditions"]["injuries_collected"]
    assert agent.profile["conditions"]["health_screen_collected"]
    assert agent.profile.get("onboarding_done") is True


def test_onboarding_blocked_without_health_screen():
    """S5：只答伤病史、没做健康筛查时不能结束建档"""
    from coach.onboarding import can_finish
    profile = {
        "basic": {"age": 28, "gender": "男", "height_cm": 178, "weight_kg": 85},
        "goal": {"primary": "fat_loss"},
        "resources": {"days_per_week": 3},
        "conditions": {"injuries": [], "injuries_collected": True},
    }
    ok, why = can_finish(profile)
    assert not ok and "健康筛查" in why


def test_plan_generated_after_onboarding():
    agent, _ = _mk()
    for msg in ("你好", "我叫阿明，男，28岁，178cm，85kg",
                "我想减脂，每周能练3天", "我没有任何伤病，没有心血管疾病或高血压，不适用怀孕，没有长期用药，医生没有限制运动"):
        agent.chat(msg)
    plan = agent.db.get_active_plan("p1_test")
    assert plan is not None
    assert len(plan["schedule"]) == 3
    assert any("减脂" in n for n in plan["notes"])


def test_checkin_persisted():
    agent, _ = _mk()
    for msg in ("你好", "男，28岁，178cm，85kg", "我想减脂，每周能练3天",
                "我没有任何伤病，没有心血管疾病或高血压，不适用怀孕，没有长期用药，医生没有限制运动"):
        agent.chat(msg)
    agent.chat("今天深蹲80kg做了5组5次，最后一组很吃力")
    checkins = agent.db.list_checkins("p1_test")
    assert len(checkins) == 1
    assert checkins[0]["type"] == "training"
    assert checkins[0]["data"]["exercises"][0]["weight_kg"] == 80.0


def test_red_flag_and_message_persistence():
    agent, _ = _mk()
    for msg in ("你好", "男，28岁，178cm，85kg", "我想减脂，每周能练3天",
                "我没有任何伤病，没有心血管疾病或高血压，不适用怀孕，没有长期用药，医生没有限制运动"):
        agent.chat(msg)
    r = agent.chat("我练的时候突然胸闷")
    assert "就医" in r and "120" in r
    flags = agent.profile["conditions"]["pain_flags"]
    assert flags and flags[-1]["kw"] == "胸闷" and flags[-1]["status"] == "open"
    msgs = agent.db.recent_messages("p1_test", 100)
    assert len(msgs) >= 8


def test_restart_restores_state():
    _, tmp_db = _mk()
    agent = CoachAgent(user_id="p1_test", db_path=tmp_db)
    for msg in ("你好", "男，28岁，178cm，85kg", "我想减脂，每周能练3天",
                "我没有任何伤病，没有心血管疾病或高血压，不适用怀孕，没有长期用药，医生没有限制运动"):
        agent.chat(msg)

    agent2 = CoachAgent(user_id="p1_test", db_path=tmp_db)
    assert agent2.profile["basic"]["age"] == 28
    assert agent2.profile["onboarding_done"] is True
    assert len(agent2.messages) > 1
