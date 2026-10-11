#!/usr/bin/env python3
"""plank 卡 prepared_v1：直提线新增素材凑齐出卡门槛（6 条 speaker 可引用绑定）。
含出卡前映射与去重核查；Q30 随卡附 speaker 批量确认清单，签核前不进运行时。"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, "/home/johb/fitness-coach-agent")
R = Path("/home/johb/fitness-coach-agent")
from coach.cards import card_fingerprint, card_for_exercise, validate_card  # noqa: E402
from coach.claim_review import content_fingerprint  # noqa: E402

now = datetime.now().astimezone().isoformat(timespec="seconds")
CARD_ID = "card-action-plank"

pool = {}
for f in ("tcy.yaml", "ksw.yaml", "cs.yaml"):
    for c in yaml.safe_load(open(R / "claims" / f, encoding="utf-8")):
        pool[c["id"]] = c

BIND_IDS = [
    "tcy-BV1Dbz4BRErt-0011",
    "tcy-BV1oEwZzVEP4-0004",   # 与 tcy-BV1oEwZzVEP4-0001 同义（同视频），绑定取完整版
    "tcy-BV1oEwZzVEP4-0005",
    "tcy-BV1oEwZzVEP4-0002",
    "ksw-BV1MG4y1G76W-0058",
    "ksw-BV1MG4y1G76W-0060",
]


def bind(cid):
    c = pool[cid]
    blogger = "谭成义" if cid.startswith("tcy") else "凯圣王"
    segs = json.loads((R / "sources" / "transcripts" / blogger / f"{c['video']}.json")
                      .read_text()).get("segments") or []
    a, b = c["ts"]
    seg = next((s["text"] for s in segs if s["end"] > a and s["start"] < b), None)
    return {"claim_id": cid, "claim_fingerprint": content_fingerprint(c),
            "video": c["video"], "ts": c["ts"],
            "url": f"https://www.bilibili.com/video/{c['video']}?t={int(c['ts'][0])}",
            "quote": (seg or c["claim"])[:80]}


card = {
    "card_id": CARD_ID,
    "version": 1,
    "scene": "平板支撑：由简到难、肩胛位控与肘支撑变式",
    "audience": "想练核心与肩胛稳定的训练者（含居家无器械场景）",
    "non_audience": "腰部不适急性期先不做本动作；腕部支撑不适者改用肘支撑版本并按难度调节",
    "purpose": "coaching_card",
    "body": (
        "1) 循序渐进（谭成义）：平板支撑直接做更难且容易腰酸，不建议一上来就做，应由简到难。\n"
        "2) 肩胛能力与肘支撑变式（谭成义）：平板支撑对肩胛骨能力的训练不太够；居家可改肘支撑——"
        "跪姿、肘往前放而不是整个小臂贴垫、手抱头，撑起时肩胛骨不要掉下去并维持住。\n"
        "3) 难度调节（谭成义）：肘越往前越难、越往后越简单，按自己能力选位置；"
        "这个动作练肩胛骨往外打开的能力、保证肩胛贴合胸壁，之后再练背感受会好很多。\n"
        "4) 动态变式（谭成义）：拉锯式平板——支撑位做前后移动，全程肩胛骨向上顶起撑住不掉；"
        "肩胛松掉容易产生胸曲问题、影响练背感觉；动作里加入呼吸能提高呼吸能力。\n"
        "5) 肩胛稳定进阶（凯圣王，并列参考）：交替支撑／交替触肩（两边手都起来算一次，十次算一组）"
        "帮助开发肩胛与肩关节稳定性；触肩时保持抗侧屈、抗侧旋，身体不要来回晃，配合呼吸。"),
    "limits": (
        "各要点为博主个人教学表达；「肩胛能力不足」为经验观察而非测量结论。"
        "凯圣王两点是肩胛稳定训练语境的并列参考，不是平板支撑的唯一标准做法。"
        "腰部出现疼痛（而非发力酸感）时先停止——安全红旗优先于卡片内容。"
        "要点 2 存在同源近重复条目（tcy-BV1oEwZzVEP4-0001），本卡绑定更完整的 -0004。"),
    "bindings": [bind(x) for x in BIND_IDS],
    "notes": (
        "prepared_v1（2026-10-11）：直提线三轮后 plank 可引用条目凑齐门槛；"
        "出卡前核查——映射全部指向 plank、无隔离条目、无 FLAGGED；"
        "近重复 tcy-0001/0004 合并表达只绑 -0004。"
        "Q30 附 6 条绑定的 speaker 批量确认清单（均为博主 solo 教学视频的语境归因，待发起人确认）。"),
    "status": "prepared_v1",
    "prepared_by": "zcode",
    "prepared_at": now,
    "review": {"status": "prepared", "stage": "card", "card_version": 1,
               "note": "prepared 待发起人签核；签核前 plank 无已审核卡，运行时回退通用教学"},
}
errs = validate_card(card)
assert not errs, errs
(R / "sources" / "maintenance" / "cards" / f"{CARD_ID}.json").write_text(
    json.dumps(card, ensure_ascii=False, indent=1), "utf-8")
assert card_for_exercise("plank") is None, "prepared 卡不得进入运行时"
print(f"prepared_v1 | 绑定 {len(card['bindings'])} | 指纹 {card_fingerprint(card)[:12]}… | 运行时回退 ✓")

q_path = R / "sources" / "maintenance" / "card_review_queue.json"
q = json.loads(q_path.read_text("utf-8"))
q["cards"].append({"card_id": CARD_ID, "version": 1, "bindings": len(card["bindings"]),
                   "kind": "new_card_v1", "title": card["scene"] + "（新卡，含 speaker 确认清单）"})
q["questions"].append({
    "id": "Q30",
    "question": ("① plank 卡逐卡 通过/退回/暂不使用；② 附带：6 条绑定的 speaker 批量确认"
                 "（tcy：BV1Dbz4BRErt、BV1oEwZzVEP4×3；ksw：BV1MG4y1G76W×2——均为博主 solo "
                 "教学视频，语境归因为本人，请按 Q8/Q27 方式确认或指出出入）"),
    "note": "签核前运行时无 plank 已审核卡；隔离条目与 FLAGGED 均未纳入",
})
q["updated_at"] = now
q_path.write_text(json.dumps(q, ensure_ascii=False, indent=1), "utf-8")
print("队列已登记 Q30（与 Q29 合计 2 张卡、2 个问题，均在 ≤5/≤3 限额内）")

s_path = R / "sources" / "maintenance" / "state.json"
s = json.loads(s_path.read_text("utf-8"))
s["updated_at"] = now
s["next_actions"].append(
    "plank 卡 prepared_v1 + Q30（含 6 条 speaker 确认清单）入队，等发起人随 Q29 一起答复；"
    "seated_row（43 条干净）与 back_extension（19 条干净）的卡 v2 增量复审已登记为候选，待发起人决定优先级")
s_path.write_text(json.dumps(s, ensure_ascii=False, indent=1), "utf-8")
print("state.json 已更新")
