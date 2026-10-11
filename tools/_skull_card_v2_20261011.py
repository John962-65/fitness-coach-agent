#!/usr/bin/env python3
"""skull_crusher 卡 v2 准备（§12.6 增量复审）：BV1Cz421i79n×3 条 speaker 已确认的
编程定位/替代方案条目进入卡正文；v1 审批不延续到新内容，prepared 待发起人签核。"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, ".")
R = Path(__file__).resolve().parent.parent
from coach.cards import card_for_exercise, card_fingerprint, validate_card  # noqa: E402
from coach.claim_review import content_fingerprint  # noqa: E402

now = datetime.now().astimezone().isoformat(timespec="seconds")
CARD_ID = "card-action-skull_crusher"
path = R / "sources" / "maintenance" / "cards" / f"{CARD_ID}.json"
path.with_suffix(".json.v1.bak").write_text(path.read_text("utf-8"), "utf-8")

card = json.loads(path.read_text("utf-8"))
assert card["version"] == 1 and card["review"]["status"] == "approved"

pool = {}
for f in ("tcy.yaml", "ksw.yaml", "cs.yaml"):
    for c in yaml.safe_load(open(R / "claims" / f, encoding="utf-8")):
        pool[c["id"]] = c


def bind(cid):
    c = pool[cid]
    segs = json.loads((R / "sources" / "transcripts" / "凯圣王" / f"{c['video']}.json")
                      .read_text()).get("segments") or []
    a, b = c["ts"]
    seg = next((s["text"] for s in segs if s["end"] > a and s["start"] < b), None)
    return {"claim_id": cid, "claim_fingerprint": content_fingerprint(c),
            "video": c["video"], "ts": c["ts"],
            "url": f"https://www.bilibili.com/video/{c['video']}?t={int(c['ts'][0])}",
            "quote": (seg or c["claim"])[:80]}


new_ids = ["ksw-BV1Cz421i79n-0002", "ksw-BV1Cz421i79n-0003", "ksw-BV1Cz421i79n-0001"]
card["version"] = 2
card["body"] += (
    "\n7) 编程定位（凯圣王，v2 新增，与上文并列参考）：想让三头上很大强度、找到大机械张力，"
    "应该用窄推（杠铃）而不是仰卧臂屈伸；仰卧臂屈伸的价值是更多代谢压力、更好孤立感——"
    "两者不是非此即彼。仰卧臂屈伸可以放在窄推之后做，对三头长头的刺激非常不错。"
    "\n8) 替代方案（凯圣王，v2 新增）：抢不到卧推架做不了窄推、或练三头时肘肩不适，"
    "可用上斜凳哑铃仰卧臂屈伸（双手掌心相对的垂直握法）替代；直杆手腕压力大者同样适用；"
    "上斜角度更好刺激三头长头。")
card["limits"] += ("；v2 新增要点的'长头刺激'等表述为视频转述，原研究未独立核验；"
                   "窄推（close_grip_bench_press）无独立卡，本卡只覆盖仰卧臂屈伸本身，"
                   "第 7 点按并列参考呈现、不裁定窄推与仰卧臂屈伸谁更优。")
card["bindings"] += [bind(x) for x in new_ids]
card["notes"] = ("v2（2026-10-11 prepared，§12.6 增量复审）：原来怎么说→v1 六点正文原样保留；"
                 "新增什么→第 7 点编程定位（窄推 vs 仰卧臂屈伸并列）与第 8 点上斜哑铃替代"
                 "（BV1Cz421i79n 3 条，发起人已确认归属）；为什么→该批条目 10-11 完成归属确认，"
                 "按 §12.6 进入增量复审而非自动挂卡；影响→三头训练的编程与替代选择；"
                 "本次需确认→第 7/8 点正文与 3 条新绑定（共 10 条绑定）。")
card["status"] = "prepared_v2"
card["prepared_by"] = "zcode"
card["prepared_at"] = now
card["review_history"] = [card.get("review", {})]
card["review"] = {"status": "prepared", "stage": "card", "card_version": 2,
                  "note": "v2 prepared 待发起人签核；v1 审批不延续到新内容"}

errs = validate_card(card)
assert not errs, errs
path.write_text(json.dumps(card, ensure_ascii=False, indent=1), "utf-8")
assert card_for_exercise("skull_crusher") is None, "prepared 卡不得进入运行时"
print(f"v{card['version']} prepared | 绑定 {len(card['bindings'])} 条 | "
      f"指纹 {card_fingerprint(card)[:12]}… | 运行时不再服务（待签核）✓")

q_path = R / "sources" / "maintenance" / "card_review_queue.json"
q = json.loads(q_path.read_text("utf-8"))
q["cards"].append({
    "card_id": CARD_ID, "version": 2, "bindings": len(card["bindings"]),
    "kind": "incremental_v2", "title": card["scene"] + "（v2 增量复审）",
    "delta": ("原 v1 六点不变；新增第 7 点（窄推 vs 仰卧臂屈伸编程定位，并列保留）"
              "与第 8 点（上斜凳哑铃替代）；绑定 7→10"),
})
q["questions"].append({
    "id": "Q29",
    "question": "skull_crusher 卡 v2（增量：编程定位＋替代方案，10 绑定）逐卡 通过/退回/暂不使用",
    "note": "v1 审批不延续到新内容；签核前运行时对该动作回退为通用教学",
})
q["updated_at"] = now
q_path.write_text(json.dumps(q, ensure_ascii=False, indent=1), "utf-8")
print("队列已登记 Q29")

s_path = R / "sources" / "maintenance" / "state.json"
s = json.loads(s_path.read_text("utf-8"))
for i, a in enumerate(s.get("next_actions", [])):
    if "close_grip/skull_crusher" in a:
        s["next_actions"][i] = ("close_grip/skull_crusher 增量（BV1Cz421i79n×3）已按 §12.6 "
                                "做成 skull_crusher 卡 v2 prepared，Q29 待发起人签核")
s["updated_at"] = now
s_path.write_text(json.dumps(s, ensure_ascii=False, indent=1), "utf-8")
print("state.json 已更新")
