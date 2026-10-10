"""一次性：P1 之后槽位替换批 2——5 张动作卡（2026-10-10）。

dumbbell_row / cable_pushdown / hanging_leg_raise / cable_fly / cable_lateral_raise：
按周计划覆盖与互补选片（背/三头/核心/胸-绳索/肩-绳索），素材全部来自已确认发言者。
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
        "card_id": "card-action-dumbbell_row",
        "scene": "哑铃划船：摆法、启动顺序、小臂肘的关系与常见错误",
        "audience": "想练背阔、能单手持哑铃维持躯干稳定的训练者",
        "non_audience": "俯身时腰酸、启动顺序纠正不过来者先降重量或换成固定轨迹划船",
        "body": (
            "1) 摆法：重心放在脚中间、正常屈髋（像打篮球累了休息的姿势），"
            "把背挺直、手放松，手与膝盖保持一到两拳宽；哑铃位于肩的里侧而不是垂直对肩——"
            "不要放在身体前方去划，离髋关节远、力臂长，腰压会变大。\n"
            "2) 启动顺序：先收紧背阔再划——肩胛内收带动，大臂向上、肘向上，"
            "肩跟肘同时向后；不是先启动腰、甩着上；背阔没感觉时，"
            "可以先做“提前收紧背阔”的固定技巧再划。\n"
            "3) 小臂与肘的关系：小臂找“被打断”的放松状态，负重通过小臂向上传递；"
            "肘屈带长二头酸、肘伸带长三头酸——用小杠铃可以解决这个问题；"
            "大臂向后伸靠背去保持，三头要放松。\n"
            "4) 常见错误：背没有收紧时肘关节可以无限向上，肩膀开始旋前、"
            "肩胛被拉上去、上斜方收紧，背阔被拉长成放松状态；"
            "后背没有变化只是把手往上提；以肩关节为支点大臂无限后伸、肘向外打开。\n"
            "5) 下放与幅度：想象把肩胛推开、靠背阔放下去——力量停在背上，不能停在腰上；"
            "离心的最大幅度是肩胛全打开的幅度；没有腰部不适可以适当抬头、加一点挺胸，"
            "背阔会收得更紧。"),
        "limits": ("24 条绑定全部来自凯圣王（BV1MG4y1G76W/BV1ij411H773/BV1vHa36zERC/"
                   "BV1rya86iEVE），发言者均已确认。“一组 15 次做完躺到垫子上”出自家庭课"
                   "衔接语境。全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1MG4y1G76W-0006", "ksw-BV1MG4y1G76W-0007", "ksw-BV1MG4y1G76W-0008",
            "ksw-BV1MG4y1G76W-0009", "ksw-BV1MG4y1G76W-0010", "ksw-BV1MG4y1G76W-0011",
            "ksw-BV1MG4y1G76W-0014",
            "ksw-BV1ij411H773-0002", "ksw-BV1ij411H773-0003", "ksw-BV1ij411H773-0004",
            "ksw-BV1ij411H773-0005", "ksw-BV1ij411H773-0006", "ksw-BV1ij411H773-0007",
            "ksw-BV1ij411H773-0009", "ksw-BV1ij411H773-0010", "ksw-BV1ij411H773-0011",
            "ksw-BV1ij411H773-0014", "ksw-BV1ij411H773-0015", "ksw-BV1ij411H773-0016",
            "ksw-BV1ij411H773-0017",
            "ksw-BV1vHa36zERC-0001", "ksw-BV1vHa36zERC-0010",
            "ksw-BV1rya86iEVE-0015"],
    },
    {
        "card_id": "card-action-cable_pushdown",
        "scene": "绳索下压：基本做法与顶峰收缩、直臂变式、新手保护",
        "audience": "想练三头、健身房有龙门架/绳索的训练者",
        "non_audience": "三头不够发达前别把肘关节角度弄得过小（凯圣王：会肘不适）；肘关节未评估问题者",
        "body": (
            "1) 基本做法（凯圣王，新手向）：正面对架子，把肩胛沉住、沉肩，"
            "不要下压时耸肩或用腰带力；身体向前微倾、上去时稍回——贴太近肘关节角度会很小；"
            "先让小臂动、做肘关节伸，固定住大臂；轨迹不是直直向下压，"
            "而是画一个半圆往后走，往下压会感到肘部不适。\n"
            "2) 顶峰收缩（谭成义）：绳索调到最高位、单手握住，先保证肩伸的位置再做臂屈伸；"
            "这个动作必须做顶峰收缩——推胸推直了张力会松，但它要锁死；"
            "记住十个字：夹肘、抬高、锁死、停顿、尺偏；"
            "手腕在伸直时稍微向内做尺偏，三头会收得更紧；回去时肩不要动、大臂收紧。\n"
            "3) 直臂变式（谭成义三头课的直杆动作）：大臂夹着身体，"
            "想象把杆掰弯、虎口发力；不用刻意内旋——过度内旋长头参与不好、"
            "锁骨处还会出现挤压；伸直时吸气维持胸腔稳定，把锁骨稳住再用力伸直；"
            "往上放时大臂不能往前跑。\n"
            "4) 新手保护：三头没有足够发达、不能产生很大压力之前，"
            "不要上来就模仿高手把肘关节角度变得很小。\n"
            "5) 衔接安排：三头动作做完不休息，直接接二头动作形成超级组"
            "（具体见坐姿龙门架弯举卡）。"),
        "limits": ("12 条绑定：谭成义 6 条（BV1hyWwzeETh/BV14JBHBYEMp“手臂跟练”，"
                   "直臂下压为该课三头第三个动作的直杆变式）＋凯圣王 6 条"
                   "（BV14v4y1G7A3 新手计划语境），发言者均已确认。"
                   "“十个字/尺偏”为博主教学口诀，不是解剖学结论。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1hyWwzeETh-0004", "tcy-BV1hyWwzeETh-0005",
            "tcy-BV14JBHBYEMp-0013", "tcy-BV14JBHBYEMp-0014",
            "tcy-BV14JBHBYEMp-0015", "tcy-BV14JBHBYEMp-0016",
            "ksw-BV14v4y1G7A3-0022-w1500", "ksw-BV14v4y1G7A3-0023-w1500",
            "ksw-BV14v4y1G7A3-0024-w1500", "ksw-BV14v4y1G7A3-0025-w1500",
            "ksw-BV14v4y1G7A3-0026-w1500", "ksw-BV14v4y1G7A3-0027-w1500"],
    },
    {
        "card_id": "card-action-hanging_leg_raise",
        "scene": "悬垂举腿：核心先撑住、幅度、退阶与变式",
        "audience": "想练腹、能悬垂（单杠或悬挂带）且肩稳定者",
        "non_audience": "沉不住肩、肋骨压不住者先用辅助带或绳索托臂；肩袖有未评估问题者",
        "body": (
            "1) 核心先撑住：身体悬着时如果腹肌是软的，更多是髋屈肌在发力——"
            "先把身体撑起来（肘撑起来、手伸直），让腹肌预先收缩并持续发力，再去抬腿。\n"
            "2) 幅度与质量：下落不要下到底，尽量下少一点、抬得高一点；"
            "上肢始终撑住不要降下去，否则腹肌会软掉；要卷高、把腹收得超级紧，"
            "不是单纯抬腿。\n"
            "3) 变式：可以加一点旋转，增强腹内外斜肌刺激；"
            "身体歪一点做，练的是腹外斜肌。\n"
            "4) 器械与退阶：不建议直接用手抓着杆做——压不住肋骨、沉不住肩，"
            "抬腿就变成练屈髋肌；推荐用悬垂举腿辅助带更好感受核心；"
            "没有器械时用绳索把大臂托在身体上撑着做，尽量别手抓杆。\n"
            "5) 安排参考（凯圣王一般腹部原则）：腹可以天天做，"
            "每次练完固定做一些、不必单独拿一天；腹是高耐力肌群，强度不用太大，坚持即可。"),
        "limits": ("15 条绑定：谭成义 14 条（BV1Ehn7zmEHN/BV1W1BFBKEdR/BV177yUB3E3B）"
                   "＋凯圣王 1 条一般腹部原则（BV1s44y1q7vt），发言者均已确认。"
                   "合作视频里粗人关于“潜水瓶核心进阶”的说法与本动作技术无关，未纳入。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1Ehn7zmEHN-0009", "tcy-BV1Ehn7zmEHN-0010",
            "tcy-BV1Ehn7zmEHN-0011", "tcy-BV1Ehn7zmEHN-0012",
            "tcy-BV1W1BFBKEdR-0012", "tcy-BV1W1BFBKEdR-0014", "tcy-BV1W1BFBKEdR-0015",
            "tcy-BV177yUB3E3B-0013", "tcy-BV177yUB3E3B-0014", "tcy-BV177yUB3E3B-0015",
            "tcy-BV177yUB3E3B-0016", "tcy-BV177yUB3E3B-0019",
            "ksw-BV1s44y1q7vt-0030-w0"],
    },
    {
        "card_id": "card-action-cable_fly",
        "scene": "龙门架/绳索夹胸：夹的方向、肘与手、变式与组次",
        "audience": "想练胸大肌外延/中缝、健身房有龙门架的训练者",
        "non_audience": "肩不舒服时先减小幅度；身体前移、含胸去夹者先改姿势",
        "body": (
            "1) 方向：往大腿根（腹股沟）方向去夹，不要往前夹——"
            "往前夹动作就变成类似含胸臂屈伸（双杠模式）；挺胸做，甚至可以开点肋，"
            "但身体不要往前移。\n"
            "2) 肘与手：不要靠手去靠近，要肘伸直去夹、把下胸充分激活；"
            "锁死时不要往前锁，贴着大腿做；头保持位置，一放就往前伸会练不到。\n"
            "3) 握法与姿势：完全正手握，吸一口气、保持挺胸、头向后伸、低下巴。\n"
            "4) 变式与侧重：上斜龙门架夹胸可以平替上斜固定夹胸器械，偏上半程，"
            "目的是先激活上胸；绳索夹下胸做外延训练——正常往里收缩更多练内侧，"
            "想练外侧需要改变角度往外延夹。\n"
            "5) 组次参考：龙门架夹胸 4 组、12~15 次；夹下胸 4 组、15~20 次；"
            "激活组不要上重量，选感受最强的重量做高次数。"),
        "limits": ("18 条绑定：谭成义 17 条（BV1fa6CBDEEu/BV1EdxhziEkb）＋陈石 1 条"
                   "（一周十组容量分配举例含绳索夹胸 3 组，BV1gzNZ68EUd），"
                   "发言者均已确认。坐姿固定器械夹胸的内容属 pec_deck 卡，不在本卡。"
                   "全部为博主经验（陈石那条为方法举例）；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1fa6CBDEEu-0017-w0", "tcy-BV1fa6CBDEEu-0018-w0",
            "tcy-BV1fa6CBDEEu-0020-w0", "tcy-BV1fa6CBDEEu-0021-w0",
            "tcy-BV1fa6CBDEEu-0022-w0", "tcy-BV1fa6CBDEEu-0023-w0",
            "tcy-BV1fa6CBDEEu-0002-w1500", "tcy-BV1fa6CBDEEu-0003-w1500",
            "tcy-BV1fa6CBDEEu-0004-w1500", "tcy-BV1fa6CBDEEu-0005-w1500",
            "tcy-BV1fa6CBDEEu-0007-w1500", "tcy-BV1fa6CBDEEu-0008-w1500",
            "tcy-BV1fa6CBDEEu-0009-w1500",
            "tcy-BV1EdxhziEkb-0008", "tcy-BV1EdxhziEkb-0009",
            "tcy-BV1EdxhziEkb-0011", "tcy-BV1EdxhziEkb-0012",
            "cs-BV1gzNZ68EUd-0004"],
    },
    {
        "card_id": "card-action-cable_lateral_raise",
        "scene": "滑轮侧平举：站位与滑轮高度、轨迹、外旋受限调整",
        "audience": "想深入刺激三角肌中束、健身房有龙门架的健身者；推举后收尾",
        "non_audience": "肩有撞击感/疼痛者先减小幅度并评估；外旋受限者按正文调低滑轮",
        "body": (
            "1) 站位与滑轮：滑轮高度调到下胸位置，握把攥在靠后的位置（攥前端容易脱手）；"
            "站在滑轮后方约半步——不要与滑轮完全平行站立，否则顶峰收缩时绳索与大臂重叠、"
            "失去抗阻；站在后方时身体向另一侧转约 30~35 度。\n"
            "2) 轨迹：不是完全平着，而是略微朝斜上方；启动时不要借力、不要动身体、"
            "不要屈肘，直接用三角肌把重量顶起来；手的运动轨迹与绳索完全一致；"
            "幅度不要做到大臂与绳索重叠的状态，停留在肩胛面——具体幅度取决于自身活动度。\n"
            "3) 安全边界：外旋位做水平外展、角度过大时，肱骨大结节后方与后盂唇容易撞击，"
            "而那个位置正是冈下肌止点；大臂外旋受限的话，把滑轮调到与髋关节同高即可。\n"
            "4) 节奏与强度：离心阶段也要控制，张力一直保持在三角肌上；"
            "选能做 12~16 次的重量，一组可以拆成两组——第一组 8~10 次（不到力竭）、"
            "完全放回休息 3~5 秒，再做 8~10 次；重量差一片时加小片微调。\n"
            "5) 安排：推荐在正式组、大强度动作（如推肩或推胸）之后收尾；"
            "刚开始训练或推举后没劲、需要更深入刺激中束的人也适合。"),
        "limits": ("16 条绑定全部来自凯圣王 BV1QR3E6qECQ（滑轮侧平举教学）"
                   "＋1 条肩胛后倾通则（BV1fjgC62EWN），发言者均已确认。"
                   "撞击风险为博主原话转述，不是医疗诊断；出现疼痛应停止并评估。"
                   "“外姿”为原视频标题用词。全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1QR3E6qECQ-0003", "ksw-BV1QR3E6qECQ-0004", "ksw-BV1QR3E6qECQ-0005",
            "ksw-BV1QR3E6qECQ-0006", "ksw-BV1QR3E6qECQ-0009", "ksw-BV1QR3E6qECQ-0010",
            "ksw-BV1QR3E6qECQ-0011", "ksw-BV1QR3E6qECQ-0012", "ksw-BV1QR3E6qECQ-0013",
            "ksw-BV1QR3E6qECQ-0014", "ksw-BV1QR3E6qECQ-0015", "ksw-BV1QR3E6qECQ-0016",
            "ksw-BV1QR3E6qECQ-0018", "ksw-BV1QR3E6qECQ-0019", "ksw-BV1QR3E6qECQ-0020",
            "ksw-BV1fjgC62EWN-0045-w1500"],
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
            "notes": "P1 之后槽位替换批 2：按周计划覆盖与互补选片",
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
        {"id": "Q16",
         "question": "本批 5 张卡（哑铃划船/绳索下压/悬垂举腿/龙门架夹胸/滑轮侧平举）请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：都是计划引擎槽位替换与周计划互补会用到的动作；绑定全部来自已确认发言者。",
         "uncertain": "绳索下压卡的“直臂下压”是谭成义三头课里的直杆变式（字幕原话“三头的第三个动作”），"
                      "与 lat 的直臂下压不是一回事，已在 limits 注明。",
         "evidence": "cards 文件 + claims 85 条"},
        {"id": "Q17",
         "question": "P1 槽位已覆盖完毕（除 weighted_pull_up 素材缺口）。下一批方向："
                     "①继续做素材充足的高频替换动作（leg_extension/hack_squat/dumbbell_fly/back_extension/hammer_curl/cable_crunch 等）；"
                     "②先补训练安排/营养恢复类卡（现有 4+4 张，主题可扩，如减脂平台期、应酬饮酒、停训复训）；"
                     "③暂停出卡，转去做 weighted_pull_up 缺口或 DESIGN §27 的 C0-C2。",
         "recommendation": "建议①：先把动作卡网络做厚，替换时教练有东西可讲；②③可以穿插。",
         "uncertain": "③里 C0-C2 是另一条工作线，本任务书范围外，你定优先级。",
         "evidence": "tools/triage_claims.py pool；claims 各动作统计"},
    ]
    queue = build_review_queue(
        [{"card_id": c["card_id"], "version": c["version"], "scene": c["scene"],
          "bindings": len(c["bindings"]), "purpose": c["purpose"],
          "status": c["status"]} for c in cards],
        questions, NOW)
    queue["cards_detail_ref"] = "sources/maintenance/cards/<card_id>.json"
    queue["mechanism_enabled"] = old.get("mechanism_enabled", True)
    queue["answered_history"] = old.get("answered_history", [])
    queue["awaiting"] = "5 张卡待逐卡签核（Q16）；Q17 下一批方向待定；Q15 待建动作仍未答"
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：5 卡 + 2 问（Q16/Q17）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
