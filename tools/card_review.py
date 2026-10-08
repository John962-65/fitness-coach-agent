#!/usr/bin/env python3
"""核心卡审批入口（任务书 §12.4/12.5，2026-10-06 机制启用）。

用法：
  python3 tools/card_review.py --list                       # 列出全部卡与状态
  python3 tools/card_review.py --show <card_id>             # 查看卡片全文与绑定
  python3 tools/card_review.py --approve <card_id> --by 发起人 --note "核对依据"
  python3 tools/card_review.py --return <card_id> --by 发起人 --note "退回原因"
  python3 tools/card_review.py --hold <card_id> --by 发起人 --note "暂不使用的原因"

规则：
- 批准只覆盖卡片展示的正文/条件/用途/绑定版本（指纹绑定，内容变化自动失效）；
- 底层 claims 的 status 不被本工具修改；
- --approve/--return 必须附 --by 与 --note，不代填。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coach.cards import (CardError, approval_valid, approve_card, card_fingerprint,
                         load_cards, validate_card)

CARDS_DIR = ROOT / "sources" / "maintenance" / "cards"


def _save(card: dict) -> None:
    (CARDS_DIR / f"{card['card_id']}.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=1), "utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", metavar="CARD_ID")
    ap.add_argument("--approve", metavar="CARD_ID")
    ap.add_argument("--return", dest="ret", metavar="CARD_ID")
    ap.add_argument("--hold", metavar="CARD_ID", help="暂不使用（不通过也不退回）")
    ap.add_argument("--by", default="")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    cards = load_cards()
    if args.list:
        for cid, c in cards.items():
            ap = c.get("review") or {}
            state = ("approved" if approval_valid(c, ap) else
                     "returned" if ap.get("status") == "returned" else "待审")
            print(f"{cid} | v{c['version']} | {c['purpose']} | 绑定{len(c['bindings'])}条 | {state}")
        return 0
    if args.show:
        c = cards.get(args.show)
        if not c:
            sys.exit(f"卡不存在: {args.show}")
        print(json.dumps(c, ensure_ascii=False, indent=1))
        return 0
    if args.approve or args.ret or args.hold:
        cid = args.approve or args.ret or args.hold
        c = cards.get(cid)
        if not c:
            sys.exit(f"卡不存在: {cid}")
        errs = validate_card(c)
        if errs:
            sys.exit(f"卡结构不合法，拒绝审批: {errs}")
        if not args.by or not args.note:
            sys.exit("--approve/--return/--hold 必须附 --by 与 --note（不代填）")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        if args.approve:
            c["review"] = approve_card(c, by=args.by, note=args.note, at=now)
            c["status"] = "approved_v%s" % c["version"]
        elif args.hold:
            c["review"] = {"status": "on_hold", "by": args.by, "note": args.note,
                           "at": now, "card_version": c["version"]}
            c["status"] = "on_hold"
        else:
            c["review"] = {"status": "returned", "by": args.by, "note": args.note,
                           "at": now, "card_version": c["version"]}
            c["status"] = "returned"
        _save(c)
        print(f"{cid} -> {c['status']}（{c['review']['status']}，指纹 {card_fingerprint(c)[:12]}…）")
        if args.approve and not approval_valid(c, c["review"]):
            sys.exit("内部错误：审批写入后即失效")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
