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

from ..analytics.activity_class import (
    CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH,
)
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
    nonstrength_reports: list[dict] = []
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
        base = f"{ex_id}-{facts['window']['start'].replace('-', '')}-" \
               f"{facts['window']['end'].replace('-', '')}"
        classes = set(cur.get("activity_classes") or [])
        nonstrength_class = (CLASS_INTERVAL if CLASS_INTERVAL in classes
                             else CLASS_STEADY_CARDIO
                             if CLASS_STEADY_CARDIO in classes else None)
        if nonstrength_class:
            series = [{"date": s["date"],
                       "activity_class": s.get("activity_class"),
                       "interval_work_seconds": s.get("interval_work_seconds"),
                       "interval_rest_seconds": s.get("interval_rest_seconds"),
                       "interval_elapsed_seconds": s.get("interval_elapsed_seconds"),
                       "steady_cardio_seconds": s.get("steady_cardio_seconds"),
                       "steady_cardio_distance_m": s.get("steady_cardio_distance_m"),
                       "longest_set_s": s.get("longest_set_s"),
                       "farthest_set_m": s.get("farthest_set_m")}
                      for s in list(reversed(prior)) + [cur]]
            trend = analyze_progress(series, measurement_type=mtype,
                                     activity_class=nonstrength_class)
            src = [_src(checkin["id"], checkin.get("revision") or 0)]
            fact_ids: list[str] = []
            if nonstrength_class == CLASS_INTERVAL:
                text = (f"{name}：HIIT 实际完成 {cur.get('interval_completed_rounds', 0)}"
                        f"/{cur.get('interval_planned_rounds', 0)} 轮，"
                        f"跳过 {cur.get('interval_skipped_rounds', 0)} 轮，"
                        f"工作 {cur.get('interval_work_seconds', 0)} 秒、"
                        f"休息 {cur.get('interval_rest_seconds', 0)} 秒"
                        f"（总经过 {cur.get('interval_elapsed_seconds', 0)} 秒）。"
                        "不折算力量容量或 e1RM。")
                fact_ids = [f"interval-work-seconds-{base}",
                            f"interval-rest-seconds-{base}",
                            f"interval-rounds-{base}"]
            else:
                secs = cur.get("steady_cardio_seconds") or 0
                dist = cur.get("steady_cardio_distance_m") or 0
                text = (f"{name}：持续性有氧 {secs} 秒"
                        + (f"、{dist} 米" if dist else "（未记录距离，不生成配速）")
                        + "。不折算力量工作组或容量。")
                fact_ids = [f"steady-cardio-seconds-{base}"]
                if dist:
                    fact_ids.append(f"steady-cardio-distance-{base}")
            findings.append({
                "finding_id": f"f-{ex_id}-nonstrength",
                "kind": "session-baseline",
                "text": text, "fact_ids": fact_ids, "source_ids": src,
            })
            findings.append({
                "finding_id": f"f-{ex_id}-nonstrength-trend",
                "kind": "trend",
                "text": (f"{name}：{_verdict_label(trend['verdict'])}。"
                         + trend.get("note", "")),
                "fact_ids": fact_ids, "source_ids": src,
            })
            nonstrength_reports.append({
                "exercise_id": ex_id, "name": name,
                "activity_class": nonstrength_class, "trend": trend,
            })
            if CLASS_STRENGTH not in classes:
                continue
        # 力量口径（同一动作若同时含力量组，仍按 strength 单独分析）
        trend = analyze_progress(
            [{"date": s["date"], "activity_class": s.get("activity_class"),
              "best_e1rm": s["best_e1rm"], "best_set": s["best_set"],
              "longest_set_s": s.get("longest_set_s"),
              "farthest_set_m": s.get("farthest_set_m")}
             for s in list(reversed(prior)) + [cur]],
            measurement_type=mtype, activity_class=CLASS_STRENGTH)
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

    if not reports and not nonstrength_reports:
        raise ValueError("本次训练记录未命中任何可分析会话")

    # ---- 方案（确定性规则，永远含「维持现状」） ----
    plan_hint = _plan_hint_for(db, user_id, reports)
    nonstrength_basis = [fid for f in findings
                         if f["finding_id"].endswith("-nonstrength")
                         for fid in f["fact_ids"]]
    options = [_option(
        "keep-current", "延续当前安排，继续观察",
        "依据：" + "；".join(
            [f"{r['name']} {r['trend_text']}" for r in reports]
            + [f"{r['name']} {_verdict_label(r['trend']['verdict'])}"
               for r in nonstrength_reports])
        + "。现有记录不需要立刻改计划；继续按计划训练并记录即可。",
        basis=[fid for r in reports for fid in r["basis_fact_ids"]]
              + nonstrength_basis,
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

    if reports:
        confidence, confidence_basis = _confidence([
            {"name": r["name"], "sessions": r["sessions"],
             "corrected": sum(1 for cid, rev in source_checkins.items() if rev > 0),
             "max_gap_days": _max_gap([s["date"] for s in r["prior"] + [r["session"]]])}
            for r in reports])
    else:
        confidence = "low"
        confidence_basis = ("本次仅含持续性有氧/间歇动作，"
                            "不套用力量趋势置信度；结果只作事实回顾")

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
    for r in nonstrength_reports:
        limitations.extend(f"{r['name']}：{lim}"
                           for lim in (r["trend"].get("limitations") or []))
        limitations.append(f"{r['name']}：该活动不计入力量工作组、容量或 e1RM")
    limitations.append("方案由规则生成（依据与取舍见各项），不构成必然正确的训练处方；"
                       "修改计划需经确认协议")

    plan_record = db.get_active_plan_record(user_id)
    names = [r["name"] for r in reports + nonstrength_reports]
    title = "训练后回顾 · " + "、".join(names[:2]) + ("等" if len(names) > 2 else "")
    summary = (f"{len(names)} 个动作已分析（力量 {len(reports)}、"
               f"有氧/间歇 {len(nonstrength_reports)}）。"
               + "；".join(
                   [f"{r['name']}趋势{_verdict_label(r['trend']['verdict'])}"
                    for r in reports]
                   + [f"{r['name']}{_verdict_label(r['trend']['verdict'])}"
                      for r in nonstrength_reports])
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
                       "exercise_ids": list(dict.fromkeys(
                           [r["exercise_id"] for r in reports]
                           + [r["exercise_id"] for r in nonstrength_reports]))},
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


# ---------------------------------------------------------------------------
# P5-C2：下一次训练进阶解读（next-training-review）
#
# 边界：解释对象是 P5-C 确定性候选引擎的输出。本分析器只做解释、适用条件
# 说明、方案取舍比较与数据不足标注——不产生候选之外的可执行数值，不编造
# 历史成绩，不修改计划（提案必须经 ChangeProposal 确认协议），不把估算
# e1RM 表述为实测。所有数值都来自确定性上下文（同源口径，构造保证）。
# ---------------------------------------------------------------------------

NEXT_TRAINING_EXPIRE_DAYS = 3   # 候选与"下一次"绑定，有效期短于训练后回顾

_ATTAINMENT_TEXT = {
    "at_top": "最近一次已达到目标次数上沿",
    "met_min": "最近一次达到目标次数下沿（尚未全部到上沿）",
    "below_target": "最近一次低于目标次数",
    "above_range": "最近一次超出目标次数范围",
    "insufficient_data": "目标达成情况数据不足",
}


def _fact_id_for(context: dict, metric: str) -> str | None:
    return next((f["fact_id"] for f in context.get("fact_refs") or []
                 if f.get("metric") == metric), None)


def _fact_ids_for(context: dict, metrics: list[str]) -> list[str]:
    out = [fid for fid in (_fact_id_for(context, m) for m in metrics) if fid]
    return list(dict.fromkeys(out))


def _recent_performance_text(context: dict) -> str:
    perf = context.get("last_actual_performance") or {}
    name = (context.get("planned_exercise") or {}).get("name") \
        or context.get("exercise_id")
    date = perf.get("date") or "未知日期"
    classes = perf.get("activity_classes") or []
    if perf.get("interval_planned_rounds"):
        return (f"{name}：最近一次（{date}）HIIT 完成 "
                f"{perf.get('interval_completed_rounds', 0)}"
                f"/{perf.get('interval_planned_rounds', 0)} 轮"
                f"（跳过 {perf.get('interval_skipped_rounds', 0)} 轮），"
                f"工作 {perf.get('interval_work_seconds', 0)} 秒、"
                f"休息 {perf.get('interval_rest_seconds', 0)} 秒。")
    if perf.get("steady_cardio_seconds"):
        dist = perf.get("steady_cardio_distance_m")
        pace = perf.get("pace_sec_per_km")
        return (f"{name}：最近一次（{date}）持续有氧 "
                f"{perf['steady_cardio_seconds']} 秒"
                + (f"、{dist} 米" if dist else "（未记录距离）")
                + (f"，配速约 {pace} 秒/公里" if pace and dist else "")
                + "。")
    reps = perf.get("rep_values") or []
    best = perf.get("best_set") or {}
    text = f"{name}：最近一次（{date}）{perf.get('working_sets', 0)} 组"
    if reps:
        text += f"，各组次数 {reps}"
    if best.get("weight_kg") is not None:
        text += f"，最佳组 {best['weight_kg']:g}kg×{best.get('reps')} 次"
    if 'mixed' in classes:
        text += "（记录混有多个活动类别，口径受限）"
    return text + "。"


def _option_detail(option: dict) -> str:
    parts = []
    if option.get("proposed_targets"):
        parts.append("候选目标：" + "、".join(
            f"{k}={v}" for k, v in option["proposed_targets"].items())
            + "（候选值，不是已完成记录）")
    t = option.get("tradeoffs") or {}
    if t.get("benefits"):
        parts.append(f"收益：{t['benefits']}")
    if t.get("costs"):
        parts.append(f"代价：{t['costs']}")
    if t.get("conditions"):
        parts.append(f"适用条件：{t['conditions']}")
    if option.get("limitations"):
        parts.append("限制：" + "；".join(option["limitations"]))
    return "。".join(parts) + "。"


def _next_confidence(context: dict, result: dict) -> tuple[str, str]:
    """按数据充分性给置信度（确定性规则，不取模型主观值）。"""
    dq = context.get("data_quality") or {}
    n = dq.get("comparable_session_count", 0)
    if not result.get("recommendations_allowed"):
        return "low", ("候选生成被安全/器械/口径条件阻断，"
                       "本次只提供事实与限制说明")
    if n >= 3 and dq.get("latest_session_comparable") \
            and not dq.get("plan_context_stale"):
        return "high", f"可比记录 {n} 次，最近一次结构可比，计划上下文为当前版本"
    if n >= 2:
        return "medium", f"可比记录 {n} 次（不足 high 档要求的 3 次）"
    return "low", f"可比记录仅 {n} 次：只支持维持与观察，不支持进阶结论"


def analyze_next_training(db, user_id: str, input_refs: dict) -> dict:
    """UserRequested → 下一次训练进阶解读（确定性打包，无 LLM）。

    input_refs: {"exercise_id": str, 以及可选计划上下文
                 plan_id / plan_version / planned_day / index /
                 planned_exercise_id}
    返回 ExpertInsight 载荷（id/user_id/task_id 由 insight_service 补齐）。
    """
    from ..training_progression import progression_service

    exercise_id = str(input_refs.get("exercise_id") or "")
    if not exercise_id:
        raise ValueError("input_refs.exercise_id 必填")
    plan_context = {k: input_refs[k] for k in (
        "plan_id", "plan_version", "planned_day", "index",
        "planned_exercise_id") if input_refs.get(k) is not None}
    result = progression_service.get_next_training_options(
        db, user_id, exercise_id, plan_context or None)
    context = result["context"]
    dq = context.get("data_quality") or {}

    # ---- 事实快照：与确定性引擎同源的 fact_refs + 恢复事实 ----
    recovery = context.get("recovery_context") or {}
    snapshot_facts = list(context.get("fact_refs") or []) + list(
        recovery.get("facts") or [])

    findings: list[dict] = []
    src_all = [f"checkin:{cid}:revision:{rev}"
               for cid, rev in (context.get("source_revisions") or {})
               .get("checkins", {}).items()]

    # ---- 发现 1：最近表现（仅真实记录） ----
    perf_metrics = {
        "strength": ["working-sets", "volume", "sessions"],
        "interval": ["interval-work-seconds", "interval-rounds"],
        "steady_cardio": ["steady-cardio-seconds", "steady-cardio-distance"],
    }.get(context.get("activity_class"), ["working-sets", "sessions"])
    findings.append({
        "finding_id": "f-next-recent",
        "kind": "session-baseline",
        "text": _recent_performance_text(context),
        "fact_ids": _fact_ids_for(context, perf_metrics),
        "source_ids": src_all[:6],
    })

    # ---- 发现 2：目标达成情况（结构可比记录的分类结果） ----
    comparability = context.get("comparability") or {}
    attainment = comparability.get("target_attainment") or {}
    if attainment:
        latest_id = next(iter(attainment))
        att = attainment[latest_id]
        text = f"目标达成：{_ATTAINMENT_TEXT.get(att.get('level'), att.get('level'))}"
        if att.get("reps"):
            text += f"（各组 {att['reps']}，目标 {att.get('target_min')}" \
                    f"-{att.get('target_max')} 次）"
        if att.get("note"):
            text += f"；{att['note']}"
        findings.append({
            "finding_id": "f-next-attainment",
            "kind": "comparison",
            "text": text,
            "fact_ids": _fact_ids_for(context, perf_metrics[:1]),
            "source_ids": src_all[:1],
        })

    # ---- 发现 3：逐候选解释（文本全部来自候选自身字段） ----
    for option in result.get("options") or []:
        findings.append({
            "finding_id": f"f-next-option-{option['option_id']}",
            "kind": "candidate-explanation",
            "text": f"候选「{option['title']}」：{_option_detail(option)}",
            "fact_ids": [fid for fid in option.get("basis_fact_ids") or []],
            "source_ids": option.get("source_ids") or [],
        })

    # ---- 发现 4：数据不足 / 限制 ----
    gaps = []
    if dq.get("comparable_session_count", 0) < 2:
        gaps.append(f"可比记录仅 {dq.get('comparable_session_count', 0)} 次："
                    "只能维持并继续观察，不构成增长或加重依据")
    if dq.get("recovery_missing"):
        gaps.append("近期没有恢复记录：恢复状态未知，不代表恢复良好")
    if dq.get("plan_context_stale"):
        gaps.append("计划上下文不是当前版本：候选未引用旧计划目标")
    if dq.get("latest_session_comparable") is False:
        gaps.append("最近一次训练结构口径不同：未纳入同口径比较")
    if result.get("blocked_reasons"):
        gaps.append("；".join(result["blocked_reasons"]))
    if gaps:
        findings.append({
            "finding_id": "f-next-gaps",
            "kind": "data-gap",
            "text": "数据与限制：" + "；".join(gaps) + "。",
            "fact_ids": [],
            "source_ids": [],
        })

    # ---- 恢复事实（有记录才呈现；独立信息，不做过度训练推断） ----
    if recovery.get("signals"):
        lines = [f"{s['metric']}={s['value']}（{s['note']}）"
                 for s in recovery["signals"]]
        findings.append({
            "finding_id": "f-next-recovery",
            "kind": "recovery-context",
            "text": "近期恢复自报：" + "；".join(lines)
                    + "。以上是主观记录事实，与训练表现不是确定因果关系；"
                      "候选中的恢复观察方向由确定性规则给出。",
            "fact_ids": [f["fact_id"] for f in recovery.get("facts") or []][:4],
            "source_ids": [],
        })

    # ---- 方案：镜像确定性候选（不含候选之外的可执行数值） ----
    options = []
    for option in result.get("options") or []:
        entry = {
            "option_id": option["option_id"],
            "title": option["title"],
            "detail": _option_detail(option),
            "basis": option.get("basis_fact_ids") or [],
            "tradeoffs": {
                "收益": (option.get("tradeoffs") or {}).get("benefits", ""),
                "代价": (option.get("tradeoffs") or {}).get("costs", ""),
                "适用条件": (option.get("tradeoffs") or {}).get("conditions", ""),
            },
            "proposed_targets": option.get("proposed_targets") or {},
            "limitations": option.get("limitations") or [],
            "action": "advisory",
        }
        proposal = option.get("plan_proposal")
        if proposal:
            entry["action"] = "proposal"
            entry["proposal_hint"] = {
                "target": "plan",
                "operations": proposal["operations"],
            }
        options.append(entry)

    confidence, confidence_basis = _next_confidence(context, result)
    name = (context.get("planned_exercise") or {}).get("name") or exercise_id
    plan_version = context.get("plan_version")
    summary = (
        f"{name}：基于 {dq.get('comparable_session_count', 0)} 次结构可比记录"
        + (f"与当前计划 v{plan_version}" if plan_version else "（无生效计划上下文）")
        + f"，确定性引擎给出 {len(options)} 个候选方向"
        + ("；" + "、".join(o["title"] for o in options) if options
           else "（当前条件不允许生成候选，原因见限制）")
        + "。候选不是处方，是否采用由你决定。")
    limitations = list(result.get("blocked_reasons") or [])
    limitations.append("候选与解释由确定性规则生成（依据与取舍见各项）；"
                       "修改长期计划必须经确认协议，确认时会重新校验")
    if any(f.get("best_e1rm") for f in [context.get("last_actual_performance")]):
        limitations.append("e1RM 为 Epley 公式估算值（1-12 次区间），非实测极限")

    checkins_rev = (context.get("source_revisions") or {}).get("checkins") or {}
    recovery_records = (context.get("source_revisions") or {}).get("recovery") or {}
    source_revision: dict = {
        "checkins": {str(k): v for k, v in checkins_rev.items()},
        # 与既有洞察约定一致：限制版本存于 "restrictions" 键（懒失效共用）
        "restrictions": (context.get("source_revisions") or {})
        .get("restrictions_version"),
        "equipment": (context.get("source_revisions") or {}).get("equipment"),
        "rules_version": progression_service.PROGRESSION_RULES_VERSION,
        "recovery_records": {str(k): v for k, v in recovery_records.items()},
        # 新增恢复记录也要使旧洞察失效（不只盯已引用的记录）
        "recovery_records_count": len(recovery_records),
    }
    if plan_version is not None:
        source_revision["plan_version"] = plan_version

    return {
        "specialist": "training_science",
        "insight_type": "next-training-review",
        "title": f"下一次训练建议 · {name}",
        "summary": summary,
        "findings": findings,
        "evidence_refs": sorted({fid for f in findings for fid in f["fact_ids"]}),
        "facts_snapshot": {
            "facts": snapshot_facts,
            "caliber": "与确定性候选引擎同源（P5-C 上下文 fact_refs + 恢复事实）",
        },
        "knowledge_refs": _knowledge_refs(db, user_id, [name]),
        "options": options,
        "limitations": limitations,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "generated_at": _now(),
        "expires_at": (datetime.now()
                       + timedelta(days=NEXT_TRAINING_EXPIRE_DAYS)
                       ).isoformat(timespec="seconds"),
        "source_revision": source_revision,
        "input_refs": {"exercise_id": exercise_id, **plan_context},
    }
