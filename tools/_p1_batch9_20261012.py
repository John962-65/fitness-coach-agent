"""一次性：Q22 后批——拆分卡 + 跪姿俯卧撑（2026-10-12 凌晨）。

reverse_back_extension：发起人裁定「拆成两个动作」后按谭成义素材出卡（12 绑定）。
knee_push_up：素材干净（7 绑定）。
同批完成 K-A02 同类重挂：俯身臂屈伸技巧→bent_over_triceps_extension、
反手杠铃臂屈伸→skull_crusher（均库内有正主）。
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
        "card_id": "card-action-reverse_back_extension",
        "scene": "反向山羊挺身（练腹）：形态、大腿后侧前提、腰椎安全与变式",
        "audience": "想用山羊挺身凳练腹/核心、健身房有该器械的训练者",
        "non_audience": "腰椎有未评估问题者先评估（正文有幅度自检）；找不到大腿后侧对抗感者先徒手练稳",
        "body": (
            "1) 定位（谭成义）：脸朝上躺在山羊挺身凳上做腹肌训练——博主称其为最推荐的动作"
            "（“无论从形体、功能还是解决疼痛问题都可以通过它改善”，原话口径）；"
            "在他的三个腹部动作框架里排第一、更推荐之列。\n"
            "2) 形态要点：上肢尽量保持直上直下、水平向上走/向远端走，不要向前卷、"
            "不要做收缩，幅度很小——做成了向前卷腹，动作意义就没了，不如去做地上卷腹。\n"
            "3) 关键前提——大腿后侧：大腿后侧必须用力对抗垫子、主动蹬住不松，"
            "保持骨盆稳定后再上下起落；没有带护垫的山羊挺身器械时更要注意。\n"
            "4) 幅度与腰椎安全：幅度越往下越难，越往下腿容易翘起、大腿后侧松掉——"
            "必须保证大腿紧贴凳子后再下；如果做时腰椎压力大、张力承载在腰侧而非腹前侧，"
            "应减小幅度，甚至直接做静态对抗维持。\n"
            "5) 变式与进阶：熟练后可加旋转增强身体旋转能力——但大腿后侧必须保持稳定，"
            "骨盆松掉再旋转可能伤腰椎；能力更强时可将手伸直做（对核心要求更高），"
            "或手持杠铃片做变式。\n"
            "6) 与正向的边界：本动作练腹；趴着练竖脊肌的正向山羊挺身是同一器械的"
            "另一个动作（back_extension），不要混。"),
        "limits": ("12 条绑定全部来自谭成义（BV1Ehn7zmEHN 5 条＋BV1W1BFBKEdR 7 条），"
                   "发言者已确认；3 条 FLAGGED（BV1W1BFBKEdR-0003/0008/0013）未纳入。"
                   "“解决疼痛问题”为博主原话，不作医疗承诺；出现腰椎疼痛即停并评估。"
                   "本卡 2026-10-12 经发起人裁定自 back_extension 拆分而来。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1Ehn7zmEHN-0014", "tcy-BV1Ehn7zmEHN-0015", "tcy-BV1Ehn7zmEHN-0016",
            "tcy-BV1Ehn7zmEHN-0018", "tcy-BV1Ehn7zmEHN-0019",
            "tcy-BV1W1BFBKEdR-0005", "tcy-BV1W1BFBKEdR-0006", "tcy-BV1W1BFBKEdR-0007",
            "tcy-BV1W1BFBKEdR-0009", "tcy-BV1W1BFBKEdR-0010", "tcy-BV1W1BFBKEdR-0011",
            "tcy-BV1W1BFBKEdR-0022"],
    },
    {
        "card_id": "card-action-knee_push_up",
        "scene": "跪姿俯卧撑：超程胸部训练与肩激活两种用法、不适调整",
        "audience": "俯卧撑做不动需要退阶者；想用瑜伽砖做超程胸部训练者；卧推前想激活肩者",
        "non_audience": "膝盖疼痛者垫毛巾/瑜伽垫仍不适则换器械推胸；肩腕急性疼痛者先评估",
        "body": (
            "1) 定位与人群（凯圣王）：女性应该练胸和卧推——瑜伽砖跪姿俯卧撑可做超程胸部训练，"
            "强化胸大肌的同时提高延展性，避免前侧长期紧张把身体拉到不良体态；"
            "俯卧撑做不动时的标准退阶是膝卧撑（或器械推胸）。\n"
            "2) 安排示例（凯圣王）：瑜伽砖跪姿俯卧撑——跪地并垫瑜伽垫或毛巾避免膝盖疼，"
            "双手垫在瑜伽砖下以增加幅度，三组 15 次，不要做到力竭或特别难受。\n"
            "3) 激活用法（谭成义）：泡沫轴和呼吸之后，做两组内旋位跪姿俯卧撑激活；"
            "小幅度下、次数少起来多，感受三头肌伸展。\n"
            "4) 不适调整：肩膀疼、弹响或手腕疼的人，可以用拳撑代替全掌撑。\n"
            "5) 价值：内旋位跪姿俯卧撑可激活并改善肩功能，减少卧推等水平推时的肩部弹响和疼痛"
            "（博主经验，弹响持续或伴疼痛先评估）。"),
        "limits": ("7 条绑定：凯圣王 3 条（BV14dGX6fEhq/BV1fyUABfERd）＋谭成义 4 条"
                   "（BV1q4UwBpE2i），发言者均已确认。瑜伽砖超程训练（凯圣王女性语境）与"
                   "内旋位激活（谭成义）两种用法并列，按目标选择。"
                   "“改善弹响/疼痛”为博主原话，不作医疗结论。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV14dGX6fEhq-0012", "ksw-BV14dGX6fEhq-0014", "ksw-BV1fyUABfERd-0024",
            "tcy-BV1q4UwBpE2i-0010", "tcy-BV1q4UwBpE2i-0011",
            "tcy-BV1q4UwBpE2i-0012", "tcy-BV1q4UwBpE2i-0013"],
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
            "notes": "Q22 后批：back_extension 拆分（发起人 2026-10-12 裁定）后反向出卡",
            "status": "prepared_v1", "prepared_by": "Zcode", "prepared_at": NOW}
    errors = validate_card(card)
    if errors:
        raise SystemExit(f"{card['card_id']} 结构不合法：{errors}")
    for b in bindings:
        if b["quote"].startswith("（字幕窗口未命中"):
            raise SystemExit(f"{card['card_id']} 绑定 {b['claim_id']} 引文未命中原文")
    return card


def remap() -> None:
    """K-A02 同类：两组错挂重挂到库内正主。"""
    ops = {
        'claims/ksw.yaml': (
            {'ksw-BV1MG4y1G76W-0043'}, 'bent_over_triceps_extension'),   # 俯身臂屈伸技巧
        'claims/tcy.yaml': (
            {f'tcy-BV1hyWwzeETh-{n:04d}' for n in (6, 7, 8)}, 'skull_crusher'),  # 反手杠铃臂屈伸
    }
    for path, (ids, target) in ops.items():
        text = open(path, encoding='utf-8').read()
        lines = text.splitlines(keepends=True)
        done = []
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s.startswith('- id: ') and s.split('- id: ')[1].strip() in ids:
                cid = s.split('- id: ')[1].strip()
                for j in range(i + 1, min(i + 20, len(lines))):
                    sj = lines[j].strip()
                    if sj.startswith('- id: '):
                        raise SystemExit(f'{cid}: 未找到 exercises')
                    if sj == 'exercises:':
                        indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                        k = j + 1
                        while k < len(lines) and lines[k].strip().startswith('- '):
                            del lines[k]
                        lines.insert(j + 1, f"{indent}- {target}\n")
                        done.append(cid)
                        break
        assert set(done) == ids, f'{path}: {done} vs {ids}'
        open(path, 'w', encoding='utf-8').write(''.join(lines))
        print(f'{path}: {len(done)} 条 -> {target}')


def main() -> int:
    remap()
    claims = load_all_claims()
    transcripts = transcript_segments()
    cards = [build_card(s, claims, transcripts) for s in CARDS]
    for card in cards:
        (MAINT / "cards" / f"{card['card_id']}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{card['card_id']} v1｜绑定 {len(card['bindings'])} 条｜正文 {len(card['body'])} 字")

    old = json.loads((MAINT / "card_review_queue.json").read_text(encoding="utf-8"))
    questions = [
        {"id": "Q23",
         "question": "本批 2 张卡（反向山羊挺身/跪姿俯卧撑）请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：反向山羊挺身是拆分裁定的直接落地（12 条绑定、3 条 FLAGGED 未纳入）；"
                           "跪姿俯卧撑素材干净（7 条）；全部 speaker 已确认、映射一致。",
         "uncertain": "跪姿俯卧撑卡并存凯圣王“瑜伽砖超程练胸”与谭成义“内旋位激活”两种用法；"
                      "反向卡正文含“解决疼痛问题”博主原话，已在 limits 注明不作医疗承诺。",
         "evidence": "cards 文件 + claims 19 条"},
    ]
    history = old.get("answered_history", [])
    history += [
        {"id": "Q22",
         "question": "本批 4 张卡（反飞鸟/器械推肩/斜板支撑划船/臀冲）逐卡 通过/退回/暂不使用",
         "answered": "通过（发起人 2026-10-11 对话原话「q22通过」）——4 卡均 approved_v1；"
                     "批准前复验 40 条绑定指纹一致、引文命中、无隔离、无 FLAGGED、映射一致；"
                     "运行时服务卡 47→51",
         "answered_at": NOW},
        {"id": "Q24back_extension",
         "question": "back_extension 正向（竖脊肌，4条）与反向（练腹，15条）拆分方案",
         "answered": "拆成两个动作（发起人 2026-10-11 对话原话「第二个问题拆成两个动作」）——"
                     "新建 reverse_back_extension（draft，68 动作 validate 通过）；15 条反向 claims 改挂；"
                     "back_extension 保留正向（凯圣王 4 条已确认 + 3 条待确认素材）并在 provenance 记拆分；"
                     "反向卡进本批（Q23）",
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
    queue["awaiting"] = ("2 张卡待逐卡签核（Q23）；band_pull_apart 素材实为肩胛上回旋训练、"
                         "与扩胸定义有出入，映射复核后再出卡")
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：2 卡 + 1 问（Q23）；Q22/拆分裁定已记入 answered_history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
