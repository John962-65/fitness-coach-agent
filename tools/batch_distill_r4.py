"""R4 批量提炼：transcripts → claims draft（长视频按 25 分钟切片）"""
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

WINDOW = 1500.0
llm = LLMClient()
tdir = ROOT / "sources" / "transcripts" / "谭成义"
log_path = ROOT / "sources" / "distill_log.txt"
log = open(log_path, "a", encoding="utf-8")

total_valid = total_flagged = 0
for tf in sorted(tdir.glob("BV*.json")):
    data = json.loads(tf.read_text(encoding="utf-8"))
    segs = data.get("segments") or []
    if not segs:
        print(f"⏭ {tf.stem} 空", flush=True)
        continue
    dur = max(s.get("end", 0) for s in segs)
    windows = ([(None, None)] if dur <= WINDOW + 300
               else [(a, min(a + WINDOW, dur)) for a in range(0, int(dur), int(WINDOW))])
    for wi, (a, b) in enumerate(windows):
        tag = f"w{a}" if a is not None else ""
        try:
            rep = dm.distill(tf, "谭成义", llm, dry_run=False,
                             start=a, end=b, tag=tag)
        except Exception as e:
            print(f"❌ {tf.stem}[{tag}]: {str(e)[:100]}", flush=True)
            log.write(f"FAIL {tf.stem} {tag}: {str(e)[:200]}\n")
            log.flush()
            continue
        n_flag = len(rep.get("flagged") or [])
        total_valid += rep["valid"]
        total_flagged += n_flag
        line = (f"✅ {tf.stem}[{tag or 'all'}] 提炼{rep['extracted']} "
                f"有效{rep['valid']} 标红{n_flag}")
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

print(f"\n== 汇总 == 有效 {total_valid}，标红 {total_flagged}", flush=True)
log.write(f"TOTAL valid={total_valid} flagged={total_flagged}\n")
log.close()
