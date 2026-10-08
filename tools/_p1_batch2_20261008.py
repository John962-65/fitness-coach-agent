"""一次性：P1 缺口处置（2026-10-08 第二批）。

1. 出面拉（face_pull）卡草稿：谭成义三次讲解口径并列保留，以用户自身感受为主（发起人 2026-10-08）；
2. 生成腿弯举/提踵的发言者画面核对清单（含前后文交接词线索），这两组素材已够，只卡归属；
3. 重建发起人队列：1 张卡 + 3 个待决问题，上一批问答进 answered_history。
不批准任何内容：签核仍只走 tools/card_review.py --approve --by 发起人。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coach.cards import assert_not_quarantined, build_review_queue, load_cards, validate_card
from coach.claim_review import content_fingerprint, source_issues
from tools._card_batch_20261008 import (MAINT, load_all_claims, quote_for,
                                        transcript_segments)


def claim_text(claim: dict) -> str:
    return str(claim.get("claim") or "")

NOW = datetime.now().astimezone().isoformat(timespec="seconds")

# 发布序由 B 站公开元数据核对（未逐帧看片）：坐姿凳上→仰卧→跟练版
PUBDATE = {"BV1utntzhE9a": "2025-09-25", "BV1fRyjBREQg": "2025-11-19",
           "BV1aC2ZBwEHC": "2025-12-07", "BV1gyiqByEWZ": "2026-01-03",
           "BV1w9kKBfEsi": "2026-01-16", "BV1LbcWzyE64": "2026-02-14",
           "BV1RjTT6FEKo": "2026-06-28", "BV1E84y1K7k7": "2023-03-03"}

FACE_PULL = {
    "card_id": "card-action-face_pull",
    "scene": "绳索面拉：用什么体位、怎么拉、放回到哪里",
    "audience": "想练肩后束与上背、有龙门架或低滑轮的训练者；能主动收肋、控制躯干者",
    "non_audience": "核心稳不住会前后晃动者先选躯干最不晃的体位（仰卧最容易做到）；"
                    "颈椎腰椎有未评估问题、动作中疼痛加重者不做大范围外旋",
    "body": (
        "1) 体位三种都行，按你自己的感受选：仰卧在地上或垫子上做，躯干最容易保持"
        "不动（谭成义 2025-11-19 明确不推荐坐姿站姿，理由是核心稳不住会前后晃动）；"
        "坐姿凳上也有完整讲法，滑轮高度调到坐下后与肚脐平行、腰背贴紧凳子"
        "（2025-09-25）；没有凳子时坐地上或用哑铃凳躺着用绳索做，效果没区别，"
        "不用纠结器械（2025-12-07）。判据是能不能保持肋骨收紧、头不前探——"
        "哪个体位做下来肩后束感受清楚、躯干不晃，就用哪个。\n"
        "2) 躯干：全程肋骨收紧、不要翘高，腰背贴紧；一用力肋骨就打开往前，"
        "既练不到肩，腰椎磨损也大。\n"
        "3) 路径：手穿过把手抓住绳子向头顶位置拉，把外展加外旋做到位——"
        "面拉本质是提拉与外旋一起完成，动作效率高。\n"
        "4) 放回幅度：不要放到底，放到底张力就松了、肌肉就松掉；放到约 2/3 位置"
        "或留一点距离就结束，整个过程流畅连贯、不要停顿。\n"
        "5) 器械与安排：用延长绳而不是三头绳，幅度更大；可排在推肩、推胸等大强度"
        "动作之后，用来定向刺激肩部并分配疲劳。"),
    "limits": (
        "体位口径分歧按发起人 2026-10-08 决定处理：三种讲法并列保留、以用户自身感受"
        "为主，不裁定哪期优先。三段讲解的发布先后（2025-09-25 坐姿凳上→2025-11-19 "
        "仰卧并明确不要坐姿站姿→2025-12-07 跟练版称坐地上或躺着皆可）由 B 站公开"
        "元数据核对，只作背景信息、不作为取舍依据；早期坐姿口径（滑轮高度调到坐下后"
        "与肚脐平行、腰背贴紧凳子，tcy-BV1utntzhE9a-0003/0005）保留在绑定里供回看，"
        "本次只核对了发布时间与字幕文本，未逐帧核对原片。14 条绑定中 13 条原条目 "
        "applies_to 为空，本卡的适用/不适用人群是卡片级限定，不代表原条目已核实适用条件。"
        "头容易前探是核心功能不好的表现，需颈腰椎位置稳定后再做；全部条目为博主经验，"
        "无研究出处。"),
    "notes": "P1 剩余 6 张动作卡的第一个可用项：面拉的素材早已在库，之前只因适用条件为空被我排在素材池外",
    "purpose": "coaching_card",
    "claim_ids": [
        "tcy-BV1fRyjBREQg-0003", "tcy-BV1fRyjBREQg-0004", "tcy-BV1fRyjBREQg-0005",
        "tcy-BV1fRyjBREQg-0006", "tcy-BV1aC2ZBwEHC-0050", "tcy-BV1aC2ZBwEHC-0051",
        "tcy-BV1aC2ZBwEHC-0052", "tcy-BV1aC2ZBwEHC-0053", "tcy-BV1utntzhE9a-0003",
        "tcy-BV1utntzhE9a-0004", "tcy-BV1utntzhE9a-0005", "tcy-BV1utntzhE9a-0006",
        "tcy-BV1utntzhE9a-0007", "ksw-BV1W2ga6xEBC-0027"],
}

BLOCKED = {"lying_leg_curl": "俯身/俯卧腿弯举", "standing_calf_raise": "站姿提踵"}

ANSWERED = {
    "Q4": "上线——以肩疼/弹响为前提的幅度内容作为 coaching_card，保留红旗优先与加重即停",
    "Q5": "要求动作卡通道只服务 coaching_card 并补测试（已实现：coach/cards.py card_for_exercise "
          "过滤 purpose，test_cards_runtime.py 两项新测试）",
    "Q6": "补 P1 素材（已核：面拉/腿弯举/提踵 素材已在库，分别卡在适用条件与发言者归属；"
          "只有负重引体是真缺口）",
    "dips 分歧": "两种做法都保留，以用户自己感受为准，怎么感受好怎么做",
    "Q7": "这些面拉口径都可以，以用户感受为主（发起人 2026-10-08 对话原话）——"
          "正文与 limits 已改为三种体位并列，发布时间只作背景",
}


def _dedupe_by_id(items: list[dict]) -> list[dict]:
    """重跑不重复追加同一条问答，也不让已记录的发起人结论被无回答副本覆盖。"""
    out: dict[str, dict] = {}
    for item in items:
        key = str(item.get("id"))
        kept = out.get(key)
        if kept is None:
            out[key] = item
        elif not kept.get("answered") and (item.get("answered")
                                           or item.get("superseded_by")):
            out[key] = item
    return list(out.values())


def build_card(claims: dict[str, dict], transcripts: dict[str, list]) -> dict:
    existing = load_cards().get(FACE_PULL["card_id"])
    if existing and (existing.get("review") or {}).get("status") == "approved":
        raise SystemExit("面拉卡已有发起人审批记录，本脚本不覆盖")
    bindings = []
    for cid in FACE_PULL["claim_ids"]:
        claim = claims[cid]
        issues = source_issues(claim)
        if issues:
            raise SystemExit(f"{cid} 来源侧不合格：{issues}")
        bindings.append({"claim_id": cid,
                         "claim_fingerprint": content_fingerprint(claim),
                         "video": claim["video"], "ts": claim["ts"],
                         "url": f"https://www.bilibili.com/video/{claim['video']}"
                                f"?t={int(claim['ts'][0])}",
                         "speaker": claim["speaker"],
                         "quote": quote_for(claim, transcripts.get(claim["video"], []))})
    assert_not_quarantined(FACE_PULL["claim_ids"])
    card = {"card_id": FACE_PULL["card_id"], "version": 1,
            "scene": FACE_PULL["scene"], "audience": FACE_PULL["audience"],
            "non_audience": FACE_PULL["non_audience"], "body": FACE_PULL["body"],
            "limits": FACE_PULL["limits"], "purpose": FACE_PULL["purpose"],
            "bindings": bindings, "notes": FACE_PULL["notes"],
            "status": "prepared_v1", "prepared_by": "Zcode", "prepared_at": NOW}
    errors = validate_card(card)
    if errors:
        raise SystemExit(f"卡结构不合法：{errors}")
    return card


def context_before(segments: list[dict], start: float, seconds: float = 18.0) -> str:
    return "".join(s.get("text", "") for s in segments
                   if start - seconds <= s.get("start", 0) < start)[:90]


def speaker_sheet(claims: list[dict], transcripts: dict) -> str:
    lines = ["# P1 待画面确认发言者清单（2026-10-08）", "",
             "> 这批素材来源、时间窗、正文都已合格，只差发言者归属；"
             "语境线索只是辅助，按任务书 §3 不能代替对照画面确认。", ""]
    for ex, cn in BLOCKED.items():
        every = [c for c in claims if ex in (c.get("exercises") or [])]
        sel = [c for c in every
               if not str(c.get("speaker") or "").strip()
               or any(m in str(c.get("speaker")) for m in ("待确认", "未知", "不确定", "语境归因"))]
        lines.append(f"## {cn}（`{ex}`）· 已挂 {len(every)} 条，其中待确认 {len(sel)} 条")
        lines.append("")
        by_video: dict[str, list[dict]] = {}
        for c in sel:
            by_video.setdefault(c["video"], []).append(c)
        for video, items in sorted(by_video.items(), key=lambda kv: -len(kv[1])):
            bloggers = "、".join(sorted({str(i.get("blogger")) for i in items}))
            date = PUBDATE.get(video, "发布日期未核对")
            lines.append(f"- **{video}**（{len(items)} 条）｜记录归属：{bloggers}"
                         f"｜发布：{date}")
            for c in sorted(items, key=lambda i: i["ts"][0])[:4]:
                segs = transcripts.get(video, [])
                lines.append(f"  - [{c['id']}] type={c.get('type')} t={int(c['ts'][0])} "
                             f"https://www.bilibili.com/video/{video}"
                             f"?t={int(c['ts'][0])}")
                lines.append(f"    - 说法：{claim_text(c)[:70]}")
                ctx = context_before(segs, c["ts"][0])
                if ctx:
                    lines.append(f"    - 前文线索：{ctx}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    claims = load_all_claims()
    transcripts = transcript_segments()
    card = build_card(claims, transcripts)
    (MAINT / "cards" / f"{card['card_id']}.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{card['card_id']} v{card['version']}｜绑定 {len(card['bindings'])} 条"
          f"｜正文 {len(card['body'])} 字")

    sheet = speaker_sheet(list(claims.values()), transcripts)
    out = ROOT / "sources" / "review_packet" / "p1_speaker_sheet_20261008.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet, encoding="utf-8")
    counts = {ex: sum(1 for c in claims.values() if ex in (c.get("exercises") or []))
              for ex in BLOCKED}
    print(f"画面核对清单 -> {out.relative_to(ROOT)}（{counts}）")

    queue_path = MAINT / "card_review_queue.json"
    old = json.loads(queue_path.read_text(encoding="utf-8"))
    questions = [
        {"id": "Q7",
         "question": "面拉体位按发布时间取新口径（仰卧/地面），早期坐姿凳上说法保留在 limits 与绑定里——"
                     "是否认可？发布序来自 B 站公开元数据（2025-09-25 / 11-19 / 12-07），未逐帧看片。",
         "recommendation": "已按发起人 2026-10-08 决定改为三种体位并列、以用户自身感受为主，"
                           "发布时间只作背景；本卡仍需逐卡签核。",
         "uncertain": "12-07 跟练版里博主自己也说「坐地上或躺着都行」，与 11-19 的"
                      "「不要坐姿站姿」并不冲突，但都不同于 9-25 的凳上坐姿。",
         "evidence": "tcy-BV1fRyjBREQg-0003 t=71｜tcy-BV1aC2ZBwEHC-0050 t=897｜"
                     "tcy-BV1utntzhE9a-0003 t=63"},
        {"id": "Q8",
         "question": "俯身/俯卧腿弯举 12 条、站姿提踵 19 条全部卡在发言者归属（双人出镜、AI 字幕不分说话人）。"
                     "清单已生成在 sources/review_packet/p1_speaker_sheet_20261008.md，"
                     "每条带跳转点与前 18 秒线索。你确认归属后我才能出这两张卡：要不要现在过一遍？",
         "recommendation": "建议只确认你打算近期用的那组（提踵 31 条集中在 BV1RjTT6FEKo、"
                           "BV1LbcWzyE64、BV1E84y1K7k7 三个视频）；"
                           "其余继续留作素材，不占人工名额。",
         "uncertain": "语境线索只能提示是谁在说，按 §3 不算画面确认。",
         "evidence": "tools/triage_claims.py speaker_unresolved 桶 2491 条"},
        {"id": "Q9",
         "question": "负重引体向上（weighted_pull_up）在 6354 条里 0 命中，现有 210 个视频的字幕里也搜不到"
                     "「负重引体/腰带加重量」相关说法——这是真素材缺口，需要新采集。"
                     "上一批 LLM 额度（collection_batch_20261006，cap 40）已用满 40/40，"
                     "按任务书 §5 续批需要你明确授权：给多少次？",
         "recommendation": "建议先授权一小批（例如 6 次：3 个候选视频×2 段），"
                           "只覆盖负重引体与剩余 P1 缺口，不到就停并记 budget_exhausted。",
         "uncertain": "选片需要先做元数据检查（免费），我没找到这三位创作者讲负重引体的现成视频。",
         "evidence": "grep 字幕 0 命中；账本 used_llm_calls=40 cap=40"},
    ]
    live = [q for q in questions if q["id"] not in ANSWERED]
    settled = [dict(q, answered=ANSWERED[q["id"]]) for q in questions if q["id"] in ANSWERED]
    queue = build_review_queue(
        [{"card_id": card["card_id"], "version": card["version"], "scene": card["scene"],
          "bindings": len(card["bindings"]), "purpose": card["purpose"],
          "status": card["status"]}], live, at=NOW)
    queue.update({
        "schema_version": old.get("schema_version", 1),
        "batch_limit": {"cards": 5, "questions": 3},
        "cards_detail_ref": "sources/maintenance/cards/<card_id>.json",
        "mechanism_enabled": old.get("mechanism_enabled", True),
        "awaiting": "面拉卡待逐卡 通过/退回/暂不使用；Q8-Q9 需回答",
        "answered_history": _dedupe_by_id(
            (old.get("answered_history") or []) +
            [dict(q, **{"answered": ANSWERED[q["id"]]})
             for q in old.get("questions", []) if q["id"] in ANSWERED] +
            [{"id": "dips 分歧处置", "answered": ANSWERED["dips 分歧"]}] + settled),
    })
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    run = {"schema_version": 1, "run_id": "maint_20261008_p1_batch2", "at": NOW,
           "code_version": {"git_rev": "15fca2e(基线) + 未提交工作区", "dirty": True},
           "approved_this_round": [
               "card-action-dumbbell_shoulder_press", "card-action-lateral_raise",
               "card-action-dips"],
           "prepared": [card["card_id"]],
           "runtime_cards_served": 23,
           "notes": "3 卡经发起人对话批准并记录原话；Q5 通道隔离已实现；"
                    "P1 剩余 6 张中 4 张为素材/归属问题，非审核问题；负重引体为真缺口待续批额度"}
    (MAINT / "runs" / "maint_20261008_p1_batch2.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列与本轮报告已更新")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
