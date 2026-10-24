"""M4 动作视频分析 Web 化回归（DESIGN_2.0 §八/§十三 M4 任务 1-8）。

关键点提取用 monkeypatch 注入合成姿态序列（真实规则引擎照跑，确定性）；
验收红线：不支持动作/低质量/不可判断必须如实提示，不以正确率包装。
"""
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach import motion_analysis as ma
from coach.motion_analysis import (compare_results, process_analysis,
                                   rules_name, segment_reps)
from test_repair_regressions import profile


# ---- 合成侧面深蹲姿态：N 次"下-上"循环 ----

def squat_frame(hip_y: float) -> list[dict]:
    """33 点骨架的极简侧面：肩(12) 髋(24) 膝(26) 踝(28) + 可见性 1。"""
    lm = [{"x": 0, "y": 0, "visibility": 0.0, "aspect_ratio": 1.0} for _ in range(33)]
    for i, (x, y) in {12: (0.5, 0.20), 24: (0.5, 0.45 + hip_y), 26: (0.5, 0.65),
                      28: (0.5, 0.85), 11: (0.5, 0.20), 23: (0.5, 0.45 + hip_y),
                      25: (0.5, 0.65), 27: (0.5, 0.85)}.items():
        lm[i] = {"x": x, "y": y, "visibility": 1.0, "aspect_ratio": 1.0}
    return lm


def squat_indexed(reps: int, deep: bool, frames_per_rep: int = 10,
                  sample_every: int = 2, fps: float = 25.0):
    """生成 reps 次蹲起：deep=True 髋过膝，False 浅蹲。"""
    low = 0.22 if deep else 0.02     # 髋相对膝(0.65)的下移量
    seq = []
    for r in range(reps):
        for j in range(frames_per_rep):
            t = j / frames_per_rep
            depth = low if 0.25 <= t <= 0.75 else low * max(0.0, 1 - 4 * abs(t - 0.5))
            seq.append(squat_frame(depth * (1 if 0.15 <= t <= 0.85 else 0.2)))
    return [(i * sample_every, kp) for i, kp in enumerate(seq)], fps


# ---- 单元 ----

def test_rules_name_mapping():
    assert rules_name("barbell_back_squat") == "squat"
    assert rules_name("romanian_deadlift") == "romanian_deadlift"
    assert rules_name("plank") is None                    # 俯卧撑/平板不在首批


def test_segment_reps_counts_cycles():
    indexed, fps = squat_indexed(reps=3, deep=True)
    reps = segment_reps("squat", indexed, fps)
    assert len(reps) == 3
    assert reps[0]["start_s"] <= reps[0]["peak_s"] <= reps[0]["end_s"]
    assert segment_reps("squat", indexed[:4], fps) == []  # 帧太少不猜


def test_process_analysis_deep_vs_shallow(monkeypatch):
    indexed, fps = squat_indexed(reps=2, deep=True)
    monkeypatch.setattr(
        "coach.vision.extract_keypoints_indexed", lambda p, s=2: (indexed, fps, len(indexed)))
    deep = process_analysis("barbell_back_squat", "v.mp4", "side")
    assert deep["supported"] and deep["frames"] == len(indexed)
    assert len(deep["reps"]) == 2
    assert not any(f["code"] == "SQUAT_SHALLOW" for f in deep["faults"])

    shallow_idx, _ = squat_indexed(reps=2, deep=False)
    monkeypatch.setattr(
        "coach.vision.extract_keypoints_indexed",
        lambda p, s=2: (shallow_idx, fps, len(shallow_idx)))
    shallow = process_analysis("barbell_back_squat", "v.mp4", "side")
    assert any(f["code"] == "SQUAT_SHALLOW" for f in shallow["faults"])


def test_process_analysis_unsupported_and_no_person(monkeypatch):
    unsupported = process_analysis("plank", "v.mp4", "side")
    assert unsupported["supported"] is False and "暂不在" in unsupported["note"]
    monkeypatch.setattr(
        "coach.vision.extract_keypoints_indexed", lambda p, s=2: ([], 25.0, 100))
    empty = process_analysis("barbell_back_squat", "v.mp4", "side")
    assert empty["frames"] == 0 and "不可判断" in empty["note"]


def test_compare_results_deterministic_diff():
    a = {"supported": True, "frames": 40, "faults": [{"code": "SQUAT_SHALLOW"},
                                                     {"code": "SQUAT_VALGUS"}],
         "reps": [{}, {}], "summary": {"signal_min": 1.0, "signal_max": 3.0}}
    b = {"supported": True, "frames": 44, "faults": [{"code": "SQUAT_SHALLOW"}],
         "reps": [{}, {}, {}], "summary": {"signal_min": 1.2, "signal_max": 3.4}}
    out = compare_results(a, b)
    assert out["faults_fixed"] == ["SQUAT_VALGUS"]
    assert out["faults_persist"] == ["SQUAT_SHALLOW"]
    assert out["reps"] == {"a": 2, "b": 3}
    assert out["summary_delta"]["signal_min"] == {"a": 1.0, "b": 1.2}
    assert compare_results(a, {"supported": False, "faults": []})["error"]


# ---- API（monkeypatch 提取层，规则引擎真实跑）----

@pytest.fixture()
def m4client(tmp_path, monkeypatch):
    indexed, fps = squat_indexed(reps=2, deep=True)
    monkeypatch.setattr(
        "coach.vision.extract_keypoints_indexed", lambda p, s=2: (indexed, fps, len(indexed)))
    app = create_app(db_path=tmp_path / "api.db")
    with TestClient(app) as c:
        app.state.db.save_profile("m4u", profile())
        yield c, tmp_path


def _tiny_video(path):
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, timeout=60)
    assert r.returncode == 0
    return path


def _wait(c, aid, tries=20):
    for _ in range(tries):
        items = c.get("/api/users/m4u/motion-analyses").json()["analyses"]
        me = next(x for x in items if x["id"] == aid)
        if me["status"] != "processing":
            return me
        time.sleep(0.3)
    raise AssertionError("分析任务未完成")


def test_api_upload_ready_timeline_and_compare(m4client):
    c, tmp = m4client
    video = _tiny_video(tmp / "sq.mp4")
    with open(video, "rb") as f:
        up = c.post("/api/users/m4u/motion-analyses",
                    files={"video": ("sq.mp4", f, "video/mp4")},
                    data={"exercise_id": "barbell_back_squat", "view": "side"})
    assert up.status_code == 200
    done = _wait(c, up.json()["analysis_id"])
    assert done["status"] == "ready"
    result = done["result"]
    assert result["supported"] and result["frames"] > 0
    assert len(result["reps"]) == 2 and result["reps"][0]["start_s"] >= 0
    assert done["video_path"]                                   # 时间轴可跳视频
    # 第二次（同样合成数据）→ 对比
    with open(video, "rb") as f:
        up2 = c.post("/api/users/m4u/motion-analyses",
                     files={"video": ("sq2.mp4", f, "video/mp4")},
                     data={"exercise_id": "barbell_back_squat", "view": "side"})
    _wait(c, up2.json()["analysis_id"])
    cmp_resp = c.get("/api/users/m4u/motion-analyses/compare",
                     params={"a": up.json()["analysis_id"],
                             "b": up2.json()["analysis_id"]})
    body = cmp_resp.json()
    assert cmp_resp.status_code == 200
    assert body["compare"]["reps"] == {"a": 2, "b": 2}
    assert "不构成动作质量评分" in body["compare"]["note"]


def test_api_unsupported_exercise_is_explicit(m4client):
    c, tmp = m4client
    video = _tiny_video(tmp / "p.mp4")
    with open(video, "rb") as f:
        up = c.post("/api/users/m4u/motion-analyses",
                    files={"video": ("p.mp4", f, "video/mp4")},
                    data={"exercise_id": "plank", "view": "side"})
    done = _wait(c, up.json()["analysis_id"])
    assert done["status"] == "ready"
    assert done["result"]["supported"] is False
    # 跨动作对比被拒
    other = c.get("/api/users/m4u/motion-analyses/compare",
                  params={"a": 1, "b": 2})
    assert other.status_code in (404, 422)
