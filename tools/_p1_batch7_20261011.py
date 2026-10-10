"""一次性：Q18 后新动作+方向①批——5 张动作卡（2026-10-11）。

t_bar_squat / lying_db_external_rotation：Q15 建库后按既定素材出卡。
leg_extension / dumbbell_fly / cable_crunch：方向①素材最厚的替换动作。
同批完成两处 K-A02 同类处置后的重挂（俯身飞鸟→rear_delt_fly）与解除（地面卷腹）。
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
        "card_id": "card-action-t_bar_squat",
        "scene": "T杠深蹲：定位、站距重心、深度、错误与自检",
        "audience": "健身房没有哈克机、想用 T 杆练腿的训练者",
        "non_audience": "腰或膝有未评估问题者先评估；还没掌握深蹲模式的新手先练自重蹲",
        "body": (
            "1) 定位（凯圣王）：很多健身房没有哈克，T 杆可以代替它——它自带一个半圆的角度，"
            "更方便做深蹲，臀宽发力比较好找。\n"
            "2) 站距与重心：用宽站距；半蹲宽站距往下时重量完全放在腿上，站直时加一个深蹲；"
            "屈髋角度大一点，不用向前释放足背屈，小腿垂直就行，脚尖冲外。\n"
            "3) 深度与髋：屈髋再多一点、身体可以再下去一点，髋关节不用向前顶。\n"
            "4) 常见错误：膝盖内扣；起来时上身不能掉下去——臀大肌发力，髋膝要联动。\n"
            "5) 整体性与自检：T 杆深蹲跟罗马尼亚硬拉一样偏整体——背不能弯、肩胛不能耸起来；"
            "脚踩死（内侧踩死），小腿保持角度身体直立、臀部再往上一点，在这个角度拉起来，"
            "膝盖不要向前顶。注意顺序从脚开始：脚、膝盖最重要，然后核心后背，最后臀收紧。"),
        "limits": ("6 条绑定全部来自凯圣王（BV1we4y1J72N），发言者已确认。同视频内容此前误挂 "
                   "t_bar_row，2026-10-10 解除（K-A02 同类）、Q15（2026-10-11）批准建库后改挂本动作。"
                   "“可以代替哈克”为博主原话，器械形态因健身房而异。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1we4y1J72N-0052", "ksw-BV1we4y1J72N-0053", "ksw-BV1we4y1J72N-0055",
            "ksw-BV1we4y1J72N-0056", "ksw-BV1we4y1J72N-0057", "ksw-BV1we4y1J72N-0058"],
    },
    {
        "card_id": "card-action-lying_db_external_rotation",
        "scene": "仰卧哑铃外旋（肩袖激活）：摆位、注意事项与用法",
        "audience": "练肩/推类前想激活肩袖、有轻哑铃的训练者；对肩弹响在意者按正文自察",
        "non_audience": "肩部有明确损伤或急性疼痛者先评估；本卡是激活用法，不替代医疗评估",
        "body": (
            "1) 定位（谭成义）：仰卧在地面做哑铃外旋推举，手腕尽可能靠近地面，"
            "让手臂处于外旋位，阻力落在肩袖而不是肩上，对肩袖刺激很好——"
            "博主称之为激活外旋功能“最好的动作，没有之一”（个人判断）。\n"
            "2) 摆位与姿势：收紧核心、腰贴住地面、不要把肋骨翘出来，动作放慢；"
            "下巴微收、头枕下去发力对抗地面；手腕不要过多发力，托住哑铃即可——"
            "目的是激活外旋功能，不是举重量。\n"
            "3) 难度调节：腿伸直做会更难（腰容易翘起）；能做到直腿做最好，"
            "做不到先屈腿把腰贴住地面。\n"
            "4) 用法与频次：多次数做、去感受肩袖和肩；博主经验：对做动作有弹响的人"
            "非常能改善这个问题——属个人经验，弹响持续或伴随疼痛应先评估再练。"),
        "limits": ("7 条绑定全部来自谭成义（BV1FL2MBME3G 肩后束热身视频），发言者已确认；"
                   "2026-10-10 解除 dumbbell_bench_press 错挂（K-A02 同类）、"
                   "Q15（2026-10-11）批准建库。“改善弹响”“最好的动作”为博主原话，"
                   "不构成医疗结论。全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1FL2MBME3G-0002", "tcy-BV1FL2MBME3G-0003", "tcy-BV1FL2MBME3G-0004",
            "tcy-BV1FL2MBME3G-0005", "tcy-BV1FL2MBME3G-0006", "tcy-BV1FL2MBME3G-0007",
            "tcy-BV1FL2MBME3G-0008"],
    },
    {
        "card_id": "card-action-leg_extension",
        "scene": "坐姿腿屈伸：三种模式的侧重与做法",
        "audience": "想分化刻画大腿前侧、健身房有腿屈伸器的训练者",
        "non_audience": "膝关节疼痛者先评估；只求基础力量的用常规模式即可",
        "body": (
            "1) 概览（谭成义）：腿屈伸可拆成三种模式；想大腿线条明显，"
            "要针对股中间肌和股直肌多练，它们突出线条感才会强——把动作拆开、"
            "尽量孤立（不是完全孤立）地去练。\n"
            "2) 模式一（最常规）：抬的时候要压紧屁股和大腿后侧根部，"
            "不要一抬就松掉、只靠前面发力；屁股对抗垫子、手紧紧握住把手，"
            "收缩到位，不要上去甩。\n"
            "3) 模式二（屈髋）：单纯针对股中间肌和股直肌——做屈髋而非屈膝"
            "（屈膝更多是股内侧肌功能，屈髋更多是股中间肌和股直肌）；"
            "可稍微带一点点惯性，上肢微微前倾、不要向后倒再抬；尽量抬高一点，"
            "腿不要锁死，微屈膝快伸直后再抬（膝盖锁死会偏向膝盖远端）。\n"
            "4) 模式三（固定远端）：保证宽身位，先把膝盖伸直、髋也伸直，"
            "保持髋伸直、膝盖始终伸直，再做屈髋伸髋——固定远端练近端，"
            "对股内侧肌这边的刻度非常好。\n"
            "5) 训练量参考：博主个人这些动作十组左右打底、三种模式合计可能 30 组左右"
            "（原话“可能有点极端，但个人就是这样练出来的”）——按自身恢复调整，不照搬。"),
        "limits": ("10 条绑定全部来自谭成义（BV1BxxAzpEzH），发言者已确认。"
                   "三种模式为同一器械的不同侧重用法，按目标选择、并列呈现。"
                   "“30 组”为博主个人训练量，不作为推荐剂量。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1BxxAzpEzH-0011", "tcy-BV1BxxAzpEzH-0012", "tcy-BV1BxxAzpEzH-0013",
            "tcy-BV1BxxAzpEzH-0014", "tcy-BV1BxxAzpEzH-0015", "tcy-BV1BxxAzpEzH-0016",
            "tcy-BV1BxxAzpEzH-0017", "tcy-BV1BxxAzpEzH-0018", "tcy-BV1BxxAzpEzH-0019",
            "tcy-BV1BxxAzpEzH-0020"],
    },
    {
        "card_id": "card-action-dumbbell_fly",
        "scene": "哑铃夹胸/飞鸟：激活与增肌两种用法、姿势轨迹与常见错误",
        "audience": "想练胸、改善肩胛滑动功能或找胸发力感的训练者",
        "non_audience": "肩前侧不适者先改姿势或评估；肩胛内收明显受限者按正文调整、不要硬做大臂代偿",
        "body": (
            "1) 两种用法——并列保留：凯圣王把哑铃夹胸当功能激活动作——不只是练胸，"
            "还能练肩胛内收外展的滑动功能、前锯肌与菱形肌的配合，并拉伸胸大肌；"
            "胸廓紧、肩胛向后滑行不好、找不到胸发力或含胸体态时，放在胸部训练第一个动作，"
            "激活后再推收益更大。谭成义不建议第一个动作做哑铃飞鸟——飞鸟更多是离心，"
            "向心都收不紧的话离心更不知道练哪去了。两种口径按各自条件并存，"
            "以自身肩胛功能与感受选择。\n"
            "2) 姿势：腿踩在凳上，骨盆微微后倾，保持降肋、收一点下巴；"
            "吸气把胸廓整个吸满，保证腹腔与胸腔的对位关系。\n"
            "3) 轨迹与肩胛：想象两手中间有一根皮筋要拉开，但动作是前后关系——"
            "前侧肌肉被拉长的同时后侧缩短；离心时在胸大肌有张力的同时主动让肩胛内收"
            "（前锯肌拉长、菱形肌与中下斜方缩短），向心时把肩胛往外推；"
            "向上不是往上推而是往里夹，夹到肩胛最大外展的行程，同时挺胸、胸收紧停住，"
            "不要放松地碰到。\n"
            "4) 常见错误：还没做离心肩胛就先内收（不推荐）；肩胛内收受限时用大臂外展带角度——"
            "容易把肱骨从肩关节往前推、负重变成杠杆把肱骨翘出去，肩前侧不适"
            "（很多兄弟推胸不适就是这个问题）；耸肩、还没吸气就下去；肋太往外翻、一侧翘起；"
            "放得太往下——即使肩胛功能好，放太低肩会代偿，跟地面平行就差不多；不要仰头。\n"
            "5) 幅度与强度：健美式卧推向心阶段肩胛前伸是追求胸大肌最强收缩"
            "（做下斜夹胸不仅前伸到头还要微微加点下降，胸大肌才能全收紧）；"
            "飞鸟夹胸这类动作每组做得很轻、不到力竭，增肌效率会很低——"
            "不存在某类动作只练红肌或白肌，关键看强度和是否力竭。"
            "徒手重复 10 到 20 次先激活胸到背的拮抗肌群通路，再拿哑铃试。"),
        "limits": ("25 条绑定：凯圣王 24 条（BV1E9an6zExw 哑铃夹胸教学 22 条＋"
                   "BV1fjgC62EWN/BV1QR3E6qECQ 各 1 条）＋谭成义 1 条（BV1fa6CBDEEu），"
                   "发言者均已确认。“放第一个动作”（凯圣王）与“不建议第一个”（谭成义）"
                   "为条件性差异，并列保留。BV1E9an6zExw-0010（FLAGGED）未纳入；"
                   "同视频 6 条俯身哑铃飞鸟内容 2026-10-11 已重挂 rear_delt_fly"
                   "（K-A02 同类），不属本动作。全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1E9an6zExw-0001", "ksw-BV1E9an6zExw-0002", "ksw-BV1E9an6zExw-0003",
            "ksw-BV1E9an6zExw-0004", "ksw-BV1E9an6zExw-0005", "ksw-BV1E9an6zExw-0006",
            "ksw-BV1E9an6zExw-0007", "ksw-BV1E9an6zExw-0008", "ksw-BV1E9an6zExw-0009",
            "ksw-BV1E9an6zExw-0011", "ksw-BV1E9an6zExw-0012", "ksw-BV1E9an6zExw-0013",
            "ksw-BV1E9an6zExw-0014", "ksw-BV1E9an6zExw-0015", "ksw-BV1E9an6zExw-0016",
            "ksw-BV1E9an6zExw-0017", "ksw-BV1E9an6zExw-0018", "ksw-BV1E9an6zExw-0019",
            "ksw-BV1E9an6zExw-0020", "ksw-BV1E9an6zExw-0021", "ksw-BV1E9an6zExw-0022",
            "ksw-BV1E9an6zExw-0023",
            "ksw-BV1fjgC62EWN-0011-w1500", "ksw-BV1QR3E6qECQ-0023",
            "tcy-BV1fa6CBDEEu-0016-w0"],
    },
    {
        "card_id": "card-action-cable_crunch",
        "scene": "跪姿龙门架卷腹：做法、负重原则与适用人群",
        "audience": "想负重练腹直肌形态、健身房有龙门架的训练者",
        "non_audience": "胸椎屈曲受限者先评估（卷腹类受限时腰椎代偿多）；追求核心能力优先于形态者按正文争议条目自行选择",
        "body": (
            "1) 做法（谭成义）：用三头绳握住尾端放在颈后，卷的时候屁股不能向后坐、"
            "要维持不动，手去靠近大腿；屁股一往后腹就不发力了——重心微微向前、"
            "向里卷，尽量把肘靠近大腿。\n"
            "2) 负重原则：腹直肌想饱满一定需要负重，不断加重才能让腹直肌变大，"
            "和其他肌肉一样。\n"
            "3) 争议并存：跪姿龙门架卷腹（磕头）可让腹直肌更饱满，但核心能力提升不好、"
            "且可能是反方向的动作——存在争议；按自己目标（形态 vs 核心能力）选择。\n"
            "4) 人群建议：女生不太建议练跪姿龙门架卷腹，除非是比赛；"
            "比基尼、形体和模特不需要太清晰的腹部，更适合其他腹部动作。\n"
            "5) 框架定位：博主把腹部训练概括为三个动作，跪姿龙门架卷腹属其中偏形态的"
            "一个——三个动作已涵盖腹直肌饱满、腹内外斜肌刻度与腹部功能；"
            "更推荐前两个，第三个只符合特定情况。\n"
            "6) 通用注意（凯圣王）：胸椎屈曲功能受限时，站姿体前屈、弯腰及卷腹类动作会受限，"
            "腰椎代偿较多、可能出现腰椎不适——先恢复胸椎活动度或降低幅度。"),
        "limits": ("7 条绑定：谭成义 6 条（BV1W1BFBKEdR）＋凯圣王 1 条通用注意（BV1k4YXznErX），"
                   "发言者均已确认。同视频 5 条地面卷腹内容 2026-10-11 已解除 cable_crunch "
                   "错挂（K-A02 同类：地面卷腹不是本动作），待建提案见队列 Q21。"
                   "“女生不建议”为博主口径，按个人目标选择。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1W1BFBKEdR-0017", "tcy-BV1W1BFBKEdR-0018", "tcy-BV1W1BFBKEdR-0019",
            "tcy-BV1W1BFBKEdR-0020", "tcy-BV1W1BFBKEdR-0021", "tcy-BV1W1BFBKEdR-0022",
            "ksw-BV1k4YXznErX-0006"],
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
        # 绑定条目必须真的映射到本动作（映射为空或错挂一律拒绝）
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
            "notes": "Q18 后批：Q15 建库两动作出卡 + 方向①替换动作；"
                     "同批完成俯身飞鸟重挂与地面卷腹解除错挂（K-A02 同类）",
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
        {"id": "Q20",
         "question": "本批 5 张卡（T杠深蹲/仰卧哑铃外旋/坐姿腿屈伸/哑铃夹胸/跪姿龙门架卷腹）"
                     "请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：前两张是 Q15 建库动作的既定出卡（6+7 条绑定），"
                           "后三张是方向①素材最厚的替换动作（10+25+7 条）；"
                           "全部绑定 speaker 已确认、无 FLAGGED、无隔离、映射与动作库一致。",
         "uncertain": "哑铃夹胸卡里“放第一个动作”（凯圣王激活用法）与“不建议第一个”"
                      "（谭成义）按并列保留呈现；跪姿龙门架卷腹卡的“女生不建议”"
                      "“可能有反方向争议”为谭成义原话口径，按目标自选。",
         "evidence": "cards 文件 + claims 55 条"},
        {"id": "Q21",
         "question": "地面卷腹 5 条（ksw-BV1MG4y1G76W-0047/0048/0050/0051/0052，家庭课腹部段）"
                     "2026-10-11 已解除 cable_crunch 错挂。是否建库 crunch（地面卷腹，自重）？"
                     "5 条素材以流程描述为主（卷腹 15 次接两头起），技术要点含量偏低。",
         "recommendation": "两个方案都合理：①建库（draft）把映射挂正，出卡可等素材攒厚；"
                           "②不建库，5 条保持空映射留池（自重卷腹技术含量低， plank/悬垂举腿已覆盖核心教学）。",
         "uncertain": "地面卷腹与 cable_crunch 的别名不得重叠（校验器会拦）——建库时命名需避开“卷腹”单用。",
         "evidence": "claims/ksw.yaml；exercises/ 无自重卷腹动作"},
    ]
    history = old.get("answered_history", [])
    history += [
        {"id": "Q18",
         "question": "方向②首批 3 张主题卡（有氧/饮酒/补剂）逐卡 通过/退回/暂不使用",
         "answered": "通过（发起人 2026-10-11 对话原话「q18通过」）——3 卡均 approved_v1；"
                     "批准前复验 61 条绑定指纹一致、引文命中、无隔离、无 FLAGGED；"
                     "运行时服务卡 39→42，主题路由三卡生效",
         "answered_at": NOW},
        {"id": "Q19",
         "question": "减脂平台期（2条）/停训复训（1条）素材不足的处置：①登记采集缺口等素材 ②接受长期缺口",
         "answered": "继续采集（发起人 2026-10-11 对话原话「q19继续采集」，即选项①）——"
                     "已登记采集缺口并做免费扫描：本地存量字幕平台期 34 处/13 视频"
                     "（BV1uuhV6YEGW 等有大段未提炼内容）、停训复训 12 处/7 视频；"
                     "随后补抓三空间剩余未抓字幕（见 runs/q19_theme_scan_*）；"
                     "提炼需 LLM 额度，未动用（采集账本 6/6 已用尽）",
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
    queue["awaiting"] = "5 张卡待逐卡签核（Q20）；Q21 地面卷腹建库提案待定；Q19 采集扫描已在执行"
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：5 卡 + 2 问（Q20/Q21）；Q18/Q19 已记入 answered_history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
