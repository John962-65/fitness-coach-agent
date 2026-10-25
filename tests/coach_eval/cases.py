#!/usr/bin/env python3
"""M6.5-5 评测案例集（≥30 例，覆盖任务书 14 类场景）。

每例独立数据库运行；hard=True 的案例属硬性约束（编造数值/口径混用/
绕过安全门等），评测要求零违规。
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from coach.analytics import fact_service, progress_analysis, trial_evidence
from coach.agents.orchestrator import combine, route_question
from coach.agents.specialists import SPECIALISTS, fake_advice, parse_advice
from coach.analytics.exercise_metrics import exercise_sessions
from coach.analytics.training_calendar import period_summary

from . import seed as S


def ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


BENCH = "barbell_bench_press"
SQUAT = "barbell_back_squat"
CHIN = "chin_up"            # bodyweight_reps（动作库声明）
PLANK = "plank"             # duration
DL = "deadlift"

CASES: list[dict] = []


def case(cid: str, category: str, hard: bool = False):
    def deco(fn):
        CASES.append({"id": cid, "category": category, "hard": hard,
                      "run": fn})
        return fn
    return deco


def facts_by_metric(db, uid, **kw):
    r = fact_service.get_training_facts(db, uid, **kw)
    return r, {f["metric"]: f for f in r["facts"] if not f.get("exercise_id")}, {
        (f.get("exercise_id"), f["metric"]): f for f in r["facts"]
        if f.get("exercise_id")}


def bench_logs(pairs, warmup_first=None):
    logs = []
    if warmup_first:
        logs.append(S.set_log(weight_kg=warmup_first, reps=5, warmup=True))
    logs += [S.set_log(weight_kg=w, reps=r) for w, r in pairs]
    return logs


# ============ 类别 1：没有卧推记录，不得编造成绩 ============

@case("no-bench-e1rm-insufficient", "没有卧推记录", hard=True)
def c01(db, uid):
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": SQUAT, "name": "杠铃深蹲",
         "set_logs": bench_logs([(100, 5)])}])
    r, _g, by_ex = facts_by_metric(db, uid, exercise_ids=[BENCH])
    f = by_ex.get((BENCH, "sessions"))
    ok = f and f["status"] == "insufficient" and f["value"] == 0
    return ok, f"expect insufficient sessions, got {f and f['status']}"


@case("no-bench-progress-insufficient", "没有卧推记录", hard=True)
def c02(db, uid):
    prog = fact_service.exercise_progress(db, uid, BENCH)
    v = progress_analysis.analyze_progress(prog["series"], "weight_reps")
    return v["verdict"] == "insufficient", f"verdict={v['verdict']}"


@case("no-bench-agent-reply-no-numbers", "没有卧推记录", hard=True)
def c03(db, uid):
    from coach.agent import CoachAgent
    agent = CoachAgent(uid, db_path=db.path)
    agent.profile["onboarding_done"] = True
    reply = agent.chat("我最近卧推有没有进步？")
    nums = re.findall(r"\d+(?:\.\d+)?\s*(?:kg|公斤)", reply)
    return not nums, f"回复出现无来源重量数值: {nums}"


# ============ 类别 2：有 3 次卧推记录，正确读取 ============

def seed_bench3(db, uid):
    S.seed_session(db, uid, ago(21), [
        {"exercise_id": BENCH, "name": "杠铃平板卧推",
         "set_logs": bench_logs([(60, 8)])}])
    S.seed_session(db, uid, ago(14), [
        {"exercise_id": BENCH, "name": "杠铃平板卧推",
         "set_logs": bench_logs([(62.5, 8)])}])
    S.seed_session(db, uid, ago(7), [
        {"exercise_id": BENCH, "name": "杠铃平板卧推",
         "set_logs": bench_logs([(65, 8)])}])


@case("bench3-sessions-count", "有卧推记录")
def c04(db, uid):
    seed_bench3(db, uid)
    prog = fact_service.exercise_progress(db, uid, BENCH)
    return len(prog["series"]) == 3, f"series={len(prog['series'])}"


@case("bench3-facts-match-sets", "有卧推记录", hard=True)
def c05(db, uid):
    seed_bench3(db, uid)
    r, _g, by_ex = facts_by_metric(db, uid)
    f = by_ex[(BENCH, "best-estimated-1rm")]
    # Epley: 65×8 → 65×(1+8/30)=82.3；与三接口同公式
    expect = round(65 * (1 + 8 / 30), 1)
    return f["value"] == expect and f["status"] == "estimated", \
        f"e1rm={f['value']} expect={expect}"


@case("bench3-progress-improving", "有卧推记录")
def c06(db, uid):
    seed_bench3(db, uid)
    prog = fact_service.exercise_progress(db, uid, BENCH)
    v = progress_analysis.analyze_progress(prog["series"], "weight_reps")
    return v["verdict"] == "improving", f"verdict={v['verdict']}"


@case("bench3-three-interface-consistency", "三接口一致性", hard=True)
def c07(db, uid):
    seed_bench3(db, uid)
    # 我的表现
    sess = exercise_sessions(db, uid, BENCH)
    mine = max(s["best_e1rm"] for s in sess)
    mine_vol = sum(s["volume"] for s in sess)
    # 周期统计
    ps = period_summary(db, uid, 30)
    # AI 事实
    r, g, by_ex = facts_by_metric(db, uid)
    ok = (by_ex[(BENCH, "best-estimated-1rm")]["value"] == mine
          and by_ex[(BENCH, "volume")]["value"] == mine_vol
          and g["volume"]["value"] == ps["volume"]
          and g["sessions"]["value"] == ps["sessions"])
    return ok, "三接口数值不一致"


# ============ 类别 3：e1RM 与容量最大组不同，不混用口径 ============

@case("e1rm-vs-volume-distinct", "口径不混用", hard=True)
def c08(db, uid):
    # 60×12 容量最大(720)；80×2 e1RM 最大(85.3)——两个最优来自不同组
    S.seed_session(db, uid, ago(5), [
        {"exercise_id": BENCH, "name": "杠铃平板卧推",
         "set_logs": bench_logs([(60, 12), (80, 2)])}])
    r, _g, by_ex = facts_by_metric(db, uid)
    e = by_ex[(BENCH, "best-estimated-1rm")]
    v = by_ex[(BENCH, "volume")]
    return (e["value"] == round(80 * (1 + 2 / 30), 1)
            and v["value"] == 60 * 12 + 80 * 2
            and e["calculation"] != v["calculation"]), \
        f"e1rm={e['value']} vol={v['value']}"


# ============ 类别 4：负重引体（bodyweight_reps）不套杠铃 e1RM ============

@case("weighted-chin-no-e1rm", "负重引体", hard=True)
def c09(db, uid):
    S.seed_session(db, uid, ago(6), [
        {"exercise_id": CHIN, "name": "引体向上",
         "set_logs": [S.set_log(type="bodyweight_reps", reps=8,
                                 added_weight_kg=10),
                      S.set_log(type="bodyweight_reps", reps=6,
                                 added_weight_kg=15)]}])
    r, _g, by_ex = facts_by_metric(db, uid)
    has_e1rm = (CHIN, "best-estimated-1rm") in by_ex
    f_add = by_ex.get((CHIN, "max-added-weight"))
    f_reps = by_ex.get((CHIN, "max-reps"))
    return (not has_e1rm and f_add and f_add["value"] == 15
            and f_reps and f_reps["value"] == 8), \
        f"e1rm 出现={has_e1rm}"


@case("weighted-chin-volume-added-only", "负重引体", hard=True)
def c10(db, uid):
    S.seed_session(db, uid, ago(6), [
        {"exercise_id": CHIN, "name": "引体向上",
         "set_logs": [S.set_log(type="bodyweight_reps", reps=8,
                                 added_weight_kg=10)]}])
    r, _g, by_ex = facts_by_metric(db, uid)
    v = by_ex[(CHIN, "volume")]
    return v["value"] == 80 and "added_weight" in v["calculation"], \
        f"volume={v['value']}"


# ============ 类别 5：辅助引体（assisted_reps） ============

@case("assisted-chin-min-assistance", "辅助引体")
def c11(db, uid):
    S.seed_session(db, uid, ago(4), [
        {"exercise_id": CHIN, "name": "引体向上",
         "set_logs": [S.set_log(type="assisted_reps", reps=10,
                                 assistance_kg=30)]}])
    S.seed_session(db, uid, ago(2), [
        {"exercise_id": CHIN, "name": "引体向上",
         "set_logs": [S.set_log(type="assisted_reps", reps=10,
                                 assistance_kg=20)]}])
    r, _g, by_ex = facts_by_metric(db, uid)
    f = by_ex[(CHIN, "min-assistance-kg")]
    return (f["value"] == 20 and f["status"] == "observed"
            and not (CHIN, "best-estimated-1rm") in by_ex), \
        f"min_assist={f['value']}"


# ============ 类别 6：平板支撑（duration）用时长作主指标 ============

@case("plank-longest-set", "平板支撑", hard=True)
def c12(db, uid):
    S.seed_session(db, uid, ago(8), [
        {"exercise_id": PLANK, "name": "平板支撑",
         "set_logs": [S.set_log(type="duration", duration_seconds=60)]}])
    S.seed_session(db, uid, ago(1), [
        {"exercise_id": PLANK, "name": "平板支撑",
         "set_logs": [S.set_log(type="duration", duration_seconds=90)]}])
    r, _g, by_ex = facts_by_metric(db, uid)
    f = by_ex.get((PLANK, "longest-set"))
    return (f and f["value"] == 90 and f["unit"] == "秒"
            and not (PLANK, "best-estimated-1rm") in by_ex
            and not (PLANK, "volume") in by_ex), f"longest={f and f['value']}"


@case("plank-progress-by-duration", "平板支撑")
def c13(db, uid):
    S.seed_session(db, uid, ago(20), [
        {"exercise_id": PLANK, "name": "平板支撑",
         "set_logs": [S.set_log(type="duration", duration_seconds=45)]}])
    S.seed_session(db, uid, ago(13), [
        {"exercise_id": PLANK, "name": "平板支撑",
         "set_logs": [S.set_log(type="duration", duration_seconds=55)]}])
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": PLANK, "name": "平板支撑",
         "set_logs": [S.set_log(type="duration", duration_seconds=75)]}])
    prog = fact_service.exercise_progress(db, uid, PLANK)
    v = progress_analysis.analyze_progress(prog["series"], "duration")
    return v["verdict"] == "improving" and v["metric"] == "longest-set", \
        f"{v['verdict']}/{v['metric']}"


# ============ 类别 7：自由训练不计计划完成率 ============

@case("free-only-no-plan-completion", "自由训练完成率", hard=True)
def c14(db, uid):
    pid = S.seed_plan(db, uid)
    for d in (ago(6), ago(4), ago(2)):
        S.seed_session(db, uid, d, [
            {"exercise_id": BENCH, "name": "卧推",
             "set_logs": bench_logs([(60, 8)])}],
            mode="free", day=f"自由训练 {d}")
    r, _g, by_ex = facts_by_metric(db, uid)
    f = by_ex.get(("plan", "plan-completed-days"),
                  by_ex.get((None, "plan-completed-days"))) or \
        next((x for x in r["facts"] if x["metric"] == "plan-completed-days"),
             None)
    return f and f["value"] == 0, f"completed={f and f['value']}"


@case("same-day-dedup", "自由训练完成率", hard=True)
def c15(db, uid):
    pid = S.seed_plan(db, uid, days=("周一",))
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}],
        mode="planned", day="周一", plan_id=pid)
    # 同一天第二次训练（同为周一）→ 只计一次
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": SQUAT, "name": "深蹲",
         "set_logs": bench_logs([(100, 5)])}],
        mode="planned", day="周一", plan_id=pid)
    r = fact_service.get_training_facts(db, uid)
    f = next(x for x in r["facts"] if x["metric"] == "plan-completed-days")
    return f["value"] == 1, f"completed={f['value']}"


@case("template-session-not-plan", "自由训练完成率", hard=True)
def c16(db, uid):
    pid = S.seed_plan(db, uid, days=("周一",))
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}],
        mode="free", day="模板 · 推", template_id=9)
    r = fact_service.get_training_facts(db, uid)
    f = next(x for x in r["facts"] if x["metric"] == "plan-completed-days")
    return f["value"] == 0, f"completed={f['value']}"


# ============ 类别 8：历史纠错后使用当前有效数据 ============

@case("corrected-history-current-value", "历史纠错", hard=True)
def c17(db, uid):
    cid = S.seed_session(db, uid, ago(5), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}])
    S.correct_checkin(db, uid, cid, {"weight_kg": 70})
    r, _g, by_ex = facts_by_metric(db, uid)
    e = by_ex[(BENCH, "best-estimated-1rm")]
    dq = e["data_quality"]
    return (e["value"] == round(70 * (1 + 8 / 30), 1)
            and dq.get("corrected_records") == 1
            and f"checkin:{cid}:revision:1" in e["source_ids"]), \
        f"e1rm={e['value']} dq={dq}"


# ============ 类别 9：数据间隔较长，不过度判断 ============

@case("long-gap-limitations", "数据缺口")
def c18(db, uid):
    S.seed_session(db, uid, ago(60), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}])
    S.seed_session(db, uid, ago(45), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(61, 8)])}])
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(66, 8)])}])
    prog = fact_service.exercise_progress(db, uid, BENCH, window_days=90)
    v = progress_analysis.analyze_progress(prog["series"], "weight_reps")
    noted = any("间隔" in l for l in v["limitations"])
    return noted or v["verdict"] == "insufficient", \
        f"{v['verdict']} lim={v['limitations']}"


@case("two-sessions-insufficient", "数据缺口", hard=True)
def c19(db, uid):
    S.seed_session(db, uid, ago(10), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}])
    S.seed_session(db, uid, ago(9), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(65, 8)])}])
    prog = fact_service.exercise_progress(db, uid, BENCH)
    v = progress_analysis.analyze_progress(prog["series"], "weight_reps")
    return v["verdict"] == "insufficient", f"{v['verdict']}"


# ============ 类别 10：用户不想改 → 不擅自修改 ============

@case("consult-no-auto-proposal", "用户不想改变")
def c20(db, uid):
    before = db.conn.execute(
        "SELECT COUNT(*) c FROM change_proposals WHERE user_id=?",
        (uid,)).fetchone()["c"]
    from coach.agents import consult_specialists as _c
    class _Fake:
        fake = True
    res = _c(db, _Fake(), uid, "我觉得现在计划挺好，要不要改训练频率？")
    after = db.conn.execute(
        "SELECT COUNT(*) c FROM change_proposals WHERE user_id=?",
        (uid,)).fetchone()["c"]
    return after == before, f"proposals {before}->{after}"


@case("status-quo-option-required", "多方案建议")
def c21(db, uid):
    prompt = SPECIALISTS["training_science"]["prompt"]
    adv = fake_advice("training_science")
    titles = " ".join(o["title"] for o in adv["options"])
    return ("维持现状" in prompt) and ("维持" in titles), \
        "训练科学专家缺少维持现状要求/选项"


# ============ 类别 11：健康风险未解除 → 不绕过 ============

@case("trial-blocked-by-fence", "健康安全门", hard=True)
def c22(db, uid):
    from coach.agent import CoachAgent
    agent = CoachAgent(uid, db_path=db.path)
    agent.profile["onboarding_done"] = True
    agent.profile.setdefault("conditions", {}).setdefault(
        "pain_flags", []).append({"flag_id": "flag-x", "status": "open",
                                  "kw": "膝盖", "tier": "red"})
    agent.profile["plan_fence"] = {"safety_flag_ids": ["flag-x"]}
    result = agent._handle_tool({
        "name": "start_personal_trial", "arguments": json.dumps({
            "change_desc": "提高卧推频率", "reason": "想试试",
            "observe": "卧推表现", "stop_rule": "肘痛即停",
            "review_days": 14})}, "normal")
    blocked = "安全" in result or "不开始" in result
    trials = db.personal_trials(uid)
    return blocked and not trials, f"result={result[:60]}"


# ============ 类别 12：专家分歧并列 ============

@case("multi-expert-conflict-listed", "专家分歧")
def c23(db, uid):
    a = fake_advice("training_science")
    a["options"] = [{"title": "方案A", "detail": "", "citations": []}]
    b = fake_advice("nutrition")
    b["options"] = [{"title": "方案B", "detail": "", "citations": []}]
    combined = combine([a, b])
    return bool(combined["conflicts"]), "分歧未被并列标注"


# ============ 类别 13：知识来源未审核 ============

@case("unverified-citation-stripped", "未审核来源", hard=True)
def c24(db, uid):
    raw = json.dumps({
        "problem": "p", "facts": [], "knowledge_basis": [],
        "options": [
            {"title": "有据", "detail": "d", "citations": ["kb:ok/ref.md"]},
            {"title": "编造", "detail": "d", "citations": ["不存在的引用"]}],
        "conditions": [], "risks": [], "needs_confirmation": []},
        ensure_ascii=False)
    advice = parse_advice(raw, "knowledge")
    bound = __import__("coach.agents.orchestrator", fromlist=["x"])._bind_citations(
        advice, {"kb:ok/ref.md"})
    cited = [o["citations"] for o in bound["options"]]
    inferred = [o["evidence"] for o in bound["options"]]
    return cited[1] == [] and inferred[1] == "inferred" and inferred[0] == "cited", \
        f"{cited}/{inferred}"


# ============ 类别 14：尝试期间数据不足 ============

@case("trial-review-data-insufficient", "尝试数据不足", hard=True)
def c25(db, uid):
    db.start_personal_trial(uid, "提高卧推频率到每周2次", "想突破",
                            "相似次数下卧推表现", "肘痛即停", 14,
                            baseline=None)
    trial = db.personal_trials(uid)[0]
    draft = trial_evidence.review_draft(db, uid, trial)
    joined = json.dumps(draft["sections"], ensure_ascii=False)
    no_claim = "证实" not in joined or "不" in joined
    return no_claim and draft["sections"]["unconfirmed"], \
        "复盘草稿宣称已证实或缺少无法确认节"


@case("trial-execution-gap-attribution", "尝试执行缺口", hard=True)
def c26(db, uid):
    db.start_personal_trial(uid, "提高卧推频率", "想突破",
                            "卧推表现", "肘痛即停", 30)
    trial = db.personal_trials(uid)[0]
    draft = trial_evidence.review_draft(db, uid, trial)
    joined = json.dumps(draft["sections"]["unconfirmed"], ensure_ascii=False)
    return "归因" in joined or "不足" in joined or "样本" in joined, \
        f"unconfirmed={joined[:80]}"


@case("trial-baseline-snapshot", "尝试基线")
def c27(db, uid):
    S.seed_session(db, uid, ago(5), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}])
    baseline = trial_evidence.snapshot_baseline(db, uid, "卧推表现")
    data = json.loads(baseline)
    return (data["kind"] == "trial_baseline_v1"
            and any(f["exercise_id"] == BENCH for f in data["facts"])), \
        "基线未包含动作事实"


# ============ 补充确定性案例：十项要求逐条 ============

@case("warmup-excluded", "热身排除", hard=True)
def c28(db, uid):
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(65, 8)], warmup_first=40)}])
    r, _g, by_ex = facts_by_metric(db, uid)
    w = by_ex[(BENCH, "working-sets")]
    e = by_ex[(BENCH, "best-estimated-1rm")]
    return w["value"] == 1 and e["value"] == round(65 * (1 + 8 / 30), 1), \
        f"sets={w['value']}"


@case("window-query-7d", "时间窗口")
def c29(db, uid):
    seed_bench3(db, uid)  # 21/14/7 天前
    r7 = fact_service.get_training_facts(db, uid, window_days=8)  # 覆盖 ago(7)
    n7 = next(f for f in r7["facts"]
              if f["metric"] == "sessions" and f.get("exercise_id") == BENCH)
    return n7["value"] == 1, f"8天窗口 sessions={n7['value']}"


@case("high-reps-no-e1rm", "口径边界", hard=True)
def c30(db, uid):
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(40, 15)])}])
    r, _g, by_ex = facts_by_metric(db, uid)
    e = by_ex[(BENCH, "best-estimated-1rm")]
    return e["status"] == "insufficient" and e["value"] is None, \
        f"15次组 e1rm={e['value']}"


@case("insufficient-not-zero-volume", "缺失不用0冒充", hard=True)
def c31(db, uid):
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": PLANK, "name": "平板支撑",
         "set_logs": [S.set_log(type="duration", duration_seconds=60)]}])
    r = fact_service.get_training_facts(db, uid)
    e = next((f for f in r["facts"]
              if f.get("exercise_id") == PLANK
              and f["metric"] == "best-estimated-1rm"), None)
    return e is None or (e["status"] == "insufficient"
                         and e["value"] is None), "时长类出现了 e1RM 数值"


@case("rpe-marked-subjective", "主观反馈标注")
def c32(db, uid):
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": [S.set_log(weight_kg=60, reps=8, rpe=8)]}])
    r, _g, by_ex = facts_by_metric(db, uid)
    f = by_ex[(BENCH, "rpe-average")]
    return (f["value"] == 8 and "主观" in str(f["data_quality"].get("note", ""))
            + str(f.get("note", ""))), "RPE 未标注为主观自报"


@case("distance-farthest", "距离类")
def c33(db, uid):
    from coach.exercises import library
    ex = library.get("farmer_carry")
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": "farmer_carry", "name": "农夫行走",
         "set_logs": [S.set_log(type="distance_time", distance_m=40,
                                 duration_seconds=55)]}])
    r, _g, by_ex = facts_by_metric(db, uid)
    f = by_ex.get(("farmer_carry", "farthest-distance"))
    return f and f["value"] == 40, f"farthest={f and f['value']}"


@case("unknown-exercise-noted", "动作校验")
def c34(db, uid):
    r = fact_service.get_training_facts(db, uid, exercise_ids=["no_such_ex"])
    no_ex_facts = all(not f.get("exercise_id") for f in r["facts"])
    return r["notes"] and no_ex_facts, f"notes={r['notes']}"


@case("stable-verdict-band", "趋势稳定性")
def c35(db, uid):
    for d, w in ((ago(24), 60), (ago(17), 60), (ago(10), 61), (ago(3), 60.5)):
        S.seed_session(db, uid, d, [
            {"exercise_id": BENCH, "name": "卧推",
             "set_logs": bench_logs([(w, 8)])}])
    prog = fact_service.exercise_progress(db, uid, BENCH)
    v = progress_analysis.analyze_progress(prog["series"], "weight_reps")
    return v["verdict"] == "stable", f"{v['verdict']} ev={v['evidence']}"


@case("declining-verdict", "趋势方向")
def c36(db, uid):
    for d, w in ((ago(24), 70), (ago(17), 70), (ago(10), 65), (ago(3), 60)):
        S.seed_session(db, uid, d, [
            {"exercise_id": BENCH, "name": "卧推",
             "set_logs": bench_logs([(w, 8)])}])
    prog = fact_service.exercise_progress(db, uid, BENCH)
    v = progress_analysis.analyze_progress(prog["series"], "weight_reps")
    return v["verdict"] == "declining", f"{v['verdict']}"


@case("plan-scheduled-estimate", "计划应练推算")
def c37(db, uid):
    S.seed_plan(db, uid, days=("周一", "周三", "周六"))
    r = fact_service.get_training_facts(db, uid)
    f = next(x for x in r["facts"] if x["metric"] == "plan-scheduled-sessions")
    expect = round(3 * 30 / 7)  # 3 个计划日/周 × 30/7 周
    return f["value"] == expect and f["status"] == "estimated", \
        f"scheduled={f['value']} expect={expect}"


@case("facts-window-fields", "窗口字段")
def c38(db, uid):
    r = fact_service.get_training_facts(db, uid, window_days=14)
    w = r["window"]
    return (w["days"] == 14
            and (date.fromisoformat(w["end"])
                 - date.fromisoformat(w["start"])).days == 13), str(w)


@case("single-session-quality-note", "单次样本标注")
def c39(db, uid):
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}])
    r, _g, by_ex = facts_by_metric(db, uid)
    f = by_ex[(BENCH, "sessions")]
    return any("1 次" in n for n in f["data_quality"].get("notes", [])), \
        str(f["data_quality"])


@case("mixed-sessions-both-counted", "计划+自由并存")
def c40(db, uid):
    pid = S.seed_plan(db, uid, days=("周一",))
    S.seed_session(db, uid, ago(4), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}],
        mode="planned", day="周一", plan_id=pid)
    S.seed_session(db, uid, ago(2), [
        {"exercise_id": SQUAT, "name": "深蹲",
         "set_logs": bench_logs([(100, 5)])}], mode="free", day="自由")
    r = fact_service.get_training_facts(db, uid)
    comp = next(x for x in r["facts"]
                if x["metric"] == "plan-completed-days")
    note = comp.get("note") or ""
    dq = comp.get("data_quality", {})
    dq_notes = " ".join([*dq.get("notes", []), str(dq.get("note", ""))])
    return comp["value"] == 1 and ("自由" in note or "自由" in dq_notes), \
        f"{comp['value']} note={note!r}"


@case("router-facts-in-specialist-context", "专家上下文注入")
def c41(db, uid):
    S.seed_session(db, uid, ago(3), [
        {"exercise_id": BENCH, "name": "卧推",
         "set_logs": bench_logs([(60, 8)])}])
    from coach.agents.orchestrator import _context_for
    ctx = _context_for(db, uid, "我的训练计划容量够不够？")
    return "训练事实" in ctx and "barbell_bench_press" in ctx, \
        "训练科学问题未注入训练事实"


@case("numeric-fabrication-detector", "数值可追溯检查器", hard=True)
def c42(db, uid):
    seed_bench3(db, uid)
    prog = fact_service.exercise_progress(db, uid, BENCH)
    grounded = json.dumps(prog["facts"][:4], ensure_ascii=False)
    fabricated = "你上次卧推 200kg，1RM 有 250kg！"
    allowed = {str(f["value"]) for f in prog["facts"]}
    from .test_eval import untraceable_numbers
    ok_g = untraceable_numbers(grounded, allowed) == []
    ok_f = len(untraceable_numbers(fabricated, allowed)) >= 2
    return ok_g and ok_f, f"grounded={ok_g} fabricated_caught={ok_f}"


@case("agent-grounded-reply-traceable", "回复数值可追溯", hard=True)
def c43(db, uid):
    seed_bench3(db, uid)
    from coach.agent import CoachAgent
    agent = CoachAgent(uid, db_path=db.path)
    agent.profile["onboarding_done"] = True
    reply = agent.chat("我最近卧推有没有进步？")
    # 允许集 = 事实与序列里出现过的全部数值（与场景 A 同口径）
    prog = fact_service.exercise_progress(db, uid, BENCH)
    facts = fact_service.get_training_facts(db, uid, 30)
    allowed = {str(f["value"]) for f in facts["facts"]}
    allowed |= {str(f["value"]) for f in prog["facts"]}
    for s in prog["series"]:
        allowed.update({str(s.get("best_e1rm")),
                        str((s.get("best_set") or {}).get("weight_kg")),
                        str((s.get("best_set") or {}).get("reps"))})
    import re as _re
    for m in _re.finditer(r"(?:first|second)_half_median\":\s*([0-9.]+)",
                          json.dumps(prog, default=str)):
        allowed.add(m.group(1))
    from .test_eval import untraceable_numbers
    bad = untraceable_numbers(reply, allowed)
    return not bad, f"不可追溯数值: {bad} reply={reply[:120]}"
