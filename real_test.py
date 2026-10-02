"""真实 API 对话冒烟：仅显式执行脚本时运行，不在导入/pytest 收集时运行。"""
import sys
import tempfile
from pathlib import Path


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
    sys.path.insert(0, str(Path(__file__).parent))
    from coach.agent import CoachAgent

    # 冒烟结果不应写进真实用户库。
    with tempfile.TemporaryDirectory(prefix="coach-smoke-") as tmp:
        agent = CoachAgent(user_id="real_test", db_path=Path(tmp) / "smoke.db")
        try:
            print(f"知识库: {len(agent.kb._files)} 个文件 | 模型: {agent.llm.model}\n")
            cases = [
                "我减脂三周了，体重两周没动，是不是平台期？",
                "深蹲的时候臀部没感觉，都是大腿前侧酸",
                "我今天训练的时候胸闷心慌",
            ]
            for q in cases:
                print(f"{'='*60}\n你: {q}\n{'-'*60}")
                reply = agent.chat(q)
                print(f"教练: {reply}\n")
        finally:
            agent.db.conn.close()


if __name__ == "__main__":
    main()
