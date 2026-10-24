"""/api 路由（2.0 B4）：薄层，全部委托 coach/ 域函数。

错误约定：
- 404：用户/资源不存在；
- 422：确定性校验未通过（ProposalRejected 等，details 带原因列表）；
- 400：请求形状不对。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from coach.agent import CoachAgent
from coach.approach import approach_view, initialize_approach, restore_revision
from coach.changes import (ProposalRejected, confirm_proposal, stage_ai,
                           submit_manual)
from coach.exercises import library
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

    @api.get("/media/{uid}/{name}")
    def media_file(uid: str, name: str, request: Request):
        """封面/片段文件（只读）。<img>/<video> 无法带自定义头，
        令牌同时接受 ?access_token= 查询参数（仅限本只读路径）。"""
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
        stamp = int(_time.time() * 1000)
        video_path = media_dir / f"v{stamp}_{Path(video.filename).name}"
        video_path.write_bytes(await video.read())
        subtitle_path = None
        if isinstance(subtitle, UploadFile) and subtitle.filename:
            if not subtitle.filename.lower().endswith((".srt", ".vtt")):
                raise HTTPException(status_code=422, detail={"error": "字幕仅支持 srt/vtt"})
            subtitle_path = media_dir / f"s{stamp}_{Path(subtitle.filename).name}"
            subtitle_path.write_bytes(await subtitle.read())
        asset_id = db.add_media_asset(uid, title, str(video_path),
                                      str(subtitle_path) if subtitle_path else None)
        # §10.4：媒体处理不阻塞请求——后台线程执行转写与候选提取
        import threading
        from coach.media_import import process_asset
        threading.Thread(
            target=process_asset, daemon=True,
            args=(db, asset_id, str(video_path),
                  str(subtitle_path) if subtitle_path else None)).start()
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
        video_path = media_dir / f"ma{int(_time.time() * 1000)}_{Path(video.filename).name}"
        video_path.write_bytes(await video.read())

        def _work() -> None:
            try:
                result = process_analysis(exercise_id, str(video_path), view)
                db.finish_motion_analysis(analysis_id, "ready", result=result)
            except Exception as e:  # noqa: BLE001 失败要留痕不吞
                db.finish_motion_analysis(analysis_id, "failed", error=str(e))

        analysis_id = db.add_motion_analysis(uid, exercise_id, view, str(video_path))
        threading.Thread(target=_work, daemon=True).start()
        return {"analysis_id": analysis_id, "status": "processing"}

    @api.get("/users/{uid}/motion-analyses")
    def motion_list(uid: str, request: Request, exercise_id: str | None = Query(None)):
        db = request.app.state.db
        _user_profile(db, uid)
        return {"analyses": db.list_motion_analyses(uid, exercise_id)}

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
        try:
            return submit_manual(db, uid, "plan", payload.get("operations"),
                                 str(payload.get("reason") or "手动编辑计划"), base)
        except ProposalRejected as e:
            raise _reject(e) from None

    # ---- 打卡 ----

    @api.get("/users/{uid}/checkins")
    def list_checkins(uid: str, request: Request, limit: int = Query(10, ge=1, le=20)):
        _user_profile(request.app.state.db, uid)
        return {"checkins": request.app.state.db.list_checkins(uid, limit)}

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
                        best = max(main, key=lambda s: (
                            (s.get("weight_kg") or 0) * (s.get("reps") or 0),
                            s.get("weight_kg") or 0))
                        ex["sets"] = len(main)
                        ex["weight_kg"] = best.get("weight_kg")
                        ex["reps"] = best.get("reps")
                        ex["rpe"] = best.get("rpe")
                    else:
                        ex.pop("weight_kg", None)
                        ex.pop("reps", None)
                        ex.pop("sets", None)
                        ex.pop("rpe", None)
                ex["exercise_id"] = None            # 动作 ID 是系统判定
                raw_name = ex.get("name", "")
                ex_id, official, _via = library.normalize(raw_name)
                if ex_id:
                    ex["exercise_id"] = ex_id
                    if official != raw_name:
                        ex["name_raw"] = raw_name
                    ex["name"] = official
                else:
                    _log_unmatched(request, uid, raw_name)
                    notes.append(f"未识别动作「{raw_name}」：已按原名记录并进入待补队列")
        checkin_id = db.record_checkin(uid, ctype, data)
        if submission_id and not db.record_checkin_submission(uid, submission_id, checkin_id):
            # 并发同 ID（极小窗口）：删除刚落的重复行，以先落库者为准
            first = db.get_checkin_submission(uid, submission_id)
            db.conn.execute("DELETE FROM checkins WHERE user_id=? AND id=?",
                            (uid, checkin_id))
            db.conn.commit()
            return {"id": first["checkin_id"], "type": ctype,
                    "warnings": notes, "existing": True}
        return {"id": checkin_id, "type": ctype, "warnings": notes}

    @api.post("/users/{uid}/checkins/{checkin_id}/correct")
    def correct_checkin(uid: str, checkin_id: int, request: Request,
                        payload: dict = Body(...)):
        try:
            updated = request.app.state.db.revise_checkin(
                uid, checkin_id, int(payload.get("expected_revision", 0)),
                payload.get("data", {}), str(payload.get("reason") or ""),
                str(payload.get("evidence") or ""))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=422, detail={"error": str(e)}) from None
        return updated

    # ---- 动作库 ----

    @api.get("/exercises")
    def exercises(q: str = "", muscle: str = "", equipment: str = "",
                  status: str = ""):
        items = library.all()
        if status:
            items = [e for e in items if e.get("status") == status]
        if muscle:
            items = [e for e in items if muscle in set(e.get("primary") or [])
                     | set(e.get("secondary") or [])]
        if equipment:
            items = [e for e in items
                     if equipment in (e.get("equipment") or [])]
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
        return {"count": len(items),
                "exercises": [{"id": e["id"], "name": e["name"],
                               "aliases": e.get("aliases") or [],
                               "pattern": e.get("pattern"),
                               "primary": e.get("primary") or [],
                               "equipment": e.get("equipment") or [],
                               "location": e.get("location") or [],
                               "status": e.get("status")} for e in items]}

    @api.get("/exercises/{ex_id}")
    def exercise_detail(ex_id: str):
        ex = library.get(ex_id)
        if not ex:
            raise HTTPException(status_code=404, detail={"error": f"动作 {ex_id} 不存在"})
        detail = dict(ex)
        if detail.get("status") != "approved":
            detail.setdefault("notes", [])
            detail["notes"] = list(detail["notes"]) + [
                "该动作的结构化属性（关节压力/替代关系）尚未经审核"]
        return detail

    # ---- AI 教练对话 ----

    @api.post("/users/{uid}/chat")
    def chat(uid: str, request: Request, message: str = Body(..., embed=True)):
        if not str(message).strip():
            raise HTTPException(status_code=400, detail={"error": "消息不能为空"})
        return {"user_id": uid, "reply": _agent(request, uid).chat(message)}

    app.include_router(api)
