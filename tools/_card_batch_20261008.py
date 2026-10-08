"""一次性：准备 2026-10-08 待审核心卡批次（3 张动作卡 + 3 个待决问题）。

正文由本次对话逐条对照 claims 手工撰写；本脚本只负责绑定证据（内容指纹、
字幕原文节选、跳转链接）、结构校验、隔离检查与落盘。不写 review 字段、
不批准任何内容：批准只能通过 tools/card_review.py --approve --by 发起人。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coach.cards import (assert_not_quarantined, build_review_queue, load_cards,
                         load_quarantined, validate_card)
from coach.claim_review import content_fingerprint, source_issues

MAINT = ROOT / "sources" / "maintenance"
TRANSCRIPTS = ROOT / "sources" / "transcripts"

NOW = datetime.now().astimezone().isoformat(timespec="seconds")

CARDS = [
    {
        "card_id": "card-action-dumbbell_shoulder_press",
        "version": 1,
        "scene": "新手学坐姿哑铃推肩：推的平面、行程和握法怎么定",
        "audience": "以增肌/形体为目标的健身房或居家训练者，肩部无急性疼痛",
        "non_audience": "肩部急性疼痛、未评估的活动度受限者；以实力举/奥举为专项者（口径不同）",
        "body": (
            "1) 推的平面：刚开始训练的人活动度不足，不建议在冠状面（身体正侧面）推，"
            "改在肩胛面推，可减少肩峰下卡压与不适。\n"
            "2) 行程：不必追求手臂推到完全垂直——完全垂直时阻力臂最大、动作很难，"
            "稍微往里一点点，行程相对更合适。\n"
            "3) 握法：保持对握，不要正手握；核心不好或肩关节能力不够时，"
            "正握很难练到目标且压力非常大。\n"
            "4) 学习顺序：先从坐姿哑铃推举入手，会了哑铃就会杠铃；坐姿推肩属形体/"
            "健美体系，站姿杠铃实力举属奥举体系。\n"
            "5) 与侧平举的关系：两者不是单选题（一个上升阻力一个下降阻力，一个复合"
            "一个更孤立）；推举能上大重量，但全是大强度动作容易神经疲劳，"
            "可在推举后用侧平举、面拉定向刺激并分配疲劳。"),
        "limits": (
            "全部为博主经验（blogger_experience），无研究出处；对握优于正握、"
            "肩胛面推是两位博主各自的主张，未做跨博主对照。原视频中他人"
            "肩部积液的个案条目（ksw-BV1W2ga6xEBC-0028）属医疗情况，"
            "未纳入正文；肩部疼痛加重、无力或麻木应先停止并另行评估。"),
        "notes": "谭成义 tcy-BV1LqJCz1EcE-0016（南瓜肩/前束效果好）属营销性表述，未纳入正文",
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1W2ga6xEBC-0006", "ksw-BV1fUBDBKEYH-0015", "tcy-BV1LqJCz1EcE-0013",
            "ksw-BV1W2ga6xEBC-0002", "ksw-BV1W2ga6xEBC-0026", "ksw-BV1W2ga6xEBC-0027",
            "ksw-BV1W2ga6xEBC-0001"],
    },
    {
        "card_id": "card-action-lateral_raise",
        "version": 1,
        "scene": "哑铃侧平举的重量、位置与幅度怎么选",
        "audience": "想把三角肌中束练大的训练者，肩部无急性疼痛",
        "non_audience": "急性肩痛、肩袖损伤未评估者；只做推举不安排孤立项的新手（非必需）",
        "body": (
            "1) 阻力特性：侧平举是上升阻力、需要更多稳定肌群参与，对新手比坐姿推举"
            "难学；两者模式不同、不是单选题，想把肩练大都有必要。\n"
            "2) 负荷：刚开始以激活为主，重量轻一点，不要太重——该重的时候重、"
            "该轻的时候轻。\n"
            "3) 安排位置：可放在推肩、推胸等大强度动作之后，用来定向刺激三角肌中束"
            "并分配疲劳。\n"
            "4) 幅度与角度（仅在无急性疼痛的前提下）：抬到当前不痛的位置即可，"
            "能力好可以更高；内旋抬肩容易撞肩、疼或弹响，就在能做的幅度上做，"
            "有效幅度会逐步变大；出现弹响或不适时可稍微外旋一点、不要下到底。"),
        "limits": (
            "第 4 点全部来自博主经验且以“肩膀疼/弹响”为语境，不构成对疼痛病因的判断："
            "本项目安全红旗（急症、胸痛、无力、麻木等）优先于本卡，疼痛加重时应停止"
            "该动作而不是缩小幅度继续练。两位博主对“疼痛时是否继续做该动作”没有"
            "一致口径：凯圣王的侧平举条目只讲负荷与安排，未讲疼痛处理。本次只核对了"
            "字幕与条目一致性，未回看原片确认这三条的现场语境（谁在什么前提下回答），"
            "若要上线为教学卡，需要你确认这个前提。"),
        "notes": "本卡 7 条绑定中 4 条带 condition=肩痛/肩弹响，均为字幕一致性证据，未做画面终核",
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1W2ga6xEBC-0001", "ksw-BV1W2ga6xEBC-0026", "ksw-BV1W2ga6xEBC-0027",
            "tcy-BV1aC2ZBwEHC-0019", "tcy-BV1q4UwBpE2i-0061", "tcy-BV1q4UwBpE2i-0064",
            "tcy-BV1utntzhE9a-0001"],
    },
    {
        "card_id": "card-action-dips",
        "version": 1,
        "scene": "双杠臂屈伸：两种做法怎么选，以及下放深度与手腕的边界",
        "audience": "能自重完成多次数双杠、想练下胸/三头或卧推辅助项的训练者",
        "non_audience": "肩肘腕有不适或基本功不足者；无法完成自重次数者（先退阶）；"
                        "腕部伤病史未评估者",
        "body": (
            "1) 先分清两种做法：含胸前倾（肘向两侧打开再向里夹、顶峰把肩胛完全推出去）"
            "偏下胸与前锯；中立位夹肘（肘贴身体往后走，像自重窄推）偏三头，"
            "是举重/力量举的俯向做法。练胸可先做下胸再平推或上斜，顺序从下往上。\n"
            "2) 练胸做法的要点：胸椎屈曲、膝盖在髋关节前方、身体有前倾角度；"
            "想象手臂向两侧打开再向内夹，下放吸气、上推呼气收紧。原因是胸大肌主要"
            "功能是水平内收，夹肘向后就把“水平外展→水平内收”的模式丢了。\n"
            "3) 两种做法都保留，按你自己的感受选：凯圣王给新手的是含胸前倾那套（他"
            "口中的「第一种」），谭成义更推荐中立位那套并认为含胸关节压力更大（他口中"
            "的「第一种」指中立位）——两人术语指向相反，不需要替谁裁定；哪套练下来"
            "胸的感受好、肩肘腕没有不适，就用哪套。\n"
            "4) 下放深度与安全：夹肘且胸中立位时下放过深对肩的压力极大；"
            "下放深度以“没有不适”为止。以肩胛状态为准——如果下放一点肩胛就被拉到"
            "前面，说明基本功不够，先在安全舒适的幅度完成。\n"
            "5) 手腕与热身：握法压在掌根，不要用手腕中间握（与推杠铃、推哑铃同理）；"
            "手腕没练过可以带护腕；必须肩肘腕完全没有不适才做，提前热身，"
            "不忍着不适训练。对卧推的底部启动与末端伸肘有帮助（发展三角肌、肱三头肌）。"),
        "limits": (
            "两套做法口径相反，发起人 2026-10-08 结论：都保留、以用户自身感受为准，"
            "不裁定谁优先（凯圣王含胸版 ksw-BV1YJvCBwECz-0010；谭成义中立位版 "
            "tcy-BV1EdxhziEkb-0007）。「感受好」指目标肌群发力舒服，不等于可以带痛"
            "继续：出现疼痛、弹响伴无力或麻木时按停止/退阶处理，安全红旗优先于本卡。"
            "全部条目为博主经验，无研究出处。带痛、带弹响做双杠不在本卡许可范围内。"),
        "notes": "该动作属性表仍为 draft；coach/plan.py:326 只在有伤病限制时锁定已审动作，"
                 "无伤病用户仍可能被处方选中该动作。本卡只批准教学表达，不等于批准动作属性",
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1YJvCBwECz-0004", "ksw-BV1YJvCBwECz-0005", "ksw-BV1YJvCBwECz-0006",
            "ksw-BV1YJvCBwECz-0016", "ksw-BV1YJvCBwECz-0020", "ksw-BV1YJvCBwECz-0010",
            "ksw-BV1YJvCBwECz-0014", "ksw-BV1YJvCBwECz-0017", "ksw-BV1YJvCBwECz-0002",
            "ksw-BV1YJvCBwECz-0003", "ksw-BV1YJvCBwECz-0023", "tcy-BV1EdxhziEkb-0001",
            "tcy-BV1EdxhziEkb-0002", "tcy-BV1EdxhziEkb-0007"],
    },
]

QUESTIONS = [
    {
        "id": "Q4",
        "question": "以“肩膀疼/弹响”为前提的幅度与角度建议（侧平举卡第 4 点）能否作为 coaching_card 上线？",
        "recommendation": "建议：保留正文但把边界锁死——安全红旗优先、疼痛加重即停、"
                          "仅在无急性疼痛前提下缩小幅度；若你认为疼痛语境本身就该隔离，"
                          "就退回并移入 quarantined。",
        "uncertain": "两条谭成义条目的原始语境需要画面确认（是否为对门诊提问的回答），"
                     "当前只有字幕一致性。",
        "evidence": "tcy-BV1q4UwBpE2i-0061 t=1090、tcy-BV1q4UwBpE2i-0064 t=1139、"
                    "tcy-BV1utntzhE9a-0001 t=31",
    },
    {
        "id": "Q5",
        "question": "reference_only 卡的用途隔离在动作卡通道上未生效：get_exercise_coaching 调 serve_card 时固定按 "
                    "explain 检查（coach/agent.py:1074、coach/cards.py:161），所以 reference_only 动作卡照样会进教练讲解/处方上下文。"
                    "是否要求动作卡通道只服务 coaching_card，reference_only 只走独立解释工具？",
        "recommendation": "建议：要求，并补一项接入测试。在此之前不要把任何动作卡降级为 reference_only。",
        "uncertain": "是否同时要求 get_coaching_card 主题通道也按用途分流。",
        "evidence": "现有测试只验证 check_use_permission 本身，未验证调用方传入的用途。",
    },
    {
        "id": "Q6",
        "question": "P1 剩余 6 张动作卡里 4 张没有任何结构干净的可用条目（weighted_pull_up、lying_leg_curl、"
                    "standing_calf_raise、face_pull），barbell_curl 的 3 条里 2 条讲的是坐姿龙门架弯举。"
                    "本批用非 P1 的 dumbbell_shoulder_press 与 dips 顶上，属于范围扩大：认可，还是只留侧平举、"
                    "其余转成采集与映射整改？",
        "recommendation": "建议：认可本批 3 张，同时把“P1 缺口补素材”列进下一轮采集；"
                          "误挂的 2 条不解除映射，等你决定是否新建 seated_cable_curl。",
        "uncertain": "dips 的动作属性表仍是 draft，建卡不等于批准属性。",
        "evidence": "tools/p1_backlog.py 2026-10-08 输出；tools/triage_claims.py pool 桶分布",
    },
]


def load_all_claims() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((ROOT / "claims").glob("*.yaml")):
        if path.stem == "conflicts":
            continue
        for claim in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            out[str(claim["id"])] = claim
    return out


def transcript_segments() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path in TRANSCRIPTS.rglob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        out[path.stem] = data.get("segments") or []
    return out


def quote_for(claim: dict, segments: list[dict]) -> str:
    start, end = claim["ts"]
    text = "".join(s.get("text", "") for s in segments
                   if s.get("end", 0) > start and s.get("start", 0) < end)
    return text[:120] if text else "（字幕窗口未命中，需人工回看原片）"


def build() -> list[dict]:
    claims = load_all_claims()
    transcripts = transcript_segments()
    cards = load_cards()
    batch = []
    for spec in CARDS:
        existing = cards.get(spec["card_id"])
        if existing and (existing.get("review") or {}).get("status") == "approved":
            raise SystemExit(
                f"{spec['card_id']} 已有发起人审批记录，本脚本不覆盖已批卡片")
        version = int(existing.get("version", 1)) if existing else 1
        bindings = []
        for cid in spec["claim_ids"]:
            claim = claims[cid]
            issues = source_issues(claim)
            if issues:
                raise SystemExit(f"{cid} 来源侧不合格：{issues}")
            bindings.append({
                "claim_id": cid,
                "claim_fingerprint": content_fingerprint(claim),
                "video": claim["video"],
                "ts": claim["ts"],
                "url": f"https://www.bilibili.com/video/{claim['video']}"
                       f"?t={int(claim['ts'][0])}",
                "speaker": claim["speaker"],
                "quote": quote_for(claim, transcripts.get(claim["video"], [])),
            })
        assert_not_quarantined(spec["claim_ids"])
        card = {
            "card_id": spec["card_id"],
            "version": version,
            "scene": spec["scene"],
            "audience": spec["audience"],
            "non_audience": spec["non_audience"],
            "body": spec["body"],
            "limits": spec["limits"],
            "purpose": spec["purpose"],
            "bindings": bindings,
            "notes": spec["notes"],
            "status": f"prepared_v{version}",
            "prepared_by": "Zcode",
            "prepared_at": NOW,
        }
        errors = validate_card(card)
        if errors:
            raise SystemExit(f"{card['card_id']} 结构不合法：{errors}")
        batch.append(card)
    return batch


def main() -> int:
    write = "--write" in sys.argv
    batch = build()
    for card in batch:
        body_chars = len(card["body"])
        missing = [b["claim_id"] for b in card["bindings"]
                   if b["quote"].startswith("（字幕")]
        print(f"{card['card_id']} v{card['version']}｜绑定 {len(card['bindings'])} 条"
              f"｜正文 {body_chars} 字｜字幕未命中 {missing or '无'}")
    if not write:
        print("\n（试运行，未落盘；加 --write 写入 prepared 卡与队列）")
        return 0

    cards_dir = MAINT / "cards"
    for card in batch:
        (cards_dir / f"{card['card_id']}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")

    queue_path = MAINT / "card_review_queue.json"
    old = json.loads(queue_path.read_text(encoding="utf-8"))
    backup_dir = MAINT / "backups" / "queue_20261008"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "card_review_queue.json").write_text(
        json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")

    queue = build_review_queue(
        [{"card_id": c["card_id"], "version": c["version"], "scene": c["scene"],
          "bindings": len(c["bindings"]), "purpose": c["purpose"],
          "status": c["status"]} for c in batch],
        QUESTIONS, at=NOW)
    queue.update({
        "schema_version": old.get("schema_version", 1),
        "batch_limit": {"cards": 5, "questions": 3},
        "cards_detail_ref": "sources/maintenance/cards/<card_id>.json",
        "mechanism_enabled": old.get("mechanism_enabled", True),
        "awaiting": "本批 3 张卡待发起人逐卡 通过/退回修改/暂不使用；"
                    "3 个待决问题需回答",
        "answered_history": old.get("questions", []),
    })
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    print(f"\n已写入 {len(batch)} 张 prepared 卡；队列备份在 {backup_dir}")
    print("隔离条目清单仍为", len(load_quarantined()), "条（本批未新增隔离）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
