"""M5.1 集成稳定性回归（发起人审查 P0-1..P1-5 处置）。

- P0-2 上传加固：大小限制/魔数/配额/重启恢复（线程独立连接与信号量由
  实现承担，此处验行为边界）；
- P1-2 入库闭环：提案审核 → YAML 入库 → library 运行时可见 → 可加入计划
  → link 拒绝库外动作；
- P1-3 周期方向：铰链与卧推合成周期起止方向修正 + 有效帧比例质量门；
- P1-4 专家知识检索注入：consult 返回 knowledge_refs 并留痕；
- P1-5 媒体签名：发放→访问→过期拒绝，长期令牌入 URL 已弃用。
"""
import io
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend import routes as routes_mod
from backend.app import create_app
from coach.agents import consult_specialists
from coach.db import Database
from coach.llm import LLMClient
from coach.motion_analysis import process_analysis, segment_reps
from test_repair_regressions import profile


def _mp4_bytes(path):
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, timeout=60)
    assert r.returncode == 0
    return path.read_bytes()


@pytest.fixture()
def c51(tmp_path, monkeypatch):
    # 缩小限额便于测试
    monkeypatch.setattr(routes_mod, "MAX_VIDEO_BYTES", 64 * 1024)
    monkeypatch.setattr(routes_mod, "MAX_USER_MEDIA_FILES", 3)
    from coach.plan import generate_plan
    app = create_app(db_path=tmp_path / "api.db")
    with TestClient(app) as c:
        app.state.db.save_profile("u", profile())
        app.state.db.create_plan("u", generate_plan(profile()))
        yield c, tmp_path, monkeypatch


# ---- P0-2 ----

def test_upload_rejects_oversize(c51):
    c, tmp, _ = c51
    big = b"\x00\x00\x00\x20ftypisom" + b"x" * (200 * 1024)
    r = c.post("/api/users/u/media/videos",
               files={"video": ("big.mp4", io.BytesIO(big), "video/mp4")},
               data={"title": "big"})
    assert r.status_code == 422 and "大小限制" in r.json()["detail"]["error"]
    assert not list((tmp / "api.db").parent.joinpath("media", "u").glob("big*"))


def test_upload_rejects_bad_magic(c51):
    c, _, _ = c51
    fake = b"just some plain text pretending to be a video file" * 10
    r = c.post("/api/users/u/media/videos",
               files={"video": ("fake.mp4", io.BytesIO(fake), "video/mp4")},
               data={"title": "fake"})
    assert r.status_code == 422 and "视频容器" in r.json()["detail"]["error"]


def test_upload_quota_by_file_count(c51, tmp_path):
    c, tmp, _ = c51
    mp4 = _mp4_bytes(tmp_path := tmp / "ok.mp4")
    for i in range(3):  # MAX_USER_MEDIA_FILES=3（字幕文件也计入目录用量）
        r = c.post("/api/users/u/media/videos",
                   files={"video": (f"v{i}.mp4", io.BytesIO(mp4), "video/mp4")},
                   data={"title": f"v{i}"})
        assert r.status_code == 200, r.text
    r = c.post("/api/users/u/media/videos",
               files={"video": ("v9.mp4", io.BytesIO(mp4), "video/mp4")},
               data={"title": "v9"})
    assert r.status_code == 422 and "文件数已达上限" in r.json()["detail"]["error"]


def test_restart_marks_processing_failed(tmp_path):
    db = Database(tmp_path / "a.db")
    db.save_profile("u", profile())
    aid = db.add_media_asset("u", "x", "/nonexistent.mp4", None)
    mid = db.add_motion_analysis("u", "barbell_back_squat", "side", "/nonexistent.mp4")
    db.conn.close()
    app = create_app(db_path=tmp_path / "a.db")  # 启动即恢复
    with TestClient(app) as c:
        assets = c.get("/api/users/u/media/videos").json()["assets"]
        assert assets[0]["status"] == "failed"
        assert "服务重启" in assets[0]["error"]
        analyses = c.get("/api/users/u/motion-analyses").json()["analyses"]
        assert analyses[0]["status"] == "failed" and "服务重启" in analyses[0]["error"]


# ---- P1-2 ----

def test_proposal_approve_enters_library_and_plan(c51, tmp_path):
    c, tmp, _ = c51
    # 造提案：上传带"壶铃摆铃"字幕的视频 → 无候选 → 直接 API 造提案
    db = c.app.state.db
    import time as _t
    ex_id_req = f"kb_swing_{_t.time():.0f}"          # 每次唯一,防残留冲突
    db.add_exercise_proposal("u", "壶铃摆铃", ["摆铃"], "hinge",
                             "用户视频提案", None, "画面里演示了壶铃摆铃")
    pid = db.list_exercise_proposals("u")[0]["id"]
    try:
        r = c.post(f"/api/users/u/exercise-proposals/{pid}/review",
                   json={"decision": "approve", "pattern": "hinge",
                         "id": ex_id_req})
        assert r.status_code == 200, r.text
        ex_id = r.json()["exercise_id"]
        # 1) library 运行时可见
        from coach.exercises import library
        assert library.get(ex_id) and library.normalize("壶铃摆铃")[0] == ex_id
        # 2) 统一检索/动作搜索可见
        found = c.get("/api/exercises", params={"q": "壶铃摆铃"}).json()
        assert any(e["id"] == ex_id for e in found["exercises"])
        # 3) 可加入计划（draft 披露由既有机制承担）
        plan = c.get("/api/users/u/plan").json()
        day = plan["content"]["schedule"][0]["day"]
        added = c.post("/api/users/u/plan/edits", json={
            "operations": [{"op": "add_exercise", "day": day,
                            "exercise": "壶铃摆铃", "sets": 3, "reps": 12}],
            "reason": "新动作入库试用",
            "base_version": plan["base_version"]})
        assert added.status_code == 200, added.text
        # 4) 库校验器仍全绿（生成 YAML 合法）
        from tools.validate import validate
        assert validate(library.root) == []
    finally:
        # 清理生成的测试动作文件,不影响其他测试
        (library.root / f"{ex_id_req}.yaml").unlink(missing_ok=True)
        library.reload()


def test_link_rejects_unknown_exercise(c51, tmp_path):
    c, tmp, _ = c51
    mp4 = _mp4_bytes(tmp / "v.mp4")
    srt = "1\n00:00:00,500 --> 00:00:03,000\n今天讲杠铃深蹲的标准动作。\n"
    up = c.post("/api/users/u/media/videos",
                files={"video": ("v.mp4", io.BytesIO(mp4), "video/mp4"),
                       "subtitle": ("s.srt", io.BytesIO(srt.encode()), "application/x-subrip")},
                data={"title": "t"})
    import time
    for _ in range(20):
        me = next(a for a in c.get("/api/users/u/media/videos").json()["assets"]
                  if a["id"] == up.json()["asset_id"])
        if me["status"] != "processing":
            break
        time.sleep(0.3)
    r = c.post(f"/api/users/u/media/{up.json()['asset_id']}/candidates/0/confirm",
               json={"action": "link", "exercise_id": "ghost_exercise"})
    assert r.status_code == 422 and "不在动作库内" in r.json()["detail"]["error"]


# ---- P1-3 ----

def hinge_frame(trunk_angle_deg: float) -> list[dict]:
    """侧面骨架：肩(12) 髋(24) 膝(26) 踝(28)——按躯干-髋-膝角放置肩点。"""
    import math
    lm = [{"x": 0, "y": 0, "visibility": 0.0, "aspect_ratio": 1.0} for _ in range(33)]
    hip = (0.50, 0.50)
    knee = (0.50, 0.68)
    ank = (0.50, 0.86)
    rad = math.radians(trunk_angle_deg)
    shoulder = (hip[0] + 0.28 * math.cos(rad), hip[1] - 0.28 * math.sin(rad))
    for i, p in {12: shoulder, 24: hip, 26: knee, 28: ank,
                 11: shoulder, 23: hip, 25: knee, 27: ank}.items():
        lm[i] = {"x": p[0], "y": p[1], "visibility": 1.0, "aspect_ratio": 1.0}
    return lm


def bench_frame(elbow_deg: float) -> list[dict]:
    import math
    lm = [{"x": 0, "y": 0, "visibility": 0.0, "aspect_ratio": 1.0} for _ in range(33)]
    sh = (0.40, 0.50)
    el = (0.50, 0.50 + 0.12 * math.sin(math.radians(elbow_deg)))
    wr = (0.50 + 0.12 * math.cos(math.radians(elbow_deg)), 0.50 + 0.12)
    for i, p in {12: sh, 14: el, 16: wr, 11: sh, 13: el, 15: wr}.items():
        lm[i] = {"x": p[0], "y": p[1], "visibility": 1.0, "aspect_ratio": 1.0}
    return lm


def _indexed(frames, sample_every=2, fps=25.0):
    return [(i * sample_every, kp) for i, kp in enumerate(frames)], fps


def test_hinge_and_bench_rep_direction():
    # 铰链：直立(角大)↔俯身(角小) 三个周期 → 3 次且 start<end
    seq = []
    for _ in range(3):
        seq += [hinge_frame(160), hinge_frame(140), hinge_frame(110),
                hinge_frame(90), hinge_frame(110), hinge_frame(140), hinge_frame(160)]
    idx, fps = _indexed(seq)
    reps = segment_reps("romanian_deadlift", idx, fps)
    assert len(reps) == 3
    assert all(r["start_s"] <= r["peak_s"] <= r["end_s"] for r in reps)
    # 卧推：肘角 大→小→大 两个周期
    bseq = []
    for _ in range(2):
        bseq += [bench_frame(160), bench_frame(120), bench_frame(80),
                 bench_frame(60), bench_frame(90), bench_frame(150)]
    bidx, bfps = _indexed(bseq)
    breps = segment_reps("bench", bidx, bfps)
    assert len(breps) == 2


def test_quality_gate_low_valid_ratio(monkeypatch):
    frames = [squat_like(0.2)] * 6 + [empty_frame()] * 6  # 一半帧无关键点
    idx, fps = _indexed(frames)
    monkeypatch.setattr("coach.vision.extract_keypoints_indexed",
                        lambda p, s=2: (idx, fps))
    result = process_analysis("barbell_back_squat", "v.mp4", "side")
    assert result["frames"] == 12
    assert result["valid_ratio"] == 0.5
    low = [f for f in frames[:6]]
    idx2, _ = _indexed(low + [empty_frame()] * 9)  # 6/15=0.4
    monkeypatch.setattr("coach.vision.extract_keypoints_indexed",
                        lambda p, s=2: (idx2, fps))
    low_result = process_analysis("barbell_back_squat", "v.mp4", "side")
    assert low_result["valid_ratio"] < 0.5
    assert "有效帧比例" in low_result["note"]


def squat_like(hip_delta):
    lm = [{"x": 0, "y": 0, "visibility": 0.0, "aspect_ratio": 1.0} for _ in range(33)]
    for i, (x, y) in {12: (0.5, 0.2), 11: (0.5, 0.2), 24: (0.5, 0.45 + hip_delta),
                      23: (0.5, 0.45 + hip_delta), 26: (0.5, 0.65), 25: (0.5, 0.65),
                      28: (0.5, 0.85), 27: (0.5, 0.85)}.items():
        lm[i] = {"x": x, "y": y, "visibility": 1.0, "aspect_ratio": 1.0}
    return lm


def empty_frame():
    return [{"x": 0, "y": 0, "visibility": 0.0, "aspect_ratio": 1.0} for _ in range(33)]


# ---- P1-4 ----

def test_consult_injects_knowledge_refs(tmp_path):
    db = Database(tmp_path / "k.db")
    db.save_profile("u", profile())
    result = consult_specialists(db, LLMClient(), "u", "减脂平台期怎么办")
    assert result["consulted"]  # 平台期 → training_science/knowledge
    assert result["knowledge_refs"], "专家建议必须带知识来源"
    engines = {r["engine"] for r in result["knowledge_refs"]}
    assert engines & {"knowledge_md", "blogger_claims", "coach_cards", "user_imports"}
    rows = db.list_consultations("u")
    assert rows[0]["advices"][0]["knowledge_refs"]  # 留痕可追溯


# ---- P1-5 ----

def test_media_signed_url_flow(tmp_path):
    app = create_app(db_path=tmp_path / "s.db", access_token="sec")
    with TestClient(app) as c:
        app.state.db.save_profile("u", profile())
        # 造一个媒体文件
        media = tmp_path / "media" / "u"
        media.mkdir(parents=True)
        (media / "cover.jpg").write_bytes(b"jpgdata")
        # 无令牌 → 401
        assert c.get("/api/media/u/cover.jpg").status_code == 401
        # 长期令牌入 URL 已弃用 → 仍 401
        assert c.get("/api/media/u/cover.jpg",
                     params={"access_token": "sec"}).status_code == 401
        # 签名发放需令牌头
        assert c.get("/api/users/u/media-sign", params={"name": "cover.jpg"}).status_code == 401
        sgn = c.get("/api/users/u/media-sign", params={"name": "cover.jpg"},
                    headers={"X-Access-Token": "sec"}).json()
        assert sgn["sig"] and sgn["ttl"] == 600
        ok = c.get(f"/api/media/u/cover.jpg?sig={sgn['sig']}&exp={sgn['exp']}")
        assert ok.status_code == 200 and ok.content == b"jpgdata"
        # 过期签名拒绝
        expired = c.get(f"/api/media/u/cover.jpg?sig={sgn['sig']}&exp=1")
        assert expired.status_code == 401
        # 篡改路径签名不匹配
        tampered = c.get(f"/api/media/u/other.jpg?sig={sgn['sig']}&exp={sgn['exp']}")
        assert tampered.status_code in (401, 404)
