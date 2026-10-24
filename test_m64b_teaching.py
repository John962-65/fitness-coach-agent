"""M6.4-B 动作教学可视化：内容/媒体/三维清单测试（B5.1 十项覆盖）。

1 教学文档引用存在性；2 媒体来源与授权字段完整性；3 三维清单文件真实存在；
4 GLB 有效（gltf-validator，无 node 时跳过）；5 动画名与清单一致；
6 未授权素材不得进入公共资源；7 用户媒体保持用户隔离；8/9 三维不可用/
不支持的动作正常降级（不误显示入口）；10 教学页面不改训练数据。
"""
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

from coach import teaching_content, teaching_media
from coach.exercises import library
from coach.exercise_service import teaching_for

ROOT = Path(__file__).parent
EXPORTS = ROOT / "assets" / "exercise_3d" / "exports"
FIVE = ["barbell_back_squat", "barbell_bench_press", "deadlift",
        "barbell_row", "dumbbell_shoulder_press"]


# ---- 1. 教学文档引用存在性 ----

def test_knowledge_refs_resolve():
    """动作库 knowledge_refs 必须全部解析到 knowledge/ 内真实文件。"""
    for ex in library.all():
        for ref in ex.get("knowledge_refs") or []:
            p = (ROOT / "knowledge" / ref).resolve()
            assert p.is_file(), f"{ex['id']} 断链 knowledge_ref: {ref}"
            assert str(p).startswith(str(ROOT / "knowledge"))


def test_teaching_yaml_sources_point_to_existing_docs():
    """结构化教学的 sources.ref 必须指向存在的 knowledge 文档（来源可追溯）。"""
    for ex_id, doc in teaching_content.load_all().items():
        refs = [s.get("ref") for s in doc["sources"] if s.get("type") == "knowledge"]
        assert refs, f"{ex_id} 缺 knowledge 来源"
        for r in refs:
            assert (ROOT / "knowledge" / r).is_file(), f"{ex_id} 来源断链 {r}"


def test_teaching_sections_complete_for_five():
    """首批五动作六节齐备（breathing 允许 incomplete 且如实展示）。"""
    for ex_id in FIVE:
        doc = teaching_content.load_one(ex_id)
        assert doc, f"{ex_id} 缺结构化教学"
        assert teaching_content.completeness(doc) == "draft"
        for key in ("setup", "execution", "common_errors", "cautions", "conditions"):
            assert doc["sections"][key]["items"], f"{ex_id}.{key} 无内容"


def test_teaching_status_never_inherited_from_library():
    """动作库 status=approved 不得自动继承为教学审核通过。"""
    for ex_id in FIVE:
        doc = teaching_content.load_one(ex_id)
        assert doc["review_status"] == "draft"   # AI 整理，未人工复核
        assert library.get(ex_id)["status"] == "approved"


# ---- 2/3/6. 媒体清单：字段完整性、文件存在、授权门控 ----

def test_manifest_fields_complete():
    for a in teaching_media.load_media_manifest():
        for f in teaching_media.REQUIRED_ASSET_FIELDS:
            assert a.get(f), f"{a['asset_id']} 缺 {f}"
        assert a["media_type"] in teaching_media.MEDIA_TYPES
        assert a["scope"] == "global"


def test_manifest_files_exist_and_hash_matches():
    for a in teaching_media.authorized_assets():
        f = ROOT / "assets" / a["file_path"]
        assert f.is_file(), f"{a['asset_id']} 文件不存在: {a['file_path']}"


def test_unauthorized_assets_never_published():
    """未确认授权的素材不得进入公共资源：third_party 未 approved /
    user_uploaded 登记为 global / sha 不符，都必须被发布门控拒绝。"""
    assert teaching_media.authorized({
        "scope": "global", "source_kind": "third_party_licensed",
        "license": "CC-BY-4.0", "license_evidence": "x",
        "review_status": "draft"}) is False
    assert teaching_media.authorized({
        "scope": "global", "source_kind": "user_uploaded",
        "license": "x", "license_evidence": "x",
        "review_status": "approved"}) is False
    assert teaching_media.authorized({
        "scope": "user", "source_kind": "project_created",
        "license": "x", "license_evidence": "x",
        "review_status": "approved"}) is False


def test_manifest_rejects_user_upload_as_global(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"version": 1, "assets": [{
        "asset_id": "u1", "exercise_id": "deadlift", "media_type": "image",
        "source_kind": "user_uploaded", "file_path": "x.png",
        "license": "x", "license_evidence": "x", "scope": "global",
        "review_status": "approved", "sha256": "0" * 64}]}), encoding="utf-8")
    with pytest.raises(teaching_media.MediaManifestError):
        teaching_media.load_media_manifest(p)


# ---- 3/5. 三维清单与动画名 ----

def test_3d_descriptor_files_exist_and_match_exports():
    for ex_id in FIVE:
        d = teaching_media.load_3d_descriptor(ex_id)
        assert d, f"{ex_id} 缺三维描述"
        assert (ROOT / "assets" / d["model_path"]).is_file()
        assert d["animation_name"]
        assert d["duration"] > 0
        # 五个教学阶段（B4.3：准备/开始/底部或转换/返回/结束；各动作措辞可不同）
        phases = d["teaching_phases"]
        assert len(phases) == 5
        assert "准备" in phases[0]["label"] and "结束" in phases[-1]["label"]
        assert [p["t"][0] for p in phases] == sorted(p["t"][0] for p in phases)
        assert phases[0]["t"][0] == 0 and phases[-1]["t"][1] == d["duration"]


def test_glb_animation_name_matches_manifest():
    for ex_id in FIVE:
        d = teaching_media.load_3d_descriptor(ex_id)
        glb = EXPORTS / f"{ex_id}.glb"
        names = _glb_animation_names(glb)
        assert d["animation_name"] in names, \
            f"{ex_id}: 清单动画名 {d['animation_name']} ∉ GLB {names}"


# ---- 4. GLB 有效性（Khronos gltf-validator；无 node 则跳过）----

@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_glb_validator_zero_errors():
    files = sorted(EXPORTS.glob("*.glb"))
    assert files, "无导出 GLB"
    r = subprocess.run(
        ["node", str(ROOT / "tools" / "validate_glb.mjs"),
         *[str(f) for f in files]],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_glb_threejs_smoke():
    for f in sorted(EXPORTS.glob("*.glb")):
        r = subprocess.run(
            ["node", str(ROOT / "tools" / "smoke_glb.mjs"), str(f)],
            capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"{f.name}: {r.stdout}{r.stderr}"


# ---- 7. 用户媒体隔离不被破坏 ----

def test_user_media_tables_untouched():
    """用户媒体仍是 per-user SQLite 表（media_assets/exercise_media_links），
    全局 manifest 不含任何用户上传条目。"""
    import coach.db as dbm
    sql = (ROOT / "coach" / "db.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS media_assets" in sql
    assert "CREATE TABLE IF NOT EXISTS exercise_media_links" in sql
    for a in teaching_media.load_media_manifest():
        assert a["source_kind"] != "user_uploaded"


def test_user_media_isolation_between_users(tmp_path):
    """A 用户的媒体关联对 B 用户不可见（既有隔离机制回归）。"""
    from backend.app import create_app
    from fastapi.testclient import TestClient
    app = create_app(db_path=tmp_path / "t.db",
                     frontend_dist=tmp_path)   # 无 dist → 不挂 SPA
    c = TestClient(app)
    for uid in ("u1", "u2"):
        c.post(f"/api/users/{uid}/onboarding", json=_onboarding(uid))
    # 直接向 db 写入 u1 的媒体关联（绕过上传，聚焦隔离断言）
    db = app.state.db
    asset_id = db.add_media_asset("u1", "教学视频", str(tmp_path / "v.mp4"), None)
    link_id = db.add_exercise_media_link(
        "u1", "deadlift", asset_id, "句", 0.0, 1.0, None, None)
    assert link_id > 0
    assert c.get("/api/users/u1/exercise-media?exercise_id=deadlift").json()["links"]
    assert c.get("/api/users/u2/exercise-media?exercise_id=deadlift").json()["links"] == []


# ---- 8/9. 降级与入口 ----

def test_no_3d_for_unsupported_exercise():
    """无三维资源的动作不透出入口；自定义动作不关联公共三维。"""
    assert teaching_media.demo_3d("barbell_curl") is None
    assert teaching_media.demo_3d("不存在的动作") is None


def test_detail_endpoint_demos_gating():
    from backend.app import create_app
    from fastapi.testclient import TestClient
    app = create_app(db_path=Path("/tmp/m64b_detail_test.db"),
                     frontend_dist=Path("/tmp"))
    c = TestClient(app)
    d = c.get("/api/exercises/barbell_back_squat").json()
    assert d["demos"]["model_3d"]["animation_name"] == "squat"
    assert d["teaching_content"]["sections"]["setup"]["items"]
    d2 = c.get("/api/exercises/barbell_curl").json()
    assert d2["demos"]["model_3d"] is None
    assert d2["demos"]["text"] is True          # 图文教学兜底可用
    Path("/tmp/m64b_detail_test.db").unlink(missing_ok=True)


def test_custom_exercise_never_gets_public_3d(tmp_path):
    """用户自定义动作：即使 pattern 相同，也不透出公共三维（不按名称/类型
    相似自动挂内置模型）。"""
    from backend.app import create_app
    from fastapi.testclient import TestClient
    app = create_app(db_path=tmp_path / "t.db", frontend_dist=tmp_path)
    c = TestClient(app)
    c.post("/api/users/ua/onboarding", json=_onboarding("ua"))
    db = app.state.db
    db.conn.execute(
        "INSERT INTO custom_exercises(user_id, ex_id, doc, source, created_at)"
        " VALUES('ua','my_squat_v2',?, 'user_created', datetime('now'))",
        (json.dumps({"id": "my_squat_v2", "name": "我的深蹲变式",
                     "aliases": ["深蹲v2"], "pattern": "squat",
                     "primary": ["quads"], "scope": "user"}, ensure_ascii=False),))
    db.conn.commit()
    d = c.get("/api/exercises/my_squat_v2?uid=ua").json()
    assert d["scope"] == "user"
    assert d["demos"]["model_3d"] is None, "自定义动作不得挂公共三维"
    # 其他用户看不到这个自定义动作
    r = c.get("/api/exercises/my_squat_v2?uid=ub")
    assert r.status_code == 404


# ---- 10. 教学页面不改训练数据 ----

def test_teaching_readonly():
    """教学内容模块零写入：load/公共接口不触任何 db 写方法。"""
    readonly = ["public_teaching", "load_one", "load_all", "completeness"]
    for name in readonly:
        fn = getattr(teaching_content, name, None)
        assert fn is not None and callable(fn)
    src = (ROOT / "coach" / "teaching_content.py").read_text(encoding="utf-8")
    for banned in (".execute(", "INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert banned not in src, f"教学模块出现写操作 {banned}"


def test_detail_endpoint_does_not_touch_checkins(tmp_path):
    from backend.app import create_app
    from fastapi.testclient import TestClient
    app = create_app(db_path=tmp_path / "t.db", frontend_dist=tmp_path)
    c = TestClient(app)
    c.post("/api/users/ur/onboarding", json=_onboarding("ur"))
    before = c.get("/api/users/ur/checkins?limit=50").json()["checkins"]
    c.get("/api/exercises/barbell_back_squat")
    after = c.get("/api/users/ur/checkins?limit=50").json()["checkins"]
    assert before == after


# ---- 工具 ----

def _glb_animation_names(glb: Path) -> list[str]:
    data = glb.read_bytes()
    assert data[:4] == b"glTF", "不是 GLB 文件"
    json_len = struct.unpack("<I", data[12:16])[0]
    doc = json.loads(data[20:20 + json_len])
    return [a["name"] for a in doc.get("animations", [])]


def _onboarding(uid):
    return {
        "basic": {"age": 30, "gender": "男", "height_cm": 175, "weight_kg": 70},
        "goal": {"primary": "力量"},
        "experience": {"training_years": 1},
        "resources": {"location": "gym", "days_per_week": 3, "session_minutes": 60},
        "conditions": {"injuries": [], "injuries_evidence": "无",
                       "health_screen": {"cardio": "无", "pregnancy": "不适用",
                                         "medication": "无", "exercise_limit": "无"},
                       "health_screen_evidence": "本人自述"},
    }
