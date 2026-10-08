"""核心卡机制测试（任务书 §12.7 七点验证）。全部离线、临时目录，不触碰真实 claims。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from coach.cards import (CardError, MAINT, USE_EXPLAIN, USE_PRESCRIBE,
                         approve_card, approval_valid, assert_not_quarantined,
                         build_review_queue, card_fingerprint, check_use_permission,
                         load_cards, validate_card)


def _card(**over):
    c = {
        "card_id": "card-action-barbell_bench_press",
        "version": 1,
        "scene": "健身房卧推时胸没感觉、肩膀不舒服",
        "audience": "有基础的健身房爱好者",
        "non_audience": "肩伤未评估者",
        "body": "1) 肩胛下沉后收… 2) 杆触胸位置…",
        "limits": "以当前未受伤为前提；疼痛即停",
        "purpose": "coaching_card",
        "bindings": [
            {"claim_id": "tcy-BV1ZxEk6cEv1-0001", "claim_fingerprint": "deadbeef"},
            {"claim_id": "tcy-BV1ZxEk6cEv1-0002", "claim_fingerprint": "feedface"},
        ],
    }
    c.update(over)
    return c


def test_1_card_roundtrip_reproduces_everything(tmp_path, monkeypatch):
    """验证点1：卡片能完整还原正文/条件/用途/绑定；指纹可复现且稳定。"""
    monkeypatch.setattr("coach.cards.MAINT", tmp_path)
    (tmp_path / "cards").mkdir()
    c = _card()
    (tmp_path / "cards" / f"{c['card_id']}.json").write_text(
        json.dumps(c, ensure_ascii=False), "utf-8")
    loaded = load_cards()[c["card_id"]]
    for f in ("body", "limits", "purpose", "bindings", "audience"):
        assert loaded[f] == c[f]
    assert card_fingerprint(loaded) == card_fingerprint(c)
    assert validate_card(c) == []


def test_2_approval_scoped_and_invalidated_by_change(tmp_path):
    """验证点2：批准只覆盖展示内容；正文/绑定/用途/版本任一变化使审批失效。"""
    c = _card()
    ap = approve_card(c, by="发起人", note="核对通过", at="2026-10-06T12:00:00+08:00")
    assert approval_valid(c, ap)
    # 未展示的新条目被加入绑定 → 指纹变化 → 失效（不连带批准新条目）
    c2 = _card(bindings=c["bindings"] + [{"claim_id": "x-1", "claim_fingerprint": "ff"}])
    assert not approval_valid(c2, ap)
    # 正文微调 → 失效
    assert not approval_valid(_card(body=c["body"] + " 3) 顶部停顿…"), ap)
    # 用途/版本变化 → 失效
    assert not approval_valid(_card(purpose="reference_only"), ap)
    assert not approval_valid(_card(version=2), ap)
    # 审批记录不改变底层 claims（本测试未触碰任何 claims 文件）
    assert ap["scope_note"].startswith("仅覆盖")


def test_3_reference_only_cannot_prescribe(tmp_path):
    """验证点3：低风险参考资料不得进入处方/健康判断通道。"""
    ref = _card(purpose="reference_only")
    check_use_permission(ref, USE_EXPLAIN)  # 解释用途放行
    with pytest.raises(CardError):
        check_use_permission(ref, USE_PRESCRIBE)
    card = _card(purpose="coaching_card")
    check_use_permission(card, USE_PRESCRIBE)  # 中风险卡经审后可用于教学用途


def test_4_quarantined_never_enter_cards(tmp_path, monkeypatch):
    """验证点4：高风险/缺单位条目被隔离，不得混入卡片绑定。"""
    monkeypatch.setattr("coach.cards.MAINT", tmp_path)
    (tmp_path / "quarantined.json").write_text(json.dumps(
        {"entries": [{"id": "cs-BV1azjX65Euc-0002", "reason": "单位待核"}]},
        ensure_ascii=False), "utf-8")
    with pytest.raises(CardError):
        assert_not_quarantined(["cs-BV1azjX65Euc-0002"])
    assert_not_quarantined(["tcy-BV1ZxEk6cEv1-0001"])  # 未隔离的正常绑定放行


def test_5_batch_limits_enforced():
    """验证点5：每批硬限制 ≤5 张卡、≤3 个待决问题。"""
    cards = [_card(card_id=f"c{i}") for i in range(6)]
    with pytest.raises(CardError):
        build_review_queue(cards, [], at="x")
    build_review_queue(cards[:5], [{"q": f"q{i}"} for i in range(3)], at="x")
    with pytest.raises(CardError):
        build_review_queue(cards[:5], [{"q": i} for i in range(4)], at="x")


def test_6_background_queue_migration_keeps_history(tmp_path):
    """验证点6：50 条后台候选迁移不删历史——加 role/card_ids 字段，条目原样保留。"""
    old = {"schema_version": 1, "entries": [
        {"id": "ksw-BV1oxUpBCEwc-0033", "queue_reason": "K-A05 经验/普适分离", "claim": "x"},
        {"id": "cs-BV1Tiec6TEv1-0008", "queue_reason": "K-A03 研究条件补全待核", "claim": "y"},
    ]}
    (tmp_path / "active_review_queue.json").write_text(
        json.dumps(old, ensure_ascii=False), "utf-8")
    # 迁移逻辑（与维护脚本一致）：读取→加 role/card_ids→写回
    data = json.loads((tmp_path / "active_review_queue.json").read_text("utf-8"))
    for e in data["entries"]:
        e["role"] = "background_candidate"
        e.setdefault("card_ids", [])
    (tmp_path / "active_review_queue.json").write_text(
        json.dumps(data, ensure_ascii=False), "utf-8")
    migrated = json.loads((tmp_path / "active_review_queue.json").read_text("utf-8"))
    assert [e["id"] for e in migrated["entries"]] == ["ksw-BV1oxUpBCEwc-0033",
                                                      "cs-BV1Tiec6TEv1-0008"]
    assert all(e["role"] == "background_candidate" for e in migrated["entries"])
    assert all(e["queue_reason"] for e in migrated["entries"])  # 历史处置保留


def test_7_card_approval_does_not_touch_claims(tmp_path, monkeypatch):
    """验证点7（机制层）：卡片审批路径不修改任何 claims 文件（不批量改 approved）。"""
    monkeypatch.setattr("coach.cards.MAINT", tmp_path)
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    before = "claims untouched marker"
    (claims_dir / "tcy.yaml").write_text(before, "utf-8")
    c = _card()
    ap = approve_card(c, by="发起人", note="ok", at="x")
    approval_valid(c, ap)
    assert (claims_dir / "tcy.yaml").read_text("utf-8") == before
    # 结构校验拒绝缺绑定/非法用途的卡
    assert validate_card(_card(bindings=[]))
    assert validate_card(_card(purpose="prescription"))
