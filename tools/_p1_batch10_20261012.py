"""一次性：Q23 后批——清尾批 3 张动作卡（2026-10-12）。

crunch（Q21 建库动作出卡）/ skull_crusher（重挂后素材成型）/ front_squat。
出完本批，干净素材池基本清空：bodyweight_squat 池混杂待复核，
其余候选素材 <5 条或需采集。只产草稿，不批准。
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
        "card_id": "card-action-crunch",
        "scene": "地面卷腹：手位颈椎、呼吸与卷法、常见错误与安排",
        "audience": "居家或热身想练腹直肌、没有器械也能做的训练者",
        "non_audience": "腰椎有未评估问题者先评估；做成仰卧起坐改不过来的先减幅度",
        "body": (
            "1) 手位与颈椎（凯圣王）：尽量不要双手抱头（照顾活动度问题），"
            "双手揪着耳朵、微收下巴、颈椎放松。\n"
            "2) 做法与呼吸：向心时一定要呼气，把腹腔尽量往下压再起来，"
            "尽量让腹往地上贴；把胸跟上背部抬起来，身体想象成跟虾米一样往里卷，"
            "下胸椎段跟腰部要牢牢贴在垫子上，往下时不能被翘起来出现反弓。\n"
            "3) 常见错误：把卷腹做成仰卧起坐、起得特别高——腹没感觉但腰会疼，"
            "这是用腰部代偿了。\n"
            "4) 安排参考：在家做标准卷腹对腹直肌刺激就足够了；"
            "组合示例为卷腹 15 次加两头起 15 次（家庭课语境）。"),
        "limits": ("5 条绑定全部来自凯圣王（BV1MG4y1G76W 家庭课腹部段），发言者已确认；"
                   "2026-10-11 解除 cable_crunch 错挂、Q21 批准建库。"
                   "两头起（V 字起）不在本卡范围。全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1MG4y1G76W-0047", "ksw-BV1MG4y1G76W-0048", "ksw-BV1MG4y1G76W-0050",
            "ksw-BV1MG4y1G76W-0051", "ksw-BV1MG4y1G76W-0052"],
    },
    {
        "card_id": "card-action-skull_crusher",
        "scene": "仰卧臂屈伸（碎颅者）：轨迹、反手变式、肘腕安全与何时少用",
        "audience": "想练三头维度、有杠铃/哑铃和凳子的训练者",
        "non_audience": "肘关节疼痛或当日肘部负荷已大者按正文调整；外旋明显受限者直接选对握",
        "body": (
            "1) 定位与变式（谭成义）：仰卧臂屈伸（碎颅者）练三头，可杠铃正手、反手或哑铃对握；"
            "三头课里反手杠铃臂屈伸练的是三头肌维度（绳索下压练的是刻度）。\n"
            "2) 轨迹：仰卧杠铃臂屈伸建议更多向斜前方推、而不是单纯向斜上方——"
            "肩的稳定和核心参与会更多，帮助建立胸廓稳定和肩关节能力。\n"
            "3) 反手姿势要求：腿不要往上放，否则核心不参与；在宽伸位、大腿稍微夹一点"
            "使骨盆稳定、腰贴紧，做肩前屈后再做臂屈伸，连续稳定地做。\n"
            "4) 常见错误与肘安全：不要把大臂回到正中央——肘关节三头肌腱压力非常大、"
            "三头会软掉，持续张力不在效率低；要在肩屈位保持三头持续收缩再做动作。\n"
            "5) 外旋受限与手腕不适：反手做时手腕疼，原因多是肩外旋受限、压力表现在手腕上"
            "——过于难受就不建议做，可改为哑铃对握；正手做时外旋受限会打开收不住、"
            "长头刺激很少，必须往里拐进去再做，拐不进去就建议用哑铃对握或反手。\n"
            "6) 何时少用（凯圣王语境，并列参考）：家庭课选择俯身臂屈伸而非仰卧臂屈伸——"
            "肘关节已经用了很多，需要相对开放、更孤立、肘压力没那么大的动作；"
            "不是否定本动作，按当日肘部累计负荷安排。"),
        "limits": ("7 条绑定：谭成义 6 条（BV1hyWwzeETh 反手杠铃臂屈伸 3＋BV14JBHBYEMp "
                   "碎颅者 3）＋凯圣王 1 条（BV1MG4y1G76W），发言者均已确认；"
                   "2026-10-12 反手臂屈伸 3 条自 close_grip_bench_press 重挂（K-A02 同类）。"
                   "tcy-BV14JBHBYEMp-0011（FLAGGED）未纳入。手腕/肘不适即减量或换握法，"
                   "持续疼痛先评估。全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1MG4y1G76W-0042",
            "tcy-BV1hyWwzeETh-0006", "tcy-BV1hyWwzeETh-0007", "tcy-BV1hyWwzeETh-0008",
            "tcy-BV14JBHBYEMp-0009", "tcy-BV14JBHBYEMp-0010", "tcy-BV14JBHBYEMp-0012"],
    },
    {
        "card_id": "card-action-front_squat",
        "scene": "颈前深蹲：定位、做法与深蹲族进阶路径",
        "audience": "深蹲族进阶者、肩活动度做不好颈后深蹲想换颈前的训练者",
        "non_audience": "手腕/肘活动度撑不住杆位者先练活动度或用泽奇过渡；腰椎有未评估问题者先评估",
        "body": (
            "1) 定位（谭成义）：深蹲最难的是抓蹲（手举杠铃再蹲），其次是颈后深蹲——"
            "大部分人不适合做颈后深蹲；颈前深蹲相对简单且最好。\n"
            "2) 做法：肘要始终往上抬、抬高之后再蹲——肘掉下来核心就散掉松掉；"
            "尽量不要屈髋，屈髋会导致动作变差、幅度变小。\n"
            "3) 进阶路径：从泽奇到颈前，从颈前到颈后，从颈后到抓蹲（按能力逐级上）。\n"
            "4) 深蹲族取舍（凯圣王）：“无深蹲不翘臀”是错的——任何深蹲都躲不开腿，"
            "靠深蹲单独练翘臀会让腿的肌肉量增加变粗；想单独侧重臀部有专门动作"
            "（如臀冲类），深蹲族练的是腿臀整体。"),
        "limits": ("5 条绑定：谭成义 4 条（BV1jQsXzREf5 颈前深蹲教学）＋凯圣王 1 条"
                   "（BV1s44y1q7vt），发言者均已确认。深蹲难度排序与进阶路径为博主原话口径；"
                   "“不翘臀”为博主对流行说法的反驳，非绝对结论。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1s44y1q7vt-0027-w0",
            "tcy-BV1jQsXzREf5-0012", "tcy-BV1jQsXzREf5-0013",
            "tcy-BV1jQsXzREf5-0014", "tcy-BV1jQsXzREf5-0017"],
    },
]


def build_card(spec: dict, claims: dict, transcripts: dict) -> dict:
    bindings = []
    for cid in spec["claim_ids"]:
        claim = claims[cid]
        issues = source_issues(claim)
        if issues:
            raise SystemExit(f"{cid} 来源侧不合格：{issues}")
        if claim.get("anti_hallucination") == "FLAGGED":
            raise SystemExit(f"{cid} 为 FLAGGED，本批从严不纳入")
        expect = spec["card_id"].removeprefix("card-action-")
        if expect not in (claim.get("exercises") or []):
            raise SystemExit(f"{cid} 未映射到 {expect}：{claim.get('exercises')}")
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
            "notes": "清尾批：干净素材池出完后转采集/映射复核",
            "status": "prepared_v1", "prepared_by": "Zcode", "prepared_at": NOW}
    errors = validate_card(card)
    if errors:
        raise SystemExit(f"{card['card_id']} 结构不合法：{errors}")
    for b in bindings:
        if b["quote"].startswith("（字幕窗口未命中"):
            raise SystemExit(f"{card['card_id']} 绑定 {b['claim_id']} 引文未命中原文")
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
    questions = [
        {"id": "Q24",
         "question": "清尾批 3 张卡（地面卷腹/仰卧臂屈伸/颈前深蹲）请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：三张都是干净素材（5/7/5 条，全部 speaker 已确认、无隔离、映射一致）；"
                           "出完本批，现有已提炼素材的干净池基本清空。",
         "uncertain": "仰卧臂屈伸卡并存反手（谭成义）与正手/对握（外旋受限调整）两种握法口径，"
                      "并保留凯圣王“何时少用”的语境条目；颈前深蹲卡“无深蹲不翘臀是错的”"
                      "为博主对流行说法的反驳，已在 limits 注明非绝对结论。",
         "evidence": "cards 文件 + claims 17 条"},
    ]
    history = old.get("answered_history", [])
    history += [
        {"id": "Q23",
         "question": "本批 2 张卡（反向山羊挺身/跪姿俯卧撑）逐卡 通过/退回/暂不使用",
         "answered": "通过（发起人 2026-10-12 对话原话「通过」）——2 卡均 approved_v1；"
                     "批准前复验 19 条绑定指纹一致、引文命中、无隔离、无 FLAGGED、映射一致；"
                     "运行时服务卡 51→53",
         "answered_at": NOW},
    ]
    queue = build_review_queue(
        [{"card_id": c["card_id"], "version": c["version"], "scene": c["scene"],
          "bindings": len(c["bindings"]), "purpose": c["purpose"],
          "status": c["status"]} for c in cards],
        questions, NOW)
    queue["cards_detail_ref"] = "sources/maintenance/cards/<card_id>.json"
    queue["mechanism_enabled"] = old.get("mechanism_enabled", True)
    queue["answered_history"] = history
    queue["awaiting"] = ("3 张卡待逐卡签核（Q24）；出完本批干净池清空，"
                         "后续出卡依赖采集（平台期/停训复训等提炼需额度续批）与映射复核（bodyweight_squat/band_pull_apart）")
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：3 卡 + 1 问（Q24）；Q23 已记入 answered_history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
