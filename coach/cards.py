"""核心教练卡机制（任务书 §12，2026-10-06 修订）。

四层：原始资料 → claims 素材池 → 核心教练卡 → 用途受限的运行时输出。
- 卡片是人工审核单位：批准只覆盖卡片实际展示的正文 + 用途 + 绑定的条目与版本（§12.4）。
- 底层 claims 不因卡片批准而改变 status（§12.7：不得批量改 approved）。
- 用途分级：reference_only（低风险，仅供解释参考）/ coaching_card（中风险，经审教学）。
  reference_only 不得请求处方/健康判断类用途（§12.3）。
- 高风险内容隔离在 quarantined.json，不进入卡片候选（§12.3）。
- 发起人队列每批最多 5 张卡 + 3 个待决问题（§12.5）。

存储：sources/maintenance/cards/<card_id>.json、card_review_queue.json、quarantined.json。
运行时门槛不变：卡片未接入 agent 输出通道前，coach/claims.py 的既有签核门槛照旧。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAINT = ROOT / "sources" / "maintenance"

PURPOSE_LEVELS = ("reference_only", "coaching_card")
# 用途请求：一般解释 vs 影响处方/健康判断（后者被 reference_only 禁止）
USE_EXPLAIN = "explain"
USE_PRESCRIBE = "prescribe_or_health_judgement"

CARD_BODY_FIELDS = ("card_id", "version", "scene", "audience", "non_audience",
                    "body", "limits", "purpose", "bindings")


class CardError(ValueError):
    pass


def card_fingerprint(card: dict) -> str:
    """卡片内容指纹：正文 + 条件 + 用途 + 绑定的条目版本。任一实质变化都使旧审批失效。"""
    payload = {k: card.get(k) for k in CARD_BODY_FIELDS}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def validate_card(card: dict) -> list[str]:
    """结构校验：§12.4 的必要字段 + 绑定形状。返回错误列表（空=合法）。"""
    errors = []
    for f in ("card_id", "version", "scene", "audience", "body", "purpose"):
        if not card.get(f):
            errors.append(f"缺必要字段 {f}")
    if card.get("purpose") not in PURPOSE_LEVELS:
        errors.append(f"purpose 非法: {card.get('purpose')!r}")
    bindings = card.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append("bindings 必须是非空数组（每条含 claim_id/claim_fingerprint）")
    else:
        for b in bindings:
            if not isinstance(b, dict) or not b.get("claim_id") or not b.get("claim_fingerprint"):
                errors.append(f"绑定缺 claim_id/claim_fingerprint: {b!r}")
    if card.get("version") in (None, "", 0):
        errors.append("version 必须为非零版本号")
    return errors


def check_use_permission(card: dict, requested_use: str) -> None:
    """用途隔离：reference_only 卡不得用于处方/健康判断（§12.3）。"""
    if card.get("purpose") == "reference_only" and requested_use == USE_PRESCRIBE:
        raise CardError(
            "reference_only 卡仅供解释参考，不得用于调整训练/饮食处方或健康判断")


def load_cards() -> dict[str, dict]:
    """读取全部卡片（sources/maintenance/cards/*.json）。"""
    out: dict[str, dict] = {}
    cdir = MAINT / "cards"
    if not cdir.exists():
        return out
    for p in sorted(cdir.glob("*.json")):
        try:
            card = json.loads(p.read_text("utf-8"))
        except json.JSONDecodeError:
            continue
        if card.get("card_id"):
            out[card["card_id"]] = card
    return out


def approve_card(card: dict, by: str, note: str, at: str,
                 stage: str = "card") -> dict:
    """生成卡片审批记录（覆盖当前版本+指纹+用途）。stage 仅供留痕，不代替人工字段。"""
    if not by or not note:
        raise CardError("审批必须记录审核者与依据，不得代填")
    return {"status": "approved", "stage": stage, "by": by, "at": at, "note": note,
            "card_version": card.get("version"),
            "fingerprint": card_fingerprint(card),
            "purpose": card.get("purpose"),
            "scope_note": "仅覆盖本卡展示的正文、条件、用途与绑定条目版本；不批准未展示的底层条目"}


def approval_valid(card: dict, approval: dict | None) -> bool:
    """审批是否对当前卡片内容仍然有效（正文/绑定/用途/版本任一实质变化即失效）。"""
    if not approval or approval.get("status") != "approved":
        return False
    return (approval.get("fingerprint") == card_fingerprint(card)
            and approval.get("card_version") == card.get("version"))


def load_quarantined() -> list[dict]:
    q = MAINT / "quarantined.json"
    if not q.exists():
        return []
    data = json.loads(q.read_text("utf-8"))
    return data.get("entries", []) if isinstance(data, dict) else data


def assert_not_quarantined(claim_ids: list[str]) -> None:
    """高风险隔离：隔离条目不得进入卡片绑定。"""
    quarantined = {e.get("id") for e in load_quarantined()}
    hit = sorted(set(claim_ids) & quarantined)
    if hit:
        raise CardError(f"隔离条目不得进入卡片: {hit}")


MAX_CARDS_PER_BATCH = 5
MAX_QUESTIONS_PER_BATCH = 3


def build_review_queue(cards: list[dict], questions: list[dict], at: str) -> dict:
    """生成面向发起人的卡审队列；硬限制每批 ≤5 张卡、≤3 个待决问题（§12.5）。"""
    if len(cards) > MAX_CARDS_PER_BATCH:
        raise CardError(f"每批最多 {MAX_CARDS_PER_BATCH} 张卡，收到 {len(cards)}")
    if len(questions) > MAX_QUESTIONS_PER_BATCH:
        raise CardError(f"每批最多 {MAX_QUESTIONS_PER_BATCH} 个待决问题，收到 {len(questions)}")
    return {"schema_version": 1, "updated_at": at, "batch_limit": {"cards": MAX_CARDS_PER_BATCH,
            "questions": MAX_QUESTIONS_PER_BATCH},
            "cards": cards, "questions": questions}


# ---------- 运行时消费（任务书 §12 第四层：用途受限的运行时输出） ----------

def approved_cards() -> dict[str, dict]:
    """只返回审批对当前内容仍然有效的卡片（正文/绑定/用途/版本任一变化即不再服务）。"""
    return {cid: c for cid, c in load_cards().items()
            if approval_valid(c, c.get("review"))}


def card_for_exercise(exercise_id: str) -> dict | None:
    """动作卡与动作库 id 直接对应（card-action-<exercise_id>）。"""
    return approved_cards().get(f"card-action-{exercise_id}")


# 主题路由表：非动作卡按主题关键词匹配（路由元数据，不属于卡片内容指纹）。
# 关键词只命中已批准的卡；未批准或已失效的卡不会被返回。
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "card-nutrition-protein-basics": ("蛋白", "乳清", "氨基酸"),
    "card-nutrition-energy-basics": ("热量", "减脂", "碳水", "能量", "代谢", "局部"),
    "card-nutrition-sustainable-habits": ("反弹", "习惯", "暴食", "坚持", "生活化"),
    "card-nutrition-sleep-recovery": ("睡眠", "失眠", "入睡", "睡不好"),
    "card-training-recovery-execution": ("恢复", "疲劳", "过度训练", "越练越累"),
    "card-training-intensity-rpe": ("rpe", "rm", "力竭", "强度单位"),
    "card-training-goal-time": ("分化", "频率", "安排", "练几次", "目标定"),
    "card-training-progression": ("加重", "进阶", "退阶", "卡住", "平台期"),
}


def card_for_topic(text: str) -> dict | None:
    t = (text or "").lower()
    for cid, kws in TOPIC_KEYWORDS.items():
        c = approved_cards().get(cid)
        if c and any(k in t for k in kws):
            return c
    return None


def serve_card(card: dict) -> str:
    """渲染已批卡片的运行时输出：正文 + 限制 + 出处节选，用途受限（仅供解释/经审教学）。"""
    check_use_permission(card, USE_EXPLAIN)
    links = "；".join(f"{b['claim_id']} {b['url']}" for b in card["bindings"][:3])
    return ("\n".join([
        f"【已审核教练卡 {card['card_id']} v{card['version']}】",
        card["body"],
        f"（限制：{card['limits']}）",
        f"（出处节选：{links}）",
    ]))
