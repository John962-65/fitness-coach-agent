"""fitness-coach-agent CLI 入口（Phase 0 最小可用）"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Windows 终端(GBK) SSH 连入时的中文输入容错
try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv(Path(__file__).parent / ".env")

from coach.agent import CoachAgent


def main() -> None:
    user_id = sys.argv[1] if len(sys.argv) > 1 else "default"
    agent = CoachAgent(user_id=user_id)

    # 登录复盘（方案 A）：已建档用户启动时展示数据回顾
    if agent.profile.get("onboarding_done"):
        from coach.review import login_recap
        try:
            recap = login_recap(agent.db, agent.user_id,
                                agent.db.get_active_plan(agent.user_id))
        except Exception:
            recap = ""  # 脏数据降级（D1 完整修复在 R2：落库校验）
            print("（打卡数据有异常，本次跳过快速回顾）\n")
        if recap:
            print(recap + "\n")

    fake_hint = "（模拟模式）" if agent.llm.fake else ""
    print(f"🏋️ 健身教练 Agent 已就绪{fake_hint}，知识库 {len(agent.kb._files)} 个文件")
    print("输入 quit 退出\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见，记得好好休息。")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "退出"):
            print("再见，记得好好休息。")
            break

        reply = agent.chat(user_input)
        print(f"\n教练: {reply}\n")


if __name__ == "__main__":
    main()
