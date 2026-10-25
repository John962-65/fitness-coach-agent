"""营养顾问确定性分析器（P1：MealRecorded / UserRequested → 日营养回顾）。

纪律（2.0 §3.5、§十三）：
- 全部数值来自 nutrient_calculator 的确定性计算（快照口径），
  绝不让 LLM 估算营养成分；
- 只报告「已记录摄入量」：当天未标记完整或有餐次缺失时，方向性建议
  降级为"补齐记录"，不用不完整数据制造摄入判断；
- 与目标比较只在目标已设置时进行，比例如实计算；
- 不生成医疗饮食处方（临床需求一律建议专业人员，写入限制）；
- 置信度按记录完整度与历史天数规则生成。
"""
from __future__ import annotations

from datetime import date as _date, datetime, timedelta

from . import nutrient_calculator
from .meal_service import MEAL_LABELS, day_summary, day_version

WINDOW_DAYS = 14          # 记录习惯观察窗
EXPIRE_DAYS = 3           # 日回顾时效短（次日新记录即失效由漂移保证）


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fact(fact_id: str, metric: str, value, unit: str, window: dict,
          source_ids: list[str], calculation: str, status: str, **quality) -> dict:
    return {"fact_id": fact_id, "metric": metric, "value": value, "unit": unit,
            "measurement_type": "nutrition", "window": window,
            "source_ids": source_ids, "calculation": calculation,
            "data_quality": quality or {}, "status": status}


def _confidence(meal_types: list[str], complete_mark: bool,
                history_days: int, has_targets: bool) -> tuple[str, str]:
    """置信度规则（写入 basis）：
    - high：用户标记完整 + 记录 ≥3 个餐次 + 近 14 天 ≥5 天有记录；
    - medium：≥2 个餐次；或满足 high 的记录面但历史不足；
    - low：仅 1 个餐次（只有零星已记录量，不给方向性建议）。
    无目标会让目标比较维度缺失（写入限制，不影响档位本身）。"""
    if complete_mark and len(meal_types) >= 3 and history_days >= 5:
        level = "high"
    elif len(meal_types) >= 2:
        level = "medium"
    else:
        level = "low"
    parts = [f"已记录 {len(meal_types)} 个餐次（{','.join(MEAL_LABELS.get(t, t) for t in meal_types) or '无'}）",
             f"当天完整标记={'是' if complete_mark else '否'}",
             f"近 {WINDOW_DAYS} 天有 {history_days} 天存在饮食记录"]
    return level, "置信度规则=记录完整度与历史天数（" + "；".join(parts) + f"）→ {level}"


def analyze_daily_nutrition(db, user_id: str, input_refs: dict) -> dict:
    """某日饮食回顾（确定性）。input_refs: {"local_date": "YYYY-MM-DD"}"""
    local_date = str(input_refs.get("local_date") or "")
    try:
        _date.fromisoformat(local_date)
    except ValueError:
        raise ValueError("local_date 需为 YYYY-MM-DD") from None
    summary = day_summary(db, user_id, local_date)
    meals = summary["meals"]
    if not meals:
        raise ValueError(f"{local_date} 没有任何饮食记录，无可分析内容")
    totals = summary["day"]["totals"]
    targets = db.get_nutrition_targets(user_id)
    history = db.meal_history(user_id, WINDOW_DAYS)
    history_days = len({m["local_date"] for m in history})
    complete_mark = summary["complete_mark"]
    meal_types = summary["meal_types_recorded"]

    window = {"start": local_date, "end": local_date, "days": 1}
    srcs = [f"meal:{m['id']}" for m in meals]
    facts, findings = [], []
    missing = {k: v for k, v in (summary["day"]["data_quality"] or {}).items()
               if v.get("unknown")}

    # ---- 事实：已记录营养合计（口径=快照求和；未知项计数） ----
    metric_map = [("energy_kcal", "已记录能量", "kcal"),
                  ("protein_g", "已记录蛋白质", "g"),
                  ("carbohydrate_g", "已记录碳水", "g"),
                  ("fat_g", "已记录脂肪", "g")]
    for key, label, unit in metric_map:
        dq = (summary["day"]["data_quality"] or {}).get(key)
        quality = ({} if dq is None
                   else {"unknown_items": dq["unknown"], "known_items": dq["known"]})
        facts.append(_fact(
            f"{key}-{local_date}", key, totals[key], unit, window, srcs,
            "sum_nutrition_snapshots_recorded",
            "observed" if dq is None else "estimated",
            note="已记录摄入量（未记录餐次≠摄入 0）" if dq is None else
                 f"含 {dq['unknown']} 个条目该营养素未知（保留缺失，未按 0 计）",
            **quality))
        finding_text = f"{label} {totals[key]:g}{unit}"
        if dq:
            finding_text += f"（{dq['unknown']} 个条目未知该值，未按 0 计）"
        if key == "energy_kcal":
            finding_text += f"；已记录餐次：{'、'.join(MEAL_LABELS.get(t, t) for t in meal_types)}"
        findings.append({"finding_id": f"f-{key}", "kind": "recorded-total",
                         "text": finding_text, "fact_ids": [f"{key}-{local_date}"],
                         "source_ids": srcs})

    # ---- 与目标比较（只在目标已设置时） ----
    if targets.get("energy_kcal") or targets.get("protein_g"):
        cmp_parts = []
        for key, label, unit in metric_map:
            t = targets.get(key)
            if not t:
                continue
            pct = round(totals[key] / t * 100, 1) if t else None
            facts.append(_fact(
                f"{key}-vs-target-{local_date}", f"{key}-vs-target", pct, "%",
                window, srcs, "recorded_over_target",
                "observed" if complete_mark else "estimated",
                target_value=t, note="" if complete_mark else "当天未标记完整，比例仅代表已记录部分"))
            cmp_parts.append(f"{label}为目标 {pct:g}%（目标 {t:g}{unit}）")
        findings.append({
            "finding_id": "f-target-compare", "kind": "target-compare",
            "text": ("目标比较（当天已标记完整）：" if complete_mark
                     else "目标比较（当天未标记完整，以下仅是已记录部分/目标，不代表全天缺口）：")
                   + "；".join(cmp_parts),
            "fact_ids": [f"{k}-vs-target-{local_date}" for k, _, _ in metric_map
                         if targets.get(k)],
            "source_ids": srcs})

    # ---- 记录习惯 ----
    findings.append({
        "finding_id": "f-recording-habit", "kind": "recording-habit",
        "text": (f"近 {WINDOW_DAYS} 天有 {history_days} 天饮食记录；"
                 f"当天{'已' if complete_mark else '未'}标记记录完整"),
        "fact_ids": [], "source_ids": srcs,
        "evidence": "context"})

    # ---- 方案（确定性规则；完整才给方向，不完整只建议补记录） ----
    options = [{
        "option_id": "keep-observing", "title": "维持当前记录习惯，继续观察",
        "detail": (f"已记录 {totals['energy_kcal']:g} kcal、蛋白质 {totals['protein_g']:g}g。"
                   "营养数据的价值主要来自长期记录趋势，不必因单日数字调整饮食。"),
        "basis": [f"energy_kcal-{local_date}"],
        "tradeoffs": {"收益": "不引入新变量；记录负担最小",
                      "代价": "变化速度取决于现状",
                      "适用条件": "无特殊医嘱"},
    }]
    complete_enough = complete_mark and len(meal_types) >= 3
    if not complete_enough:
        options.append({
            "option_id": "complete-records", "title": "先把记录补完整，再谈调整",
            "detail": ("当天未标记完整或缺餐次记录时，任何『摄入不足/超标』的判断都会"
                       "建立在不知道未记录部分的基础上。建议先把三餐记全（或在餐后"
                       "标记当天记录完整），系统再给可比较的方向。"),
            "basis": [f"energy_kcal-{local_date}"],
            "tradeoffs": {"收益": "后续比较与分析才有依据",
                          "代价": "需要记录投入",
                          "适用条件": "愿意精确或粗略记录（可在营养目标页设置意愿）"},
        })
    elif targets.get("energy_kcal") or targets.get("protein_g"):
        gaps = []
        if targets.get("energy_kcal"):
            pct = totals["energy_kcal"] / targets["energy_kcal"]
            if pct < 0.8:
                gaps.append(f"已记录能量为目标 {round(pct * 100)}%（已标记完整）")
            elif pct > 1.2:
                gaps.append(f"已记录能量超目标 {round((pct - 1) * 100)}%（已标记完整）")
        if targets.get("protein_g") and totals["protein_g"] / targets["protein_g"] < 0.8:
            gaps.append(f"蛋白质 {totals['protein_g']:g}g 低于目标 {targets['protein_g']:g}g")
        if gaps:
            options.append({
                "option_id": "review-direction", "title": "参考方向：与目标差距较大，可自行调整",
                "detail": ("依据：" + "；".join(gaps) +
                           "。这只是基于已记录数据与你自己设置目标的参考方向——"
                           "如何调整、是否调整由你决定；持续观察比单日纠正更重要。"),
                "basis": [f"{k}-vs-target-{local_date}" for k, _, _ in metric_map
                          if targets.get(k)],
                "tradeoffs": {"收益": "缩小与自设目标的偏差",
                              "代价": "饮食自由度/记录负担可能上升",
                              "适用条件": "目标是你自己设的且仍认同；无临床营养医嘱"},
            })

    # ---- 置信度与限制 ----
    confidence, confidence_basis = _confidence(
        meal_types, complete_mark, history_days,
        bool(targets.get("energy_kcal") or targets.get("protein_g")))
    limitations = [
        "数值为「已记录摄入量」——未记录的餐次不代表摄入为 0",
        "食物营养值为参考约值（内置目录/你录入的标签），非实验室测定",
    ]
    if missing:
        limitations.append(f"部分条目营养素未知：{'、'.join(missing)}（保留缺失，未按 0 计）")
    if not complete_mark:
        limitations.append("当天未标记记录完整，不做全天摄入充分性判断")
    if not (targets.get("energy_kcal") or targets.get("protein_g")):
        limitations.append("未设置营养目标，未做目标比较（可在营养目标页设置）")
    limitations.append("本分析不构成医疗饮食处方；疾病治疗/临床营养需求请咨询专业人员")

    src_revision = {"meals": {local_date: day_version(db, user_id, local_date)},
                    "targets_updated_at": targets.get("updated_at")}
    title = f"饮食回顾 · {local_date}"
    summary_text = (f"已记录 {totals['energy_kcal']:g} kcal、蛋白质 {totals['protein_g']:g}g"
                    f"（{len(meal_types)} 个餐次"
                    f"{'，已标记完整' if complete_mark else '，未标记完整'}）。"
                    f"共 {len(options)} 个参考方向，均由你决定。")

    return {
        "specialist": "nutrition",
        "insight_type": "daily-nutrition-review",
        "title": title,
        "summary": summary_text,
        "findings": findings,
        "evidence_refs": sorted({fid for f in findings for fid in f["fact_ids"]}),
        "facts_snapshot": {"window": window, "facts": facts,
                           "caliber": "nutrient_calculator 快照求和；未知项保留缺失"},
        "knowledge_refs": [],
        "options": options,
        "limitations": limitations,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "generated_at": _now(),
        "expires_at": (datetime.now() + timedelta(days=EXPIRE_DAYS)
                       ).isoformat(timespec="seconds"),
        "source_revision": src_revision,
        "input_refs": {"local_date": local_date},
    }
