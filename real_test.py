"""真实 API 对话测试：三个典型场景"""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.path.insert(0, str(Path(__file__).parent))

from coach.agent import CoachAgent

agent = CoachAgent(user_id="real_test")
print(f"知识库: {len(agent.kb._files)} 个文件 | 模型: {agent.llm.model}\n")

cases = [
    "我减脂三周了，体重两周没动，是不是平台期？",
    "深蹲的时候臀部没感觉，都是大腿前侧酸",
    "我今天训练的时候胸闷心慌",
]

for q in cases:
    print(f"{'='*60}\n你: {q}\n{'-'*60}")
    reply = agent.chat(q)
    tool_calls = [m for m in agent.messages if m.get("role") == "tool"]
    if tool_calls:
        last = tool_calls[-1]["content"][:60].replace("\n", " ")
        print(f"[系统: 加载了知识文件 - {last}...]")
    print(f"教练: {reply}\n")
