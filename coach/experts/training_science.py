"""训练科学顾问的确定性分析器（P0 第一个真实工作台的分析内核）。

纪律（2.0 §二、§十一）：
1. 全部数值来自 fact_service / exercise_metrics / progress_analysis
   同一套口径——与「我的表现」「周期统计」「AI 训练事实」三个既有接口
   数值一致由构造保证，本模块绝不另写公式；
2. 置信度按数据充分性规则生成（见 _confidence），不取模型主观值；
3. 每条发现都带 fact_ids（对应 facts_snapshot）与 source_ids
   （checkin:ID:revision:N 追溯链），evidence_validator 负责复核；
4. 方案永远包含「延续当前安排/继续观察」；调整方向只给依据与取舍，
   计划修改必须走统一修改协议（recommendation_service.stage_option_proposal）；
5. 数据不足的维度如实标注，不用单次表现外推趋势。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..analytics.exercise_metrics import entry_identity, exercise_sessions
from ..analytics.fact_service import get_training_facts
from ..analytics.progress_analysis import analyze_progress

WINDOW_DAYS = 60          # 分析窗口：与趋势分析一致
EXERCISE_CAP = 3          # 单次回顾覆盖的动作数上限（按正式组数取前几个）
EXPIRE_DAYS = 14          # 洞察默认有效期
# 置信度规则阈值（写入 confidence_basis，用户可见）
CONF_HIGH_SESSIONS = 4
CONF_MAX_GAP_DAYS = 10
# 加重方向参考幅度（kg）——只作示例档位，不构成必然正确的处方
LOAD_STEP_KG = 2.5


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _src(checkin_id: int, revision: int) -> str:
    return f"checkin:{checkin_id}:revision:{revision or 0}"


def _session_for(sessions: list[dict], checkin_id: int) -> dict | None:
    return next((s for s in sessions if s["checkin_id"] == checkin_id), None)


def _avg_rpe(session: dict) -> float | None:
    rpes = [st.get("rpe") for st in session.get("sets") or []
            if isinstance(st.get("rpe"), (int, float))]
    return round(sum(rpes) / len(rpes), 1) if rpes else None


def _confidence(reports: list[dict]) -> tuple[str, str]:
    """按数据充分性规则生成置信度（2.0 §2.2：不采用模型主观置信度）。

    规则（全部写入 basis，可复核）：
    - 每个动作按窗口内会话数、纠错数、最大记录间隔独立评级：
      ≥4 次且无纠错且间隔 ≤10 天 → high；2-3 次（或 high 条件中有扣分项）→ medium；
      仅 1 次 → low；
    - 整体取各动作中最低档（保守），basis 列出每个动作的计数明细。
    """
    order = {"low": 0, "medium": 1, "high": 2}
    parts, worst = [], "high"
    for r in reports:
        n, corrected, gap = r["sessions"], r["corrected"], r["max_gap_days"]
        if n >= CONF_HIGH_SESSIONS and corrected == 0 \
                and (gap is not None and gap <= CONF_MAX_GAP_DAYS):
            level = "high"
        elif n >= 2:
            level = "medium"
        else:
            level = "low"
        if order[level] < order[worst]:
            worst = level
        why = []
        if corrected:
            why.append(f"含纠错 {corrected} 条")
        if gap is not None and gap > CONF_MAX_GAP_DAYS:
            why.append(f"记录间隔最长 {gap} 天")
        parts.append(f"{r['name']}：窗口内 {n} 次{('（' + '，'.join(why) + '）') if why else ''}"
                     f" → {level}")
    basis = ("置信度规则=窗口会话数/纠错/记录间隔（整体取最低档）："
             + "；".join(parts))
    return worst, basis


def _verdict_label(verdict: str) -> str:
    return {"improving": "上行", "stable": "平稳", "declining": "下行",
            "insufficient": "数据不足"}.get(verdict, verdict)


def _option(option_id: str, title: str, detail: str, basis: list[str],
            benefits: str, costs: str, conditions: str,
            proposal_hint: dict | None = None) -> dict:
    opt = {"option_id": option_id, "title": title, "detail": detail,
           "basis": basis, "tradeoffs": {"收益": benefits, "代价": costs,
                                         "适用条件": conditions},
           "action": "proposal" if proposal_hint else "advisory"}
    if proposal_hint:
        opt["proposal_hint"] = proposal_hint
    return opt


def _load_option(report: dict, plan_hint: dict | None) -> dict:
    """加重方向（weight_reps）：给依据与取舍；计划内在册时附提案提示。"""
    s, prior = report["session"], report["prior"]
    best_w = (s.get("best_set") or {}).get("weight_kg")
    step = LOAD_STEP_KG if (best_w or 0) >= 40 else 1.25
    next_w = round((best_w or 0) + step, 2)
    rpe_note = "" if report["avg_rpe"] is not None else "（本次未记 RPE，按完成组数判断）"
    hint = None
    if plan_hint:
        hint = {"target": "plan",
                "operations": [{"op": "edit_set_prescription",
                                "day": plan_hint["day"],
                                "exercise": plan_hint["name"],
                                "weight_kg": next_w,
                                "note": "依据训练科学工作台回顾，小幅加重"}]}
    return _option(
        "try-heavier", f"下次可尝试小幅加重（如 {next_w:g}kg 档位）",
        f"依据：本次最佳组 {report['best_text']}，{report['trend_text']}。"
        f"可在保持次数目标不变的前提下上调负重{rpe_note}。这只是参考方向，"
        "是否加重由你结合当天状态决定。",
        basis=report["basis_fact_ids"],
        benefits="延续渐进超负荷刺激；幅度小、便于归因",
        costs="完成难度上升；技术负荷增加",
        conditions="下次训练热身与正式组质量正常时再做；连续失败则回落",
        proposal_hint=hint)


def _recover_option(report: dict) -> dict:
    return _option(
        "check-recovery", "下调本次对比压力，先检查恢复",
        f"依据：{report['trend_text']}。连续低于近期水平通常先查睡眠、疲劳与"
        "动作质量，而不是立即归因训练方案。",
        basis=report["basis_fact_ids"],
        benefits="避免带着明显疲劳硬顶强度",
        costs="短期训练量下降",
        conditions="与恢复记录（P2 上线后）交叉确认更稳")


def analyze_post_workout(db, user_id: str, input_refs: dict) -> dict:
    """WorkoutSaved → 训练后回顾（确定性，无 LLM）。

    input_refs: {"checkin_id": int}
    返回 ExpertInsight 载荷（不含 id/user_id/task_id，由 insight_service 补齐）。
    """
    checkin_id = input_refs.get("checkin_id")
    checkin = db.get_checkin(user_id, int(checkin_id)) if checkin_id else None
    if not checkin or checkin["type"] != "training":
        raise ValueError("分析对象训练记录不存在")

    # ---- 会话内动作（稳定 ID 优先；未识别动作如实降级） ----
    exercise_ids: list[str] = []
    unmatched: list[str] = []
    for ex in checkin["data"].get("exercises") or []:
        if not isinstance(ex, dict):
            continue
        ex_id = entry_identity(db, user_id, ex)
        if ex_id:
            if ex_id not in exercise_ids:
                exercise_ids.append(ex_id)
        elif ex.get("name"):
            unmatched.append(str(ex["name"]))
    if not exercise_ids:
        raise ValueError("本次训练没有可分析的动作（全部未识别）")

    facts = get_training_facts(db, user_id, WINDOW_DAYS,
                               exercise_ids=exercise_ids)
    findings: list[dict] = []
    reports: list[dict] = []
    source_checkins: dict[int, int] = {}
    option_templates: list[dict] = []

    for ex_id in exercise_ids[:EXERCISE_CAP]:
        doc = db_conn_exercise(db, user_id, ex_id) or {}
        name = doc.get("name") or ex_id
        mtype = doc.get("measurement") or "weight_reps"
        sessions = exercise_sessions(db, user_id, ex_id)
        cur = _session_for(sessions, checkin["id"])
        if not cur:
            continue
        for s in sessions:
            source_checkins[s["checkin_id"]] = s.get("revision") or 0
        prior = [s for s in sessions if s is not cur
                 and s["date"] <= cur["date"]]
        # 趋势（含本次）：progress_analysis 自己判断样本是否足够
        # prior 来自 sessions（新→旧），需转成旧→新再补本次
        trend = analyze_progress(
            [{"date": s["date"], "best_e1rm": s["best_e1rm"],
              "best_set": s["best_set"], "longest_set_s": s.get("longest_set_s"),
              "farthest_set_m": s.get("farthest_set_m")}
             for s in list(reversed(prior)) + [cur]],
            measurement_type=mtype)
        base = f"{ex_id}-{facts['window']['start'].replace('-', '')}-" \
               f"{facts['window']['end'].replace('-', '')}"
        report = {"exercise_id": ex_id, "name": name, "mtype": mtype,
                  "session": cur, "prior": prior, "trend": trend,
                  "sessions": len(sessions), "avg_rpe": _avg_rpe(cur),
                  "basis_fact_ids": [
                      f"best-estimated-1rm-{base}" if mtype == "weight_reps"
                      else f"max-reps-{base}"]}
        report["best_text"] = _best_set_text(cur, mtype)
        ev = trend.get("evidence") or {}
        med = ""
        if "first_half_median" in ev:
            med = (f"（前半窗中位数 {ev['first_half_median']}"
                   f" → 后半窗 {ev['second_half_median']}，"
                   f"样本 {ev.get('sessions_total', len(sessions))} 次）")
        report["trend_text"] = (f"近 {WINDOW_DAYS} 天该动作趋势"
                                f"{_verdict_label(trend['verdict'])}{med}"
                                if trend["verdict"] != "insufficient"
                                else f"趋势数据不足（{'; '.join(trend['limitations'])}）")
        reports.append(report)

        # ---- 发现 1：本次基本盘 ----
        findings.append({
            "finding_id": f"f-{ex_id}-session",
            "kind": "session-baseline",
            "text": (f"{name}：本次 {cur['working_sets']} 组正式组、"
                     f"总容量 {cur['volume']:g}kg、最佳组 {report['best_text']}"
                     + (f"、平均 RPE {report['avg_rpe']:g}（主观自报）"
                        if report["avg_rpe"] is not None else "")),
            "fact_ids": [f"working-sets-{base}", f"volume-{base}"],
            "source_ids": [_src(checkin["id"], checkin.get("revision") or 0)],
        })
        # ---- 发现 2：与窗口内此前水平比较 ----
        findings.extend(_comparison_findings(ex_id, name, base, cur, prior, mtype,
                                             checkin))
        # ---- 发现 3：趋势（含依据与限制） ----
        findings.append({
            "finding_id": f"f-{ex_id}-trend",
            "kind": "trend",
            "text": f"{name}：{report['trend_text']}。{trend.get('note', '')}",
            "fact_ids": report["basis_fact_ids"],
            "source_ids": [_src(cid, rev) for cid, rev in source_checkins.items()],
        })

    if not reports:
        raise ValueError("本次训练记录未命中任何可分析会话")

    # ---- 方案（确定性规则，永远含「维持现状」） ----
    plan_hint = _plan_hint_for(db, user_id, reports)
    options = [_option(
        "keep-current", "延续当前安排，继续观察",
        "依据：" + "；".join(f"{r['name']} {r['trend_text']}" for r in reports)
        + "。现有记录不需要立刻改计划；继续按计划训练并记录即可。",
        basis=[fid for r in reports for fid in r["basis_fact_ids"]],
        benefits="不引入新变量，归因清晰", costs="进步速度可能不变",
        conditions="无未解除的伤病限制；状态正常")]
    for report in reports:
        verdict = report["trend"]["verdict"]
        if report["mtype"] == "weight_reps" and (
                verdict == "improving"
                or (verdict in ("stable", "insufficient")
                    and _beat_prior_best(report))):
            options.append(_load_option(report, plan_hint.get(report["exercise_id"])))
        elif verdict == "declining":
            options.append(_recover_option(report))
    # 去重（多动作可能产生同 ID 的模板方案，只保留首个）
    seen, uniq = set(), []
    for opt in options:
        if opt["option_id"] in seen and opt["option_id"] != "keep-current":
            continue
        seen.add(opt["option_id"])
        uniq.append(opt)
    options = uniq[:4]

    confidence, confidence_basis = _confidence([
        {"name": r["name"], "sessions": r["sessions"],
         "corrected": sum(1 for cid, rev in source_checkins.items() if rev > 0),
         "max_gap_days": _max_gap([s["date"] for s in r["prior"] + [r["session"]]])}
        for r in reports])

    limitations = []
    if unmatched:
        limitations.append(f"未识别动作未纳入分析：{'、'.join(unmatched)}")
    if len(exercise_ids) > EXERCISE_CAP:
        limitations.append(f"本次共 {len(exercise_ids)} 个动作，回顾覆盖正式组最多的"
                           f"前 {EXERCISE_CAP} 个")
    for r in reports:
        limitations.extend(f"{r['name']}：{lim}"
                           for lim in (r["trend"].get("limitations") or []))
        if r["mtype"] == "weight_reps":
            limitations.append(f"{r['name']}：e1RM 为 Epley 公式估算值（1-12 次区间），非实测极限")
    limitations.append("方案由规则生成（依据与取舍见各项），不构成必然正确的训练处方；"
                       "修改计划需经确认协议")

    plan_record = db.get_active_plan_record(user_id)
    names = [r["name"] for r in reports]
    title = "训练后回顾 · " + "、".join(names[:2]) + ("等" if len(names) > 2 else "")
    summary = (f"{len(reports)} 个动作已分析。"
               + "；".join(f"{r['name']}趋势{_verdict_label(r['trend']['verdict'])}"
                           for r in reports)
               + f"。共 {len(options)} 个可选方向（含维持现状），均由你决定。")

    return {
        "specialist": "training_science",
        "insight_type": "post-workout-review",
        "title": title,
        "summary": summary,
        "findings": findings,
        "evidence_refs": sorted({fid for f in findings for fid in f["fact_ids"]}),
        "facts_snapshot": {"window": facts["window"], "facts": facts["facts"],
                           "exercises_covered": facts["exercises_covered"],
                           "caliber": facts["caliber"]},
        "knowledge_refs": _knowledge_refs(db, user_id, names),
        "options": options,
        "limitations": limitations,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "generated_at": _now(),
        "expires_at": (datetime.now() + timedelta(days=EXPIRE_DAYS)
                       ).isoformat(timespec="seconds"),
        "source_revision": {
            "checkins": {str(cid): rev for cid, rev in source_checkins.items()},
            **({"plan_version": plan_record["version"]} if plan_record else {}),
        },
        "input_refs": {"checkin_id": checkin["id"],
                       "exercise_ids": [r["exercise_id"] for r in reports]},
    }


def db_conn_exercise(db, user_id: str, ex_id: str) -> dict | None:
    from .. import exercise_service
    return exercise_service.get_exercise(db, user_id, ex_id)


def _best_set_text(session: dict, mtype: str) -> str:
    bs = session.get("best_set") or {}
    if mtype == "bodyweight_reps":
        added = next((st.get("added_weight_kg") for st in session["sets"]
                      if st.get("added_weight_kg")), None)
        return f"{bs.get('reps')} 次/组" + (f"（额外负重 {added:g}kg）" if added else "")
    if bs:
        return f"{bs['weight_kg']:g}kg×{bs.get('reps')} 次"
    if session.get("longest_set_s"):
        return f"单组最长 {session['longest_set_s']:g} 秒"
    if session.get("farthest_set_m"):
        return f"单组最远 {session['farthest_set_m']:g} 米"
    return "—"


def _comparison_findings(ex_id: str, name: str, base: str, cur: dict,
                         prior: list[dict], mtype: str,
                         checkin: dict) -> list[dict]:
    """本次 vs 窗口内此前水平（只比同口径主指标）。"""
    out = []
    src = [_src(checkin["id"], checkin.get("revision") or 0)]
    src += [_src(s["checkin_id"], s.get("revision") or 0) for s in prior[:10]]
    if mtype == "weight_reps":
        prior_best = max((s["best_e1rm"] for s in prior if s["best_e1rm"]),
                         default=None)
        if cur.get("best_e1rm") and prior_best:
            diff = (cur["best_e1rm"] - prior_best) / prior_best
            word = ("高于" if diff > 0.01 else "低于" if diff < -0.01 else "持平于")
            out.append({
                "finding_id": f"f-{ex_id}-compare",
                "kind": "comparison",
                "text": (f"{name}：本次最佳估算 e1RM {cur['best_e1rm']:.1f}kg"
                         f"{word}此前窗口内最好 {prior_best:.1f}kg"
                         f"（{(diff * 100):+.1f}%，估算口径）"),
                "fact_ids": [f"best-estimated-1rm-{base}"],
                "source_ids": src})
        elif cur.get("best_e1rm") and not prior_best:
            out.append({
                "finding_id": f"f-{ex_id}-compare",
                "kind": "comparison",
                "text": f"{name}：本次为窗口内首次可估算 e1RM 的训练，无此前对比基线",
                "fact_ids": [f"best-estimated-1rm-{base}"],
                "source_ids": src})
    elif prior:
        key = ("farthest_set_m" if mtype == "distance_time"
               else "longest_set_s" if mtype == "duration"
               else "working_sets")
        metric = {"farthest_set_m": "单组最远距离（米）",
                  "longest_set_s": "单组最长时长（秒）",
                  "working_sets": "正式组数"}.get(key, key)
        pv = [s.get(key) for s in prior if s.get(key) is not None]
        cv = cur.get(key)
        if pv and cv is not None:
            avg = sum(pv) / len(pv)
            out.append({
                "finding_id": f"f-{ex_id}-compare",
                "kind": "comparison",
                "text": (f"{name}：本次{metric} {cv:g}，此前窗口均值 {avg:.1f}"
                         f"（{len(pv)} 次）"),
                "fact_ids": [],
                "source_ids": src})
    return out


def _beat_prior_best(report: dict) -> bool:
    cur = report["session"].get("best_e1rm")
    prior = max((s["best_e1rm"] for s in report["prior"] if s["best_e1rm"]),
                default=None)
    return bool(cur and prior and cur > prior)


def _max_gap(dates: list[str]) -> int | None:
    if len(dates) < 2:
        return None
    ds = sorted(date.fromisoformat(d) for d in dates)
    return max((b - a).days for a, b in zip(ds, ds[1:]))


def _plan_hint_for(db, user_id: str, reports: list[dict]) -> dict[str, dict]:
    """动作在当前生效计划内的册位置（day + 官方名）——用于提案提示。"""
    record = db.get_active_plan_record(user_id)
    hint: dict[str, dict] = {}
    if not record:
        return hint
    ids = {r["exercise_id"] for r in reports}
    for day in record["content"].get("schedule", []):
        for entry in day.get("exercises", []):
            if entry.get("exercise_id") in ids:
                hint.setdefault(entry["exercise_id"],
                                {"day": day["day"],
                                 "name": entry.get("name") or entry["exercise_id"]})
    return hint


def _knowledge_refs(db, user_id: str, names: list[str]) -> list[dict]:
    """共享知识检索（确定性；只收已审核来源，草稿不得作为依据）。"""
    try:
        from ..knowledge_search import search
        result = search(db, user_id, " ".join(names[:2]) + " 训练 进阶")
    except Exception:
        return []
    refs = []
    for engine, payload in (result.get("engines") or {}).items():
        for hit in (payload.get("hits") or [])[:2]:
            refs.append({"engine": engine, "ref": hit.get("ref"),
                         "title": hit.get("title"),
                         "provenance": hit.get("provenance")})
    return refs[:4]
