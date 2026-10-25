"""P4 回归：动作技术工作台后端链路。

覆盖任务书场景 B/D/E 的后端断言与 §七 自动化要求：
五动作支持 / 视频质量门与观察结构 / 技术档案（单一历史）/ 洞察（教学
审核状态如实声明、无三维力矩、康复限制联动）/ 漂移失效 / 删除与隔离 /
模型版本。视频分析流程复用 test_m4 的 monkeypatch 关键点提取。
"""
import json
import pytest
from datetime import date
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.db import Database
from coach.experts import insight_service, registry, task_dispatcher
from coach.movement.analysis import analyze_movement_review
from coach.motion_analysis import (ANALYSIS_MODEL_VERSION, build_observations,
                                   process_analysis, rules_name)
from test_m4 import squat_indexed
from test_repair_regressions import profile

TODAY = date.today().isoformat()
DEMO_FIVE = ("barbell_back_squat", "barbell_bench_press", "deadlift",
             "barbell_row", "dumbbell_shoulder_press")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    indexed, fps = squat_indexed(reps=2, deep=True)
    monkeypatch.setattr(
        "coach.vision.extract_keypoints_indexed",
        lambda p, s=2: (indexed, fps, len(indexed)))
    app = create_app(db_path=tmp_path / "p4.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.save_profile("other", profile())
        yield c, db


# ---- P4-0：五动作全覆盖 ----

def test_all_five_demo_exercises_supported():
    for ex in DEMO_FIVE:
        assert rules_name(ex), f"{ex} 应在视频分析支持范围"
    assert rules_name("plank") is None  # 范围外如实不支持
    assert registry.SPECIALISTS["movement"]["workbench"] == "ready"
    # 观察生成纪律：视角限制声明永远在
    obs = build_observations("squat", "side", *squat_indexed(1, True)[:2], [], [],
                             {"signal_min": 1})
    assert any("二维投影角" in o["text"] for o in obs)


def test_row_and_press_period_segmentation():
    """划船/肩推用肘角信号切周期（与 bench 同一确定性机制）。"""
    from coach.motion_analysis import segment_reps

    def press_frame(bent: bool):
        """肩(12)-肘(14)-腕(16) 简化侧面：bent=屈肘下放（小角度），伸直=推起。"""
        lm = [{"x": 0.5, "y": 0, "visibility": 1.0, "aspect_ratio": 1.0}
              for _ in range(33)]
        lm[12] = {"x": 0.5, "y": 0.30, "visibility": 1.0, "aspect_ratio": 1.0}
        if bent:   # 屈肘：肘向下略外，腕向内收 → 肘角小
            lm[14] = {"x": 0.46, "y": 0.42, "visibility": 1.0, "aspect_ratio": 1.0}
            lm[16] = {"x": 0.44, "y": 0.32, "visibility": 1.0, "aspect_ratio": 1.0}
        else:      # 推起：肘腕竖直在肩上方 → 肘角≈180
            lm[14] = {"x": 0.5, "y": 0.18, "visibility": 1.0, "aspect_ratio": 1.0}
            lm[16] = {"x": 0.5, "y": 0.06, "visibility": 1.0, "aspect_ratio": 1.0}
        lm[11], lm[13], lm[15] = lm[12], lm[14], lm[16]
        return lm
    seq = []
    for _rep in range(2):
        seq += [press_frame(True)] * 5 + [press_frame(False)] * 5  # 下放-推起 x2
    indexed, fps = [(i * 2, kp) for i, kp in enumerate(seq)], 25.0
    reps = segment_reps("shoulder_press", indexed, fps)
    assert len(reps) == 2


# ---- 场景 B：上传→质量→观察→洞察（可追溯） ----

def test_scenario_b_upload_profile_and_insight(client):
    c, db = client
    import io
    import subprocess
    video = "/tmp/p4-test-video.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-pix_fmt", "yuv420p", video], check=True, timeout=60)
    with open(video, "rb") as f:
        resp = c.post("/api/users/u/motion-analyses",
                      files={"video": ("squat.mp4", f, "video/mp4")},
                      data={"exercise_id": "barbell_back_squat", "view": "side"})
    assert resp.status_code == 200
    aid = resp.json()["analysis_id"]
    # worker 为后台线程：轮询等待分析完成并建立技术档案（1:1，单一历史）
    import time
    profile_data = None
    for _ in range(40):
        me = next((a for a in c.get("/api/users/u/motion-analyses").json()["analyses"]
                   if a["id"] == aid), None)
        profile_data = db.get_motion_tech_profile("u", aid)
        if me and me["status"] != "processing" and profile_data:
            break
        time.sleep(0.25)
    assert profile_data, "worker 完成后应建立技术档案"
    assert profile_data["video_quality"]["status"] == "usable"
    assert profile_data["video_quality"]["view"] == "side"
    assert any("二维投影角" in o["text"]
               for o in profile_data["motion_observations"])
    # API 附带档案
    detail = next(a for a in c.get("/api/users/u/motion-analyses").json()["analyses"]
                  if a["id"] == aid)
    assert detail["tech_profile"]["video_quality"]["status"] == "usable"
    # 洞察：观察引用档案；draft 教学如实声明；无三维力矩；无法判断声明
    res = task_dispatcher.run_task(db, task_dispatcher.enqueue(
        db, "u", "movement", "movement-review", "UserRequested",
        {"analysis_id": aid}))
    ins = res["insight"]
    assert ins["confidence"] == "medium"
    assert any("不足以作为" in f["text"] for f in ins["findings"])  # draft 教学
    assert ins["knowledge_refs"] == []  # draft 不得作为引用依据
    assert any(f["kind"] == "unable-to-judge" for f in ins["findings"])
    # 排除"无法判断"声明本身（那里是对测不了什么的否定性说明）
    text_all = " ".join(f["text"] for f in ins["findings"]
                        if f["kind"] != "unable-to-judge") + ins["summary"]
    for term in ("力矩", "腰椎损伤", "半月板"):
        assert term not in text_all
    snap_ids = {f["fact_id"] for f in ins["facts_snapshot"]["facts"]}
    assert set(ins["evidence_refs"]) <= snap_ids


# ---- 质量门：关键点缺失降级 ----

def test_keypoint_missing_degrades_not_fabricates(tmp_path):
    """关键点缺失时不输出精确角度（P4-2）。"""
    monkey_indexed = ([(0, [])], 25.0, 1)  # 无人体(indexed, fps, total_sampled)
    import coach.vision as vision
    orig = vision.extract_keypoints_indexed
    vision.extract_keypoints_indexed = lambda p, s=2: monkey_indexed
    try:
        result = process_analysis("barbell_back_squat", "/tmp/x.mp4", "side")
    finally:
        vision.extract_keypoints_indexed = orig
    assert result["detection_ratio"] == 0.0
    assert result["reps"] == [] and "不可判断" in result["note"]
    obs = build_observations("squat", "side", monkey_indexed[0],
                             monkey_indexed[1], [], [], {})
    assert any(o["kind"] == "insufficient" for o in obs)


def test_poor_quality_insight_suggests_rerecord(tmp_path):
    db = Database(tmp_path / "q.db")
    db.save_profile("u", profile())
    aid = db.conn.execute(
        "INSERT INTO motion_analyses(user_id, exercise_id, view, video_path,"
        " status, result, created_at) VALUES('u','barbell_back_squat','side',"
        "'/tmp/x.mp4','ready',?,?)",
        (json.dumps({"supported": True, "frames": 3, "detection_ratio": 0.3,
                     "valid_ratio": 0.2, "faults": [], "reps": []}),
         "2026-10-25T10:00:00")).lastrowid
    db.conn.commit()
    db.upsert_motion_tech_profile("u", aid, "barbell_back_squat", {
        "model_version": ANALYSIS_MODEL_VERSION,
        "video_quality": {"status": "poor", "view": "side",
                          "detection_ratio": 0.3, "valid_ratio": 0.2,
                          "limitations": ["可见关键点不足"]},
        "motion_observations": [{"kind": "insufficient", "text": "无观察结果"}],
        "phase_timestamps": []})
    ins = analyze_movement_review(db, "u", {"analysis_id": aid})
    assert ins["confidence"] == "low"
    assert ins["options"][0]["option_id"] == "re-record"
    assert any(f["kind"].startswith("observation/insufficient")
               for f in ins["findings"])


# ---- 场景 D：长期档案（历史/对比/漂移/删除） ----

def test_scenario_d_history_drift_delete_and_isolation(client):
    c, db = client
    # 两个假分析（直接落库；上传链路已被场景 B 覆盖）
    def seed(version_suffix, status="usable"):
        aid = db.conn.execute(
            "INSERT INTO motion_analyses(user_id, exercise_id, view, video_path,"
            " status, result, created_at) VALUES('u','barbell_back_squat','side',"
            "'/tmp/x.mp4','ready',?,?)",
            (json.dumps({"supported": True, "frames": 30, "reps": [
                {"rep": 1, "start_s": 1.0, "end_s": 2.0, "peak_s": 1.5}]}),
             f"2026-10-{version_suffix}T10:00:00")).lastrowid
        db.conn.commit()
        db.upsert_motion_tech_profile("u", aid, "barbell_back_squat", {
            "model_version": ANALYSIS_MODEL_VERSION,
            "video_quality": {"status": status, "view": "side",
                              "detection_ratio": 0.9, "valid_ratio": 0.9,
                              "limitations": []},
            "motion_observations": [{"kind": "rep-count", "text": f"v{version_suffix}"}],
            "phase_timestamps": [{"rep": 1, "start_s": 1.0, "end_s": 2.0,
                                  "peak_s": 1.5}]})
        return aid
    aid1, aid2 = seed(20), seed(24)
    listed = c.get("/api/users/u/motion-analyses").json()["analyses"]
    assert len(listed) == 2 and all(a["tech_profile"] for a in listed)
    # 对比接口可比性（既有 compare_results）
    cmp = c.get(f"/api/users/u/motion-analyses/compare?a={aid1}&b={aid2}").json()
    assert "compare" in cmp
    # 洞察失效：档案重算（同内容长度不同）→ 旧洞察失效
    res = task_dispatcher.run_task(db, task_dispatcher.enqueue(
        db, "u", "movement", "movement-review", "UserRequested",
        {"analysis_id": aid1}))
    ins = res["insight"]
    db.upsert_motion_tech_profile("u", aid1, "barbell_back_squat", {
        "model_version": ANALYSIS_MODEL_VERSION,
        "video_quality": {"status": "usable", "view": "side"},
        "motion_observations": [{"kind": "rep-count", "text": "重算后观察不同了x"}],
        "phase_timestamps": [{"rep": 1, "start_s": 1.0, "end_s": 2.0, "peak_s": 1.5}]})
    stale = insight_service.get_insight(db, "u", ins["id"])
    assert stale["status"] == "invalidated" and "视频档案" in stale["status_reason"]
    # 删除：档案与分析一起删；洞察引用已删数据
    assert c.delete(f"/api/users/u/motion-analyses/{aid2}").status_code == 200
    assert db.get_motion_tech_profile("u", aid2) is None
    assert c.get(f"/api/users/other/motion-analyses").json()["analyses"] == []
    assert c.delete(f"/api/users/other/motion-analyses/{aid1}").status_code == 404
    # 用户备注
    assert c.post(f"/api/users/u/motion-analyses/{aid1}/notes",
                  json={"notes": "感觉这次深度不错"}).status_code == 200
    assert db.get_motion_tech_profile("u", aid1)["user_notes"] == "感觉这次深度不错"


# ---- 场景 E：康复安全联动 ----

def test_scenario_e_rehab_restriction_shown_not_bypassed(tmp_path):
    db = Database(tmp_path / "e.db")
    db.save_profile("u", profile())
    from coach.rehab import restriction_service
    restriction_service.create_restriction(db, "u", {
        "source_type": "professional",
        "source_evidence": "李医生:膝部两周内避免深蹲类动作",
        "affected_activities": {"regions": ["knee"], "movements": []},
        "restriction_description": "膝部两周内避免深蹲类动作"})
    aid = db.conn.execute(
        "INSERT INTO motion_analyses(user_id, exercise_id, view, video_path,"
        " status, result, created_at) VALUES('u','barbell_back_squat','side',"
        "'/tmp/x.mp4','ready',?,?)",
        (json.dumps({"supported": True, "frames": 30, "reps": [], "faults": []}),
         "2026-10-25T10:00:00")).lastrowid
    db.conn.commit()
    db.upsert_motion_tech_profile("u", aid, "barbell_back_squat", {
        "model_version": ANALYSIS_MODEL_VERSION,
        "video_quality": {"status": "usable", "view": "side"},
        "motion_observations": [{"kind": "rep-count", "text": "1 个周期"}],
        "phase_timestamps": []})
    ins = analyze_movement_review(db, "u", {"analysis_id": aid})
    kinds = [f["kind"] for f in ins["findings"]]
    assert "safety-restriction" in kinds  # 限制在洞察中只读展示
    # 不生成训练修改建议（options 无 proposal 类型；无一键改计划）
    assert all(o.get("action") != "proposal" for o in ins["options"])
    assert all("提案" not in o["title"] for o in ins["options"])
    text_all = " ".join(f["text"] for f in ins["findings"])
    assert "遵循限制" in text_all or "遵循限制" in str(
        [o["detail"] for o in ins["options"]])
    # 限制不被分析取消
    assert len(db.list_restrictions("u", "active")) == 1
    # 限制版本变化 → 洞察失效
    ins_id = None
    from coach.experts import task_dispatcher as td
    res = td.run_task(db, td.enqueue(db, "u", "movement", "movement-review",
                                     "UserRequested", {"analysis_id": aid}))
    ins_id = res["insight"]["id"]
    restriction_service.lift_restriction(
        db, "u", db.list_restrictions("u", "active")[0]["id"], 0,
        "复诊时李医生确认膝部恢复良好,可逐步恢复深蹲类动作", "复诊结论")
    stale = insight_service.get_insight(db, "u", ins_id)
    assert stale["status"] == "invalidated" and "限制" in stale["status_reason"]


def test_model_version_recorded_and_immutable_semantics():
    """模型版本进档案；升级语义：跨版本数值不解释为动作变化（文档纪律）。"""
    assert "mediapipe" in ANALYSIS_MODEL_VERSION
    assert "vision-rules" in ANALYSIS_MODEL_VERSION
