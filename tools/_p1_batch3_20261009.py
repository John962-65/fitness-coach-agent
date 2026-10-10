"""一次性：P1 第三批——腿弯举/提踵两张动作卡（2026-10-09）。

背景：Q8 的 31 条发言者归属经发起人 2026-10-09 确认（原 10-08 清单每视频只列前 4 条，
全量清单见 tools/q8_speaker_sheet_full.py 生成的 p1_speaker_sheet_20261009.md）。
本脚本只产出草稿并推入发起人队列，不批准任何内容。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coach.cards import assert_not_quarantined, build_review_queue, validate_card  # noqa: E402
from coach.claim_review import content_fingerprint, source_issues  # noqa: E402
from tools._card_batch_20261008 import (MAINT, load_all_claims, quote_for,  # noqa: E402
                                        transcript_segments)

NOW = datetime.now().astimezone().isoformat(timespec="seconds")

LEG_CURL = {
    "card_id": "card-action-lying_leg_curl",
    "scene": "俯身/坐姿腿弯举：脚怎么放、骨盆怎么稳、下放放到哪",
    "audience": "想练大腿后侧、有俯身或坐姿腿弯举器械的训练者；俯身时能收腹维持骨盆稳定者",
    "non_audience": "要弓腰反弓才能做完的人先减重或改坐姿；膝盖有未评估问题、动作中疼痛加重者不做",
    "body": (
        "1) 脚位两种都行，按自己感受选：内八（股骨内旋）更多练向心，能让大腿后侧"
        "预先发力；外八（股骨外旋）更多练离心，要放到底、上到 2/3 行程就结束。"
        "两种都要勾脚、不要绷脚——绷直脚小腿容易抽筋、参与太多。\n"
        "2) 骨盆与核心：全程收腹、骨盆不要前倾反弓；脚的位置一松就说明过了，"
        "核心收住即使有点前倾也没问题。\n"
        "3) 下放：不一定放到底——下到底结构会松掉、肌腱压力也大，留一点空间，"
        "或从约 2/3 位置开始。\n"
        "4) 组次示例（视频原话，不是处方）：内旋位 6 个＋外旋位 6 个共 12 个一组、"
        "五组左右；另一期说法是四组左右、每组约 15 个。没有俯身器械，坐姿也 OK。\n"
        "5) 顺序参考：腿部训练的第一个正式动作可以先练大腿后侧——从内侧和后侧"
        "开始更好，因为股骨缺的内旋内收能力更多。"),
    "limits": ("12 条绑定全部来自谭成义三个视频（2026-01-03/01-16/06-28），"
               "发言者归属经发起人 2026-10-09 逐条确认；组次的两种说法跨视频并列保留，"
               "以自身感受为准，不裁定哪次更对。全部为博主经验、无研究出处；"
               "applies_to 全空，本卡适用/不适用人群是卡片级限定，不代表原条目已核实条件。"),
    "purpose": "coaching_card",
    "claim_ids": [
        "tcy-BV1gyiqByEWZ-0013", "tcy-BV1gyiqByEWZ-0014", "tcy-BV1gyiqByEWZ-0015",
        "tcy-BV1gyiqByEWZ-0016", "tcy-BV1gyiqByEWZ-0017", "tcy-BV1gyiqByEWZ-0018",
        "tcy-0552", "tcy-0553", "tcy-0554", "tcy-0555", "tcy-0929", "tcy-0930"],
}

CALF = {
    "card_id": "card-action-standing_calf_raise",
    "scene": "站姿提踵：站姿还是坐姿、垫高与脚位、常见错误与进阶",
    "audience": "想练小腿或改善足踝功能的训练者；能扶住支撑单脚站稳者",
    "non_audience": "站不稳、内外翻控制不住的人先练稳定（夹物或扶墙）再负重；踝关节有未评估问题、疼痛加重者不做",
    "body": (
        "1) 站姿优先：对大部分人建议站姿踮脚——坐姿踮脚腓肠肌参与可能过多，"
        "站姿能用上更多深层肌肉；谭成义把小腿称作“第二、第三个心脏”，建议刻意练。\n"
        "2) 垫高：前脚掌踩在前方垫高位置（台阶边），后脚跟悬空，行程更大、拉伸更多；"
        "但前脚掌不能完全离开支撑。脚往前放会简单些，越朝前足远端发力越难。\n"
        "3) 发力与常见错误：大拇指球和小拇指球都要踩住、脚趾脚球始终抓地；"
        "下放时前脚掌别翘起、脚趾别松。身体位置全部固定、只做踮脚，"
        "向上是向上向后，不要往前顶、不要屈膝代偿，也不要整个人前倾。\n"
        "4) 不稳的练法：控制不住内外翻时，拿有体积的东西（瑜伽球、卡扣、小水瓶）"
        "夹在两只脚后跟中间、脚尖朝前固定双脚；标准后练单腿提踵，减少支撑点加难。\n"
        "5) 组次示例（跨博主不同，并列保留）：凯圣王 10 次×3 组（脚尖朝前）后进阶单腿；"
        "谭成义 20 次×4 组，下去慢、起来略快。太久没练，头两次三组左右就够，不酸了再加。"),
    "limits": ("19 条绑定：谭成义 15 条（2026-02-14/06-28 两视频）＋凯圣王 4 条"
               "（2023-03-03 视频），发言者归属经发起人 2026-10-09 逐条确认；"
               "组次口径跨博主不同，按并列保留规则呈现、以用户自身感受为准。"
               "“第二心脏”“改善血糖、减脂效率”等是视频原话的类比/经验说法，"
               "不是医疗结论，不能当作治病或保证效果用；全部为博主经验、无研究出处，"
               "applies_to 全空，本卡人群限定是卡片级限定。"),
    "purpose": "coaching_card",
    "claim_ids": [
        "tcy-0473", "tcy-0474", "tcy-0475", "tcy-0476", "tcy-0477", "tcy-0478",
        "tcy-0479", "tcy-0480", "tcy-0481", "tcy-0482",
        "tcy-BV1LbcWzyE64-0014", "tcy-BV1LbcWzyE64-0015", "tcy-BV1LbcWzyE64-0016",
        "tcy-BV1LbcWzyE64-0017", "tcy-BV1LbcWzyE64-0018",
        "ksw-BV1E84y1K7k7-0017", "ksw-BV1E84y1K7k7-0018",
        "ksw-BV1E84y1K7k7-0019", "ksw-BV1E84y1K7k7-0020"],
}


def build_card(spec: dict, claims: dict, transcripts: dict) -> dict:
    bindings = []
    for cid in spec["claim_ids"]:
        claim = claims[cid]
        issues = source_issues(claim)
        if issues:
            raise SystemExit(f"{cid} 来源侧不合格：{issues}")
        bindings.append({
            "claim_id": cid,
            "claim_fingerprint": content_fingerprint(claim),
            "video": claim["video"], "ts": claim["ts"],
            "url": f"https://www.bilibili.com/video/{claim['video']}?t={int(claim['ts'][0])}",
            "speaker": claim["speaker"],
            "quote": quote_for(claim, transcripts.get(claim["video"], []))})
    assert_not_quarantined(spec["claim_ids"])
    card = {"card_id": spec["card_id"], "version": 1, "scene": spec["scene"],
            "audience": spec["audience"], "non_audience": spec["non_audience"],
            "body": spec["body"], "limits": spec["limits"],
            "purpose": spec["purpose"], "bindings": bindings,
            "notes": "Q8 发言者归属经发起人 2026-10-09 确认后制作（31 条全量清单 "
                     "sources/review_packet/p1_speaker_sheet_20261009.md）",
            "status": "prepared_v1", "prepared_by": "Zcode", "prepared_at": NOW}
    errors = validate_card(card)
    if errors:
        raise SystemExit(f"{card['card_id']} 结构不合法：{errors}")
    return card


def main() -> int:
    claims = load_all_claims()
    transcripts = transcript_segments()
    cards = [build_card(s, claims, transcripts) for s in (LEG_CURL, CALF)]
    for card in cards:
        (MAINT / "cards" / f"{card['card_id']}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{card['card_id']} v{card['version']}｜绑定 {len(card['bindings'])} 条"
              f"｜正文 {len(card['body'])} 字")

    old = json.loads((MAINT / "card_review_queue.json").read_text(encoding="utf-8"))
    questions = [
        {"id": "Q10",
         "question": "lying_leg_curl（腿弯举）与 standing_calf_raise（提踵）两张卡已按 Q8 确认的归属做好，请逐卡 通过/退回/暂不使用。",
         "recommendation": "两张都建议通过：绑定条目全部来自已确认发言者，组次分歧已按并列保留规则呈现。",
         "uncertain": "组次为视频原话区间（12个×5组 vs 15个×4组；10×3 vs 20×4），二者场景可能不同但原文未说明，卡内只并列不裁决。",
         "evidence": "claims 31 条 + p1_speaker_sheet_20261009.md"},
        {"id": "Q11",
         "question": "新建 3 个动作（lateral_band_walk 侧向弹力带移动 / bent_over_triceps_extension 俯身哑铃臂屈伸 / seated_cable_curl 坐姿龙门架弯举）的相关 18 条 claims 里，11 条 speaker 仍为「待确认」（均在这三位博主的单人视频里）：要不要按记录归属一并确认，以便之后给这 3 个动作出卡？",
         "recommendation": "建议确认——这 11 条均出自谭成义单人教学视频（BV1pZiZBxE8y / BV1MvwxzGEio / BV1ND5S6pEgx / BV1wvMF6ZEqL），非合集双人出镜。",
         "uncertain": "本人未看画面，按 §3 不能代替你确认。",
         "evidence": "claims/tcy.yaml 对应条目 speaker 字段"},
        {"id": "Q12",
         "question": "三个新动作的 joint_stress（关节压力粗粒度 0-3）我按隔离动作惯例填了默认值并标 pending：是否由你最终核定？",
         "recommendation": "建议你直接核定或让我按惯例保留 pending，不影响出卡与引用。",
         "uncertain": "joint_stress 影响伤病替换逻辑，设计书 21.2③b 标注必须由发起人判断。",
         "evidence": "exercises/{lateral_band_walk,bent_over_triceps_extension,seated_cable_curl}.yaml _provenance.joint_stress: pending"},
    ]
    queue = build_review_queue(
        [{"card_id": c["card_id"], "version": c["version"], "scene": c["scene"],
          "bindings": len(c["bindings"]), "purpose": c["purpose"],
          "status": c["status"]} for c in cards],
        questions, NOW)
    queue["cards_detail_ref"] = "sources/maintenance/cards/<card_id>.json"
    queue["mechanism_enabled"] = old.get("mechanism_enabled", True)
    queue["answered_history"] = old.get("answered_history", [])
    queue["awaiting"] = ("两张新卡待逐卡 通过/退回/暂不使用；Q11（11 条新动作 claims 的发言者）、"
                        "Q12（三个新动作的 joint_stress）待回答")
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：2 卡 + 3 问")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
