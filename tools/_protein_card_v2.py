#!/usr/bin/env python3
"""蛋白质卡 v2 升级 + 冲突台账（2026-10-07 发起人要求的专项核查）。"""
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, ".")
R = Path(__file__).resolve().parent.parent
from coach.claim_review import content_fingerprint  # noqa: E402
from coach.cards import card_fingerprint, validate_card  # noqa: E402

now = datetime.now().astimezone().isoformat(timespec="seconds")

# 1) 冲突台账
cf_path = R / "sources" / "maintenance" / "conflicts.json"
cf = json.loads(cf_path.read_text())
cf["records"].append({
    "id": "conf-2026-1007-01",
    "topic": "蛋白质需求：新手 vs 老手方向相反",
    "related_claims": ["cs-BV1Y1tb6GEgw-0012", "cs-BV1Y1tb6GEgw-0007",
                       "ksw-BV1A4zjB7EcE-0029", "ksw-BV1A4zjB7EcE-0004"],
    "status": "待裁决",
    "positions": {
        "陈石": "训练初期需求上升，1.6-2.0g/kg（引ISSN立场+氮平衡研究）；老手1.2g/kg即可，1.6与3.2倍增肌无差异",
        "凯圣王": "新手训练强度低、肌肉量少应从低起量渐进（减脂基础0.8-1g/kg），总结为'新手少吃、老手多吃'（由肌肉量驱动）",
        "谭成义": "按每周训练量分层1.2-2.0g/kg，蛋白质建议固定不常调，通过调碳水适应身体",
    },
    "note": "两人推理均有出处但实操结论相反；可能源于口径不同（训练初期适应期 vs 稳态肌肉量维持）。卡片v2并列呈现，不自动裁决",
})
cf["updated_at"] = now
cf_path.write_text(json.dumps(cf, ensure_ascii=False, indent=1), "utf-8")

# 2) 蛋白质卡 v2
pool = {}
for f in ["tcy.yaml", "ksw.yaml", "cs.yaml"]:
    for c in yaml.safe_load(open(R / "claims" / f, encoding="utf-8")):
        pool[c["id"]] = c

def bind(cid):
    c = pool[cid]
    blogger = "谭成义" if cid.startswith("tcy") else ("凯圣王" if cid.startswith("ksw") else "陈石")
    tf = R / "sources" / "transcripts" / blogger / f"{c['video']}.json"
    seg = None
    if tf.exists():
        segs = json.loads(tf.read_text()).get("segments") or []
        a, b = c["ts"]
        seg = next((s["text"] for s in segs if s["end"] > a and s["start"] < b), None)
    return {"claim_id": cid, "claim_fingerprint": content_fingerprint(c),
            "video": c["video"], "ts": c["ts"],
            "url": f"https://www.bilibili.com/video/{c['video']}?t={int(c['ts'][0])}",
            "quote": (seg or c["claim"])[:80]}

card = json.loads((R / "sources" / "maintenance" / "cards" /
                   "card-nutrition-protein-basics.json").read_text())
card["version"] = 2
card["body"] = (
    "1) 蛋白质是肌肉重组的原材料，但不是越多越好——原材料要与训练给的'设计图纸'匹配。\n"
    "2) 大致区间（含三餐全部来源）：一般减脂人群约0.8-1g/kg，有训练者1.1-1.3，肌肉量大者1.3-1.5（凯圣王）；"
    "谭成义按每周训练量分层给1.2-2.0g/kg，且建议蛋白质固定、平时主要调碳水。\n"
    "3) 减脂期可比增肌期略高——低碳下身体会糖异生分解肌肉蛋白，足量蛋白维持氮平衡（两位博主一致）。\n"
    "4) 【两位博主结论相反，按你的情况选起点】新手vs老手：陈石引ISSN立场与研究认为训练初期需求更高"
    "（1.6-2.0g/kg），老手1.2g/kg即可；凯圣王认为新手训练强度低、肌肉量少，应从低起量渐进、"
    "随肌肉量增长再加（'新手少吃、老手多吃'）。共同点：不模仿职业选手的大剂量，按尿液泡沫与胃肠反应微调。\n"
    "5) 自检：尿液泡沫异常多（像洗衣粉）提示过量；胃肠胀气可能是消化负担。\n"
    "6) 蛋白粉是'方便'不是'神器'：自然食物最优、吃不够时补位；BCAA等氨基酸补剂两位博主都认为非必需。")
card["limits"] = ("三方数值均为视频转述、研究出处未独立核验；区间含全部食物来源；肾脏疾病等特殊人群遵医嘱。"
                  "要点4的分歧是真实观点冲突（见 conflicts.json conf-2026-1007-01），未经裁决不统一口径。")
card["bindings"] = [bind(x) for x in
                    ["cs-BV1Y1tb6GEgw-0007", "cs-BV1Y1tb6GEgw-0011", "cs-BV1Y1tb6GEgw-0012",
                     "ksw-BV1A4zjB7EcE-0005", "ksw-BV1A4zjB7EcE-0016", "ksw-BV1A4zjB7EcE-0021",
                     "ksw-BV1A4zjB7EcE-0029", "tcy-0791", "cs-BV1S7bN6ME2g-0023"]]
card["notes"] = ("v2：按发起人'查三位博主蛋白质内容'要求全面复核后改写——显式呈现凯圣王/陈石在'新手vs老手'"
                 "上的相反结论与谭成义的训练量分层框架（2026-10-07）")
errs = validate_card(card)
assert not errs, errs
(R / "sources" / "maintenance" / "cards" / "card-nutrition-protein-basics.json").write_text(
    json.dumps(card, ensure_ascii=False, indent=1), "utf-8")
print(f"蛋白质卡 v{card['version']} | 绑定{len(card['bindings'])}条 | 指纹{card_fingerprint(card)[:12]}…")

# 3) 队列同步
q_path = R / "sources" / "maintenance" / "card_review_queue.json"
q = json.loads(q_path.read_text())
for c in q["cards"]:
    if c["card_id"] == "card-nutrition-protein-basics":
        c["bindings"] = len(card["bindings"])
        c["version"] = 2
        c["title"] = card["scene"] + "（v2：含新手vs老手口径分歧，三方观点并列）"
q["updated_at"] = now
q_path.write_text(json.dumps(q, ensure_ascii=False, indent=1), "utf-8")
print("队列已同步 v2")

# 4) 检查点
s_path = R / "sources" / "maintenance" / "state.json"
s = json.loads(s_path.read_text())
s["updated_at"] = now
s["last_completed_step"] = ("蛋白质专项核查：全库181条/33视频盘点，发现新手vs老手口径真冲突"
                            "（陈石1.6-2.0 vs 凯圣王新手少吃），蛋白质卡升v2三方并列+冲突台账conf-2026-1007-01；"
                            "补抓《增肌饮食误区》12条零标红（账本4/8）")
s_path.write_text(json.dumps(s, ensure_ascii=False, indent=1), "utf-8")
print("检查点已更新")
