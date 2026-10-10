"""一次性：Q20/Q21 后批——4 张动作卡（2026-10-11 深夜）。

rear_delt_fly（俯身飞鸟重挂后素材最厚）/ machine_shoulder_press / chest_supported_row /
hip_thrust。machine_chest_press 本轮放弃：素材薄且 4 条已被 pec_deck 卡绑定。
只产草稿，不批准。
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
        "card_id": "card-action-rear_delt_fly",
        "scene": "反飞鸟（后束）：坐姿器械与俯身哑铃两种形态、握法侧重与常见错误",
        "audience": "想练三角肌后束、改善后束薄弱/中后束之间有缝的训练者",
        "non_audience": "肩有撞击感或疼痛者先减小幅度并评估；后束完全没感受者先做激活",
        "body": (
            "1) 定位与变式：反飞鸟练三角肌后束，常见坐姿器械（夹胸/反飞鸟一体机）与"
            "俯身哑铃两种形态；推肩、反飞鸟、侧平举都能练到后束，但不先激活它"
            "神经传导很差、怎么练也练不起来——激活非常有必要（谭成义）；"
            "后束不是很好，可以再加一个坐姿反飞鸟。\n"
            "2) 坐姿器械反飞鸟：高度低时处于耸肩状态——耸肩不一定错，取决于想练什么；"
            "靠背有斜角度更趋向练后束；手拉过来时顺着三角肌后束肌纤维方向，"
            "高度以三角肌发力明显为准；向后幅度尽可能大、尽量收紧，不要到一半就结束"
            "（效率低）；放回不要完全回去——完全回去张力就松掉了，快结束留一点距离再走。\n"
            "3) 握法与侧重：内旋位时三角肌前束预先收缩、后束预先拉长，对后束刺激更强；"
            "对握中立位更复合；平常正手练太多、中束后束之间有坑或缝，可以选对握或反手练一练；"
            "反手肘的压力可能比较大，要在能接受的范围内做。肩胛骨后缩多一点没关系，"
            "只要三角肌后束感受强、幅度大点没事；感受不好则先做后束激活。"
            "单手反飞鸟行程更大、一侧刺激更强，两侧做效率更高；单手时身体一定要稳定不要晃，"
            "放的时候也不要完全松掉。\n"
            "4) 俯身哑铃飞鸟：重量要偏轻（太重根本控制不了）；采用对握——对三角肌中束和"
            "后束之间的凹陷更好（正手虽让后束更孤立，但凹陷会越来越大）；从外展位开始做、"
            "不要从下方开始（从下方开始三角肌不发力），大臂稍微往前一点点、不要在原位置做；"
            "深吸一口气把胸口抵住凳子、不要往后仰，维持住之后再飞（身体塌掉则前表链和"
            "后表链没有拮抗功能、结构混乱）；肩胛骨活动过大练不到太多后束——把大臂和哑铃"
            "往前放一点再抬；放的时候不要放到底（张力软掉），下到 2/3 就结束，"
            "头不要往前跑。\n"
            "5) 器械调整与不适：健身房靠垫是平的甚至往前，可以屁股往后坐形成前倾位去做；"
            "做反飞鸟时肩膀不舒服的人，放松三角肌后感受会很好。"),
        "limits": ("20 条绑定全部来自谭成义（BV1PcNQ6AE3f 一体机教学 11 条、BV1utntzhE9a "
                   "肩部课俯身飞鸟 6 条、BV1FL2MBME3G/BV1Xs97BqEsQ/BV1aC2ZBwEHC 各 1 条），"
                   "发言者均已确认。坐姿器械与俯身哑铃两种形态按器械条件并列，不评优劣。"
                   "tcy-BV1PcNQ6AE3f-0001（FLAGGED）未纳入。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1PcNQ6AE3f-0020", "tcy-BV1PcNQ6AE3f-0021", "tcy-BV1PcNQ6AE3f-0022",
            "tcy-BV1PcNQ6AE3f-0023", "tcy-BV1PcNQ6AE3f-0024", "tcy-BV1PcNQ6AE3f-0025",
            "tcy-BV1PcNQ6AE3f-0026", "tcy-BV1PcNQ6AE3f-0027", "tcy-BV1PcNQ6AE3f-0029",
            "tcy-BV1PcNQ6AE3f-0030", "tcy-BV1PcNQ6AE3f-0031",
            "tcy-BV1FL2MBME3G-0017", "tcy-BV1Xs97BqEsQ-0018", "tcy-BV1aC2ZBwEHC-0067",
            "tcy-BV1utntzhE9a-0008", "tcy-BV1utntzhE9a-0009", "tcy-BV1utntzhE9a-0010",
            "tcy-BV1utntzhE9a-0011", "tcy-BV1utntzhE9a-0012", "tcy-BV1utntzhE9a-0013"],
    },
    {
        "card_id": "card-action-machine_shoulder_press",
        "scene": "器械推肩（史密斯）：定位、轨迹幅度、握法与控制",
        "audience": "肩膀力量和肌肉量为目标、健身房的训练者；新手按正文选固定器械",
        "non_audience": "肩关节活动度受限者按正文控制幅度；已是自由重量熟练者本卡偏基础",
        "body": (
            "1) 定位（凯圣王，新手计划语境）：肩安排在第四个动作时体力已不充沛，"
            "再做自由动作要求会难一些——训练目的是提高肩膀力量和一定肌肉量，"
            "固定器械的推举是稳妥选择。\n"
            "2) 安全的双面性：固定器械的安全来自角度固定、容错率高，但不安全因素也来自"
            "容错率太高——做杠铃推举小臂到错误角度绝对推不起来，史密斯即使小臂到很夸张的"
            "角度还是能推起来，你可能不知道肩关节已经在错误角度受力。"
            "所以器械推肩更要做对，而不是靠器械兜底。\n"
            "3) 轨迹：整个小臂要在肩胛面，不要过分打开也不要过分靠前，"
            "在身体差不多 15 度夹角的位置上。\n"
            "4) 幅度：刚开始锻炼的人没必要把推举放到很低——很考验肌肉量和肩关节活动度，"
            "肩胛活动度不好容易变成旋前、肩肘压力大；放到鼻子高度就是比较舒适的位置。\n"
            "5) 握法与控制：握好后杆不能压到前手掌，尽量向后放在掌根部；"
            "向上时两个肘关节自然向里收紧、把肩收紧；肘关节不能到超伸状态、保持微曲；"
            "离心时不要自由落体，一定要适当控制。"),
        "limits": ("6 条绑定全部来自凯圣王（BV14v4y1G7A3 新手计划语境），发言者已确认。"
                   "ksw-BV14v4y1G7A3-0007-w1500（FLAGGED）未纳入。"
                   "“容错率太高也有不安全因素”为博主原话的安全提醒，不是器械否定。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV14v4y1G7A3-0008-w1500", "ksw-BV14v4y1G7A3-0009-w1500",
            "ksw-BV14v4y1G7A3-0010-w1500", "ksw-BV14v4y1G7A3-0011-w1500",
            "ksw-BV14v4y1G7A3-0012-w1500", "ksw-BV14v4y1G7A3-0013-w1500"],
    },
    {
        "card_id": "card-action-chest_supported_row",
        "scene": "斜板/俯卧支撑划船：目标肌群、做法与常见错误",
        "audience": "想练中背/菱形肌、俯身划船撑不住腰想要支撑式的训练者",
        "non_audience": "肩部有未评估问题者先评估；胸口抵不住垫子者先调器械高度",
        "body": (
            "1) 定位：俯卧位划船类动作主要练菱形肌及整个中背（从中间到两边），"
            "包括三角肌后束、大圆肌（谭成义）；凯圣王对海豹划船的概括："
            "它就是肩胛内收的卧推离心阶段。\n"
            "2) 握法：正手和对握都可以，没有关系。\n"
            "3) 做法：先收紧腹肌、深吸一口气维持住再拉；幅度不要拉到底、不要放到底，"
            "从中间位置开始、尽量拉高一点；拉的时候头不要往下掉，头要向后伸再做动作。\n"
            "4) 常见错误：拉的时候胸口起来、腰反弓——应保证躯干稳定，"
            "胸口抵住垫子后再做，拉的时候不要起来。\n"
            "5) 幅度要点：胸口能抵住垫子的面积越大越好，拉高一点，"
            "放的时候不要放太多。"),
        "limits": ("8 条绑定：谭成义 7 条（BV1BTWWzuEMs 背部课）＋凯圣王 1 条"
                   "（BV1fjgC62EWN，海豹划船概括），发言者均已确认。"
                   "“海豹划船”与斜板俯卧支撑划船的器械形态可能不同，按同一力学原理理解。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1BTWWzuEMs-0013", "tcy-BV1BTWWzuEMs-0015", "tcy-BV1BTWWzuEMs-0016",
            "tcy-BV1BTWWzuEMs-0017", "tcy-BV1BTWWzuEMs-0018", "tcy-BV1BTWWzuEMs-0019",
            "tcy-BV1BTWWzuEMs-0020", "ksw-BV1fjgC62EWN-0025-w1500"],
    },
    {
        "card_id": "card-action-hip_thrust",
        "scene": "臀冲/臀推：定位、女性上重量、不粗腿的搭配与进阶",
        "audience": "以臀为主要目标、想给臀部上重量的训练者（凯圣王素材以女性视角展开，男性同样适用）",
        "non_audience": "腰椎有未评估问题者先评估；腘绳肌柔韧性不足者先练髋屈活动度",
        "body": (
            "1) 定位：臀冲是练臀绕不过去的动作、能加很大重量（凯圣王安排示例：做三组十次）；"
            "女性增肌时下肢受体多于上肢，臀的力量容易比很多男性大——臀冲是很多女性训练的主项。\n"
            "2) 想练臀不想粗腿（凯圣王）：硬拉、外展动作、垫上单独刺激的训练收益比深蹲高；"
            "深蹲可以做，但不能占所有训练的 70%~80% 以上。\n"
            "3) 女性上重量（凯圣王）：哈克深蹲、罗马尼亚硬拉、臀冲深蹲是可以上重量的动作；"
            "前期不推荐上重量——蹲的重量大，就算以髋屈为主导，股四头肌肯定也会发展。\n"
            "4) 进阶路径：随着髋伸功能增加逐步进阶——加负重（放哑铃）、做单腿臀桥，"
            "或用杠铃做杠铃臀推，强化髋伸肌群。\n"
            "5) 小技巧：主动收紧大腿的小收缩（脚不动但大腿有往外转的感觉），"
            "在做臀冲或宽站距哈克时最后都可以用。"),
        "limits": ("6 条绑定全部来自凯圣王（BV1we4y1J72N×2/BV14dGX6fEhq×2/BV1s44y1q7vt/"
                   "BV17Lp9zHELA），发言者均已确认。“女性练臀”为博主经验口径，"
                   "性别差异表述不构成生理结论；上重量节奏按个人恢复调整。"
                   "周期相关（卵泡期容量训练）条目涉医疗敏感，本批未纳入。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1we4y1J72N-0034", "ksw-BV1we4y1J72N-0046",
            "ksw-BV14dGX6fEhq-0035", "ksw-BV14dGX6fEhq-0036",
            "ksw-BV1s44y1q7vt-0028-w0", "ksw-BV17Lp9zHELA-0019"],
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
            "notes": "Q20/Q21 后批：重挂后 rear_delt_fly 素材最厚；"
                     "machine_chest_press 因素材薄且与 pec_deck 卡重叠放弃",
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
        {"id": "Q22",
         "question": "本批 4 张卡（反飞鸟/器械推肩/斜板支撑划船/臀冲）请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：反飞鸟是俯身飞鸟重挂后素材最厚的动作（20 条），"
                           "其余三张 6-8 条绑定全部 speaker 已确认、无 FLAGGED、无隔离、映射一致。",
         "uncertain": "臀冲卡含“女性下肢受体多于上肢”等博主经验口径的性别表述，"
                      "已在 limits 注明不构成生理结论；器械推肩卡保留“容错率太高也有不安全因素”"
                      "的博主安全提醒。周期相关（卵泡期）条目涉医疗敏感，本批未纳入。",
         "evidence": "cards 文件 + claims 40 条"},
    ]
    history = old.get("answered_history", [])
    history += [
        {"id": "Q20",
         "question": "本批 5 张卡（T杠深蹲/仰卧哑铃外旋/坐姿腿屈伸/哑铃夹胸/跪姿龙门架卷腹）逐卡 通过/退回/暂不使用",
         "answered": "通过（发起人 2026-10-11 对话原话「q20通过」）——5 卡均 approved_v1；"
                     "批准前复验 55 条绑定指纹一致、引文命中、无隔离、无 FLAGGED、映射一致；"
                     "运行时服务卡 42→47",
         "answered_at": NOW},
        {"id": "Q21",
         "question": "地面卷腹 5 条解除 cable_crunch 错挂后，是否建库 crunch（地面卷腹，自重）",
         "answered": "建库（发起人 2026-10-11 对话原话「q21建库」）——exercises/crunch.yaml 已建"
                     "（draft，joint_stress pending；命名避开单用“卷腹”防与绳索卷腹归一混淆），"
                     "5 条 claims 已重挂 crunch；动作库 66→67，validate 通过",
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
    queue["awaiting"] = "4 张卡待逐卡签核（Q22）"
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：4 卡 + 1 问（Q22）；Q20/Q21 已记入 answered_history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
