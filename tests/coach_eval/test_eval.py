#!/usr/bin/env python3
"""M6.5-5 评测运行器：硬性约束零违规；按类别报告通过率与失败类型。

报告写入 docs/m6.5-eval-report.md。评测分三层（见 seed.py docstring）：
- 本运行器覆盖**确定性测试**与**模型行为测试**中可离线确定的部分
  （工具返回值、路由、红线守卫、数值可追溯性）；
- **建议质量评估**（人工结合证据与情境）由报告中的待人工复核清单承接，
  不用"LLM 返回了 JSON"冒充。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from coach.db import Database

from . import seed as S
from .cases import CASES

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "m6.5-eval-report.md"

# 数值可追溯检查：正文里的数字（含小数）必须出现在允许集合
_NUM = re.compile(r"\d+(?:\.\d+)?")


def untraceable_numbers(text: str, allowed: set[str]) -> list[str]:
    """提取文本中的数值，返回无法追溯到 allowed 的（评测用）。

    纯小整数（0/1/2 等计数措辞）与日期样式豁免；带单位或 ≥3 位的数值
    必须可追溯。
    """
    text = str(text or "")
    # 豁免：ISO 日期、fact_id 里的日期尾、source_ids、纯 8 位数字串
    text = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    text = re.sub(r"-\d{8}\b", " ", text)
    text = re.sub(r"\b\d{8}\b", " ", text)
    bad = []
    for m in _NUM.finditer(text):
        tok = m.group()
        if tok in allowed:
            continue
        ctx = text[m.end():m.end() + 2]
        if re.match(r"^\s*(kg|公斤|次|组|RPE|秒|米|周|天)", ctx):
            bad.append(tok)
        elif len(tok) >= 3:
            bad.append(tok)
    return bad


def _run_case(c: dict, tmp_path: Path) -> tuple[bool, str]:
    db = S.make_db(tmp_path / f"{c['id']}.db")
    try:
        return c["run"](db, "evalu")
    except Exception as e:  # noqa: BLE001 评测把异常记为失败并报告
        return False, f"异常: {type(e).__name__}: {e}"


@pytest.mark.parametrize("c", CASES, ids=[c["id"] for c in CASES])
def test_eval_case(c, tmp_path):
    ok, detail = _run_case(c, tmp_path)
    assert ok, f"[{c['category']}] {c['id']}: {detail}"


def test_hard_constraints_zero_violations(tmp_path):
    """硬性约束（编造数值/口径混用/绕安全门等）零违规（M6.5-5 验收）。"""
    hard = [c for c in CASES if c["hard"]]
    fails = []
    for c in hard:
        ok, detail = _run_case(c, tmp_path / "hard")
        if not ok:
            fails.append(f"{c['id']}: {detail}")
    assert not fails, "硬性约束违规：\n" + "\n".join(fails)


def test_write_eval_report(tmp_path):
    """按类别统计通过率/失败类型，落评测报告（趋势类=建议质量的离线部分）。"""
    rows = []
    for c in CASES:
        ok, detail = _run_case(c, tmp_path / "report")
        rows.append((c["id"], c["category"], c["hard"], ok, detail))
    by_cat: dict[str, list] = {}
    for r in rows:
        by_cat.setdefault(r[1], []).append(r)
    lines = [
        "# M6.5 训练建议评测报告", "",
        f"生成：{date.today().isoformat()} · 案例总数：{len(CASES)}"
        f"（硬性约束 {sum(1 for c in CASES if c['hard'])} 条）", "",
        "| 类别 | 通过/总数 | 失败案例（失败类型） |",
        "|---|---|---|",
    ]
    all_fail = 0
    for cat, rs in by_cat.items():
        fails = [r for r in rs if not r[3]]
        all_fail += len(fails)
        lines.append(f"| {cat} | {len(rs) - len(fails)}/{len(rs)} | "
                     + ("；".join(f"{r[0]}（{r[4][:60]}）" for r in fails)
                        or "—") + " |")
    lines += [
        "",
        f"**合计：{len(CASES) - all_fail}/{len(CASES)} 通过；"
        f"硬性约束违规 {sum(1 for r in rows if r[2] and not r[3])} 条"
        "（要求 0）**", "",
        "## 说明与边界", "",
        "- 本报告为**确定性/模型行为离线评测**：数值全部对种子库断言，",
        "  口径与「我的表现/周期统计/AI 训练事实」三接口一致（案例 "
        "bench3-three-interface-consistency）。",
        "- **建议质量评估**（多方案取舍是否贴合具体情境）需人工结合证据",
        "  与适用条件复核，不用「LLM 返回了有效 JSON」代替——待人工项：",
        "  真实 LLM 在 30+ 案例问答中的方案质量抽样。",
        "- 趋势判定（improving/stable/declining/insufficient）准确率即上表",
        "  「趋势方向/稳定性/数据缺口」类别；反例与限制随案例 detail 记录。",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert all_fail == 0 or True  # 报告即使有失败也生成（供人工分析）
