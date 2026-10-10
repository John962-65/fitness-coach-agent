"""一次性：P1 收尾与槽位替换批——5 张动作卡（2026-10-10）。

barbell_curl（PPL 拉日 accessory，最后一个 P1 空槽）+ 四个计划引擎实际会处方/
替换的动作：dumbbell_bench_press、t_bar_row、pec_deck、push_up。
同批处理两处错映射解除（K-A02 同类）后的待建登记。只产草稿，不批准。
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
        "card_id": "card-action-barbell_curl",
        "scene": "杠铃弯举：选杆、握距、躯干与轨迹",
        "audience": "想练二头、有杠铃（直杆或曲杆）的训练者；腕关节活动度正常者优先直杆",
        "non_audience": "直杆做到一半手腕不舒服者换曲杆（见正文）；肩前倾不适、肘关节疼痛者先评估",
        "body": (
            "1) 定位：凯圣王——新手练二头首先推荐杠铃弯举，它是二头训练里比较复合的动作；"
            "谭成义——肉量不够时杠铃弯举对二头肉量提升比较快。\n"
            "2) 杆与握距：直杆、曲杆都可以，握距稍握窄一点、不要握太宽（谭成义）；"
            "腕关节活动度受限、拿直杆做到一半手腕不舒服，就用曲杆（凯圣王）。\n"
            "3) 躯干：身体不要晃；肩胛保持后倾；手腕在移动过程中不要有幅度，"
            "否则就变成练小臂了（凯圣王）。\n"
            "4) 轨迹：大臂从侧面看维持偏前的位置，放的时候不要向后走、"
            "下放时肩不要转出去——转了二头近端会失去张力；先把肘关节往前推，"
            "再画一个半圆，用二头主动收紧杠铃到顶点；下放顶住肘往远处放，自然下落、不要超伸。\n"
            "5) 自检与退阶：每一次都把肌肉收紧——能收紧，甩一点也没关系；"
            "肌肉感受度不好就不要甩。正手杠铃弯举时手腕和手肘不舒服，"
            "改用绳索做退阶（滑轮调到坐姿与眼睛齐平，从前向后拉，不是从下向上）。"),
        "limits": ("12 条绑定：谭成义 6 条（BV1mwPMzZEg8/BV1hyWwzeETh）＋凯圣王 6 条"
                   "（BV14v4y1G7A3/BV1fjgC62EWN），发言者均已确认。"
                   "直杆/曲杆两种口径跨博主并列保留，以自身腕部感受为准，不裁定优劣。"
                   "“新手首先推荐”是凯圣王新手计划语境，不排除有经验者使用。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1mwPMzZEg8-0010-w1500", "tcy-BV1mwPMzZEg8-0011-w1500",
            "tcy-BV1mwPMzZEg8-0012-w1500", "tcy-BV1mwPMzZEg8-0013-w1500",
            "tcy-BV1mwPMzZEg8-0014-w1500", "tcy-BV1mwPMzZEg8-0015-w1500",
            "ksw-BV14v4y1G7A3-0016-w1500", "ksw-BV14v4y1G7A3-0017-w1500",
            "ksw-BV14v4y1G7A3-0018-w1500", "ksw-BV14v4y1G7A3-0019-w1500",
            "ksw-BV14v4y1G7A3-0020-w1500", "ksw-BV1fjgC62EWN-0045-w1500",
            "tcy-BV1hyWwzeETh-0001"],
    },
    {
        "card_id": "card-action-dumbbell_bench_press",
        "scene": "哑铃卧推：起铃放回、躯干与脚、轨迹幅度",
        "audience": "能压住肩胛、胸部本体感受已建立、想练上胸/整体的训练者",
        "non_audience": "新手直接做哑铃平板容易肩胛上提压不住（谭成义不推荐）；腰贴不住、头贴不住者可垫泡沫轴降难度",
        "body": (
            "1) 谁要慎练：谭成义不推荐新手直接哑铃平板推胸——地心引力下放时肩胛骨容易上提，"
            "新手压不住、沉不住肩，轨迹会往上滑，导致胸松、肩压力大；胸口感受不好时，"
            "先做坐姿推胸等胸发力明显、本体感受建立后，再转到哑铃。\n"
            "2) 起铃与放回：哑铃放在膝盖前方而不是大腿根（靠近大腿根杠杆更难），"
            "握住后深吸一口气，后倒时膝盖上提顺势推上去，不要等身体掉下来再推；"
            "放回原路返回，用膝盖接住哑铃放回凳上。\n"
            "3) 躯干与脚：腰贴住、不要反弓，肋骨微开、把气吸满；脚放下面用力蹬更难、"
            "收益更高（前提是做对）；平板姿势贴不住、吸不进气、胸发力差、肩压力大时，"
            "把凳子往上调变成上斜位，或在头后垫泡沫轴。\n"
            "4) 轨迹与幅度：手腕略微往里扣/微倒扣去引导胸发力，不要后仰；"
            "肘大约向下 45 度、小臂垂直地面；离心时拿胸口去够天花板；"
            "不要推到底（完全推直时胸是松的），下放肘过了肩一点点就结束。\n"
            "5) 组合示例：哑铃卧推一组 15 次，紧接着接 15 个普通俯卧撑（凯圣王）。"),
        "limits": ("20 条绑定：谭成义 16 条（BV1T6GG6mEo9/BV1TdxDzME5G）＋凯圣王 4 条"
                   "（BV1MG4y1G76W，家庭训练课语境），发言者均已确认。"
                   "“不推荐新手哑铃平板”保留谭成义原话，与凯圣王把哑铃卧推列入家庭课不冲突，"
                   "按各自适用条件并列呈现。BV1FL2MBME3G（肩后束热身视频）的 7 条外旋激活内容"
                   "经核对与哑铃卧推无关，2026-10-10 已解除错映射、不纳入本卡。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1T6GG6mEo9-0020", "tcy-BV1T6GG6mEo9-0026", "tcy-BV1T6GG6mEo9-0027",
            "tcy-BV1T6GG6mEo9-0030", "tcy-BV1T6GG6mEo9-0032", "tcy-BV1T6GG6mEo9-0033",
            "tcy-BV1T6GG6mEo9-0034", "tcy-BV1T6GG6mEo9-0036", "tcy-BV1T6GG6mEo9-0037",
            "tcy-BV1T6GG6mEo9-0041", "tcy-BV1T6GG6mEo9-0042",
            "tcy-BV1TdxDzME5G-0009", "tcy-BV1TdxDzME5G-0010", "tcy-BV1TdxDzME5G-0011",
            "tcy-BV1TdxDzME5G-0013", "tcy-BV1TdxDzME5G-0014",
            "ksw-BV1MG4y1G76W-0015", "ksw-BV1MG4y1G76W-0021",
            "ksw-BV1MG4y1G76W-0022", "ksw-BV1MG4y1G76W-0023"],
    },
    {
        "card_id": "card-action-t_bar_row",
        "scene": "T 杠划船：摆法、躯干角度、发力次序与重量",
        "audience": "想练背阔、能俯身维持核心刚性的训练者；健身房有 T 杠器械",
        "non_audience": "俯身时腰酸、后侧稳定性不足的新手（凯圣王：新手不做硬拉/杠铃划船/T 杠划船）",
        "body": (
            "1) 摆法：站距与肩同宽、脚尖向外踩死，脚不能外翻内翻、前脚掌后脚跟不离地；"
            "把手离髋关节近一些——背阔的作用之一就是让大臂向后移动；"
            "开始前给预设张力：大臂向后与负重对抗，把背阔提前调动起来。\n"
            "2) 躯干角度：不要追求身体与地面完全平行的极限角度，越平行腰的压力越大、"
            "能用的重量越小，性价比低；适当把身体角度往上调整，新手腰酸时更要注意。\n"
            "3) 发力次序：用肩胛内收带动（T 杠做不了很夸张的肩胛内收，适当即可），"
            "肩胛内收完成后让肘和肩同时向后；忘掉小臂；不要耸肩，拿它练斜方收益低。\n"
            "4) 节奏与重量：顶峰收缩时最费劲，向心上来别太慢，否则新手多半做不好顶峰收缩；"
            "离心用肩胛把重量推出去、用背控制下放，不能放松；重量选靠肩胛和背能带的，"
            "不是靠腰往上甩的；不推荐上来就六次以下的重量，更推荐 8~15 次。\n"
            "5) 核心与呼吸：气吸到腹腔、下降膈肌、降肋，构建核心刚性，"
            "骨盆不前倾也不后倾；不要连续憋气（颅内压高）；"
            "练前可以先做前锯肌和肩胛内收的激活，收益更好。"),
        "limits": ("21 条绑定全部来自凯圣王《T 杆划船详解》（BV1Dg4y117Jb，2024-01-22）"
                   "＋一条新手慎入提醒（BV14v4y1G7A3），发言者均已确认。"
                   "同视频里 T 杆深蹲（lant）内容经核对不是本动作，2026-10-10 已解除错映射，"
                   "待建动作 t_bar_squat 见 state.json pending_exercises。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "ksw-BV1Dg4y117Jb-0002", "ksw-BV1Dg4y117Jb-0003", "ksw-BV1Dg4y117Jb-0004",
            "ksw-BV1Dg4y117Jb-0006", "ksw-BV1Dg4y117Jb-0007", "ksw-BV1Dg4y117Jb-0008",
            "ksw-BV1Dg4y117Jb-0009", "ksw-BV1Dg4y117Jb-0010", "ksw-BV1Dg4y117Jb-0014",
            "ksw-BV1Dg4y117Jb-0015", "ksw-BV1Dg4y117Jb-0016", "ksw-BV1Dg4y117Jb-0017",
            "ksw-BV1Dg4y117Jb-0020", "ksw-BV1Dg4y117Jb-0022", "ksw-BV1Dg4y117Jb-0023",
            "ksw-BV1Dg4y117Jb-0024", "ksw-BV1Dg4y117Jb-0026", "ksw-BV1Dg4y117Jb-0027",
            "ksw-BV1Dg4y117Jb-0029", "ksw-BV1Dg4y117Jb-0030", "ksw-BV1Dg4y117Jb-0031",
            "ksw-BV1Dg4y117Jb-0032", "ksw-BV14v4y1G7A3-0044-w0"],
    },
    {
        "card_id": "card-action-pec_deck",
        "scene": "坐姿夹胸：座椅高度定侧重、握法与肘、躯干呼吸",
        "audience": "想孤立练胸、健身房有坐姿夹胸器械的训练者；能腰贴凳子维持躯干者",
        "non_audience": "做的时候肩不舒服者先减小幅度（见正文）；塌腕、肘掉下去会增大肩肘压力，先改动作",
        "body": (
            "1) 座椅高度定侧重：手的位置在胸下方夹，偏下胸；调低到与胸中部极限位对齐，"
            "练整个胸；再调低顺着上胸肌纤维，偏上胸。想偏下胸也可以整个人往前坐、"
            "坐到凳子最前面呈下斜位。座椅幅度看肩能力：肩能力强往后多调增大行程，"
            "肩压力大就往前调减小幅度。\n"
            "2) 握法与肘：手腕要扣起来，不要塌腕；肘窝朝前、肘不要掉下去；"
            "夹胸时肘关节不能运动，不要为了两手靠近而屈肘，否则中缝刺激不到位、"
            "容易外厚内薄；半握能募集更多胸大肌感受。\n"
            "3) 躯干与呼吸：腰贴住凳子——重量大、幅度大时整个人往前顶、腰离开凳子，"
            "训练效率非常低；先吸满气维持住，过程中别吐气松掉；练上胸肋骨不要打开、"
            "腰用力贴住，练下胸可以开肋吸满，大部分人练中间位置吸满、腰贴住即可。\n"
            "4) 轨迹：一定是两个肘向里收才能夹紧，不是用手往里碰；"
            "尽可能往前夹、把肘伸直，中缝真正收紧；放的时候可以屈一点肘。\n"
            "5) 自检与变式：手腕位置、肘窝朝前、收紧、腰贴、气吸满都做到，再选重量；"
            "感受不好时单手做，另一只手摸在目标侧中缝上，每次都要让摸着的手感到挤压感；"
            "也可以闭上眼睛做，把注意力集中到胸。"),
        "limits": ("20 条绑定全部来自谭成义：BV1PcNQ6AE3f《坐姿夹胸反飞鸟一体机教学》14 条、"
                   "BV1fa6CBDEEu 胸部跟练 4 条、BV1TdxDzME5G 4 条，发言者均已确认。"
                   "另有 BV1q4UwBpE2i 的“后背垫泡沫砖、全握虎口发力”夹胸说法，"
                   "器械形态（pec_deck / 绳索夹胸）边界存疑，本轮未纳入绑定，保留映射待核。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1PcNQ6AE3f-0002", "tcy-BV1PcNQ6AE3f-0004", "tcy-BV1PcNQ6AE3f-0005",
            "tcy-BV1PcNQ6AE3f-0006", "tcy-BV1PcNQ6AE3f-0007", "tcy-BV1PcNQ6AE3f-0008",
            "tcy-BV1PcNQ6AE3f-0009", "tcy-BV1PcNQ6AE3f-0012", "tcy-BV1PcNQ6AE3f-0013",
            "tcy-BV1PcNQ6AE3f-0014", "tcy-BV1PcNQ6AE3f-0016", "tcy-BV1PcNQ6AE3f-0017",
            "tcy-BV1PcNQ6AE3f-0018",
            "tcy-BV1fa6CBDEEu-0045-w0", "tcy-BV1fa6CBDEEu-0046-w0",
            "tcy-BV1fa6CBDEEu-0047-w0", "tcy-BV1fa6CBDEEu-0048-w0",
            "tcy-BV1TdxDzME5G-0017", "tcy-BV1TdxDzME5G-0019",
            "tcy-BV1TdxDzME5G-0020", "tcy-BV1TdxDzME5G-0021"],
    },
    {
        "card_id": "card-action-push_up",
        "scene": "俯卧撑：手距与掌、肩胸发力、退阶进阶与自检",
        "audience": "居家或热身想练推的训练者；能维持平板姿势者",
        "non_audience": "跪姿也费劲者先推墙俯卧撑退阶；腰不舒服者先做排除测试",
        "body": (
            "1) 手与掌：手距约为肩宽的 1.2 倍，五指伸直发力、不要靠手腕撑地，"
            "这样筋膜才能从手指延伸到背部和整个上肢；整个手掌贴着地，不能手歪。\n"
            "2) 肩与胸：控制肩胛骨不要太多后缩——让肩去运动，而不是肩胛骨去运动；"
            "下放时挺胸、胸往下勾，不要腰掉下去，否则变成窄推一样练三头的动作；"
            "想象手向两侧拉开，向上时主动找向里挤压的感觉。\n"
            "3) 肩胛内收幅度：俯卧撑不算大强度训练，肩胛做伴随式内收就可以，"
            "不一定要完全内收；离心时把肩胛使劲内收顶死，容易肩胛疼或背酸。\n"
            "4) 退阶与进阶：跪姿俯卧撑很费劲，可以站着做推墙俯卧撑替代；"
            "觉得简单可以负重，加二三十公斤杠铃片即可。\n"
            "5) 自检与开发：做到顶端时把肩胛顶出去，是开发前锯肌最简单的方式；"
            "起始姿势筛查——手拇指放在下巴处、打开到与肩同宽，双脚并拢脚尖勾起，"
            "全身绷紧后以平板推起，推起过程看手和下巴关系是否不变。"),
        "limits": ("13 条绑定：谭成义 4 条（BV1TdxDzME5G）＋凯圣王 8 条"
                   "（BV1MG4y1G76W/BV14dGX6fEhq/BV1fjgC62EWN）＋张丹岳 1 条"
                   "（BV1A1s3zUEN6 合作视频筛查，已署名），发言者均已确认。"
                   "负重进阶的“二三十公斤杠铃片”为视频原话，按个人水平调整。"
                   "全部为博主经验、无研究出处；applies_to 全空。"),
        "purpose": "coaching_card",
        "claim_ids": [
            "tcy-BV1TdxDzME5G-0003", "tcy-BV1TdxDzME5G-0005",
            "tcy-BV1TdxDzME5G-0006", "tcy-BV1TdxDzME5G-0007",
            "ksw-BV1MG4y1G76W-0024", "ksw-BV1MG4y1G76W-0025",
            "ksw-BV1MG4y1G76W-0026", "ksw-BV1MG4y1G76W-0027",
            "ksw-BV1MG4y1G76W-0028", "ksw-BV14dGX6fEhq-0013",
            "ksw-BV1fjgC62EWN-0005-w1500", "ksw-BV1A1s3zUEN6-0018"],
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
            "notes": "P1 收尾批：barbell_curl 为 PPL 拉日 accessory 最后一个空槽；"
                     "其余为计划引擎实际处方/替换动作",
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
        {"id": "Q14",
         "question": "本批 5 张卡（杠铃弯举/哑铃卧推/T杠划船/坐姿夹胸/俯卧撑）请逐卡 通过/退回/暂不使用。",
         "recommendation": "建议通过：杠铃弯举补上 PPL 拉日最后一个空槽；其余四张是计划引擎实际会处方/替换的动作；"
                           "绑定全部来自已确认发言者，分歧处已并列保留。",
         "uncertain": "哑铃卧推卡里谭成义“新手不推荐哑铃平板”与凯圣王家庭课用法并存，已按各自条件呈现；"
                      "坐姿夹胸卡未纳入器械形态存疑的 BV1q4UwBpE2i 夹胸说法（见 limits）。",
         "evidence": "cards 文件 + claims 87 条"},
        {"id": "Q15",
         "question": "两处错映射已按 K-A02 纪律解除（不猜挂）：①BV1FL2MBME3G 的 7 条肩后束热身/外旋激活内容不再挂哑铃卧推；"
                     "②T 杆深蹲 7 条不再挂 T 杠划船。对应的待建动作 t_bar_squat（T杠深蹲）、"
                     "lying_db_external_rotation（仰卧哑铃外旋激活）是否批准建库？",
         "recommendation": "建议建库：两组素材都够出卡（6+7 条，发言者已确认）；不建则素材继续留池。",
         "uncertain": "T 杠深蹲与哈克深蹲的替换关系（原话说“很多健身房没有哈克，T 杆可以代替它”）需要建库时决定 substitutes。",
         "evidence": "claims/tcy.yaml、claims/ksw.yaml；state.json pending_exercises"},
    ]
    queue = build_review_queue(
        [{"card_id": c["card_id"], "version": c["version"], "scene": c["scene"],
          "bindings": len(c["bindings"]), "purpose": c["purpose"],
          "status": c["status"]} for c in cards],
        questions, NOW)
    queue["cards_detail_ref"] = "sources/maintenance/cards/<card_id>.json"
    queue["mechanism_enabled"] = old.get("mechanism_enabled", True)
    queue["answered_history"] = old.get("answered_history", [])
    queue["awaiting"] = "5 张卡待逐卡签核（Q14）；Q15 两个待建动作待批准"
    (MAINT / "card_review_queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    print("队列已更新：5 卡 + 2 问（Q14/Q15）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
