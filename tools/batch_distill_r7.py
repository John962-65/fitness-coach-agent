"""R7 批量提炼：2026-10-04 新抓取的 TCY 11 + KSW 9 文字稿 → claims draft。

长视频按 25 分钟窗口切片（与 batch_distill_r4.py 同策略），
只处理本轮清单内的文件，避免重复提炼存量视频。
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("distill_mod", ROOT / "tools" / "distill.py")
dm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dm)

from coach.llm import LLMClient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

WINDOW = 1500.0

TARGETS = {
    "谭成义": [
        "BV1z8Th6BEij", "BV1UsYe6fEiR", "BV1tRhs6hE8j", "BV1GzEg6wEVb",
        "BV1pZiZBxE8y", "BV1MvwxzGEio", "BV1LbcWzyE64", "BV1gyiqByEWZ",
        "BV1ND5S6pEgx", "BV1succzFE4v", "BV1wvMF6ZEqL",
    ],
    "凯圣王": [
        "BV1XNUkBfERC", "BV1VqqnBuETA", "BV1oxUpBCEwc", "BV1yyU8ByEgS",
        "BV1cUevzTEb4", "BV1dgtc6aEPL", "BV1Db8Q6uEbZ", "BV1trao6WEMs",
        "BV1qtGx6AEMz",
    ],
}

load_dotenv(ROOT / ".env")
llm = LLMClient()
if llm.fake:
    sys.exit("FAKE_LLM 开着，提炼结果为占位不能入库——用真实 key 跑。")

log_path = ROOT / "sources" / "distill_log.txt"
log = open(log_path, "a", encoding="utf-8")

total_valid = total_flagged = total_calls = 0
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
                log.write(f"FAIL R7 {bv} {tag}: {str(e)[:200]}\n")
                log.flush()
                continue
            n_flag = len(rep.get("flagged") or [])
            total_valid += rep["valid"]
            total_flagged += n_flag
            total_calls += 2
            line = f"✅ R7 {blogger}/{bv}[{tag or 'all'}] 提炼{rep['extracted']} 有效{rep['valid']} 标红{n_flag}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

print(f"\n== R7 汇总 == 有效 {total_valid}，标红 {total_flagged}，LLM 调用约 {total_calls}", flush=True)
log.write(f"R7 TOTAL valid={total_valid} flagged={total_flagged}\n")
log.close()
