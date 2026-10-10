"""一次性：方向②训练/营养主题批——3 张主题卡（2026-10-11）。

Q17 发起人选方向②（先补训练安排/营养恢复类卡）。素材摸底：
有氧 77 条已确认 / 酒精 45 条 / 补剂 103 条 → 出 3 张；
减脂平台期仅 2 条、停训复训仅 1 条，不足以出卡（缺口提交 Q19）。
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
        "card_id": "card-training-cardio-basics",
        "scene": "有氧：定位、强度与频率、空腹有氧、与力量的关系",
        "audience": "想安排有氧但不确定强度/频率/与力量怎么搭配的训练者",
        "non_audience": "有医生限制运动强度者先遵医嘱；把有氧当唯一减脂手段者先看热量卡",
        "body": (
            "1) 定位（谭成义）：把有氧当成正式训练，而不是单纯的消耗——如果只是为了消耗，"
            "还不如少吃两口；做有氧的目的是更强的心肺功能和糖原合成能力，要带目的性、"
            "不断提高强度。凯圣王：新手进健身房先提高心肺功能，心肺是所有运动的基础。\n"
            "2) 强度——两种口径并列：谭成义推荐时间短、强度大的有氧（最推荐间歇跑），"
            "不建议时间长、强度低（效率太低、对力量帮助也小）；陈石按全天结算看："
            "中低强度有氧每 100 大卡约七八十大卡来自脂肪，但由此推出“只有中低强度有氧才减脂”"
            "是片面结论——同样卡路里消耗下，散步、高强度有氧、力量训练的减脂效果都差不多，"
            "别当二极管，按自己的目标和生活调节。陈石另提醒：高强度有氧可能升高压力和皮质醇，"
            "本身压力大的人需斟酌。\n"
            "3) 频率与时长参考：谭成义——一周 3 到 4 次、一次 30 到 40 分钟基本够用，"
            "做太多影响训练状态和增肌效率（一周 6-7 次每天都做容易疲劳、抗拒甚至崩盘），"
            "时间可固定、靠提高强度提效率（如从爬坡改爬楼）。陈石——以减内脏脂肪为目标，"
            "每周有氧量至少约 10 MET·h（如 10km/h 跑步每周 60 分钟以上）；每周 150 分钟时"
            "腰围和体脂改善明显；新手可选任意有氧、强度稍微有点喘，一周 100 到 150 分钟，"
            "做完若睡眠/免疫/心情/训练热情变差，可能训练过度，先适应当前量再进阶。\n"
            "4) 空腹有氧——两种口径并列：凯圣王——刚开始训练不建议空腹有氧（有低血糖风险），"
            "身体没问题可以把有氧放在早上空腹、效果更好；陈石——卡路里消耗一样时，"
            "空腹与不空腹全天燃脂效果是一样的。\n"
            "5) 与力量的关系：凯圣王——BMI 低但体脂高的人群（尤其女性）应做力量训练，"
            "而不是节食加大量有氧；谭成义——有氧提升线粒体能力，阻力训练与有氧结合"
            "线粒体整体能力才上升，对增肌减脂都更好；呼气/呼吸控制训练难以在力量中做，"
            "可放进中低强度有氧。"),
        "limits": ("23 条绑定：凯圣王 6 条＋谭成义 9 条＋陈石 8 条，发言者均已确认。"
                   "强度口径（谭成义短时大强度 vs 陈石同卡路里下形式不重要）与空腹口径"
                   "（凯圣王新手别空腹/陈石空腹不空腹一样）为条件性方法差异，并列保留、"
                   "以用户目标与感受为准，不评唯一赢家。陈石多条为视频转述研究结论，"
                   "未独立核验原研究；10 MET·h、150 分钟、3-4 次/30-40 分钟等数字为博主口径。"
                   "全部为博主经验或转述；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1we4y1J72N-0047", "ksw-BV1we4y1J72N-0048",
            "ksw-BV14v4y1G7A3-0001-w0", "ksw-BV14v4y1G7A3-0005-w0",
            "ksw-BV14v4y1G7A3-0030-w0", "ksw-BV14v4y1G7A3-0034-w0",
            "tcy-BV1RsigBkEUN-0001", "tcy-BV1RsigBkEUN-0002", "tcy-BV1RsigBkEUN-0003",
            "tcy-BV1RsigBkEUN-0005", "tcy-BV1RsigBkEUN-0008",
            "tcy-BV1uuhV6YEGW-0025", "tcy-BV1uuhV6YEGW-0026", "tcy-BV1uuhV6YEGW-0027",
            "tcy-BV1w53J6REfW-0021",
            "cs-BV174u86zEUf-0003", "cs-BV174u86zEUf-0007", "cs-BV174u86zEUf-0014",
            "cs-BV174u86zEUf-0015", "cs-BV174u86zEUf-0016",
            "cs-BV1CfMZ64ErB-0014", "cs-BV1DH3a6qEaV-0006", "cs-BV1DH3a6qEaV-0013"],
    },
    {
        "card_id": "card-nutrition-alcohol",
        "scene": "饮酒：总量与风险、对睡眠恢复的影响、应酬前的现实做法、依赖自测",
        "audience": "有应酬或饮酒习惯、想知道酒精对训练与恢复影响的成年人",
        "non_audience": "疑似酒精依赖者优先寻求专业帮助（见正文自测），本卡不替代；未成年人不适用",
        "body": (
            "1) 总量与风险（陈石，转述研究）：饮酒量越多健康风险越高，不存在“适量有益”的"
            "保护剂量；每天小于 1-2 标准杯全因死亡率无明显变化、但也没有保护作用，"
            "超过两杯后明显上升；女性约 25 克酒精（约两标准杯）风险就开始上升，男性约 45 克。"
            "约 30%-40% 的中国人存在 ALDH2 基因变异（喝酒容易脸红），乙醛清除能力弱。\n"
            "2) 中国人特别风险（陈石，转述研究）：纳入遗传因素后，饮酒量与中风风险呈线性关系"
            "（每周多 280 克酒精、中风风险上升约 28%），脑出血概率上升约 58%——"
            "转述数字未核验原研究，供理解量级用。\n"
            "3) 对睡眠与恢复——两种口径并列：共同点是酒精破坏睡眠结构、减少 REM"
            "（快速眼动期，与动作细节的程序记忆整合相关）、剂量越大影响越深。"
            "凯圣王口径：酒精不影响入睡甚至更快入睡，但会大范围减少深睡眠；"
            "陈石转述的研究口径：连续三天睡前饮酒上半夜深睡眠增多、下半夜减少，"
            "总体深睡眠时间没变。凯圣王建议：睡前尽量不饮酒，小酌怡情、聚会喝酒没问题，"
            "天天自己灌自己没必要且影响训练；睡前大量碳水或酒精都可能影响深睡眠。\n"
            "4) 应酬前的现实做法（陈石）：目标只是降低体内酒精浓度峰值——喝酒前先吃东西"
            "是最有效的办法（研究中约 700 大卡的正餐可降峰值约 50%，未核验），"
            "空腹饮酒峰值非常高、不可取；饮酒前和饮酒当时不要喝碳酸饮料"
            "（二氧化碳加快胃排空、吸收更快、更容易断片）。注意：这些办法只降峰值、"
            "不减少进入身体的酒精总量，长期伤害不会因此减少。\n"
            "5) 依赖自测（陈石）：过去 12 个月中酒精使用障碍（AUD）11 条自测条目符合超过 2 条，"
            "可能已经不是单纯喝酒的问题，应寻求专业心理支持。"),
        "limits": ("20 条绑定：陈石 17 条＋凯圣王 3 条，发言者均已确认。"
                   "多条为视频转述研究结论，精确数字（1-2 标准杯、25/45 克、280 克、"
                   "0.35/0.5 克每公斤、约 700 大卡降 50% 等）未独立核验原研究，"
                   "同 K-A03 关注点，仅供理解量级。健康风险内容不构成医疗建议，"
                   "安全红旗与医生意见优先；与睡眠恢复卡的边界：睡眠机制详见该卡，"
                   "本卡聚焦饮酒本身。cs-BV11QFbzgE2S-0009（FLAGGED）未纳入。"
                   "全部为博主经验或转述；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "cs-BV11QFbzgE2S-0001", "cs-BV11QFbzgE2S-0004", "cs-BV11QFbzgE2S-0005",
            "cs-BV11QFbzgE2S-0006", "cs-BV11QFbzgE2S-0007", "cs-BV11QFbzgE2S-0008",
            "cs-BV1u4NS6iEs4-0009", "cs-BV1u4NS6iEs4-0010", "cs-BV1u4NS6iEs4-0011",
            "cs-BV1u4NS6iEs4-0012", "cs-BV1u4NS6iEs4-0014",
            "cs-BV1ffcHzLEib-0005", "cs-BV1ffcHzLEib-0006", "cs-BV1ffcHzLEib-0007",
            "cs-BV1ffcHzLEib-0014", "cs-BV1M9ZuBnE17-0005", "cs-BV1ZRF1zGEZU-0001",
            "ksw-BV1rRSKBCE5p-0014", "ksw-BV1rRSKBCE5p-0023", "ksw-BV14ys4zeEVJ-0023"],
    },
    {
        "card_id": "card-nutrition-supplements",
        "scene": "补剂：定位、肌酸（剂量/时机分歧）、鱼油与镁、不要本末倒置",
        "audience": "想理性看待补剂、不确定吃什么/怎么吃的训练者",
        "non_audience": "期待补剂替代饮食与睡眠者（本卡明确反对）；有肾病等医疗限制者先遵医嘱",
        "body": (
            "1) 定位（凯圣王）：补剂是“补充”，不是大补或增强剂——先把饮食吃满"
            "（碳水、蛋白质、脂肪、水、维生素、矿物质、膳食纤维），补剂只用于弥补"
            "日常照顾不到的营养素；食物能代替的优先选食物。谭成义：复合维生素是基础补剂，"
            "不锻炼的人也需要，矿物质不够状态就不好。\n"
            "2) 肌酸（三家都讲，剂量与时机口径并列）：陈石——肌酸在增肌增力、改善恢复、"
            "运动表现乃至认知方面循证基础扎实，堪称运动补剂第一，女性可能更需要；"
            "把脱发、失眠、长痘直接归因肌酸属于错误归因（要先排除其他变量），"
            "“吃肌酸一定要狂喝水”是经典谣言。凯圣王——如果只推荐一个补剂就是肌酸，"
            "放在练后高碳水那一餐吃（练前吃没用，它不是快效的东西）。谭成义——"
            "训练日每天 3 克、饭后吃。剂量与时机三家口径不一，按自身情况选择，不裁定优劣。\n"
            "3) 鱼油与矿物质（谭成义/凯圣王）：谭成义——鱼油是必需脂肪酸，选有 IFOS 认证"
            "或大牌子；钙每天 300~600 毫克、镁 200~300 毫克（博主自述剂量）。凯圣王——"
            "不常吃深海鱼的人鱼油可能是必备，可做营养素筛查、缺什么补什么，"
            "每周定期吃一次动物内脏补充脂溶性维生素；鱼油、甘氨酸镁放练后第二餐、"
            "要配碳水吃；缺镁等影响睡眠时，能通过食物补充就不动用补剂。\n"
            "4) 不要本末倒置：凯圣王——调整皮质醇最重要的一步是睡眠，改善睡眠比任何补剂"
            "都重要且便宜；谭成义——不要一上来就吃褪黑素等补剂，先通过呼吸、作息、光线"
            "把身体自我调控能力调好，不行再适当补充。\n"
            "5) 个人经验条目（谭成义）：自己一直在吃的是肌酸、谷氨酰胺和钙镁片——"
            "注意这是个人经验，谷氨酰胺的循证依据未出现在素材中。"),
        "limits": ("18 条绑定：凯圣王 7 条＋谭成义 7 条＋陈石 4 条，发言者均已确认。"
                   "剂量（肌酸 3 克/天、钙 300~600 毫克、镁 200~300 毫克）为博主原话，"
                   "未与权威推荐量核对；肌酸时机（凯圣王练后高碳水餐 vs 谭成义每天饭后）"
                   "口径并列保留。咖啡因半衰期条目在隔离区（K-A03）未纳入；"
                   "cs-BV1icM86YEif-0001（FLAGGED）未纳入。全部为博主经验或转述；"
                   "applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1RTq6B8ED7-0035", "ksw-BV1RTq6B8ED7-0036", "ksw-BV1RTq6B8ED7-0026",
            "ksw-BV1RTq6B8ED7-0027", "ksw-BV1RTq6B8ED7-0020",
            "ksw-BV1rRSKBCE5p-0017", "ksw-BV14ys4zeEVJ-0021",
            "tcy-BV1cTSsBbEJy-0030", "tcy-BV1cTSsBbEJy-0036", "tcy-BV1cTSsBbEJy-0037",
            "tcy-BV1cTSsBbEJy-0039", "tcy-BV1cTSsBbEJy-0040",
            "tcy-BV1q4UwBpE2i-0076", "tcy-BV1w53J6REfW-0022",
            "cs-BV1icM86YEif-0002", "cs-BV1icM86YEif-0005",
            "cs-BV1niKQ6wEB2-0001", "cs-BV1niKQ6wEB2-0002"],
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
            "notes": "Q17 方向②（发起人 2026-10-11）训练/营养主题批；"
                     "口径分歧一律并列保留（发起人 2026-10-08 规则）",
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
        {"id": "Q18",
         "question": "方向②首批 3 张主题卡（有氧/饮酒/补剂）请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：素材量三家都充足（有氧 77/酒精 45/补剂 103 条已确认），"
                           "绑定 61 条全部 speaker 已确认、无 FLAGGED、无隔离条目；"
                           "口径分歧（有氧强度与空腹、深睡眠影响、肌酸剂量时机）已按并列保留规则呈现。",
         "uncertain": "酒精卡含较多转述研究的精确数字（中风+28%/脑出血+58%/0.35g/kg 等），"
                      "与被隔离的咖啡因条目同类（K-A03 关注点），已在 limits 注明“未核验原研究、"
                      "供理解量级”；若你觉得不稳，可退回改为只保留定性表述。",
         "evidence": "cards 文件 + claims 61 条；隔离区 14 条已核对未纳入"},
        {"id": "Q19",
         "question": "方向②摸底发现两个主题素材不足：减脂平台期仅 2 条、停训复训仅 1 条（且讲的是"
                     "姨妈停训场景）。处置：①登记为采集缺口，等后续视频素材攒够再出卡；"
                     "②接受长期缺口（这两问走通用知识层/教练判断，不出博主卡）。",
         "recommendation": "建议①：平台期是高频问题，值得等素材；停训复训可①②并用。",
         "uncertain": "知识库 80_troubleshooting 已有通用平台期/停训复训文件（provenance: general，"
                      "不点名博主），运行时 L2/L3 仍可回答，只是没有“已审核教练卡”级别的内容。",
         "evidence": "claims 全文检索：平台期 2 条（tcy-BV1uuhV6YEGW）、停训 1 条（cs）"},
    ]
    history = old.get("answered_history", [])
    history += [
        {"id": "Q15",
         "question": "t_bar_squat / lying_db_external_rotation 两个待建动作是否批准建库",
         "answered": "登记（发起人 2026-10-11 对话原话「q15登记啊继续」）——两动作已建库"
                     "（draft，joint_stress pending，占位值并 provenance 标注 pending）；"
                     "13 条错挂解除后的 claims 重挂新 id（ksw 6 条→t_bar_squat、tcy 7 条→"
                     "lying_db_external_rotation），并清除重复键残行；动作库 64→66，validate 通过",
         "answered_at": NOW},
        {"id": "Q16",
         "question": "本批 5 张卡（哑铃划船/绳索下压/悬垂举腿/龙门架夹胸/滑轮侧平举）逐卡 通过/退回/暂不使用",
         "answered": "通过（发起人 2026-10-11 对话原话「q16通过」）——5 卡均 approved_v1；"
                     "批准前复验：23+12+13+18+16 共 82 条绑定指纹与 claims 现状一致、"
                     "引文命中原文、无隔离条目；运行时服务卡 34→39，全库 39 张全部审批有效",
         "answered_at": NOW},
        {"id": "Q17",
         "question": "下一批方向：①高频替换动作卡 ②训练安排/营养恢复卡 ③暂停出卡",
         "answered": "方向②（发起人 2026-10-11 对话原话「q17选择方向2」）——本批即按方向②产出"
                     "3 张主题卡（Q18）；减脂平台期/停训复训素材不足的处置见 Q19",
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
    queue["awaiting"] = "3 张主题卡待逐卡签核（Q18）；Q19 平台期/停训复训素材缺口的处置待定"
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：3 卡 + 2 问（Q18/Q19）；Q15/Q16/Q17 已记入 answered_history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
