"""/api 路由（2.0 B4）：薄层，全部委托 coach/ 域函数。

错误约定：
- 404：用户/资源不存在；
- 422：确定性校验未通过（ProposalRejected 等，details 带原因列表）；
- 400：请求形状不对。
"""
from __future__ import annotations

import hmac
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from coach.agent import CoachAgent
from coach.approach import approach_view, initialize_approach, restore_revision
from coach.changes import (ProposalRejected, confirm_proposal, stage_ai,
                           submit_manual)
from coach.exercises import CUSTOM_HIIT_EXERCISE_ID, library
from coach.goals import SUPPORTED_GOALS
from coach.medical import training_permission
from coach.plan import generate_plan, plan_to_text
from coach.profile import merge_patch, open_pain_flags, profile_summary
from coach.validate import coerce_checkin


def _reject(e: ProposalRejected) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": str(e), "details": e.errors})


def _user_profile(db, uid: str) -> dict:
    profile = db.get_existing_profile(uid)
    if not profile:
        raise HTTPException(status_code=404, detail={"error": f"用户 {uid} 不存在"})
    return profile


def _agent(request: Request, uid: str) -> CoachAgent:
    agents: dict = request.app.state.agents
    if uid not in agents:
        agents[uid] = CoachAgent(uid, db_path=request.app.state.db_path)
    return agents[uid]


def _log_unmatched(request: Request, uid: str, raw_name: str) -> None:
    """未识别动作进待补队列（与 agent 行为一致：不静默丢弃，20.4）。"""
    path = request.app.state.db.path.parent / "unmatched_exercises.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"user": uid, "name": raw_name,
                            "at": datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")


# ---- M5.1 P0-2：上传资源限制 ----
MAX_VIDEO_BYTES = 200 * 1024 * 1024          # 单文件 200MB（测试可 monkeypatch）
MAX_USER_MEDIA_BYTES = 2 * 1024 * 1024 * 1024  # 每用户媒体总量 2GB
MAX_USER_MEDIA_FILES = 200                   # 每用户文件数
_UPLOAD_CHUNK = 1024 * 1024
# 媒体处理串行化（本地 CPU 单任务，避免多个重任务竞争）
import threading as _threading
_WORKER_SEMAPHORE = _threading.Semaphore(1)


class UploadRejected(HTTPException):
    def __init__(self, status_code: int, msg: str):
        super().__init__(status_code=status_code, detail={"error": msg})


async def _stream_upload_to(upload, dest: Path, max_bytes: int) -> int:
    """流式落盘：分块写、超限即断、首块校验容器魔数。"""
    total, first = 0, True
    with open(dest, "wb") as f:
        while True:
            chunk = await upload.read(_UPLOAD_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                f.close()
                dest.unlink(missing_ok=True)
                raise UploadRejected(
                    422, f"文件超过大小限制（{max_bytes // (1024 * 1024)}MB）")
            if first:
                head = bytes(chunk[:16])
                if not (head[4:8] == b"ftyp" or head[:4] == b"\x1a\x45\xdf\xa3"):
                    dest.unlink(missing_ok=True)
                    raise UploadRejected(
                        422, "文件内容不是合法的视频容器（mp4/mov/webm/mkv）")
                first = False
            f.write(chunk)
    if total == 0:
        dest.unlink(missing_ok=True)
        raise UploadRejected(422, "空文件")
    return total


def _user_media_usage(media_dir: Path) -> tuple[int, int]:
    files = bytes_ = 0
    if media_dir.exists():
        for p in media_dir.rglob("*"):
            if p.is_file():
                files += 1
                bytes_ += p.stat().st_size
    return files, bytes_


def _run_media_worker(app, fn, *args):
    """后台任务：独立数据库连接（不与请求共享）+ 串行信号量。"""
    def _work():
        from coach.db import Database as _DB
        worker_db = _DB(app.state.db.path)
        with _WORKER_SEMAPHORE:
            try:
                fn(worker_db, *args)
            finally:
                worker_db.conn.close()
    t = _threading.Thread(target=_work, daemon=True)
    t.start()
    return t


def _load_aliases(raw) -> list:
    import json as _json
    if isinstance(raw, list):
        return [str(a) for a in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            v = _json.loads(raw)
            return [str(a) for a in v] if isinstance(v, list) else []
        except ValueError:
            return []
    return []


def register_routes(app) -> None:
    api = APIRouter(prefix="/api")

    # ---- 基础 ----

    @api.get("/health")
    def health():
        return {"status": "ok", "exercises": len(library)}

    # ---- 档案 ----

    @api.get("/users/{uid}/profile")
    def get_profile(uid: str, request: Request):
        db = request.app.state.db
        profile = _user_profile(db, uid)
        return {
            "user_id": uid,
            "profile": profile,
            "summary": profile_summary(profile),
            "plan_fenced": bool(profile.get("plan_fence")),
            "medical": {"status": training_permission(profile).status,
                        "allows_prescription":
                            training_permission(profile).allows_prescription},
        }

    # ---- 表单化建档（2.0 M1：建档不要求经过 LLM）----
    #
    # 确定性路径：表单文本即用户本人的自述（比 agent 转述更强的依据），
    # 校验完全对齐 onboarding 门槛（健康筛查四项必答、伤病必答）；
    # PAR-Q 阳性时 generate_plan 自动落到医疗暂停模板，前端如实展示。

    @api.post("/users/{uid}/onboarding")
    def onboard(uid: str, request: Request, payload: dict = Body(...)):
        db = request.app.state.db
        profile = db.get_profile(uid)
        if profile.get("onboarding_done"):
            raise HTTPException(status_code=409,
                                detail={"error": "该用户已完成建档；修改请走档案更新"})
        errors: list[str] = []

        def _num(value, lo, hi):
            return (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and lo <= value <= hi)

        basic = payload.get("basic") or {}
        if not _num(basic.get("age"), 10, 100):
            errors.append("basic.age 必须是 10-100 的数字")
        if not _num(basic.get("height_cm"), 100, 250):
            errors.append("basic.height_cm 必须是 100-250 的数字")
        if not _num(basic.get("weight_kg"), 25, 300):
            errors.append("basic.weight_kg 必须是 25-300 的数字")
        if basic.get("gender") not in ("男", "女", "其他"):
            errors.append("basic.gender 必须是 男/女/其他")

        goal = payload.get("goal") or {}
        if goal.get("primary") not in SUPPORTED_GOALS:
            errors.append(f"goal.primary 必须是 {SUPPORTED_GOALS} 之一")

        resources = payload.get("resources") or {}
        if not _num(resources.get("days_per_week"), 1, 7) \
                or float(resources["days_per_week"]).is_integer() is False:
            errors.append("resources.days_per_week 必须是 1-7 的整数")
        if resources.get("location") not in ("gym", "home"):
            errors.append("resources.location 必须是 gym/home")
        if not _num(resources.get("session_minutes"), 10, 240):
            errors.append("resources.session_minutes 必须是 10-240 的数字")

        conditions = payload.get("conditions") or {}
        injuries = conditions.get("injuries")
        if not isinstance(injuries, list) or not all(
                isinstance(i, str) and i.strip() for i in injuries):
            errors.append("conditions.injuries 必须是伤病描述列表（可为空列表）")
        if not str(conditions.get("injuries_evidence") or "").strip():
            errors.append("conditions.injuries_evidence 必填（例如「没有伤病」或伤病史描述）")
        screen = conditions.get("health_screen") or {}
        for key in ("heart", "pregnancy", "medication", "clearance"):
            if not str(screen.get(key) or "").strip():
                errors.append(f"conditions.health_screen.{key} 必答（PAR-Q 四项不可跳过）")
        if not str(conditions.get("health_screen_evidence") or "").strip():
            errors.append("conditions.health_screen_evidence 必填")
        if errors:
            raise HTTPException(status_code=422, detail={"error": "建档信息不完整",
                                                         "details": errors})

        experience = payload.get("experience") or {}
        patch = {
            "basic": basic,
            "goal": goal,
            "experience": experience,
            "resources": resources,
            "conditions": conditions,
        }
        merged, _report = merge_patch(profile, patch)
        merged["onboarding_done"] = True
        plan = generate_plan(merged, exercise_states=db.all_exercise_states(uid))
        merged.setdefault("experience", {})["level"] = plan["level"]
        plan_id = db.create_plan(uid, plan, profile=merged)
        return {
            "plan_id": plan_id, "version": db.get_active_plan_record(uid)["version"],
            "medical_status": plan.get("medical_status"),
            "suspended": not plan.get("schedule"),
            "level": plan["level"],
            "text": plan_to_text(plan),
        }

    # ---- 训练执行辅助：上次重量/派生状态（M1「自动读取上次训练重量」）----

    @api.get("/users/{uid}/exercise-states")
    def exercise_states(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        out = []
        for s in db.all_exercise_states(uid):
            out.append({
                "exercise_id": s.get("exercise_id"),
                "last_weight": s.get("last_weight"), "last_rpe": s.get("last_rpe"),
                "best_e1rm": s.get("best_e1rm"), "status": s.get("status"),
                "discomfort": s.get("discomfort"), "preference": s.get("preference"),
            })
        return {"states": out}

    # ---- 个人尝试列表（我的页）----

    @api.get("/users/{uid}/trials")
    def trials(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"trials": db.personal_trials(uid, limit=20)}

    # ---- 今日简报（确定性，无 LLM）----

    @api.get("/users/{uid}/today")
    def today(uid: str, request: Request):
        db = request.app.state.db
        profile = _user_profile(db, uid)
        plan_record = db.get_active_plan_record(uid)
        permission = training_permission(profile)
        flags = open_pain_flags(profile)
        due_notes = [n for n in db.open_coach_notes(uid) if n.get("due_review")]
        stale_notes = db.notes_for_reconfirm(uid)
        trials = [t for t in db.personal_trials(uid) if t.get("due_review")]
        rows = db.conn.execute(
            "SELECT created_at FROM checkins WHERE user_id=? AND type='training'"
            " ORDER BY id DESC", (uid,)).fetchall()
        last_training = rows[0]["created_at"][:10] if rows else None
        days_since = (date.fromisoformat(date.today().isoformat())
                      - date.fromisoformat(last_training)).days if last_training else None
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        sessions_this_week = sum(
            1 for r in rows if (r["created_at"] or "")[:10] >= week_ago)
        approach = db.get_approach(uid)
        plan_stale = bool(
            approach and plan_record
            and plan_record["content"].get("approach_revision", 0) < approach["revision"])
        return {
            "user_id": uid,
            "medical": {"status": permission.status,
                        "allows_prescription": permission.allows_prescription},
            "plan_fenced": bool(profile.get("plan_fence")),
            "open_pain_flags": len(flags),
            "due_review_notes": [n["id"] for n in due_notes + stale_notes],
            "due_review_trials": [t["id"] for t in trials],
            "last_training_date": last_training,
            "days_since_last_training": days_since,
            "sessions_last_7_days": sessions_this_week,
            "plan_days_per_week": (plan_record["content"].get("requested_days_per_week")
                                   if plan_record else None),
            "plan": ({"id": plan_record["id"], "version": plan_record["version"],
                      "template": plan_record["content"].get("template"),
                      "days": [{"day": d["day"], "focus": d.get("focus"),
                                "exercises": [e["name"] for e in d.get("exercises", [])]}
                               for d in plan_record["content"].get("schedule", [])]}
                     if plan_record else None),
            "plan_stale_vs_approach": plan_stale,
            "onboarding_done": bool(profile.get("onboarding_done")),
        }

    # ---- 训练方式 ----

    @api.get("/users/{uid}/approach")
    def get_approach(uid: str, request: Request):
        return approach_view(request.app.state.db, uid)

    @api.post("/users/{uid}/approach/initialize")
    def init_approach(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        initialize_approach(db, uid)
        return approach_view(db, uid)

    @api.get("/users/{uid}/approach/revisions")
    def approach_revisions(uid: str, request: Request,
                           limit: int = Query(50, ge=1, le=200)):
        return {"revisions": request.app.state.db.list_approach_revisions(uid, limit)}

    @api.post("/users/{uid}/approach/revisions/{revision}/restore")
    def approach_restore(uid: str, revision: int, request: Request,
                         reason: str = Body("", embed=True)):
        try:
            doc = restore_revision(request.app.state.db, uid, revision,
                                   initiator="user", reason=reason)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return {"restored_from": revision, "approach": doc}

    # ---- 统一修改协议 ----

    @api.post("/users/{uid}/changes")
    def submit_change(uid: str, request: Request,
                      payload: dict = Body(...)):
        db = request.app.state.db
        target = payload.get("target")
        operations = payload.get("operations")
        base_version = payload.get("base_version")
        reason = str(payload.get("reason") or "")
        if not isinstance(operations, list):
            raise HTTPException(status_code=400, detail={"error": "operations 必须是列表"})
        try:
            result = submit_manual(db, uid, target, operations, reason, base_version)
        except ProposalRejected as e:
            raise _reject(e) from None
        return result

    @api.post("/users/{uid}/changes/ai")
    def stage_change(uid: str, request: Request, payload: dict = Body(...)):
        """AI 建议暂存（pending，等用户确认）。本轮主要为协议完整性预留。"""
        db = request.app.state.db
        try:
            result = stage_ai(db, uid, payload.get("target"),
                              payload.get("operations"),
                              str(payload.get("reason") or ""),
                              payload.get("base_version"))
        except ProposalRejected as e:
            raise _reject(e) from None
        return result

    @api.get("/users/{uid}/changes")
    def list_changes(uid: str, request: Request,
                     status: str | None = Query(None), limit: int = Query(20, ge=1, le=100)):
        return {"proposals": request.app.state.db.list_proposals(uid, status, limit)}

    @api.post("/users/{uid}/changes/{proposal_id}/confirm")
    def confirm_change(uid: str, proposal_id: str, request: Request,
                       message: str = Body(..., embed=True)):
        try:
            return confirm_proposal(request.app.state.db, uid, proposal_id, message)
        except ProposalRejected as e:
            raise _reject(e) from None

    # ---- M3：统一知识库（检索 / 导入 / 审核）----

    @api.get("/knowledge/search")
    def knowledge_search(request: Request, uid: str = "",
                         q: str = Query(..., min_length=1)):
        from coach.knowledge_search import search as _ksearch
        return _ksearch(request.app.state.db, uid or None, q)

    @api.post("/users/{uid}/knowledge/imports")
    def knowledge_import(uid: str, request: Request, payload: dict = Body(...)):
        from coach.knowledge_import import extract_pdf_text, import_knowledge
        db = request.app.state.db
        _user_profile(db, uid)
        kind = str(payload.get("kind") or "text")
        content = payload.get("content")
        if kind == "pdf":
            import base64
            raw = str(content or "")
            try:
                data = base64.b64decode(raw, validate=False)
            except Exception:
                raise HTTPException(status_code=400,
                                    detail={"error": "pdf 内容需要 base64 编码"}) from None
            try:
                content = extract_pdf_text(data)
            except ValueError as e:
                raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        result = import_knowledge(db, uid, str(payload.get("title") or "未命名资料"),
                                  kind, str(content or ""),
                                  str(payload.get("origin") or ""))
        if result.get("error"):
            raise HTTPException(status_code=422, detail={"error": result["error"]})
        return result

    @api.get("/users/{uid}/knowledge/imports")
    def knowledge_imports(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"sources": db.list_knowledge_sources(uid)}

    @api.get("/users/{uid}/knowledge/claims")
    def knowledge_claims(uid: str, request: Request,
                         status: str | None = Query(None)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"claims": db.list_knowledge_claims(uid, status)}

    @api.post("/users/{uid}/knowledge/claims/{claim_id}/review")
    def knowledge_review(uid: str, claim_id: int, request: Request,
                         decision: str = Body(..., embed=True)):
        db = request.app.state.db
        _user_profile(db, uid)
        if decision not in ("approve", "reject"):
            raise HTTPException(status_code=400,
                                detail={"error": "decision 必须是 approve/reject"})
        claim = db.get_knowledge_claim(uid, claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail={"error": "观点不存在"})
        if claim["status"] == "quarantined":
            raise HTTPException(
                status_code=422,
                detail={"error": "该观点已隔离（高风险内容），不能通过审核放行；"
                                 "它永远不会成为训练处方依据"})
        if not db.review_knowledge_claim(uid, claim_id,
                                         "approved" if decision == "approve" else "rejected"):
            raise HTTPException(status_code=422,
                                detail={"error": "只有待审核观点能被审核"})
        return {"id": claim_id,
                "status": "approved" if decision == "approve" else "rejected"}

    # ---- M3.2：视频导入（上传/任务状态/候选确认/动作媒体）----

    # M5.1 P1-5：短时签名 URL（替代长期令牌入 URL——浏览器历史/日志不再泄漏令牌）
    _SIG_TTL_SECONDS = 600

    def _media_sig(secret: str, uid: str, name: str, exp: int) -> str:
        import hashlib
        return hmac.new(secret.encode(), f"{uid}/{name}/{exp}".encode(),
                        hashlib.sha256).hexdigest()[:32]

    @api.get("/users/{uid}/media-sign")
    def media_sign(uid: str, request: Request, name: str = Query(...)):
        """发放 10 分钟媒体签名（需令牌头/本机模式）；前端 img/video 用
        /api/media/{uid}/{name}?sig=&exp= 访问，不再携带长期 access_token。"""
        token = request.app.state.access_token
        if token and request.headers.get("X-Access-Token") != token:
            raise HTTPException(status_code=401, detail={"error": "需要访问令牌"})
        import time as _t
        exp = int(_t.time()) + _SIG_TTL_SECONDS
        secret = token or "local-media"
        return {"sig": _media_sig(secret, uid, name, exp), "exp": exp,
                "ttl": _SIG_TTL_SECONDS}

    @api.get("/media/{uid}/{name}")
    def media_file(uid: str, name: str, request: Request,
                   sig: str = "", exp: int = 0):
        """封面/片段文件（只读）。鉴权三选一：令牌头 / 短时签名(sig+exp) /
        本机无令牌模式。长期 access_token 查询参数已弃用（P1-5 泄漏风险）。"""
        token = request.app.state.access_token
        if token:
            ok = request.headers.get("X-Access-Token") == token
            if not ok and sig and exp:
                import time as _t
                ok = (exp >= int(_t.time())
                      and hmac.compare_digest(sig, _media_sig(token, uid, name, exp)))
            if not ok:
                raise HTTPException(status_code=401,
                                    detail={"error": "媒体访问需要令牌头或有效签名"})
        base = (request.app.state.db.path.parent / "media" / uid).resolve()
        target = (base / name).resolve()
        if not str(target).startswith(str(base)) or not target.is_file():
            raise HTTPException(status_code=404, detail={"error": "文件不存在"})
        return FileResponse(target)

    @api.post("/users/{uid}/media/videos")
    async def media_upload(uid: str, request: Request):
        from starlette.datastructures import UploadFile
        import time as _time
        db = request.app.state.db
        _user_profile(db, uid)
        form = await request.form()
        video = form.get("video")
        subtitle = form.get("subtitle")
        title = str(form.get("title") or "未命名视频")
        if not isinstance(video, UploadFile) or not video.filename:
            raise HTTPException(status_code=400, detail={"error": "需要 video 文件"})
        if not video.filename.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
            raise HTTPException(status_code=422, detail={"error": "仅支持 mp4/mov/webm/mkv"})
        media_dir = db.path.parent / "media" / uid
        media_dir.mkdir(parents=True, exist_ok=True)
        # M5.1 P0-2：配额先行（文件数/总字节）
        usage_files, usage_bytes = _user_media_usage(media_dir)
        if usage_files >= MAX_USER_MEDIA_FILES:
            raise UploadRejected(422, f"媒体文件数已达上限（{MAX_USER_MEDIA_FILES}），请清理后再传")
        if usage_bytes >= MAX_USER_MEDIA_BYTES:
            raise UploadRejected(422, "媒体总容量已达上限（2GB），请清理后再传")
        stamp = int(_time.time() * 1000)
        video_path = media_dir / f"v{stamp}_{Path(video.filename).name}"
        size = await _stream_upload_to(video, video_path, MAX_VIDEO_BYTES)
        if usage_bytes + size > MAX_USER_MEDIA_BYTES:
            video_path.unlink(missing_ok=True)
            raise UploadRejected(422, "媒体总容量已达上限（2GB），请清理后再传")
        subtitle_path = None
        if isinstance(subtitle, UploadFile) and subtitle.filename:
            if not subtitle.filename.lower().endswith((".srt", ".vtt")):
                video_path.unlink(missing_ok=True)
                raise HTTPException(status_code=422, detail={"error": "字幕仅支持 srt/vtt"})
            subtitle_path = media_dir / f"s{stamp}_{Path(subtitle.filename).name}"
            subtitle_path.write_bytes(await subtitle.read())
        asset_id = db.add_media_asset(uid, title, str(video_path),
                                      str(subtitle_path) if subtitle_path else None)
        # §10.4：媒体处理不阻塞请求——后台线程（独立 DB 连接+串行信号量）
        from coach.media_import import process_asset
        _run_media_worker(request.app, process_asset, asset_id, str(video_path),
                          str(subtitle_path) if subtitle_path else None)
        return {"asset_id": asset_id, "status": "processing"}

    @api.get("/users/{uid}/media/videos")
    def media_list(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"assets": db.list_media_assets(uid)}

    @api.post("/users/{uid}/media/{asset_id}/candidates/{index}/confirm")
    def media_confirm(uid: str, asset_id: int, index: int, request: Request,
                      payload: dict = Body(...)):
        from coach.media_import import make_clip, make_cover
        db = request.app.state.db
        _user_profile(db, uid)
        asset = db.get_media_asset(uid, asset_id)
        if not asset or asset["status"] != "ready":
            raise HTTPException(status_code=422,
                                detail={"error": "视频尚未处理完成或处理失败"})
        candidates = asset.get("candidates") or []
        if not 0 <= index < len(candidates):
            raise HTTPException(status_code=404, detail={"error": "候选不存在"})
        cand = candidates[index]
        action = payload.get("action")
        if action == "reject":
            candidates[index]["status"] = "rejected"
            db.update_media_asset(asset_id, status="ready", candidates=candidates)
            return {"result": "rejected"}
        if action == "new":
            proposal_id = db.add_exercise_proposal(
                uid, str(payload.get("name") or cand.get("name") or "未命名动作"),
                [str(a) for a in (payload.get("aliases") or [])][:8],
                str(payload.get("pattern") or ""), str(payload.get("note") or ""),
                asset_id, cand.get("sentence") or "")
            candidates[index]["status"] = "proposed"
            db.update_media_asset(asset_id, status="ready", candidates=candidates)
            return {"result": "proposed", "proposal_id": proposal_id}
        if action == "link":
            exercise_id = str(payload.get("exercise_id") or cand.get("exercise_id") or "")
            if not exercise_id:
                raise HTTPException(status_code=422, detail={"error": "缺少 exercise_id"})
            from coach import exercise_service as _svc
            if not _svc.get_exercise(db, uid, exercise_id):  # 内置或本人自定义
                raise HTTPException(status_code=422,
                                    detail={"error": f"动作 {exercise_id} 不在动作库内"})
            media_dir = Path(asset["video_path"]).parent
            cover = make_cover(asset["video_path"], cand.get("start") or 0.0,
                               str(media_dir / f"cover_{asset_id}_{index}.jpg"))
            clip = make_clip(asset["video_path"], cand.get("start") or 0.0,
                             cand.get("end") or 0.0,
                             str(media_dir / f"clip_{asset_id}_{index}.mp4"))
            link_id = db.add_exercise_media_link(
                uid, exercise_id, asset_id, cand.get("sentence") or "",
                float(cand.get("start") or 0), float(cand.get("end") or 0),
                cover, clip)
            if link_id is None:
                raise HTTPException(status_code=422,
                                    detail={"error": "该片段已关联过这个动作"})
            candidates[index]["status"] = "linked"
            db.update_media_asset(asset_id, status="ready", candidates=candidates)
            return {"result": "linked", "link_id": link_id,
                    "cover": bool(cover), "clip": bool(clip)}
        raise HTTPException(status_code=400, detail={"error": "action 必须是 link/new/reject"})

    @api.get("/users/{uid}/exercise-media")
    def exercise_media(uid: str, request: Request, exercise_id: str = Query(...)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"links": db.list_exercise_media(uid, exercise_id)}

    @api.get("/users/{uid}/exercise-proposals")
    def exercise_proposal_list(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"proposals": db.list_exercise_proposals(uid)}

    @api.post("/users/{uid}/exercise-proposals/{proposal_id}/review")
    def exercise_proposal_review(uid: str, proposal_id: int, request: Request,
                                 payload: dict = Body(...)):
        """M5.2 P0-2 原子审核：pending 校验 → 冲突检查 → 插入 custom_exercises
        → 读回确认 → 才提交 approved。任何失败保持提案 pending 并清理产物。
        自定义动作只入 SQLite（本人可见），绝不写 exercises/ 目录（P0-1）。
        """
        import re as _re
        from coach import exercise_service as _svc
        db = request.app.state.db
        _user_profile(db, uid)
        decision = payload.get("decision")
        if decision not in ("approve", "reject"):
            raise HTTPException(status_code=400,
                                detail={"error": "decision 必须是 approve/reject"})
        row = db.conn.execute(
            "SELECT * FROM exercise_proposals WHERE user_id=? AND id=?",
            (uid, proposal_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"error": "提案不存在"})
        if row["status"] != "pending":
            raise HTTPException(status_code=422,
                                detail={"error": f"提案已处于 {row['status']} 状态，不能重复审核"})
        if decision == "reject":
            db.conn.execute(
                "UPDATE exercise_proposals SET status='rejected' WHERE id=?",
                (proposal_id,))
            db.conn.commit()
            return {"proposal_id": proposal_id, "status": "rejected"}

        # ---- approve：全部校验先行，任何失败提案保持 pending ----
        import yaml as _yaml
        proposal = dict(row)
        ex_id = _re.sub(r"[^a-z0-9_]+", "_",
                        str(payload.get("id") or proposal["name"]).strip().lower())
        if not ex_id or not ex_id[0].isalpha():
            raise HTTPException(status_code=422,
                                detail={"error": "动作 id 非法（须以字母开头）"})
        if library.get(ex_id) or db.get_custom_exercise(uid, ex_id):
            raise HTTPException(status_code=422,
                                detail={"error": f"动作 id {ex_id!r} 已存在"})
        pattern = payload.get("pattern") or proposal.get("pattern") or "isolation"
        if pattern not in ("squat", "hinge", "lunge", "h_push", "v_push",
                           "h_pull", "v_pull", "isolation", "core", "carry"):
            pattern = "isolation"
        name = proposal["name"]
        aliases = [str(a) for a in (payload.get("aliases")
                                    or _load_aliases(proposal.get("aliases")))][:8]
        conflicts = _svc.alias_conflicts(db, uid, name, aliases)
        if conflicts:
            raise HTTPException(status_code=422,
                                detail={"error": "名称/别名与既有动作冲突",
                                        "details": conflicts[:5]})
        doc = {
            "id": ex_id, "name": name,
            "aliases": list(dict.fromkeys([name, *aliases])),
            "pattern": pattern,
            "primary": [str(x) for x in (payload.get("primary") or [])][:4],
            "secondary": [], "equipment": [str(x) for x in (payload.get("equipment") or ["bodyweight"])][:3],
            "location": ["gym", "home"],
            "level_min": "beginner", "joint_stress": {},
            "track_e1rm": False, "substitutes": [], "status": "draft",
            "scope": "user",
            "_provenance": {"source": "user_video_proposal",
                            "proposal_id": proposal_id,
                            "sentence": proposal.get("sentence") or ""},
        }
        # 插入 → 读回确认 → 提交审核状态（最后一步）
        inserted = db.add_custom_exercise(uid, ex_id, doc)
        if inserted is None:
            raise HTTPException(status_code=422,
                                detail={"error": f"动作 id {ex_id!r} 已存在"})
        readback = db.get_custom_exercise(uid, ex_id)
        if not readback or readback["name"] != name:
            db.conn.execute("DELETE FROM custom_exercises WHERE user_id=? AND ex_id=?",
                            (uid, ex_id))
            db.conn.commit()
            raise HTTPException(status_code=422,
                                detail={"error": "入库读回校验失败，已回滚"})
        db.conn.execute("UPDATE exercise_proposals SET status='approved' WHERE id=?",
                        (proposal_id,))
        db.conn.commit()
        # 可选：把提案依据片段关联到新动作
        link_id = None
        if payload.get("link_media") and proposal.get("asset_id"):
            from coach.media_import import make_clip, make_cover
            asset = db.get_media_asset(uid, proposal["asset_id"])
            if asset and asset["status"] == "ready":
                sentence = proposal.get("sentence") or ""
                start = 0.0
                for cnd in asset.get("candidates") or []:
                    if sentence and cnd.get("sentence") == sentence:
                        start = float(cnd.get("start") or 0)
                media_dir = Path(asset["video_path"]).parent
                cover = make_cover(asset["video_path"], start,
                                   str(media_dir / f"cover_prop{proposal_id}.jpg"))
                clip = make_clip(asset["video_path"], start, start + 15,
                                 str(media_dir / f"clip_prop{proposal_id}.mp4"))
                link_id = db.add_exercise_media_link(
                    uid, ex_id, asset["id"], sentence, start, start + 15,
                    cover, clip)
        return {"proposal_id": proposal_id, "status": "approved",
                "exercise_id": ex_id, "media_link_id": link_id,
                "scope": "user",
                "note": "已入你的自定义动作库（仅本人可见；status=draft，"
                        "加入计划时将带披露说明）"}

    @api.post("/users/{uid}/media/{asset_id}/manual-proposal")
    def media_manual_proposal(uid: str, asset_id: int, request: Request,
                              payload: dict = Body(...)):
        """M5.2 P0-3：无候选视频也能从 UI 手动创建新动作提案。"""
        db = request.app.state.db
        _user_profile(db, uid)
        asset = db.get_media_asset(uid, asset_id)
        if not asset or asset["status"] != "ready":
            raise HTTPException(status_code=422,
                                detail={"error": "视频尚未处理完成或处理失败"})
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail={"error": "需要动作名称"})
        sentence = str(payload.get("sentence") or "").strip()
        if not sentence and asset.get("transcript"):
            sentence = str(asset["transcript"][0].get("text") or "")[:200]
        proposal_id = db.add_exercise_proposal(
            uid, name, [str(a) for a in (payload.get("aliases") or [])][:8],
            str(payload.get("pattern") or "isolation"),
            str(payload.get("note") or "手动创建（无自动候选）"),
            asset_id, sentence)
        return {"proposal_id": proposal_id, "status": "pending"}

    # ---- M4：动作视频分析（上传/任务/结果/对比）----

    @api.post("/users/{uid}/motion-analyses")
    async def motion_upload(uid: str, request: Request):
        from starlette.datastructures import UploadFile
        import threading
        import time as _time
        from coach.motion_analysis import process_analysis
        db = request.app.state.db
        _user_profile(db, uid)
        form = await request.form()
        video = form.get("video")
        exercise_id = str(form.get("exercise_id") or "").strip()
        view = str(form.get("view") or "side")
        if view not in ("side", "front", "back"):
            raise HTTPException(status_code=422, detail={"error": "view 必须是 side/front/back"})
        if not isinstance(video, UploadFile) or not video.filename:
            raise HTTPException(status_code=400, detail={"error": "需要 video 文件"})
        if not exercise_id:
            raise HTTPException(status_code=422, detail={"error": "需要 exercise_id"})
        media_dir = db.path.parent / "media" / uid
        media_dir.mkdir(parents=True, exist_ok=True)
        usage_files, usage_bytes = _user_media_usage(media_dir)
        if usage_files >= MAX_USER_MEDIA_FILES:
            raise UploadRejected(422, f"媒体文件数已达上限（{MAX_USER_MEDIA_FILES}），请清理后再传")
        video_path = media_dir / f"ma{int(_time.time() * 1000)}_{Path(video.filename).name}"
        size = await _stream_upload_to(video, video_path, MAX_VIDEO_BYTES)
        if usage_bytes + size > MAX_USER_MEDIA_BYTES:
            video_path.unlink(missing_ok=True)
            raise UploadRejected(422, "媒体总容量已达上限（2GB），请清理后再传")

        def _process(wdb) -> None:
            try:
                result = process_analysis(exercise_id, str(video_path), view)
                wdb.finish_motion_analysis(analysis_id, "ready", result=result)
                # P4：建立技术档案（1:1 扩展表）并通知动作技术顾问。
                # 整体容错：分析已落库，档案/事件失败只留日志不回滚。
                try:
                    from coach.motion_analysis import ANALYSIS_MODEL_VERSION
                    quality_status = "usable" if result.get("supported") \
                        and result.get("frames", 0) > 0 \
                        and (result.get("detection_ratio") or 0) >= 0.5 else "poor"
                    if not result.get("supported"):
                        quality_status = "unsupported"
                    wdb.upsert_motion_tech_profile(uid, analysis_id, exercise_id, {
                        "model_version": result.get("model_version",
                                                    ANALYSIS_MODEL_VERSION),
                        "video_quality": {
                            "status": quality_status, "view": view,
                            "detection_ratio": result.get("detection_ratio"),
                            "valid_ratio": result.get("valid_ratio"),
                            "limitations": [f.get("hint") for f in
                                            (result.get("faults") or [])
                                            if f.get("code") in
                                            ("UNSUPPORTED", "UNSUPPORTED_VIEW",
                                             "INSUFFICIENT_DATA")]
                            or ([] if quality_status == "usable" else
                                [result.get("note", "")])},
                        "motion_observations": result.get("observations") or [],
                        "phase_timestamps": result.get("reps") or [],
                    })
                    from coach.experts import task_dispatcher
                    task_dispatcher.on_event(wdb, uid, "VideoAnalysisCompleted",
                                             {"analysis_id": analysis_id,
                                              "exercise_id": exercise_id,
                                              "motion_version":
                                                  wdb.motion_profile_version(uid)})
                except Exception:  # noqa: BLE001 档案/事件失败不回滚分析
                    pass
            except Exception as e:  # noqa: BLE001 失败要留痕不吞
                wdb.finish_motion_analysis(analysis_id, "failed", error=str(e))

        analysis_id = db.add_motion_analysis(uid, exercise_id, view, str(video_path))
        _run_media_worker(request.app, _process)
        return {"analysis_id": analysis_id, "status": "processing"}

    @api.get("/users/{uid}/motion-analyses")
    def motion_list(uid: str, request: Request, exercise_id: str | None = Query(None)):
        db = request.app.state.db
        _user_profile(db, uid)
        analyses = db.list_motion_analyses(uid, exercise_id)
        # P4：附带技术档案（1:1 扩展；旧记录 profile=None 如实标注）
        for a in analyses:
            a["tech_profile"] = db.get_motion_tech_profile(uid, a["id"])
        return {"analyses": analyses}

    @api.delete("/users/{uid}/motion-analyses/{analysis_id}")
    def motion_delete(uid: str, analysis_id: int, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        if not db.delete_motion_analysis(uid, analysis_id):
            raise HTTPException(status_code=404,
                                detail={"error": "分析记录不存在"})
        return {"deleted": analysis_id}

    @api.post("/users/{uid}/motion-analyses/{analysis_id}/notes")
    def motion_notes(uid: str, analysis_id: int, request: Request,
                     notes: str = Body(..., embed=True)):
        db = request.app.state.db
        _user_profile(db, uid)
        if not db.set_motion_user_notes(uid, analysis_id, notes):
            raise HTTPException(status_code=404,
                                detail={"error": "技术档案不存在（旧版分析无档案）"})
        return {"analysis_id": analysis_id, "user_notes": notes}

    @api.get("/users/{uid}/motion-analyses/compare")
    def motion_compare(uid: str, request: Request,
                       a: int = Query(...), b: int = Query(...)):
        from coach.motion_analysis import compare_results
        db = request.app.state.db
        _user_profile(db, uid)
        ra, rb = (db.get_motion_analysis(uid, a), db.get_motion_analysis(uid, b))
        if not ra or not rb:
            raise HTTPException(status_code=404, detail={"error": "分析记录不存在"})
        if ra["status"] != "ready" or rb["status"] != "ready":
            raise HTTPException(status_code=422, detail={"error": "两次分析都需完成处理"})
        if ra["exercise_id"] != rb["exercise_id"]:
            raise HTTPException(status_code=422,
                                detail={"error": "对比需要同一动作的两次分析"})
        return {"a": {"id": a, **ra["result"]}, "b": {"id": b, **rb["result"]},
                "compare": compare_results(ra["result"], rb["result"])}

    # ---- M5：个人尝试闭环（发起/结束复盘）+ 方式版本内容 ----

    @api.post("/users/{uid}/trials")
    def trial_start(uid: str, request: Request, payload: dict = Body(...)):
        """发起新尝试（五要素必填；同一时间仅一个进行中）。"""
        db = request.app.state.db
        _user_profile(db, uid)
        fields = {k: str(payload.get(k) or "").strip()
                  for k in ("change_desc", "reason", "observe", "stop_rule")}
        missing = [k for k, v in fields.items() if not v]
        if missing:
            raise HTTPException(status_code=422,
                                detail={"error": "个人尝试五要素必填（改变什么/为什么/观察什么/何时停止）",
                                        "details": [f"缺少 {m}" for m in missing]})
        days = payload.get("review_days")
        if days is not None and (not isinstance(days, int) or isinstance(days, bool)
                                 or not 1 <= days <= 180):
            raise HTTPException(status_code=422,
                                detail={"error": "review_days 必须是 1-180 的整数"})
        try:
            trial_id = db.start_personal_trial(
                uid, fields["change_desc"], fields["reason"],
                fields["observe"], fields["stop_rule"], days,
                baseline=str(payload.get("baseline") or "").strip() or None)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return {"trial_id": trial_id, "status": "active"}

    @api.get("/users/{uid}/trials/{trial_id}")
    def trial_detail(uid: str, trial_id: int, request: Request,
                     review: int = Query(0, ge=0, le=1)):
        """尝试详情：观察进展；review=1 或到达观察条件时附复盘草稿。"""
        from coach.training_progression import trial_service
        db = request.app.state.db
        _user_profile(db, uid)
        trial = db.get_personal_trial(uid, trial_id)
        if not trial:
            raise HTTPException(status_code=404,
                                detail={"error": "尝试不存在"})
        observation = trial_service.trial_observation(db, uid, trial)
        out = {"trial": trial_service.public_trial(trial), "observation": observation}
        if review or observation.get("due_for_review") or trial["status"] != "active":
            out["review"] = trial_service.trial_review(db, uid, trial)
        return out

    @api.post("/users/{uid}/trials/{trial_id}/decision")
    def trial_decision(uid: str, trial_id: int, request: Request,
                       payload: dict = Body(...)):
        """P5-C3 用户决策：keep/adjust/stop/observe；任何分支都不自动改计划。"""
        from coach.training_progression import trial_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return trial_service.decide_trial(
                db, uid, trial_id, str(payload.get("decision") or ""),
                str(payload.get("note") or ""))
        except ValueError as e:
            raise HTTPException(status_code=422,
                                detail={"error": str(e)}) from None

    @api.post("/users/{uid}/trials/{trial_id}/end")
    def trial_end(uid: str, trial_id: int, request: Request,
                  payload: dict = Body(...)):
        """结束并复盘：记录期间感受/执行情况 + 最终决定。"""
        db = request.app.state.db
        _user_profile(db, uid)
        decision = str(payload.get("decision") or "")
        if decision not in ("keep", "stop", "adjust"):
            raise HTTPException(status_code=422,
                                detail={"error": "decision 必须是 keep/stop/adjust"})
        outcome = str(payload.get("outcome") or "").strip()
        if not outcome:
            raise HTTPException(status_code=422,
                                detail={"error": "复盘需要记录尝试期间的感受/执行情况"})
        if not db.end_personal_trial(uid, trial_id, outcome, decision):
            raise HTTPException(status_code=404,
                                detail={"error": "尝试不存在或已结束"})
        return {"trial_id": trial_id, "status": "ended", "decision": decision}

    @api.get("/users/{uid}/approach/revisions/{revision}")
    def approach_revision_content(uid: str, revision: int, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        snap = db.get_approach_revision(uid, revision)
        if not snap:
            raise HTTPException(status_code=404, detail={"error": f"版本 v{revision} 不存在"})
        return {"revision": revision, "content": snap["content"],
                "created_at": snap["created_at"], "initiator": snap["initiator"]}

    # ---- M2：咨询留痕 / 计划版本历史与恢复 ----

    @api.get("/users/{uid}/consultations")
    def consultations(uid: str, request: Request,
                      limit: int = Query(5, ge=1, le=20)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"consultations": db.list_consultations(uid, limit)}

    @api.get("/users/{uid}/plan/revisions")
    def plan_revisions(uid: str, request: Request,
                       limit: int = Query(20, ge=1, le=100)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"revisions": db.list_plan_versions(uid, limit)}

    @api.post("/users/{uid}/plan/revisions/{version}/restore")
    def plan_restore(uid: str, version: int, request: Request,
                     reason: str = Body("", embed=True)):
        from coach.changes import ProposalRejected as _PR, restore_plan_version
        try:
            return restore_plan_version(request.app.state.db, uid, version, reason)
        except _PR as e:
            raise _reject(e) from None

    # ---- 计划 ----

    @api.get("/users/{uid}/plan")
    def get_plan(uid: str, request: Request):
        db = request.app.state.db
        profile = _user_profile(db, uid)
        record = db.get_active_plan_record(uid)
        if not record:
            raise HTTPException(status_code=404, detail={"error": "当前没有生效的计划"})
        return {
            "plan_id": record["id"], "version": record["version"],
            "fenced": bool(profile.get("plan_fence")),
            "base_version": {"plan_id": record["id"], "plan_version": record["version"]},
            "content": record["content"],
            "text": plan_to_text(record["content"]),
        }

    @api.post("/users/{uid}/plan/edits")
    def plan_edits(uid: str, request: Request, payload: dict = Body(...)):
        """计划手动编辑（2.0 §4.1：常规编辑不需 AI 批准，安全校验不豁免）。

        M1.1 P0-1：base_version 必填——客户端必须携带打开编辑器时的计划版本，
        不允许后端自动补最新版，否则并发编辑会绕过乐观锁把旧操作应用到新计划。
        """
        db = request.app.state.db
        if not db.get_active_plan_record(uid):
            raise HTTPException(status_code=404, detail={"error": "当前没有生效的计划"})
        base = payload.get("base_version")
        if not isinstance(base, dict) or not base.get("plan_id") or not base.get("plan_version"):
            raise HTTPException(
                status_code=422,
                detail={"error": "缺少 base_version：请携带打开编辑器时的计划版本"
                                 "（plan_id + plan_version），防止并发修改互相覆盖"})
        from coach import exercise_service as _svc
        resolver = (lambda t, _u=uid, _d=db:
                    _svc.resolve(_d, _u, t))
        try:
            return submit_manual(db, uid, "plan", payload.get("operations"),
                                 str(payload.get("reason") or "手动编辑计划"), base,
                                 resolver=resolver)
        except ProposalRejected as e:
            raise _reject(e) from None

    # ---- 打卡 ----

    @api.get("/users/{uid}/checkins")
    def list_checkins(uid: str, request: Request, limit: int = Query(20, ge=1, le=50),
                      offset: int = Query(0, ge=0), date: str = ""):
        # M6.3.1：date=YYYY-MM-DD 供训练日历查看当天完整记录（不受列表窗口限制）
        import re as _re
        if date and not _re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise HTTPException(status_code=422, detail={"error": "date 需为 YYYY-MM-DD"})
        _user_profile(request.app.state.db, uid)
        return {"checkins": request.app.state.db.list_checkins(
            uid, limit, offset=offset, date=date or None)}

    @api.post("/users/{uid}/checkins")
    def save_checkin(uid: str, request: Request, payload: dict = Body(...)):
        """确定性打卡落库（与 agent save_checkin 同一套清洗与归一，不经 LLM）。

        M1.1：
        - P0-2 幂等——可选 submission_id（客户端稳定提交 ID），重试同一 ID
          返回已保存结果，不重复入库（响应已丢/断网重放场景）。
        - P0-4 逐组——exercises[].set_logs 每组完整保存；聚合字段
          （sets/weight_kg/reps/rpe）由服务端从正式组派生，保证旧复盘/调整
          引擎无感兼容，客户端不再上传"最后一组"式聚合。
        """
        db = request.app.state.db
        ctype = payload.get("type", "training")
        if ctype not in ("training", "body", "diet"):
            raise HTTPException(status_code=400,
                                detail={"error": "type 必须是 training/body/diet"})
        submission_id = str(payload.get("submission_id") or "").strip()[:64]
        if submission_id:
            existing = db.get_checkin_submission(uid, submission_id)
            if existing:
                return {"id": existing["checkin_id"], "type": ctype,
                        "warnings": [], "existing": True}
        data, warnings = coerce_checkin(ctype, payload.get("data", {}))
        notes = list(warnings)
        if ctype == "training":
            for ex in data.get("exercises", []):
                # P0-4：有逐组记录时，聚合字段一律从正式组派生（以容量最大的组为代表组）
                logs = ex.get("set_logs") if isinstance(ex.get("set_logs"), list) else None
                if logs:
                    main = [s for s in logs if isinstance(s, dict) and not s.get("warmup")]
                    if main:
                        # M6.4-A：bodyweight_reps 的负荷 = 额外负重（自重不可比，不计入容量口径）
                        # P5-A：复杂组代表段=段中容量最大段（主级字段从段派生）
                        def _load(s: dict):
                            if s.get("method") in ("drop_set", "rest_pause",
                                                   "unilateral")                                     and isinstance(s.get("segments"), list):
                                t = s.get("type") or "weight_reps"
                                best = max((seg for seg in s["segments"]
                                            if seg.get("reps")),
                                           key=lambda g: ((
                                               (g.get("added_weight_kg") or 0)
                                               if t == "bodyweight_reps"
                                               else (g.get("weight_kg") or 0))
                                               * g["reps"]), default=None)
                                if best is None:
                                    return None
                                return (best.get("added_weight_kg")
                                        if t == "bodyweight_reps"
                                        else best.get("weight_kg"))
                            return s.get("added_weight_kg") \
                                if s.get("type") == "bodyweight_reps" \
                                else s.get("weight_kg")

                        def _reps_of(s: dict):
                            if s.get("method") in ("drop_set", "rest_pause",
                                                   "unilateral")                                     and isinstance(s.get("segments"), list):
                                return sum(g.get("reps") or 0
                                           for g in s["segments"])
                            return s.get("reps")
                        best = max(main, key=lambda s: (
                            (_load(s) or 0) * (_reps_of(s) or 0), _load(s) or 0))
                        ex["sets"] = len(main)
                        ex["weight_kg"] = _load(best)
                        ex["reps"] = _reps_of(best)
                        ex["rpe"] = best.get("rpe")
                    else:
                        ex.pop("weight_kg", None)
                        ex.pop("reps", None)
                        ex.pop("sets", None)
                        ex.pop("rpe", None)
                # M6.3：客户端（自由训练/临时替换）可携带会话中的稳定 exercise_id；
                # 仅当该 id 确实存在（内置库或本人自定义）时采信，否则仍由名称系统判定
                claimed = ex.get("exercise_id")
                claimed_ok = isinstance(claimed, str) and claimed and (
                    bool(library.get(claimed))
                    or request.app.state.db.get_custom_exercise(uid, claimed) is not None)
                ex["exercise_id"] = claimed if claimed_ok else None
                raw_name = ex.get("name", "")
                if claimed_ok:
                    ex.pop("name_raw", None)
                else:
                    ex_id, official, _via = library.normalize(raw_name)
                    if ex_id:
                        ex["exercise_id"] = ex_id
                        if official != raw_name:
                            ex["name_raw"] = raw_name
                        ex["name"] = official
                    else:
                        _log_unmatched(request, uid, raw_name)
                        notes.append(f"未识别动作「{raw_name}」：已按原名记录并进入待补队列")
                record_id = ex.get("exercise_id") or CUSTOM_HIIT_EXERCISE_ID
                for log in ex.get("set_logs") or []:
                    hiit = log.get("hiit") if isinstance(log, dict) else None
                    if not isinstance(hiit, dict):
                        continue
                    if hiit.get("exercise_id") and hiit["exercise_id"] != record_id:
                        notes.append("HIIT 计划身份与记录动作不一致，已以记录动作为准")
                    hiit["exercise_id"] = record_id
                    for block in hiit.get("blocks") or []:
                        block_id = block.get("exercise_id")
                        valid_block_id = isinstance(block_id, str) and block_id and (
                            bool(library.get(block_id))
                            or db.get_custom_exercise(uid, block_id) is not None)
                        if not valid_block_id:
                            block["exercise_id"] = CUSTOM_HIIT_EXERCISE_ID
                            notes.append("HIIT 动作身份无法识别，已按自定义间歇活动记录")
                replacement_of = ex.get("session_replacement_of")
                if replacement_of:
                    from coach.substitution import (
                        SafetyGateError as _SubSafety,
                        validate_session_replacement_safety,
                    )
                    try:
                        validate_session_replacement_safety(
                            db, uid, str(ex.get("exercise_id") or ""),
                            ex.get("set_logs"))
                    except _SubSafety as e:
                        raise HTTPException(status_code=422,
                                            detail={"error": str(e)}) from None
        if ctype == "training":
            from coach.analytics.activity_class import stamp_training_data
            stamp_training_data(db, uid, data)
        checkin_id = db.record_checkin(uid, ctype, data)
        if submission_id and not db.record_checkin_submission(uid, submission_id, checkin_id):
            # 并发同 ID（极小窗口）：删除刚落的重复行，以先落库者为准
            first = db.get_checkin_submission(uid, submission_id)
            db.conn.execute("DELETE FROM checkins WHERE user_id=? AND id=?",
                            (uid, checkin_id))
            db.conn.commit()
            return {"id": first["checkin_id"], "type": ctype,
                    "warnings": notes, "existing": True}
        # P0 专家平台：训练保存 → WorkoutSaved → 订阅的确定性分析（如训练后回顾）。
        # 事件分发整体容错：专家分析失败绝不阻塞打卡保存（2.0 §11.4）。
        if ctype == "training":
            try:
                from coach.experts import task_dispatcher
                task_dispatcher.on_event(db, uid, "WorkoutSaved",
                                         {"checkin_id": checkin_id})
            except Exception:  # noqa: BLE001 打卡主流程已成功，专家链路异常只留任务日志
                pass
        return {"id": checkin_id, "type": ctype, "warnings": notes}

    # ---- M6.4-A：训练模板（可复用，与计划/会话独立） ----

    @api.get("/users/{uid}/training-templates")
    def list_training_templates(uid: str, request: Request):
        _user_profile(request.app.state.db, uid)
        return {"templates": request.app.state.db.list_training_templates(uid)}

    @api.post("/users/{uid}/training-templates")
    def save_training_template(uid: str, request: Request, payload: dict = Body(...)):
        db = request.app.state.db
        _user_profile(db, uid)
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail={"error": "模板名称必填"})
        entries = payload.get("entries")
        if not isinstance(entries, list) or not entries:
            # P5-B：HIIT 模板（doc.hiit）允许无力量动作条目
            if not (isinstance(payload.get("hiit"), dict)
                    and payload["hiit"].get("blocks")):
                raise HTTPException(status_code=422,
                                    detail={"error": "模板至少需要一个动作"})
        doc = {"entries": entries}
        if payload.get("note"):
            doc["note"] = str(payload["note"])[:200]
        # P5-B：HIIT 模板（编排块随模板保存，load 自动带出）
        if isinstance(payload.get("hiit"), dict) and payload["hiit"].get("blocks"):
            hiit = payload["hiit"]
            blocks = hiit["blocks"]
            if (not isinstance(hiit.get("name"), str) or not hiit["name"].strip()
                    or not isinstance(blocks, list) or not 1 <= len(blocks) <= 12):
                raise HTTPException(status_code=422, detail={"error": "HIIT 模板编排无效"})
            total_work = 0
            total_rest = 0
            for block in blocks:
                if not isinstance(block, dict) or not str(block.get("name") or "").strip():
                    raise HTTPException(status_code=422, detail={"error": "HIIT 模板编排无效"})
                work = block.get("work_seconds")
                rest = block.get("rest_seconds")
                rounds = block.get("rounds")
                if (not isinstance(work, int) or isinstance(work, bool) or not 1 <= work <= 86400
                        or not isinstance(rest, int) or isinstance(rest, bool) or not 0 <= rest <= 86400
                        or not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= 999):
                    raise HTTPException(status_code=422, detail={"error": "HIIT 模板编排无效"})
                block_id = block.get("exercise_id")
                if (not isinstance(block_id, str) or not block_id
                        or not (library.get(block_id)
                                or db.get_custom_exercise(uid, block_id))):
                    raise HTTPException(status_code=422,
                                        detail={"error": "HIIT 模板动作身份无效"})
                total_work += work * rounds
                total_rest += rest * rounds
            if total_work > 86400 or total_rest > 86400:
                raise HTTPException(status_code=422,
                                    detail={"error": "HIIT 模板总时长不能超过 24 小时"})
            plan_id = hiit.get("exercise_id")
            if plan_id is not None and (
                    not isinstance(plan_id, str) or not plan_id
                    or not (library.get(plan_id)
                            or db.get_custom_exercise(uid, plan_id))):
                raise HTTPException(status_code=422,
                                    detail={"error": "HIIT 模板动作身份无效"})
            doc["hiit"] = hiit
            hiit_index = payload.get("hiit_index", len(entries))
            if (not isinstance(hiit_index, int) or isinstance(hiit_index, bool)
                    or not 0 <= hiit_index <= len(entries)):
                raise HTTPException(status_code=422,
                                    detail={"error": "HIIT 模板位置无效"})
            doc["hiit_index"] = hiit_index
        try:
            tid = db.save_training_template(
                uid, name[:40], doc,
                template_id=payload.get("id"))
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)}) from None
        return {"id": tid, "name": name}

    @api.delete("/users/{uid}/training-templates/{template_id}")
    def delete_training_template(uid: str, template_id: int, request: Request):
        try:
            request.app.state.db.delete_training_template(uid, template_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)}) from None
        return {"deleted": template_id}

    # ---- M6.3 训练数据分析（逐组口径） ----

    @api.get("/users/{uid}/exercise-stats/{exercise_id}")
    def exercise_stats(uid: str, exercise_id: str, request: Request):
        from coach import analytics
        db = request.app.state.db
        _user_profile(db, uid)
        sessions = analytics.exercise_sessions(db, uid, exercise_id)
        return {"sessions": sessions, "records": analytics.personal_records(sessions)}

    @api.get("/users/{uid}/training-calendar")
    def training_calendar(uid: str, request: Request, year: int, month: int):
        from coach import analytics
        _user_profile(request.app.state.db, uid)
        return analytics.month_calendar(request.app.state.db, uid, year, month)

    @api.get("/users/{uid}/period-summary")
    def period_summary(uid: str, request: Request, days: int = 30):
        from coach import analytics
        _user_profile(request.app.state.db, uid)
        return analytics.period_summary(request.app.state.db, uid, days)

    @api.get("/users/{uid}/training-facts")
    def training_facts(uid: str, request: Request,
                       window_days: int = Query(30, ge=1, le=400)):
        from coach.analytics.fact_service import get_training_facts
        _user_profile(request.app.state.db, uid)
        return get_training_facts(request.app.state.db, uid, window_days)

    @api.get("/users/{uid}/training-progression/{exercise_id}")
    def training_progression(uid: str, exercise_id: str, request: Request,
                             plan_id: int | None = Query(None),
                             plan_version: int | None = Query(None),
                             planned_day: str | None = Query(None),
                             index: int | None = Query(None),
                             planned_exercise_id: str | None = Query(None)):
        """P5-C2：下一次训练确定性候选（只读）。

        只读取数据，不创建训练完成记录，不直接修改计划；计划上下文参数
        用于定位当前用户计划中的动作与版本一致性检查——所有读取都按
        user_id 过滤，伪造他人计划上下文只会得到"过期/不存在"。
        """
        from coach.experts import insight_service
        from coach.training_progression import progression_service
        db = request.app.state.db
        _user_profile(db, uid)
        plan_context = {k: v for k, v in {
            "plan_id": plan_id, "plan_version": plan_version,
            "planned_day": planned_day, "index": index,
            "planned_exercise_id": planned_exercise_id}.items()
            if v is not None}
        try:
            result = progression_service.get_next_training_options(
                db, uid, exercise_id, plan_context or None)
        except ValueError as e:
            raise HTTPException(status_code=404,
                                detail={"error": str(e)}) from None
        # 附最近一次同动作的 next-training-review 洞察状态（读取时懒失效）
        related = [i for i in insight_service.list_insights(
            db, uid, specialist="training_science", limit=10)
            if i.get("insight_type") == "next-training-review"
            and str((i.get("input_refs") or {}).get("exercise_id") or "")
            == exercise_id]
        result["insight"] = {
            "id": related[0]["id"], "status": related[0]["status"],
            "status_reason": related[0].get("status_reason"),
            "generated_at": related[0]["generated_at"],
        } if related else None
        return result

    @api.post("/users/{uid}/training-progression/{exercise_id}/adopt")
    def training_progression_adopt(uid: str, exercise_id: str,
                                   request: Request, payload: dict = Body(...)):
        """P5-C3：长期采用候选——由服务端根据当前有效候选构造提案操作。

        不信任前端提交的 proposed_targets：服务端重新计算候选并按
        option_id 取出对应操作，再走统一 ChangeProposal 确认协议
        （pending → 用户确认 → 重新校验版本与安全后提交）。
        """
        from coach.changes import ProposalRejected, stage_ai
        from coach.training_progression import progression_service
        db = request.app.state.db
        _user_profile(db, uid)
        option_id = str(payload.get("option_id") or "").strip()
        if not option_id:
            raise HTTPException(status_code=422,
                                detail={"error": "option_id 必填"})
        plan_context = {k: payload.get(k) for k in (
            "plan_id", "plan_version", "planned_day", "index",
            "planned_exercise_id")} if isinstance(payload, dict) else {}
        plan_context = {k: v for k, v in plan_context.items() if v is not None}
        try:
            result = progression_service.get_next_training_options(
                db, uid, exercise_id, plan_context or None)
        except ValueError as e:
            raise HTTPException(status_code=404,
                                detail={"error": str(e)}) from None
        option = next((o for o in result.get("options") or []
                       if o.get("option_id") == option_id), None)
        if not option:
            raise HTTPException(status_code=422,
                                detail={"error": "候选不存在或已过期，"
                                        "请重新获取建议后再采用"})
        proposal = option.get("plan_proposal")
        if not proposal:
            raise HTTPException(status_code=422,
                                detail={"error": "该候选与当前计划没有实际差异，"
                                        "没有可提交的修改操作"})
        base = result["context"]
        if not base.get("plan_id") or base.get("plan_version") is None:
            raise HTTPException(status_code=422,
                                detail={"error": "当前没有生效计划上下文，"
                                        "无法创建长期修改提案"})
        try:
            staged = stage_ai(
                db, uid, "plan", proposal["operations"],
                f"采用下一次训练建议：{option['title']}"
                f"（候选 {option_id}，规则 {result['rules_version']}）",
                {"plan_id": base["plan_id"],
                 "plan_version": base["plan_version"]})
        except ProposalRejected as e:
            raise _reject(e) from None
        return {**staged, "note": "提案已暂存（pending）：确认前长期计划保持不变；"
                                 "确认时会重新校验计划版本与安全状态"}

    @api.post("/users/{uid}/training-progression/{exercise_id}/trial")
    def training_progression_trial(uid: str, exercise_id: str,
                                   request: Request, payload: dict = Body(...)):
        """P5-C3：从一个确定性候选创建个人尝试（服务端重新计算候选）。"""
        from coach.training_progression import trial_service
        db = request.app.state.db
        _user_profile(db, uid)
        option_id = str(payload.get("option_id") or "").strip()
        if not option_id:
            raise HTTPException(status_code=422,
                                detail={"error": "option_id 必填"})
        plan_context = {k: payload.get(k) for k in (
            "plan_id", "plan_version", "planned_day", "index",
            "planned_exercise_id")}
        plan_context = {k: v for k, v in plan_context.items() if v is not None}
        try:
            return trial_service.start_trial_from_candidate(
                db, uid, exercise_id, option_id, plan_context or None,
                window_days=payload.get("window_days") or 14,
                min_sessions=payload.get("min_sessions") or 3)
        except ValueError as e:
            raise HTTPException(status_code=422,
                                detail={"error": str(e)}) from None

    @api.post("/users/{uid}/checkins/{checkin_id}/correct")
    def correct_checkin(uid: str, checkin_id: int, request: Request,
                        payload: dict = Body(...)):
        try:
            data = payload.get("data", {})
            if isinstance(data, dict):
                from coach.analytics.activity_class import stamp_training_data
                stamp_training_data(request.app.state.db, uid, data,
                                    source="correction_snapshot",
                                    preserve_snapshot=True)
            updated = request.app.state.db.revise_checkin(
                uid, checkin_id, int(payload.get("expected_revision", 0)),
                data, str(payload.get("reason") or ""),
                str(payload.get("evidence") or ""))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return updated

    # ---- P5-B2：训练地点与器械 ----

    @api.get("/users/{uid}/equipment")
    def equipment_list(uid: str, request: Request):
        from coach import equipment as _eq
        db = request.app.state.db
        _user_profile(db, uid)
        return {"equipment": _eq.all_equipment(db, uid),
                "categories": _eq.CATEGORY_LABELS}

    @api.post("/users/{uid}/equipment")
    def equipment_create(uid: str, request: Request, payload: dict = Body(...)):
        from coach import equipment as _eq
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return {"equipment": _eq.create_custom_equipment(db, uid, payload)}
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.patch("/users/{uid}/equipment/{equipment_id}")
    def equipment_update(uid: str, equipment_id: str, request: Request,
                         payload: dict = Body(...)):
        from coach import equipment as _eq
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return {"equipment": _eq.update_custom_equipment(
                db, uid, equipment_id, payload)}
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.delete("/users/{uid}/equipment/{equipment_id}")
    def equipment_delete(uid: str, equipment_id: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        if not db.delete_user_equipment(uid, equipment_id):
            raise HTTPException(status_code=404, detail={"error": "自定义器械不存在"})
        return {"deleted": equipment_id}

    def _locations_payload(db, uid: str) -> dict:
        from coach import equipment as _eq
        profile = _user_profile(db, uid)
        locations = db.list_training_locations(uid)
        if not locations and not profile.get("locations_initialized"):
            current_kind = (profile.get("resources") or {}).get("location") or "gym"
            _eq.seed_default_locations(
                db, uid, current_kind if current_kind in ("gym", "home") else "gym")
            profile["locations_initialized"] = True
            db.save_profile(uid, profile)
            locations = db.list_training_locations(uid)
        catalog = _eq.equipment_map(db, uid)
        current = next((x for x in locations if x["is_current"]), None)
        return {
            "locations": [_eq.location_view(db, uid, x, catalog) for x in locations],
            "current_id": current["id"] if current else None,
            "equipment": list(catalog.values()),
            "categories": _eq.CATEGORY_LABELS,
        }

    @api.get("/users/{uid}/locations")
    def locations_list(uid: str, request: Request):
        return _locations_payload(request.app.state.db, uid)

    @api.post("/users/{uid}/locations")
    def locations_create(uid: str, request: Request, payload: dict = Body(...)):
        from coach import equipment as _eq
        db = request.app.state.db
        _user_profile(db, uid)
        name = str(payload.get("name") or "").strip()[:40]
        kind = str(payload.get("kind") or "custom")
        if not name:
            raise HTTPException(status_code=422, detail={"error": "地点名称必填"})
        if kind not in _eq.LOCATION_KINDS:
            raise HTTPException(status_code=422, detail={"error": "地点类型无效"})
        equipment = _eq.normalize_location_equipment(
            db, uid, payload.get("required_equipment"), payload.get("optional_equipment"))
        try:
            loc = db.create_training_location(uid, {
                "name": name, "kind": kind, **equipment,
            }, make_current=bool(payload.get("current")))
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return {"location": _eq.location_view(db, uid, loc)}

    @api.patch("/users/{uid}/locations/{location_id}")
    def locations_update(uid: str, location_id: int, request: Request,
                         payload: dict = Body(...)):
        from coach import equipment as _eq
        db = request.app.state.db
        _user_profile(db, uid)
        current = db.get_training_location(uid, location_id)
        if not current:
            raise HTTPException(status_code=404, detail={"error": "训练地点不存在"})
        patch = {}
        if "name" in payload:
            name = str(payload.get("name") or "").strip()[:40]
            if not name:
                raise HTTPException(status_code=422, detail={"error": "地点名称必填"})
            patch["name"] = name
        if "kind" in payload:
            kind = str(payload.get("kind") or "")
            if kind not in _eq.LOCATION_KINDS:
                raise HTTPException(status_code=422, detail={"error": "地点类型无效"})
            patch["kind"] = kind
        if "required_equipment" in payload or "optional_equipment" in payload:
            equipment = _eq.normalize_location_equipment(
                db, uid,
                payload.get("required_equipment", current["required_equipment"]),
                payload.get("optional_equipment", current["optional_equipment"]))
            patch.update(equipment)
        try:
            loc = db.update_training_location(uid, location_id, patch)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return {"location": _eq.location_view(db, uid, loc)}

    @api.post("/users/{uid}/locations/{location_id}/select")
    def locations_select(uid: str, location_id: int, request: Request):
        from coach import equipment as _eq
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            loc = db.select_training_location(uid, location_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)}) from None
        return {"location": _eq.location_view(db, uid, loc)}

    @api.delete("/users/{uid}/locations/{location_id}")
    def locations_delete(uid: str, location_id: int, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        if not db.delete_training_location(uid, location_id):
            raise HTTPException(status_code=404, detail={"error": "训练地点不存在"})
        return {"deleted": location_id}

    # ---- 动作库 ----

    @api.get("/exercises")
    def exercises(request: Request, q: str = "", muscle: str = "",
                  equipment: str = "", pattern: str = "", location: str = "",
                  status: str = "", uid: str = "", location_id: int | None = None,
                  available: bool = False, frequent: bool = False):
        from coach import equipment as _eq
        from coach import exercise_service as _svc
        db = request.app.state.db
        items = _svc.list_exercises(db, uid or None)
        loc = None
        if location_id is not None:
            if not uid:
                raise HTTPException(status_code=422, detail={"error": "地点筛选需要 uid"})
            loc = db.get_training_location(uid, location_id)
            if not loc:
                raise HTTPException(status_code=404, detail={"error": "训练地点不存在"})
        elif available and uid:
            loc = next((x for x in db.list_training_locations(uid) if x["is_current"]), None)
        if available and not loc:
            raise HTTPException(status_code=422, detail={"error": "可执行筛选需要训练地点"})
        if status:
            items = [e for e in items if e.get("status") == status]
        if muscle:
            items = [e for e in items if muscle in set(e.get("primary") or [])
                     | set(e.get("secondary") or [])]
        if equipment:
            items = [e for e in items
                     if equipment in (e.get("equipment") or [])]
        if pattern:
            items = [e for e in items if e.get("pattern") == pattern]
        if location:
            items = [e for e in items if location in (e.get("location") or [])]
        if q:
            matched = set()
            ql = q.lower()
            for e in items:
                if ql in e["name"].lower() or ql == e["id"].lower() or any(
                        ql in str(a).lower() for a in (e.get("aliases") or [])):
                    matched.add(e["id"])
            ex_id, official, _via = library.normalize(q)
            if ex_id:
                matched.add(ex_id)
            items = [e for e in items if e["id"] in matched]

        catalog = _eq.equipment_map(db, uid) if uid else \
            {x["id"]: x for x in _eq.system_equipment()}
        available_ids = _eq.location_available_ids(db, uid, loc) if uid and loc else set()
        if available:
            items = [e for e in items if _eq.exercise_availability(
                db, uid, e, loc, catalog, available_ids)["available"]]
        frequent_ids = {x["exercise_id"] for x in db.all_exercise_states(uid)} if uid else set()
        if frequent:
            items = [e for e in items if e["id"] in frequent_ids]
        out = []
        for e in items:
            availability = _eq.exercise_availability(
                db, uid, e, loc, catalog, available_ids) if loc else {
                    "available": None, "missing_equipment_ids": [],
                    "missing_equipment": [], "missing_optional_equipment": [],
                    "location_ok": None}
            out.append({
                "id": e["id"], "name": e["name"],
                "aliases": e.get("aliases") or [],
                "pattern": e.get("pattern"),
                "primary": e.get("primary") or [],
                "equipment": e.get("equipment") or [],
                "equipment_names": [catalog.get(x, {"name": x})["name"]
                                    for x in (e.get("equipment") or [])],
                "location": e.get("location") or [],
                "status": e.get("status"),
                "measurement": e.get("measurement") or "weight_reps",
                "activity": e.get("activity") or "strength",
                "scope": e.get("scope", "builtin"),
                "available": availability["available"],
                "missing_equipment": availability["missing_equipment"],
                "missing_optional_equipment": availability["missing_optional_equipment"],
                "location_ok": availability["location_ok"],
                "frequent": e["id"] in frequent_ids,
            })
        return {"count": len(out), "exercises": out}

    @api.get("/exercises/{ex_id}")
    def exercise_detail(request: Request, ex_id: str, uid: str = ""):
        from coach import exercise_service as _svc
        from coach import teaching_content, teaching_media
        ex = _svc.get_exercise(request.app.state.db, uid or None, ex_id)
        if not ex:
            raise HTTPException(status_code=404, detail={"error": f"动作 {ex_id} 不存在"})
        detail = dict(ex)
        # M6.2：教学文档（knowledge_refs 指向的人工整理内容，含来源；无关联为空表）
        detail["teaching"] = _svc.teaching_for(ex_id)
        # M6.4-B B1：结构化教学（teaching/*.yaml，逐节审核状态）+ 演示可用性。
        # 三维入口只按稳定 exercise_id 关联；自定义动作无公共三维，绝不按名称
        # 相似自动挂到内置模型。
        structured = teaching_content.public_teaching(ex_id)
        detail["teaching_content"] = structured
        demo_3d = (teaching_media.demo_3d(ex_id)
                   if detail.get("scope") == "builtin" else None)
        if demo_3d:
            base = f"/api/assets/exercise-3d/{ex_id}/"
            demo_3d["model_url"] = base + Path(demo_3d["model_path"]).name
            if demo_3d.get("preview_path"):
                demo_3d["preview_url"] = base + Path(demo_3d["preview_path"]).name
        detail["demos"] = {
            "model_3d": demo_3d,
            "text": bool(structured or detail["teaching"]),
            # 视频演示：公共视频暂无授权素材（B0 缺口如实记录）；入口仅由
            # 用户自己导入关联的 exercise_media_links 决定（前端已有数据）。
            "public_video": False,
        }
        if detail.get("status") != "approved":
            detail.setdefault("notes", [])
            detail["notes"] = list(detail["notes"]) + [
                "该动作的结构化属性（关节压力/替代关系）尚未经审核"]
        return detail

    # ---- P5-B2：动作替代候选与服务端安全校验 ----

    @api.get("/users/{uid}/exercise-substitutes")
    def exercise_substitutes(uid: str, request: Request,
                             exercise_id: str = Query(...),
                             location_id: int | None = None):
        from coach import substitution
        _user_profile(request.app.state.db, uid)
        try:
            return substitution.find_candidates(
                request.app.state.db, uid, exercise_id, location_id)
        except substitution.SafetyGateError as e:
            raise HTTPException(status_code=403, detail={"error": str(e)}) from None
        except substitution.SubstitutionError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.post("/users/{uid}/exercise-substitutions/validate")
    def exercise_substitution_validate(uid: str, request: Request,
                                       payload: dict = Body(...)):
        from coach import substitution
        _user_profile(request.app.state.db, uid)
        try:
            return substitution.validate_substitution(
                request.app.state.db, uid,
                str(payload.get("source_exercise_id") or ""),
                str(payload.get("target_exercise_id") or ""),
                payload.get("location_id"))
        except substitution.SafetyGateError as e:
            raise HTTPException(status_code=403, detail={"error": str(e)}) from None
        except substitution.SubstitutionError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    # ---- M6.4-B B2/B3：公共三维教学资产（只下发 manifest 已授权文件）----

    @api.get("/assets/exercise-3d/{ex_id}/{name}")
    def exercise_3d_asset(ex_id: str, name: str):
        from coach import teaching_media
        f = teaching_media.asset_file_for_serving(ex_id, name)
        if not f:
            raise HTTPException(status_code=404,
                                detail={"error": "教学资源不存在或未授权发布"})
        media_type = "model/gltf-binary" if f.suffix == ".glb" else None
        # 文件内容受 manifest sha256 约束；带版本号缓存键可安全长缓存
        return FileResponse(f, media_type=media_type, headers={
            "Cache-Control": "public, max-age=3600"})


    # ---- P0 专家平台：工作台 / 任务 / 洞察 / 设置 ----

    @api.get("/users/{uid}/experts/overview")
    def experts_overview(uid: str, request: Request):
        """Experts 中心页：注册表 + 各顾问最新洞察计数 + 任务状态。"""
        from coach.experts import registry
        db = request.app.state.db
        _user_profile(db, uid)
        counts: dict[str, int] = {}
        for row in db.conn.execute(
                "SELECT specialist, COUNT(*) AS n FROM expert_insights"
                " WHERE user_id=? AND status IN ('ready','viewed')"
                " GROUP BY specialist", (uid,)):
            counts[row["specialist"]] = row["n"]
        return {
            "specialists": [
                {**s, "active_insights": counts.get(s["specialist"], 0)}
                for s in registry.specialists_view()],
            "orchestrator": registry.ORCHESTRATOR,
            "shared_services": registry.SHARED_SERVICES,
            "settings": db.expert_settings(uid),
            "pending_tasks": db.list_expert_tasks(uid, status="pending", limit=5),
        }

    @api.post("/users/{uid}/collaboration/analysis")
    def collaboration_analysis(uid: str, request: Request,
                               payload: dict = Body(...)):
        """P6：用户主动请求跨专家联合分析（UserRequested；确定性，无 LLM）。"""
        from coach.collaboration.coordinator import SCENARIOS
        from coach.experts import task_dispatcher
        db = request.app.state.db
        _user_profile(db, uid)
        scenario = str(payload.get("scenario") or "")
        if not scenario:
            raise HTTPException(status_code=422,
                                detail={"error": "scenario 必填"})
        if scenario not in SCENARIOS:
            raise HTTPException(
                status_code=422,
                detail={"error": f"未知协作场景 {scenario!r}（可选："
                                 f"{sorted(SCENARIOS)}）"})
        params = {"scenario": scenario}
        if payload.get("exercise_id"):
            params["exercise_id"] = str(payload["exercise_id"])
        if payload.get("window_days"):
            params["window_days"] = int(payload["window_days"])
        try:
            task = task_dispatcher.enqueue(db, uid, "collaboration",
                                           "collaboration-review",
                                           "UserRequested", params)
        except ValueError as e:
            raise HTTPException(status_code=422,
                                detail={"error": str(e)}) from None
        if not task:
            raise HTTPException(status_code=429,
                                detail={"error": "同类分析正在进行或频率受限，请稍后再试"})
        return task_dispatcher.run_task(db, task)

    @api.post("/users/{uid}/collaboration/{insight_id}/decision")
    def collaboration_decision(uid: str, insight_id: str, request: Request,
                               payload: dict = Body(...)):
        """P6：联合报告的用户决策（ignore/observe/propose；propose 走确认协议）。"""
        from coach.collaboration import decision_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return decision_service.record_decision(
                db, uid, insight_id, str(payload.get("decision") or ""),
                payload.get("option_id"))
        except ProposalRejected as e:
            raise _reject(e) from None
        except ValueError as e:
            raise HTTPException(status_code=422,
                                detail={"error": str(e)}) from None

    @api.get("/users/{uid}/experts/settings")
    def experts_settings(uid: str, request: Request):
        _user_profile(request.app.state.db, uid)
        return request.app.state.db.expert_settings(uid)

    @api.post("/users/{uid}/experts/settings")
    def experts_save_settings(uid: str, request: Request,
                              payload: dict = Body(...)):
        db = request.app.state.db
        _user_profile(db, uid)
        proactive = payload.get("proactive_enabled")
        if not isinstance(proactive, bool):
            raise HTTPException(status_code=400,
                                detail={"error": "proactive_enabled 必须是布尔值"})
        try:
            return db.save_expert_settings(
                uid, proactive, int(payload.get("min_interval_minutes") or 0))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.post("/users/{uid}/experts/analysis")
    def request_analysis(uid: str, request: Request, payload: dict = Body(...)):
        """用户主动请求分析（UserRequested：不受主动分析开关限制）。"""
        from coach.experts import task_dispatcher
        db = request.app.state.db
        _user_profile(db, uid)
        specialist = str(payload.get("specialist") or "")
        task_type = str(payload.get("task_type") or "post-workout-review")
        params = payload.get("params") or {}
        if task_type == "next-training-review":
            if not params.get("exercise_id"):
                raise HTTPException(
                    status_code=422,
                    detail={"error": "params.exercise_id 必填"
                            "（下一次训练解读针对指定动作）"})
        elif not params.get("checkin_id"):
            raise HTTPException(status_code=422,
                                detail={"error": "params.checkin_id 必填（暂支持对指定训练做回顾）"})
        try:
            task = task_dispatcher.enqueue(db, uid, specialist, task_type,
                                           "UserRequested", params)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        if not task:
            raise HTTPException(status_code=429,
                                detail={"error": "同类分析正在进行或频率受限，请稍后再试"})
        result = task_dispatcher.run_task(db, task)
        return result

    @api.get("/users/{uid}/experts/tasks")
    def expert_tasks(uid: str, request: Request,
                     specialist: str | None = Query(None),
                     status: str | None = Query(None),
                     limit: int = Query(20, ge=1, le=100)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"tasks": db.list_expert_tasks(uid, specialist, status, limit)}

    @api.get("/users/{uid}/experts/tasks/{task_id}")
    def expert_task_detail(uid: str, task_id: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        task = db.get_expert_task(uid, task_id)
        if not task:
            raise HTTPException(status_code=404, detail={"error": "任务不存在"})
        return {**task, "events": db.expert_task_events(task_id)}

    @api.post("/users/{uid}/experts/tasks/{task_id}/cancel")
    def expert_task_cancel(uid: str, task_id: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        task = db.get_expert_task(uid, task_id)
        if not task:
            raise HTTPException(status_code=404, detail={"error": "任务不存在"})
        if task["status"] != "pending":
            raise HTTPException(status_code=422,
                                detail={"error": f"任务状态为 {task['status']}，只有未执行任务可取消"})
        db.update_expert_task(uid, task_id, status="cancelled",
                              event="cancelled", event_detail="用户取消")
        return {"task_id": task_id, "status": "cancelled"}

    @api.get("/users/{uid}/expert-insights")
    def expert_insights(uid: str, request: Request,
                        specialist: str | None = Query(None),
                        status: str | None = Query(None),
                        limit: int = Query(20, ge=1, le=100)):
        """洞察列表（读取时懒判定失效/到期——数据漂移不会以旧充新）。"""
        from coach.experts import insight_service
        db = request.app.state.db
        _user_profile(db, uid)
        return {"insights": insight_service.list_insights(
            db, uid, specialist, status, limit)}

    @api.get("/users/{uid}/expert-insights/{insight_id}")
    def expert_insight_detail(uid: str, insight_id: str, request: Request):
        from coach.experts import insight_service
        db = request.app.state.db
        _user_profile(db, uid)
        insight = insight_service.get_insight(db, uid, insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail={"error": "分析不存在"})
        return insight

    @api.post("/users/{uid}/expert-insights/{insight_id}/view")
    def expert_insight_view(uid: str, insight_id: str, request: Request):
        from coach.experts import insight_service
        db = request.app.state.db
        _user_profile(db, uid)
        insight = insight_service.mark_viewed(db, uid, insight_id)
        if not insight:
            raise HTTPException(status_code=404,
                                detail={"error": "分析不存在或当前状态不能标记已读"})
        return insight

    @api.post("/users/{uid}/expert-insights/{insight_id}/dismiss")
    def expert_insight_dismiss(uid: str, insight_id: str, request: Request):
        """忽略建议：用户明确决策"先不采纳"，历史保留、可重新分析。"""
        from coach.experts import insight_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            insight = insight_service.dismiss(db, uid, insight_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        if not insight:
            raise HTTPException(status_code=404, detail={"error": "分析不存在"})
        return insight

    @api.post("/users/{uid}/expert-insights/{insight_id}/regenerate")
    def expert_insight_regenerate(uid: str, insight_id: str, request: Request):
        """重新分析：以最新数据重跑（旧的 invalidated/dismissed 保留为历史）。"""
        from coach.experts import insight_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return insight_service.regenerate(db, uid, insight_id)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.post("/users/{uid}/expert-insights/{insight_id}/options/{option_id}/proposal")
    def expert_insight_proposal(uid: str, insight_id: str, option_id: str,
                                request: Request):
        """方案 → 待确认修改提案（统一修改协议 AI 路径；确认门在 /changes）。
        绝不经此接口直接生效——顾问没有写权限（2.0 §2.4）。"""
        from coach.experts import recommendation_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return recommendation_service.stage_option_proposal(
                db, uid, insight_id, option_id)
        except ProposalRejected as e:
            raise _reject(e) from None
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    # ---- P1 营养系统：食物库 / 餐次 / 汇总与趋势 / 目标 / 食谱 ----

    @api.get("/nutrition/foods")
    def nutrition_foods(request: Request, uid: str = "", q: str = "",
                        category: str = "", scope: str = "",
                        limit: int = Query(40, ge=1, le=200)):
        from coach.nutrition import food_catalog, meal_service
        meal_service.init_nutrition(request.app.state.db)  # 首次访问装载内置目录
        foods = request.app.state.db.search_foods(uid or None, q, category, scope, limit)
        return {"count": len(foods), "categories": food_catalog.CATEGORIES,
                "foods": foods}

    @api.post("/users/{uid}/nutrition/foods")
    def nutrition_add_food(uid: str, request: Request, payload: dict = Body(...)):
        """自定义食物（营养标签录入；按用户隔离，与内置同名不允许）。"""
        from coach.nutrition import food_catalog
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            food = food_catalog.validate_custom_food(payload)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        food["source_name"] = "用户录入（营养标签/自估）"
        food["license"] = "用户自录数据"
        food_id = db.add_custom_food(uid, food)
        if food_id is None:
            raise HTTPException(status_code=422,
                                detail={"error": "已有同名食物（内置或你的自定义），请换名称"})
        return {"food_id": food_id, "food": db.get_food(uid, food_id)}

    @api.put("/users/{uid}/nutrition/foods/{food_id}")
    def nutrition_update_food(uid: str, food_id: str, request: Request,
                              payload: dict = Body(...)):
        from coach.nutrition import food_catalog
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            patch = food_catalog.validate_custom_food(payload)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        if not db.update_custom_food(uid, food_id, patch):
            raise HTTPException(status_code=404,
                                detail={"error": "食物不存在或不是你的自定义食物"})
        return {"food": db.get_food(uid, food_id)}

    @api.get("/nutrition/foods/{food_id}")
    def nutrition_food_detail(request: Request, food_id: str, uid: str = ""):
        food = request.app.state.db.get_food(uid or None, food_id)
        if not food:
            raise HTTPException(status_code=404, detail={"error": "食物不存在"})
        return food

    @api.get("/users/{uid}/meals")
    def nutrition_meals(uid: str, request: Request, date: str = Query(...)):
        import re as _re
        if not _re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise HTTPException(status_code=422, detail={"error": "date 需为 YYYY-MM-DD"})
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.nutrition import meal_service
        return meal_service.day_summary(db, uid, date)

    @api.post("/users/{uid}/meals")
    def nutrition_save_meal(uid: str, request: Request, payload: dict = Body(...)):
        """记录餐次（快照服务端构造；保存成功触发 MealRecorded→营养分析）。"""
        from coach.nutrition import meal_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            result = meal_service.record_meal(
                db, uid, str(payload.get("date") or ""), str(payload.get("meal_type") or ""),
                payload.get("items") or [], str(payload.get("notes") or ""))
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return result

    @api.put("/users/{uid}/meals/{meal_id}")
    def nutrition_update_meal(uid: str, meal_id: int, request: Request,
                              payload: dict = Body(...)):
        from coach.nutrition import meal_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return meal_service.update_meal(
                db, uid, meal_id, payload.get("items") or [],
                payload.get("notes"), payload.get("meal_type"))
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.delete("/users/{uid}/meals/{meal_id}")
    def nutrition_delete_meal(uid: str, meal_id: int, request: Request):
        from coach.nutrition import meal_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            meal_service.delete_meal(db, uid, meal_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)}) from None
        return {"deleted": meal_id}

    @api.post("/users/{uid}/meals/copy-day")
    def nutrition_copy_day(uid: str, request: Request, payload: dict = Body(...)):
        """复制某天全部餐次到另一天（沿用当时快照，不重算）。"""
        db = request.app.state.db
        _user_profile(db, uid)
        from_date, to_date = str(payload.get("from_date") or ""), str(payload.get("to_date") or "")
        import re as _re
        if not (_re.match(r"^\d{4}-\d{2}-\d{2}$", from_date)
                and _re.match(r"^\d{4}-\d{2}-\d{2}$", to_date)):
            raise HTTPException(status_code=422,
                                detail={"error": "from_date/to_date 需为 YYYY-MM-DD"})
        count = db.copy_day_meals(uid, from_date, to_date)
        if count:
            from coach.nutrition.meal_service import _fire_meal_recorded
            _fire_meal_recorded(db, uid, to_date)
        return {"copied": count}

    @api.get("/users/{uid}/nutrition/summary")
    def nutrition_summary(uid: str, request: Request, date: str = Query(...)):
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.nutrition import meal_service
        return meal_service.day_summary(db, uid, date)

    @api.get("/users/{uid}/nutrition/trends")
    def nutrition_trends(uid: str, request: Request, days: int = Query(7, ge=1, le=90)):
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.nutrition import meal_service
        return meal_service.trends(db, uid, days)

    @api.post("/users/{uid}/nutrition/days/{date}/complete")
    def nutrition_day_complete(uid: str, date: str, request: Request,
                                complete: bool = Body(..., embed=True)):
        db = request.app.state.db
        _user_profile(db, uid)
        db.set_day_complete(uid, date, complete)
        # 完整性变化会改变分析结论边界 → 重新分析该日
        from coach.nutrition.meal_service import _fire_meal_recorded
        _fire_meal_recorded(db, uid, date)
        return {"date": date, "complete": complete}

    @api.get("/users/{uid}/nutrition/targets")
    def nutrition_targets_get(uid: str, request: Request):
        db = request.app.state.db
        profile = _user_profile(db, uid)
        from coach.nutrition import target_service
        return {"targets": db.get_nutrition_targets(uid),
                "reference": target_service.estimate_reference(profile)}

    @api.post("/users/{uid}/nutrition/targets")
    def nutrition_targets_save(uid: str, request: Request, payload: dict = Body(...)):
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            targets = db.save_nutrition_targets(uid, {
                "energy_kcal": payload.get("energy_kcal"),
                "protein_g": payload.get("protein_g"),
                "carbohydrate_g": payload.get("carbohydrate_g"),
                "fat_g": payload.get("fat_g"),
                "preferences": payload.get("preferences") or {},
                "allergies": payload.get("allergies") or [],
                "budget_note": payload.get("budget_note"),
                "precision_willing": payload.get("precision_willing")})
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        # 目标变化改变"目标比较"维度 → 重新分析当天（幂等由 day_version 保证）
        from coach.nutrition.meal_service import _fire_meal_recorded
        if db.meals_on(uid, date.today().isoformat()):
            _fire_meal_recorded(db, uid, date.today().isoformat())
        return {"targets": targets}

    @api.get("/users/{uid}/nutrition/frequent")
    def nutrition_frequent(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.nutrition import meal_service
        return {"foods": meal_service.frequent_foods(db, uid)}

    @api.get("/users/{uid}/nutrition/recipes")
    def nutrition_recipes(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"recipes": db.list_recipes(uid)}

    @api.post("/users/{uid}/nutrition/recipes")
    def nutrition_save_recipe(uid: str, request: Request, payload: dict = Body(...)):
        """把一组食物存为食谱（快照复用）。name + items 必填。"""
        db = request.app.state.db
        _user_profile(db, uid)
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail={"error": "食谱名称必填"})
        try:
            from coach.nutrition import meal_service
            items = meal_service.resolve_items(db, uid, payload.get("items") or [])
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        recipe_id = db.save_recipe(uid, name, items, payload.get("id"))
        return {"recipe_id": recipe_id}

    @api.delete("/users/{uid}/nutrition/recipes/{recipe_id}")
    def nutrition_delete_recipe(uid: str, recipe_id: int, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            db.delete_recipe(uid, recipe_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)}) from None
        return {"deleted": recipe_id}

    # ---- P2 身体数据与恢复管理 ----

    @api.get("/users/{uid}/body-measurements")
    def body_measurements_list(uid: str, request: Request,
                               start: str = "", end: str = "",
                               limit: int = Query(200, ge=1, le=1000)):
        import re as _re
        if (start and not _re.match(r"^\d{4}-\d{2}-\d{2}$", start)) \
                or (end and not _re.match(r"^\d{4}-\d{2}-\d{2}$", end)):
            raise HTTPException(status_code=422,
                                detail={"error": "start/end 需为 YYYY-MM-DD"})
        db = request.app.state.db
        _user_profile(db, uid)
        return {"measurements": db.list_body_measurements(uid, start or None,
                                                          end or None, limit)}

    @api.post("/users/{uid}/body-measurements")
    def body_measurements_add(uid: str, request: Request, payload: dict = Body(...)):
        """新增测量（指标全部可选但至少一项；幂等 submission_id 可选）。"""
        from coach.body import measurement_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            result = measurement_service.record_measurement(
                db, uid, payload.get("data") or payload,
                submission_id=str(payload.get("submission_id") or "")[:64] or None)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        measurement = db.get_body_measurement(uid, result["measurement_id"])
        return {**result, "measurement": measurement}

    @api.patch("/users/{uid}/body-measurements/{mid}")
    def body_measurement_update(uid: str, mid: int, request: Request,
                                payload: dict = Body(...)):
        """编辑测量 = 修订（保留原值；纠错需 reason+evidence）。"""
        from coach.body import measurement_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            updated = measurement_service.update_measurement(
                db, uid, mid, int(payload.get("expected_revision", 0)),
                payload.get("data") or {}, str(payload.get("reason") or ""),
                str(payload.get("evidence") or ""))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return updated

    @api.delete("/users/{uid}/body-measurements/{mid}")
    def body_measurement_delete(uid: str, mid: int, request: Request):
        from coach.body import measurement_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            measurement_service.delete_measurement(db, uid, mid)
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)}) from None
        return {"deleted": mid}

    @api.get("/users/{uid}/body-measurements/{mid}/revisions")
    def body_measurement_revisions(uid: str, mid: int, request: Request):
        _user_profile(request.app.state.db, uid)
        return {"revisions": request.app.state.db.body_measurement_revisions(uid, mid)}

    @api.get("/users/{uid}/body-summary")
    def body_summary(uid: str, request: Request, days: int = Query(30, ge=1, le=3650)):
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.body import body_metrics
        measurements = db.list_body_measurements(uid)
        return body_metrics.summarize(measurements, window_days=days)

    @api.get("/users/{uid}/body-trend")
    def body_trend(uid: str, request: Request, metric: str = "weight_kg",
                   days: int = Query(0, ge=0, le=3650)):
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.body import trend_service
        try:
            return trend_service.trend_for(db, uid, metric, days or None)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.get("/users/{uid}/recovery-checkins")
    def recovery_list(uid: str, request: Request,
                      days: int = Query(90, ge=1, le=365)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"checkins": db.list_recovery_checkins(uid, days)}

    @api.post("/users/{uid}/recovery-checkins")
    def recovery_record(uid: str, request: Request, payload: dict = Body(...)):
        """记录/更新当天恢复（当天一条；更新需 reason+evidence 走修订）。"""
        from coach.recovery import checkin_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return checkin_service.record_checkin(
                db, uid, payload.get("data") or payload,
                submission_id=str(payload.get("submission_id") or "")[:64] or None)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.delete("/users/{uid}/recovery-checkins/{rid}")
    def recovery_delete(uid: str, rid: int, request: Request):
        from coach.recovery import checkin_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            checkin_service.delete_checkin(db, uid, rid)
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)}) from None
        return {"deleted": rid}

    @api.get("/users/{uid}/recovery-summary")
    def recovery_summary(uid: str, request: Request,
                         days: int = Query(14, ge=1, le=90)):
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.recovery import recovery_metrics
        return recovery_metrics.recovery_snapshot(db, uid, window_days=days)

    @api.get("/users/{uid}/pre-training-recovery-brief")
    def recovery_brief(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        from coach.recovery import recovery_analysis
        return recovery_analysis.pre_training_brief(db, uid)

    # ---- P3 康复辅助：症状 / 限制 / 专业安排 / 安全视图 ----

    @api.get("/users/{uid}/symptom-episodes")
    def symptom_episodes(uid: str, request: Request, status: str | None = Query(None)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"episodes": db.list_symptom_episodes(uid, status)}

    @api.get("/users/{uid}/symptom-episodes/{eid}")
    def symptom_episode_detail(uid: str, eid: int, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        ep = db.get_symptom_episode(uid, eid)
        if not ep:
            raise HTTPException(status_code=404, detail={"error": "事件不存在"})
        return {**ep, "observations": db.list_symptom_observations(uid, eid),
                "region_label": __import__("coach.rehab.symptom_service",
                                           fromlist=["REGION_LABELS"]).REGION_LABELS.get(
                    ep["body_region"], ep["body_region"])}

    @api.post("/users/{uid}/symptom-episodes")
    def symptom_report(uid: str, request: Request, payload: dict = Body(...)):
        """报告身体不适：保存 → 同步安全分流（即时返回，不依赖后台任务）→
        按结果维护 triage_recommended 限制。"""
        from coach.rehab import symptom_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            result = symptom_service.report_episode(
                db, uid, payload.get("data") or payload,
                submission_id=str(payload.get("submission_id") or "")[:64] or None)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return result

    @api.post("/users/{uid}/symptom-episodes/{eid}/observations")
    def symptom_observe(uid: str, eid: int, request: Request,
                        payload: dict = Body(...)):
        """追加观察（不覆盖历史；分流同步执行）。"""
        from coach.rehab import symptom_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return symptom_service.add_observation(db, uid, eid,
                                                   payload.get("data") or payload)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.post("/users/{uid}/symptom-episodes/{eid}/status")
    def symptom_status(uid: str, eid: int, request: Request,
                       payload: dict = Body(...)):
        from coach.rehab import symptom_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return symptom_service.update_episode_status(
                db, uid, eid, str(payload.get("status") or ""),
                str(payload.get("reason") or ""), str(payload.get("evidence") or ""))
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.post("/rehab/triage-preview")
    def rehab_triage_preview(payload: dict = Body(...)):
        """分流预览（不落库；供记录页实时提示）。确定性规则，无需用户上下文。"""
        from coach.rehab import triage_rules
        return triage_rules.triage(
            str(payload.get("description") or ""),
            severity=payload.get("severity"),
            functional_limitations=payload.get("functional_limitations"),
            onset_at=payload.get("onset_at"),
            professional_evaluated=bool(payload.get("professional_evaluated")))

    @api.get("/users/{uid}/training-restrictions")
    def restrictions_list(uid: str, request: Request,
                          status: str | None = Query("active")):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"restrictions": db.list_restrictions(uid, status)}

    @api.post("/users/{uid}/training-restrictions")
    def restriction_create(uid: str, request: Request, payload: dict = Body(...)):
        from coach.rehab import restriction_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return restriction_service.create_restriction(db, uid, payload)
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.post("/users/{uid}/training-restrictions/{rid}/lift")
    def restriction_lift(uid: str, rid: int, request: Request,
                         payload: dict = Body(...)):
        """解除限制：按来源类型校验依据（professional 必须附专业人员说明）。"""
        from coach.rehab import restriction_service
        db = request.app.state.db
        _user_profile(db, uid)
        try:
            return restriction_service.lift_restriction(
                db, uid, rid, int(payload.get("expected_revision", 0)),
                str(payload.get("lift_evidence") or ""),
                str(payload.get("reason") or ""))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None

    @api.get("/users/{uid}/safety-view")
    def safety_view_api(uid: str, request: Request):
        from coach.rehab import safety_integration
        db = request.app.state.db
        profile = _user_profile(db, uid)
        view = safety_integration.safety_view(db, uid)
        return {"permission": {"status": view.permission_status,
                               "reason": view.permission_reason,
                               "allows_prescription": view.allows_prescription},
                "plan_fenced": view.plan_fenced,
                "fence_reason": view.fence_reason,
                "active_restrictions": view.active_restrictions,
                "summary_lines": view.summary_lines(),
                "disclaimer": "多来源限制并存时全部生效（并集）；"
                              "任何专家只能收紧不能解除"}

    @api.get("/users/{uid}/care-plans")
    def care_plans_list(uid: str, request: Request):
        db = request.app.state.db
        _user_profile(db, uid)
        plans = db.list_care_plans(uid)
        out = []
        for p in plans:
            activities = db.list_care_activities(uid, p["id"])
            out.append({**p, "activities": [
                {**a, "logs": db.care_activity_logs(uid, a["id"], limit=14)}
                for a in activities]})
        return {"plans": out}

    @api.post("/users/{uid}/care-plans")
    def care_plan_create(uid: str, request: Request, payload: dict = Body(...)):
        """录入专业人员提供的安排（来源说明必填；软件只记录不增强度）。"""
        from coach.rehab import symptom_service as _ss
        db = request.app.state.db
        _user_profile(db, uid)
        title = str(payload.get("title") or "").strip()
        source = str(payload.get("professional_source") or "").strip()
        if not title or not source:
            raise HTTPException(status_code=422,
                                detail={"error": "安排名称与专业人员来源说明必填"})
        plan_id = db.create_care_plan(uid, {
            "title": title[:80], "professional_source": source[:200],
            "applicable_conditions": str(payload.get("applicable_conditions") or "")[:300]
                                     or None,
            "related_episode_id": payload.get("related_episode_id"),
            "review_at": payload.get("review_at")})
        for a in (payload.get("activities") or [])[:10]:
            if isinstance(a, dict) and str(a.get("name") or "").strip():
                db.add_care_activity(uid, plan_id, {
                    "name": str(a["name"])[:80],
                    "frequency": str(a.get("frequency") or "")[:80] or None,
                    "notes": str(a.get("notes") or "")[:200] or None})
        from coach.experts import task_dispatcher
        try:
            task_dispatcher.on_event(db, uid, "CareActivityRecorded",
                                     {"care_plan_id": plan_id,
                                      "symptoms_version": db.symptoms_version(uid)})
        except Exception:  # noqa: BLE001
            pass
        return {"plan_id": plan_id}

    @api.post("/users/{uid}/care-activities/{aid}/log")
    def care_activity_log(uid: str, aid: int, request: Request,
                          payload: dict = Body(...)):
        import re as _re
        db = request.app.state.db
        _user_profile(db, uid)
        date = str(payload.get("local_date") or "")
        if not _re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            raise HTTPException(status_code=422,
                                detail={"error": "local_date 需为 YYYY-MM-DD"})
        log_id = db.log_care_activity(uid, aid, date,
                                      bool(payload.get("completed")),
                                      str(payload.get("feedback") or "")[:300] or None)
        if log_id is None:
            raise HTTPException(status_code=422,
                                detail={"error": "该活动当天已有记录"})
        return {"log_id": log_id}

    # ---- AI 教练对话 ----

    @api.post("/users/{uid}/chat")
    def chat(uid: str, request: Request, message: str = Body(..., embed=True)):
        if not str(message).strip():
            raise HTTPException(status_code=400, detail={"error": "消息不能为空"})
        return {"user_id": uid, "reply": _agent(request, uid).chat(message)}

    app.include_router(api)
