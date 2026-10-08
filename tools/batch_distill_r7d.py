"""R7d 批量提炼：第三波 38 个视频（陈石 20 + 凯圣王 10 + 谭成义 8）。

陈石：补剂/糖/有氧/训练判断/女性/酒精/久坐/运动时间。
凯圣王：新手入门一分化/二分化带练/FMS筛查/女性系列③④/蛋白质/碳水/皮质醇/睡眠。
谭成义：拉伸/泡沫轴/肩痛/体态/增肌减脂同时/肩肘腕调整/安全进步/有氧与力量。
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path("/home/johb/fitness-coach-agent")
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("distill_mod", ROOT / "tools" / "distill.py")
dm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dm)

from coach.llm import LLMClient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

WINDOW = 1500.0

TARGETS = {
    "陈石": [
        "BV1icM86YEif", "BV1niKQ6wEB2", "BV1E1AUzoELJ", "BV1CzjY6kE4x",
        "BV1azjX65Euc", "BV1b2hR6EE2H", "BV1hN8z6MEYS", "BV1DH3a6qEaV",
        "BV1NRM26hEWX", "BV1LqaJ6aEQb", "BV1VnA8zAEf5", "BV1VMw4zSEKP",
        "BV16xFgzLE9K", "BV1uS6aB6Ezk", "BV1SDf4BuEJD", "BV1sUkKBAERi",
        "BV1NMTi6FEn7", "BV11QFbzgE2S", "BV1pG7w69EJm", "BV1H9aV6xEQW",
    ],
    "凯圣王": [
        "BV14v4y1G7A3", "BV1A1s3zUEN6", "BV1Nc411P7nc", "BV14dGX6fEhq",
        "BV1N6786uEts", "BV1A4zjB7EcE", "BV1kSsozkEEJ", "BV14ys4zeEVJ",
        "BV1rRSKBCE5p", "BV1s44y1q7vt",
    ],
    "谭成义": [
        "BV1EkV96nEyg", "BV1Xs97BqEsQ", "BV1LYzWBxEvT", "BV1Dbz4BRErt",
        "BV1cTSsBbEJy", "BV1QF4r6BE2S", "BV1W1BFBKEdR", "BV1RsigBkEUN",
    ],
}

load_dotenv(ROOT / ".env")
llm = LLMClient()
if llm.fake:
    sys.exit("FAKE_LLM 开着，提炼结果为占位不能入库——用真实 key 跑。")

log_path = ROOT / "sources" / "distill_log.txt"
log = open(log_path, "a", encoding="utf-8")

total_valid = total_flagged = 0
for blogger, vids in TARGETS.items():
    for bv in vids:
        tf = ROOT / "sources" / "transcripts" / blogger / f"{bv}.json"
        if not tf.exists():
            print(f"⏭ {bv} 无文字稿", flush=True)
            continue
        data = json.loads(tf.read_text(encoding="utf-8"))
        segs = data.get("segments") or []
        if not segs:
            print(f"⏭ {bv} 空", flush=True)
            continue
        dur = max(s.get("end", 0) for s in segs)
        windows = ([(None, None)] if dur <= WINDOW + 300
                   else [(a, min(a + WINDOW, dur)) for a in range(0, int(dur), int(WINDOW))])
        for a, b in windows:
            tag = f"w{a}" if a is not None else ""
            try:
                rep = dm.distill(tf, blogger, llm, dry_run=False, start=a, end=b, tag=tag)
            except Exception as e:
                print(f"❌ {bv}[{tag or 'all'}]: {str(e)[:120]}", flush=True)
                log.write(f"FAIL R7d {bv} {tag}: {str(e)[:200]}\n")
                log.flush()
                continue
            n_flag = len(rep.get("flagged") or [])
            total_valid += rep["valid"]
            total_flagged += n_flag
            line = f"✅ R7d {blogger}/{bv}[{tag or 'all'}] 提炼{rep['extracted']} 有效{rep['valid']} 标红{n_flag}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

print(f"\n== R7d 汇总 == 有效 {total_valid}，标红 {total_flagged}", flush=True)
log.write(f"R7d TOTAL valid={total_valid} flagged={total_flagged}\n")
log.close()
