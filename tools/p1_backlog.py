"""P1 高频动作审核包（设计书 24.1）：先审计划模板实际用到的动作，不追求全量

> 第一优先级是"一个小而完整的可信教练版本"：10–15 个高频动作 +
> 一套有出处的方法论。本工具从 5 套槽位模板的 default 动作反查 claims，
> 按 24.1 只列 cue / method / error / self_check（anecdote 等暂不处理），
> 并标注反幻觉标记与合作视频 speaker 待确认条目，生成发起人的审核清单。

用法：
  python3 tools/p1_backlog.py                          # 打印清单
  python3 tools/p1_backlog.py --out review_backlog_P1.md
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coach.plan import (BUSY_SLOTS, FULL_BODY_A, FULL_BODY_B,  # noqa: E402
                        PPL_ADVANCED_SLOTS, PPL_SLOTS)

CLAIMS = ROOT / "claims"
BLOGGER_FILE = {"ksw": "凯圣王", "tcy": "谭成义", "cs": "陈石"}
BLOGGER_ORDER = {"凯圣王": 0, "谭成义": 1, "陈石": 2}
# 24.1：优先 cue / error / self_check（method 挂 cues 字段，一并纳入）
P1_TYPES = ("cue", "method", "error", "self_check")
ROLE_LABEL = {"main": "主力", "secondary": "次要", "accessory": "辅助"}


def _git_short() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _template_defaults() -> list[tuple[str, str]]:
    """槽位模板的 default 动作（去重；主力角色优先，同级别按首次出现序）"""
    slots = [*BUSY_SLOTS, *FULL_BODY_A, *FULL_BODY_B,
             *[s for day in PPL_SLOTS.values() for s in day],
             *[s for day in PPL_ADVANCED_SLOTS.values() for s in day]]
    role_rank = {"main": 0, "secondary": 1, "accessory": 2}
    first_pos: dict[str, int] = {}
    best_role: dict[str, str] = {}
    for i, s in enumerate(slots):
        d = s["default"]
        if d not in first_pos:
            first_pos[d] = i
            best_role[d] = s["role"]
        elif role_rank[s["role"]] < role_rank[best_role[d]]:
            best_role[d] = s["role"]
    ordered = sorted(first_pos, key=lambda d: (role_rank[best_role[d]], first_pos[d]))
    return [(d, best_role[d]) for d in ordered]


def _load_claims() -> list[dict]:
    claims: list[dict] = []
    for f in sorted(CLAIMS.glob("*.yaml")):
        if f.stem == "conflicts":
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(data, list):
            claims += [c for c in data if isinstance(c, dict) and c.get("id")]
    return claims


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from coach.exercises import library as exercise_lib

    claims = _load_claims()
    defaults = _template_defaults()

    lines: list[str] = []
    p1_total = 0
    p1_flagged = 0
    p1_speaker = 0
    gap_actions: list[str] = []

    lines.append("# P1 高频动作审核包（设计书 24.1）")
    lines.append("")
    lines.append(f"> 生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}｜基线 commit：`{_git_short()}`")
    lines.append("> 目标人群：无明确医疗禁忌、有一定训练基础、每周 2–4 次的健身房用户")
    lines.append("> 审核范围：槽位模板实际用到的动作；类型只列 cue/method/error/self_check"
                "（anecdote 等本轮跳过）")
    lines.append("")

    for ex_id, role in defaults:
        ex = exercise_lib.get(ex_id) or {}
        name = ex.get("name", ex_id)
        status = ex.get("status", "?")
        rel = [c for c in claims if ex_id in (c.get("exercises") or [])]
        p1 = [c for c in rel if c.get("type") in P1_TYPES]
        skip = len(rel) - len(p1)
        flagged = [c for c in p1 if c.get("anti_hallucination") == "FLAGGED"]
        speaker_pending = [c for c in p1 if c.get("speaker") == "待确认"]
        p1_total += len(p1)
        p1_flagged += len(flagged)
        p1_speaker += len(speaker_pending)

        lines.append(f"## {name}（`{ex_id}`）· {ROLE_LABEL.get(role, role)}"
                     f"{'｜动作库 status: ' + status if status != 'approved' else ''}")
        lines.append("")
        if not p1:
            gap_actions.append(f"{name}（{ex_id}）")
            lines.append("**暂无 P1 类型素材**——本轮只能用通用知识教学（标 general，不点名博主）。")
            lines.append("")
            continue

        by_blogger: dict[str, list[dict]] = {}
        for c in p1:
            by_blogger.setdefault(c.get("blogger", "?"), []).append(c)
        for blogger in sorted(by_blogger, key=lambda b: BLOGGER_ORDER.get(b, 9)):
            cs = by_blogger[blogger]
            kinds: dict[str, int] = {}
            for c in cs:
                kinds[c["type"]] = kinds.get(c["type"], 0) + 1
            kind_text = "、".join(f"{k}×{v}" for k, v in sorted(kinds.items()))
            fl = f"，🚩 反幻觉标记 {len([c for c in cs if c.get('anti_hallucination') == 'FLAGGED'])} 条（优先核）" \
                if any(c.get("anti_hallucination") == "FLAGGED" for c in cs) else ""
            lines.append(f"- **{blogger}**：{len(cs)} 条（{kind_text}{fl}）")
        if speaker_pending:
            vids = sorted({c.get("video", "?") for c in speaker_pending})
            lines.append(f"- ⚠️ **speaker 待确认 {len(speaker_pending)} 条**"
                         f"（{('、'.join(vids))}，双人出镜/字幕不分说话人，审核时先定归属，"
                         "无法确认就不作个人归因）")
        if skip:
            lines.append(f"- 另有 {skip} 条非 P1 类型（anecdote/principle 等，本轮跳过）")
        lines.append("- 审核命令：")
        for blogger in sorted(by_blogger, key=lambda b: BLOGGER_ORDER.get(b, 9)):
            lines.append(f"  ```bash")
            lines.append(f"  python3 tools/review_ui.py --blogger {blogger} "
                         f"--exercise {ex_id} --types cue,error,self_check,method")
            lines.append(f"  ```")
        lines.append("")

    est_lo = p1_total * 20 // 60
    est_hi = p1_total * 30 // 60
    lines.append("---")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 模板动作 {len(defaults)} 个；P1 类型待审条目 **{p1_total} 条**"
                 f"（🚩 反幻觉标记 {p1_flagged}，speaker 待确认 {p1_speaker}）")
    lines.append(f"- 预估审核时长：每条 20–30 秒 ≈ **{est_lo}–{est_hi} 分钟**（不含跳转视频核对画面）")
    if gap_actions:
        lines.append(f"- 无 P1 素材的动作（{len(gap_actions)}）：{'、'.join(gap_actions)}"
                     "——教学时用通用知识，审核条目到位后再补")
    lines.append("")
    lines.append("审核顺序建议：主力动作在前（深蹲/卧推/硬拉类，条目多、教练价值最高）；"
                 "🚩 条目优先核对原文；speaker 待确认的先定归属再 approve。"
                 "approve 后跑 `python3 tools/review_ui.py --apply` 挂到动作库，"
                 "运行时即通过 get_exercise_coaching 带出处引用。")

    text = "\n".join(lines) + "\n"
    if args.out:
        (ROOT / args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {ROOT / args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
