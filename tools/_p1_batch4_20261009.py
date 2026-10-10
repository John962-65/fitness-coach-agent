"""一次性：3 个新动作的教学卡（2026-10-09 晚，Q11 speaker 确认后）。

lateral_band_walk / bent_over_triceps_extension / seated_cable_curl：
三条线的 claims 均已挂新动作 id，speaker 经发起人 2026-10-09 确认（Q11）。
只产草稿推队列，不批准。
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

CARDS = [
    {
        "card_id": "card-action-lateral_band_walk",
        "scene": "弹力带侧向移动（臀部激活）：带子位置、屈膝量与膝盖走向",
        "audience": "练腿/练臀前想激活臀部、有弹力带的训练者",
        "non_audience": "动作中膝盖疼痛加重者不做；站不稳、维持不了屈髋位者先徒手练稳",
        "body": (
            "1) 摆位：弹力带套在膝盖上方一点，两脚与肩同宽，屈髋位；"
            "做之前就要先感受到臀部发力明显再去做。\n"
            "2) 屈膝量：不要屈膝太多（压力到大腿前侧）也不要伸膝太多（到大腿后侧），"
            "要找平衡点即臀位。\n"
            "3) 膝盖走向：想着膝盖向外走、而不是脚走；走的过程中膝盖始终对着脚尖，"
            "从正面看这条线始终是正的，并保证足弓参与。\n"
            "4) 量与变式：一般两到三组，做完屁股会超级酸；外展对抗做完后，"
            "可以找一块瑜伽砖垫在膝盖内侧夹住，做内收对抗的侧向移动，"
            "同样用手摸屁股感受发力。"),
        "limits": ("5 条绑定全部来自谭成义单人视频（BV1pZiZBxE8y），"
                   "发言者归属经发起人 2026-10-09 确认（Q11）。本卡为热身/激活用法，"
                   "全部为博主经验、无研究出处；applies_to 全空，本卡人群限定是卡片级限定。"),
        "purpose": "coaching_card",
        "claim_ids": ["tcy-BV1pZiZBxE8y-0018", "tcy-BV1pZiZBxE8y-0019",
                      "tcy-BV1pZiZBxE8y-0020", "tcy-BV1pZiZBxE8y-0021",
                      "tcy-BV1pZiZBxE8y-0022"],
    },
    {
        "card_id": "card-action-bent_over_triceps_extension",
        "scene": "俯身哑铃臂屈伸：姿势怎么摆、肘锁不锁、做几组",
        "audience": "想针对性练三头刻度、有哑铃和床/墙可扶的训练者",
        "non_audience": "肘关节疼痛者（锁肘会放大不适）；维持不了俯身姿势者先练躯干稳定",
        "body": (
            "1) 做法：扶床或墙俯身，大臂向后像划船姿势，把肘伸直、三头完全收紧；"
            "下放时大臂不要掉下来。这个动作重量会比较轻，太重维持不住。\n"
            "2) 锁肘：每次都要把肘锁死（只要肘不疼），会感觉三头收得非常紧；"
            "如果每次到一半就结束，三头刻度不会好。\n"
            "3) 组次：每边 10~12 次，左边做完再做右边，做三组、每组每边 12 次。\n"
            "4) 定位：它更趋向三头肌的刻度；颈后臂屈伸更趋向维度，"
            "视频里两个兼顾着选（颈后臂屈伸是另一个动作，不在本卡范围）。"),
        "limits": ("4 条绑定全部来自谭成义单人视频（BV1MvwxzGEio），"
                   "发言者归属经发起人 2026-10-09 确认（Q11）。「肘不疼」是锁肘的前提，"
                   "安全红旗优先于本卡内容；全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": ["tcy-BV1MvwxzGEio-0037", "tcy-BV1MvwxzGEio-0038",
                      "tcy-BV1MvwxzGEio-0039", "tcy-BV1MvwxzGEio-0040"],
    },
    {
        "card_id": "card-action-seated_cable_curl",
        "scene": "坐姿龙门架弯举：手臂怎么架、握法、放回到哪",
        "audience": "想练二头肌腹、健身房有龙门架/钢线站的训练者",
        "non_audience": "坐姿弓背或肩部前倾不适者（可先垫子或换站姿）；肩腕有未评估问题者",
        "body": (
            "1) 摆位：大臂架在膝盖上（架久了可垫垫子），关节被固定、肩关节不会被带跑，"
            "压力小且不易代偿——视频里说这个动作对二头肌腹帮助非常大，想快速变大是首选。\n"
            "2) 握法与发力：保持外旋位、半握（更靠尺侧，能让二头内侧更饱满），"
            "肘窝朝上、手腕勾起来；大臂尽量靠近远端，弯举时保证肘窝和手腕在一条线上，"
            "想着把二头当球挤爆。\n"
            "3) 放回：不要完全放到底——放到底二头是松的、不发力，"
            "起始应从有张力的位置开始；放的时候手腕不要松、不要塌下去，勾住去放。\n"
            "4) 安排：做完三头动作后不休息直接做，形成二头加三头的超级组；"
            "躯干保持稳定不要被重量带走；没必要为了增加行程低头弯举；"
            "只做颈前（眼前）就够了，不要做颈后。"),
        "limits": ("9 条绑定来自谭成义三个单人视频（BV14JBHBYEMp / BV1ND5S6pEgx / "
                   "BV1wvMF6ZEqL），其中 BV1ND5S6pEgx-0009/0010 的「大臂卡在膝盖上」"
                   "经字幕上下文核对与 BV14JBHBYEMp 的坐姿龙门架弯举为同一动作；"
                   "发言者归属经发起人 2026-10-09 确认（Q11）。"
                   "全部为博主经验、无研究出处；applies_to 全空，本卡人群限定是卡片级限定。"),
        "purpose": "coaching_card",
        "claim_ids": ["tcy-BV14JBHBYEMp-0024", "tcy-BV14JBHBYEMp-0025",
                      "tcy-BV14JBHBYEMp-0026", "tcy-BV14JBHBYEMp-0027",
                      "tcy-BV1ND5S6pEgx-0009", "tcy-BV1ND5S6pEgx-0010",
                      "tcy-BV1wvMF6ZEqL-0010", "tcy-BV1wvMF6ZEqL-0011",
                      "tcy-BV1wvMF6ZEqL-0012"],
    },
]


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
            "notes": "Q11 speaker 确认（2026-10-09）后制作；3 个新动作 2026-10-09 建库",
            "status": "prepared_v1", "prepared_by": "Zcode", "prepared_at": NOW}
    errors = validate_card(card)
    if errors:
        raise SystemExit(f"{card['card_id']} 结构不合法：{errors}")
    return card


def main() -> int:
    claims = load_all_claims()
    transcripts = transcript_segments()
    cards = [build_card(s, claims, transcripts) for s in CARDS]
    for card in cards:
        (MAINT / "cards" / f"{card['card_id']}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{card['card_id']} v1｜绑定 {len(card['bindings'])} 条｜正文 {len(card['body'])} 字")

    old = json.loads((MAINT / "card_review_queue.json").read_text(encoding="utf-8"))
    pending = [q for q in old.get("questions", []) if q.get("id") == "Q12"]
    questions = pending + [
        {"id": "Q13",
         "question": "3 个新动作的教学卡（侧向弹力带移动 / 俯身哑铃臂屈伸 / 坐姿龙门架弯举）已做好，请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：18 条绑定 speaker 均已确认（Q11），映射与动作库定义一致。",
         "uncertain": "三个动作的 joint_stress 仍是 pending（Q12），不影响卡内容但影响伤病替换。",
         "evidence": "cards 文件 + claims 18 条"},
    ]
    queue = build_review_queue(
        [{"card_id": c["card_id"], "version": c["version"], "scene": c["scene"],
          "bindings": len(c["bindings"]), "purpose": c["purpose"],
          "status": c["status"]} for c in cards],
        questions, NOW)
    queue["cards_detail_ref"] = "sources/maintenance/cards/<card_id>.json"
    queue["mechanism_enabled"] = old.get("mechanism_enabled", True)
    queue["answered_history"] = old.get("answered_history", [])
    queue["awaiting"] = ("3 张新动作卡待逐卡签核（Q13）；Q12（joint_stress）待发起人核定；"
                        "负重引体全量扫描进行中")
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：3 卡 + 2 问（Q12/Q13）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
