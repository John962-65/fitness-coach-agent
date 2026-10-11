"""R6c：凯圣王首批素材 → 文字稿 → claims draft"""
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("ft", ROOT / "tools" / "fetch_transcript.py")
ft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ft)
spec2 = importlib.util.spec_from_file_location("dm", ROOT / "tools" / "distill.py")
dm = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(dm)
from coach.llm import LLMClient  # noqa: E402

COOKIE = ROOT / "sources" / "cookies" / "bilibili.txt"
BATCH = [
    ("BV1FcdZBNEm3", "split_programming"),          # 三分化①训练计划
    ("BV1zTf2B3Ead", "mechanical_tension"),          # 机械张力
    ("BV1SD4C63EUV", "lat_pulldown_omnibus"),        # 高位下拉大全
    ("BV1xw3B61EUg", "romanian_deadlift"),
    ("BV1vz4R6JEmr", "bulgarian_split_squat"),
    ("BV1zoaw69Eys", "dumbbell_row"),
    ("BV1vFgQ6hEWH", "lateral_raise"),
    ("BV1qF6wBaEWu", "rdl_breakdown"),
]

llm = LLMClient()
for bv, covers in BATCH:
    out = ROOT / "sources" / "transcripts" / "凯圣王" / f"{bv}.json"
    if not out.exists():
        try:
            data = ft.fetch_bilibili(f"https://www.bilibili.com/video/{bv}",
                                     "凯圣王", COOKIE, None, "small", False)
            data["platform"] = "bilibili"
            data["covers"] = covers
            ft.write_transcript("凯圣王", data)
            print(f"✅ 抓取 {bv} {covers} {data['source']} {len(data['segments'])}段", flush=True)
        except Exception as e:
            print(f"❌ 抓取 {bv}: {str(e)[:100]}", flush=True)
            continue
    try:
        rep = dm.distill(out, "凯圣王", llm)
        print(f"   提炼 {rep['valid']} 条（标红 {len(rep['flagged'])}）", flush=True)
    except Exception as e:
        print(f"❌ 提炼 {bv}: {str(e)[:100]}", flush=True)
    time.sleep(2)
