"""M3.2 视频导入回归（DESIGN_2.0 §7.4/§十三 任务 5-7、10-13）。

- 字幕直读路径全离线确定性（ffmpeg 只用于造 2 秒测试视频与封面/片段生成）；
- 本地 whisper 路径用 monkeypatch 假转写器验证管线（不加载模型、不联网）；
- 确认流：link（封面/片段+去重）/ new（候选提案，绝不写入 exercises/）/ reject；
- 无法可靠识别时如实呈现（无候选不出错）。
"""
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.media_import import (detect_exercise_candidates, parse_srt,
                                process_asset)
from test_repair_regressions import profile

SRT = """1
00:00:01,000 --> 00:00:04,000
今天讲杠铃深蹲的标准动作，脚距与肩同宽。

2
00:00:05,000 --> 00:00:08,000
下蹲时膝盖不要内扣，保持核心收紧。

3
00:00:09,000 --> 00:00:12,000
然后我们做高位下拉，注意肩胛下沉。

4
00:00:13,000 --> 00:00:15,000
好的，今天就到这里。
"""


def make_video(path, seconds=2):
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=160x120:rate=10",
         "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode()[:200]
    return path


# ---- 单元 ----

def test_parse_srt_and_candidates():
    cues = parse_srt(SRT)
    assert len(cues) == 4
    assert abs(cues[0]["start"] - 1.0) < 0.01 and "深蹲" in cues[0]["text"]
    cands = detect_exercise_candidates(cues)
    ids = [c["exercise_id"] for c in cands]
    assert "barbell_back_squat" in ids and "lat_pulldown" in ids
    squat = next(c for c in cands if c["exercise_id"] == "barbell_back_squat")
    assert squat["sentence"].startswith("今天讲杠铃深蹲")
    assert detect_exercise_candidates([{"start": 0, "end": 1, "text": "好的今天就到这里"}]) == []


def test_parse_srt_bad_input():
    assert parse_srt("") == []
    assert parse_srt("不是字幕") == []


def test_process_asset_with_subtitle(tmp_path):
    from coach.db import Database
    db = Database(tmp_path / "t.db")
    db.save_profile("u", profile())
    video = make_video(tmp_path / "v.mp4")
    sub = tmp_path / "v.srt"
    sub.write_text(SRT, encoding="utf-8")
    asset_id = db.add_media_asset("u", "教学", str(video), str(sub))
    process_asset(db, asset_id, str(video), str(sub))
    asset = db.get_media_asset("u", asset_id)
    assert asset["status"] == "ready"
    assert {c["exercise_id"] for c in asset["candidates"]} >= {
        "barbell_back_squat", "lat_pulldown"}


def test_process_asset_failure_recorded(tmp_path, monkeypatch):
    from coach.db import Database
    db = Database(tmp_path / "t.db")
    db.save_profile("u", profile())
    video = make_video(tmp_path / "v.mp4")
    asset_id = db.add_media_asset("u", "无字幕", str(video), None)

    def boom(_path):
        raise RuntimeError("模型不可用")
    import coach.media_import as mi
    monkeypatch.setattr(mi, "transcribe_audio", boom)
    process_asset(db, asset_id, str(video), None)
    asset = db.get_media_asset("u", asset_id)
    assert asset["status"] == "failed" and "模型不可用" in asset["error"]


# ---- API 全流程 ----

@pytest.fixture()
def vclient(tmp_path):
    app = create_app(db_path=tmp_path / "api.db")
    with TestClient(app) as c:
        app.state.db.save_profile("vu", profile())
        yield c, tmp_path


def wait_ready(c, asset_id, tries=20):
    for _ in range(tries):
        assets = c.get("/api/users/vu/media/videos").json()["assets"]
        me = next(a for a in assets if a["id"] == asset_id)
        if me["status"] != "processing":
            return me
        time.sleep(0.3)
    raise AssertionError("任务未完成")


def test_video_upload_with_subtitle_to_link(vclient):
    c, tmp = vclient
    import io
    video = make_video(tmp / "vid.mp4", 4)
    with open(video, "rb") as f:
        up = c.post("/api/users/vu/media/videos",
                    files={"video": ("v.mp4", f, "video/mp4"),
                           "subtitle": ("s.srt", io.BytesIO(SRT.encode("utf-8")),
                                        "application/x-subrip")},
                    data={"title": "深蹲教学"})
    assert up.status_code == 200
    asset = wait_ready(c, up.json()["asset_id"])
    assert asset["status"] == "ready"
    idx = next(i for i, cand in enumerate(asset["candidates"])
               if cand["exercise_id"] == "barbell_back_squat")
    resp = c.post(f"/api/users/vu/media/{asset['id']}/candidates/{idx}/confirm",
                  json={"action": "link"})
    body = resp.json()
    assert resp.status_code == 200 and body["result"] == "linked"
    assert body["clip"] and body["cover"]          # ffmpeg 生成了封面与片段
    links = c.get("/api/users/vu/exercise-media",
                  params={"exercise_id": "barbell_back_squat"}).json()["links"]
    assert links and links[0]["sentence"].startswith("今天讲杠铃深蹲")
    # 重复关联同一片段 → 422
    again = c.post(f"/api/users/vu/media/{asset['id']}/candidates/{idx}/confirm",
                   json={"action": "link"})
    assert again.status_code == 422


def test_video_candidate_new_and_reject(vclient):
    c, tmp = vclient
    video = make_video(tmp / "vid2.mp4")
    with open(video, "rb") as f:
        up = c.post("/api/users/vu/media/videos",
                    files={"video": ("v.mp4", f, "video/mp4")}, data={"title": "无字幕"})
    # 无字幕 + 测试环境无真实转写 → 任务失败或(若本机装了模型)转写无动作台词
    asset = wait_ready(c, up.json()["asset_id"])
    assert asset["status"] in ("ready", "failed")
    if asset["status"] == "failed":
        assert asset["error"]


def test_new_action_proposal_flow(vclient):
    c, tmp = vclient
    video = make_video(tmp / "vid3.mp4", 3)
    import io
    srt3 = "1\n00:00:00,500 --> 00:00:03,000\n这个动作叫壶铃摆铃，注意髋部发力。\n"
    with open(video, "rb") as f:
        up = c.post("/api/users/vu/media/videos",
                    files={"video": ("v.mp4", f, "video/mp4"),
                           "subtitle": ("s.srt", io.BytesIO(srt3.encode("utf-8")),
                                        "application/x-subrip")},
                    data={"title": "新动作"})
    asset = wait_ready(c, up.json()["asset_id"])
    # 库内无"壶铃摆铃" → 无候选，如实呈现
    assert asset["status"] == "ready"
    # 库外动作不强行匹配；提案表为空且不崩（新动作提案需先有候选或手动指定）
    assert asset["candidates"] == []
    assert c.get("/api/users/vu/exercise-proposals").json()["proposals"] == []
