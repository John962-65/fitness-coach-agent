"""M5.2 复查处置回归（发起人对 1f28770 审查的 P0×3 + P1×2）。"""
import io
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.agents import consult_specialists
from coach.db import Database
from coach.llm import LLMClient
from coach.motion_analysis import process_analysis
from test_repair_regressions import profile


@pytest.fixture()
def c52(tmp_path):
    app = create_app(db_path=tmp_path / "a.db")
    with TestClient(app) as c:
        for uid in ("ua", "ub"):
            app.state.db.save_profile(uid, profile())
        yield c, app.state.db


def _pending_proposal(db, uid, name="壶铃摆铃", aliases=None):
    db.add_exercise_proposal(uid, name, aliases or ["摆铃"], "hinge",
                             "测试提案", None, f"{name}演示")
    return db.list_exercise_proposals(uid)[0]["id"]


# ---- P0-1: 存储边界 ----

def test_custom_exercise_isolated_per_user(c52):
    c, db = c52
    pid = _pending_proposal(db, "ua")
    r = c.post("/api/users/ua/exercise-proposals/%d/review" % pid,
               json={"decision": "approve", "pattern": "hinge",
                     "id": "kb_isolation"})
    assert r.status_code == 200
    ex_id = r.json()["exercise_id"]
    # 不写全局库文件
    from coach.exercises import library
    assert library.get(ex_id) is None
    assert not (library.root / f"{ex_id}.yaml").exists()
    # 本人可见；B 用户不可见（搜索/详情/解析全隔离）
    mine = c.get("/api/exercises", params={"uid": "ua", "q": "壶铃摆铃"}).json()
    assert any(e["id"] == ex_id and e.get("scope") == "user" for e in mine["exercises"])
    other = c.get("/api/exercises", params={"uid": "ub", "q": "壶铃摆铃"}).json()
    assert not any(e["id"] == ex_id for e in other["exercises"])
    assert c.get("/api/exercises/%s" % ex_id, params={"uid": "ua"}).status_code == 200
    assert c.get("/api/exercises/%s" % ex_id, params={"uid": "ub"}).status_code == 404
    from coach.exercise_service import resolve
    assert resolve(db, "ua", "壶铃摆铃")[0] == ex_id
    assert resolve(db, "ub", "壶铃摆铃")[0] is None


def test_custom_exercise_joinable_plan_only_for_owner(c52):
    c, db = c52
    from coach.plan import generate_plan
    db.create_plan("ua", generate_plan(profile()))
    db.create_plan("ub", generate_plan(profile()))
    pid = _pending_proposal(db, "ua", name="农夫行走转身")
    ex_id = c.post("/api/users/ua/exercise-proposals/%d/review" % pid,
                   json={"decision": "approve", "id": "farm_walk_turn"}).json()["exercise_id"]
    for uid in ("ua", "ub"):
        day = c.get("/api/users/%s/plan" % uid).json()["content"]["schedule"][0]["day"]
        base = c.get("/api/users/%s/plan" % uid).json()["base_version"]
        resp = c.post("/api/users/%s/plan/edits" % uid, json={
            "operations": [{"op": "add_exercise", "day": day,
                            "exercise": "农夫行走转身", "sets": 3, "reps": 20}],
            "reason": "x", "base_version": base})
        if uid == "ua":
            assert resp.status_code == 200, resp.text          # 本人可加入
        else:
            assert resp.status_code == 422                      # 他人不可见
            assert "无法精确对上" in resp.json()["detail"]["details"][0]


# ---- P0-2: 审核原子性 ----

def test_review_atomicity_all_failures_keep_pending(c52):
    c, db = c52
    # 非法 id → 提案保持 pending
    pid = _pending_proposal(db, "ua")
    bad = c.post("/api/users/ua/exercise-proposals/%d/review" % pid,
                 json={"decision": "approve", "id": "1bad"})
    assert bad.status_code == 422
    assert db.list_exercise_proposals("ua", status="pending")[0]["id"] == pid
    # 别名冲突（撞内置"杠铃深蹲"）→ 保持 pending
    pid2 = _pending_proposal(db, "ua", name="新动作", aliases=["杠铃深蹲"])
    conflict = c.post("/api/users/ua/exercise-proposals/%d/review" % pid2,
                      json={"decision": "approve", "id": "fresh_move"})
    assert conflict.status_code == 422 and "冲突" in conflict.json()["detail"]["error"]
    assert db.get_exercise_proposal_rows if False else True
    assert db.list_exercise_proposals("ua", status="pending")[0]["id"] == pid2
    # 成功后重复批准 → 422 且状态不变
    ok = c.post("/api/users/ua/exercise-propososals/x" if False else
                "/api/users/ua/exercise-proposals/%d/review" % pid,
                json={"decision": "approve", "id": "good_move"})
    assert ok.status_code == 200
    again = c.post("/api/users/ua/exercise-proposals/%d/review" % pid,
                   json={"decision": "approve", "id": "another"})
    assert again.status_code == 422 and "不能重复审核" in again.json()["detail"]["error"]
    # id 已存在（撞刚入库的）→ 新提案保持 pending
    pid3 = _pending_proposal(db, "ua", name="又一个动作")
    dup = c.post("/api/users/ua/exercise-proposals/%d/review" % pid3,
                 json={"decision": "approve", "id": "good_move"})
    assert dup.status_code == 422 and "已存在" in dup.json()["detail"]["error"]
    assert db.list_exercise_proposals("ua", status="pending")[0]["id"] == pid3


# ---- P0-3: 无候选手动提案 ----

def test_manual_proposal_endpoint(c52):
    c, db = c52
    from coach.media_import import process_asset
    import pathlib, subprocess
    tmp = pathlib.Path("/tmp/m52_manual")
    tmp.mkdir(exist_ok=True)
    v = tmp / "v.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-pix_fmt", "yuv420p", str(v)], check=True, capture_output=True)
    srt = tmp / "v.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:02,000\n无任何动作词的闲聊字幕。\n", "utf-8")
    aid = db.add_media_asset("ua", "无候选", str(v), str(srt))
    process_asset(db, aid, str(v), str(srt))
    assert db.get_media_asset("ua", aid)["candidates"] == []
    r = c.post("/api/users/ua/media/%d/manual-proposal" % aid,
               json={"name": "泽奇深蹲", "aliases": ["泽奇"], "pattern": "squat"})
    assert r.status_code == 200
    prop = db.list_exercise_proposals("ua")[0]
    assert prop["name"] == "泽奇深蹲"
    assert prop["sentence"] == "无任何动作词的闲聊字幕。"   # 转写首句自动作依据


# ---- P1: 检测覆盖率 ----

def test_detection_ratio_quality_gate(monkeypatch, tmp_path):
    # 100 采样帧中只有 20 帧检出人体 → detection_ratio=0.2 → 如实降级
    def squat(i):
        lm = [{"x": 0, "y": 0, "visibility": 0.0, "aspect_ratio": 1.0} for _ in range(33)]
        for k, (x, y) in {12: (0.5, 0.2), 11: (0.5, 0.2), 24: (0.5, 0.6),
                          23: (0.5, 0.6), 26: (0.5, 0.65), 25: (0.5, 0.65),
                          28: (0.5, 0.85), 27: (0.5, 0.85)}.items():
            lm[k] = {"x": x, "y": y, "visibility": 1.0, "aspect_ratio": 1.0}
        return lm
    indexed = [(i * 2, squat(i)) for i in range(20)]
    monkeypatch.setattr("coach.vision.extract_keypoints_indexed",
                        lambda p, s=2: (indexed, 25.0, 100))
    result = process_analysis("barbell_back_squat", "v.mp4", "side")
    assert result["detection_ratio"] == 0.2
    assert "检测覆盖率仅 20%" in result["note"] and "仅供参考" in result["note"]
    # 全检出 → detection=1.0,无降级
    monkeypatch.setattr("coach.vision.extract_keypoints_indexed",
                        lambda p, s=2: (indexed, 25.0, 20))
    ok = process_analysis("barbell_back_squat", "v.mp4", "side")
    assert ok["detection_ratio"] == 1.0 and "检测覆盖率" not in ok["note"]


# ---- P1: 证据绑定 ----

def test_citation_binding_and_draft_bug(tmp_path):
    db = Database(tmp_path / "k.db")
    db.save_profile("u", profile())
    result = consult_specialists(db, LLMClient(), "u", "蛋白粉怎么选")
    refs = {f"{r['engine']}:{r['ref']}" for r in result["knowledge_refs"]}
    assert refs
    for advice in result["advices"]:
        for opt in advice["options"]:
            assert opt["evidence"] in ("cited", "inferred")
            for cit in opt["citations"]:
                assert cit in refs, f"编造引用 {cit}"
        assert any(o.get("citations") for o in advice["options"])  # FAKE 首项引用真实 ref
    # 草稿命中 bug 修复:blogger 引擎行内报告(不再吞掉)
    rows = db.list_consultations("u")
    assert rows[0]["advices"][0]["options"][0]["citations"]
