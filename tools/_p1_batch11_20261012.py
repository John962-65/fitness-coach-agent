"""一次性：归属确认后解锁批——1 张动作卡 + 2 张主题卡（2026-10-12）。

back_extension 正向卡：发起人 2026-10-12 批量确认归属后素材凑齐（11 条）。
card-training-layoff-comeback / card-training-fat-loss-plateau：停训复训与减脂平台期主题
（Q19 登记的缺口，经 zcode 直提+归属确认后素材成立）。只产草稿，不批准。
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
        "card_id": "card-action-back_extension",
        "scene": "山羊挺身（正向）：定位、做法要点、无器械替代与边界",
        "audience": "想强化竖脊肌和下背、健身房有山羊挺身凳/罗马椅的训练者",
        "non_audience": "腰椎有未评估问题者先评估；孕期与急性腰痛者不做",
        "body": (
            "1) 定位（凯圣王）：山羊挺身练竖脊肌加后侧，改善下背问题；波浪式山羊挺身专门练竖脊肌"
            "——竖脊肌贯穿整个背部，强化它对脊柱健康非常重要（女性日常弯腰、抱重物，"
            "青少年脊柱健康同样需要）。\n"
            "2) 做法要点（凯圣王）：趴着双手向前伸直向上抬，一定要向正前方、不要坐着"
            "（坐着动作就打开了）；一定不要用爆发力，两边同时发力，"
            "最后竖脊肌和下背部会非常酸痛。\n"
            "3) 动作细节（谭成义）：不负重；膝盖微屈；上身保持一个整体；屈髋下放、"
            "角度不用太大；上半身松掉是常见错误——腰要保持紧。\n"
            "4) 无器械替代（谭成义）：趴在瑜伽垫上、让人按住脚，向上抬一样练竖脊肌。\n"
            "5) 边界（凯圣王）：通过山羊挺身或仰卧起坐很难练到深层小肌肉群——"
            "深层稳定与功能性训练是另一回事，本卡是竖脊肌主导的训练。"),
        "limits": ("10 条绑定：凯圣王 7 条（BV1MG4y1G76W/BV14dGX6fEhq/BV1FcdZBNEm3/"
                   "BV1xY411S747）＋谭成义 3 条（BV1Fzd2BBEdM 课程录播），归属均经发起人 "
                   "2026-10-12 确认；tcy-0261（FLAGGED）未纳入。反向（朝上练腹）用法在 reverse_back_extension 卡，"
                   "本卡只覆盖正向练竖脊肌（2026-10-12 拆分裁定）。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "is_action": True,
        "action_id": "back_extension",
        "claim_ids": [
            "ksw-BV1MG4y1G76W-0055", "ksw-BV1MG4y1G76W-0056",
            "ksw-BV14dGX6fEhq-0022", "ksw-BV14dGX6fEhq-0023",
            "ksw-0017", "ksw-0055", "ksw-BV1xY411S747-0049-w1500",
            "tcy-0258", "tcy-0259", "tcy-0260"],
    },
    {
        "card_id": "card-training-layoff-comeback",
        "scene": "停训与恢复训练：停训会掉什么、什么时候该主动停、恢复节奏",
        "audience": "因过节/出差/生活变故停训的人；减脂期练到状态变差需要主动停的人",
        "non_audience": "伤病停训遵医嘱；本卡不覆盖疾病相关停训",
        "body": (
            "1) 停训会掉什么（凯圣王，Q&A）：停训两周左右最多掉点肌浆，肌原纤维很难掉；"
            "回来训练一到两周就能恢复。\n"
            "2) 过节停训（凯圣王）：在家停训十几天没问题，主要别糟蹋身体、别熬夜；"
            "停训一两周后如果真的掉了肌肉，肯定是生活不规律或吃得不对，跟停训本身没关系。\n"
            "3) 恢复节奏（凯圣王）：恢复期至少安排两周以上把状态拉回来。\n"
            "4) 什么时候该主动停（陈石）：减脂一两个月后人变衰——营养不良让睡眠变差、"
            "免疫力变差、精力与日常消耗下降，减肥效果反而变差；这时应停下来休息约两周，"
            "好好吃饭把热量吃平衡（碳水、蛋白质、脂肪吃够、适当活动）；精力恢复后再减，"
            "消耗更高、状态更好——磨刀不误砍柴工。\n"
            "5) 节点因人而异（陈石）：休息节点不是每个人统一的；过度节食者"
            "（如每天约 1000 大卡）衰得更快，可能不到一个月就崩。"),
        "limits": ("8 条绑定：凯圣王 4 条（BV1tEkxBsE8M 过年停训 Q&A）＋陈石 4 条"
                   "（BV1S2Lq68EYD），归属经发起人 2026-10-12 确认。"
                   "“肌浆/肌原纤维”为博主通俗表述；伤病或疾病相关停训遵医嘱，安全红旗优先；"
                   "复训的具体计划由教练结合用户档案给，本卡是博主口径的原则。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1tEkxBsE8M-0001", "ksw-BV1tEkxBsE8M-0002",
            "ksw-BV1tEkxBsE8M-0003", "ksw-BV1tEkxBsE8M-0004",
            "cs-BV1S2Lq68EYD-0001", "cs-BV1S2Lq68EYD-0002",
            "cs-BV1S2Lq68EYD-0003", "cs-BV1S2Lq68EYD-0004"],
    },
    {
        "card_id": "card-training-fat-loss-plateau",
        "scene": "减脂平台期：机制口径、代谢受损信号、恶性循环与应对节奏",
        "audience": "减脂期体重长期不掉、怀疑平台期的训练者",
        "non_audience": "内分泌疾病或服用相关药物者先就医；本卡不构成医学判断",
        "body": (
            "1) 机制口径（谭成义）：减脂短期看热量缺口，长期看激素稳定——过度追求大缺口"
            "导致饮食结构混乱、激素水平下降，进而出现平台期；所有饮食、有氧、训练都要"
            "跟着状态走，状态不好去减脂非常容易出现平台期且很难减下去。\n"
            "2) 代谢受损信号（凯圣王）：吃得够少仍然减不下去，可能是代谢受损的信号——"
            "大脑的优先级是活下去，节食会让激素水平和脂肪储存能力提高。\n"
            "3) 恶性循环（凯圣王）：自述“吃得很注意、动得很多但减不下去”的人，"
            "“吃得很注意”往往就是吃得足够少——越减不下去越吃越少（吃不到 1000 大卡减不下去"
            "改 800、再减到 600 的滑坡）；缺碘会让代谢变慢又减不下去、再少吃最终把自己搞翻"
            "（博主经验：可考虑每周加几顿海带补碘）。\n"
            "4) 营养素（凯圣王）：减脂期最可怕的是只计算碳水、忽略营养素——到最后减不下去"
            "很可能就是营养素摄入不全、人没有状态；配餐要食物多样化，蛋白质、膳食纤维、"
            "维生素矿物质吃够（对血糖波动控制也有好处）。\n"
            "5) 应对节奏（凯圣王，个人做法）：以五斤为一个单位，减一段时间后设置一个平台期"
            "给力量做适应或提高，再继续往下；减脂速度要适度——一周约 0.5~1.5kg"
            "（大体重 1.5 可接受、小体重 0.25~0.5 都 OK），减太快有皮下脂肪断裂、皮肤松弛"
            "和健康代价，关注腰围维度和照片对比。\n"
            "6) 体重波动（凯圣王）：短期体重波动都是水分，跟脂肪没关系。"),
        "limits": ("13 条绑定：凯圣王 11 条（BV19eLAzDELv/BV1S4XhYgEwm/BV1Zp57zhEed/"
                   "BV1tBcaecEdy/BV1vzRGYTEPs）＋谭成义 2 条（BV1uuhV6YEGW），"
                   "归属经发起人 2026-10-12 确认。机制解释（激素/代谢/缺碘）为博主口径，"
                   "不构成医学诊断；“假平台期=皮质醇保水”一条 FLAGGED 未纳入；"
                   "力量加重停滞走训练进阶卡，本卡聚焦减脂停滞；0.5~1.5kg/周、五斤单位等"
                   "数字为博主口径。全部为博主经验或转述；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV19eLAzDELv-0002", "ksw-BV19eLAzDELv-0003",
            "ksw-BV1S4XhYgEwm-0001", "ksw-BV1S4XhYgEwm-0002", "ksw-BV1S4XhYgEwm-0003",
            "ksw-BV1Zp57zhEed-0001", "ksw-BV1Zp57zhEed-0002",
            "ksw-BV1tBcaecEdy-0001", "ksw-BV1tBcaecEdy-0002",
            "ksw-BV1vzRGYTEPs-0001", "ksw-BV1vzRGYTEPs-0002",
            "tcy-BV1uuhV6YEGW-0002", "tcy-BV1uuhV6YEGW-0036"],
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
        if spec.get("is_action"):
            expect = spec["action_id"]
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
            "notes": "归属确认（发起人 2026-10-12「确认」）后解锁批",
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
        {"id": "Q28",
         "question": "解锁批 3 张卡（山羊挺身正向/停训复训/减脂平台期）请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：32 条绑定全部为发起人 2026-10-12 确认归属的素材；"
                           "back_extension 正向卡是拆分裁定的收尾；两张主题卡兑现 Q19 缺口（减脂平台期/停训复训）。",
         "uncertain": "山羊挺身卡含谭成义“万金油”原话与凯圣王“练不到深层小肌群”的局限表述；"
                      "平台期卡的机制解释（激素/代谢/缺碘）为博主口径，limits 已注明不构成医学诊断；"
                      "组7（BV1aqsXeRE2B 5 条）因 Q9 已判非本人发言，维持不可引用未纳入。",
         "evidence": "cards 文件 + claims 32 条；speaker_confirmation_sheet_20261012.md"},
    ]
    history = old.get("answered_history", [])
    history += [
        {"id": "Q27",
         "question": "speaker 归属确认怎么排",
         "answered": "批量确认（发起人 2026-10-12 对话原话「确认」）——30 条落「凯圣王/谭成义（发起人 "
                     "2026-10-12 确认归属）」留痕；组7（BV1aqsXeRE2B 5 条）因 Q9 已判说话人非本人、"
                     "整批确认无法回答实际归属，维持不可引用（如需归属请指认对谈嘉宾）",
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
    queue["awaiting"] = "3 张卡待逐卡签核（Q28）；组7 归属维持不可引用"
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：3 卡 + 1 问（Q28）；Q27 已记入 answered_history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
