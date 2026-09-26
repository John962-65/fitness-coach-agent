"""pytest 公共配置：全部测试走 FAKE_LLM + 临时库，不碰真实 data/coach.db"""
import os
import sys
from pathlib import Path

os.environ["FAKE_LLM"] = "1"
sys.path.insert(0, str(Path(__file__).parent))
