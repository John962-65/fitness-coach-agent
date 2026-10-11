"""R4 批量抓取：P0/P1 动作与编程/营养主题视频 → 文字稿（幂等，已抓的跳过）"""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ft", ROOT / "tools" / "fetch_transcript.py")
ft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ft)

COOKIE = ROOT / "sources" / "cookies" / "bilibili.txt"

# (BV, 标注的覆盖动作/主题)
BATCH = [
    ("BV1hauq6EEfW", "romanian_deadlift"),
    ("BV1JHC5B2E6H", "incline_bench_press+chest_warmup"),
    ("BV1Myez6LEwX", "dumbbell_incline_press"),
    ("BV128bX6eExV", "lateral_raise"),
    ("BV14QKF6FEkP", "lat_pulldown"),
    ("BV1dnkmBaEyo", "lat_pulldown_variant"),
    ("BV1E8un61EVg", "dumbbell_row+rear_delt"),
    ("BV1ZxEk6cEv1", "chest_private_teaching(bench)"),
    ("BV1csj36CEf9", "shoulder_private_teaching(ohp)"),
    ("BV1HR7o6CE8q", "back_private_teaching(row)"),
    ("BV1RjTT6FEKo", "legs_private_teaching(squat)"),
    ("BV1Fzd2BBEdM", "split_leg_day"),
    ("BV1hnrWBHEu7", "split_pull_day"),
    ("BV1w9kKBfEsi", "split_last"),
    ("BV1xuUmBaErm", "bench_shoulder_pain(caution)"),
    ("BV1S8ArzREru", "beginner_programming"),
    ("BV1g2A7zdENX", "3month_cut_plan"),
    ("BV1fempB5EV5", "macros_nutrition"),
]

results = []
for bv, covers in BATCH:
    out = ROOT / "sources" / "transcripts" / "谭成义" / f"{bv}.json"
    if out.exists():
        n = len(json.loads(out.read_text()).get("segments", []))
        results.append((bv, covers, "cached", n))
        print(f"⏭  {bv} {covers} cached({n}段)", flush=True)
        continue
    for attempt in (1, 2):
        try:
            data = ft.fetch_bilibili(f"https://www.bilibili.com/video/{bv}",
                                     "谭成义", COOKIE, None, "small", False)
            data["platform"] = "bilibili"
            data["covers"] = covers
            ft.write_transcript("谭成义", data)
            results.append((bv, covers, data["source"], len(data["segments"])))
            print(f"✅ {bv} {covers} {data['source']} {len(data['segments'])}段", flush=True)
            break
        except Exception as e:
            print(f"❌ {bv} 尝试{attempt}失败: {str(e)[:120]}", flush=True)
            if attempt == 2:
                results.append((bv, covers, "FAILED", 0))
            time.sleep(5)
    time.sleep(2)

print("\n== 汇总 ==")
for r in results:
    print(*r)
ok = sum(1 for r in results if r[2] not in ("FAILED",))
print(f"成功 {ok}/{len(results)}")
sys.exit(0 if ok == len(results) else 1)
