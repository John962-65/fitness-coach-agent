"""R7c 批量提炼：浏览器搜索补缺口的 13 个视频（KSW 10 + TCY 3）。

凯圣王老"详解"系列（倒蹬/引体/T杆划船/哑铃划船/侧平举变式）、
功能训练/家庭私教课（核心技能包、居家）、谭成义深蹲模式/腹肌/保加利亚蹲。
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
    "凯圣王": [
        "BV1mT4y1b7Z5", "BV1tf421Q7th", "BV1Dg4y117Jb", "BV1we4y1J72N",
        "BV1Uf421v7Rf", "BV1xY411S747", "BV1MG4y1G76W", "BV1E84y1K7k7",
        "BV1ij411H773", "BV111NmeLEPP",
    ],
    "谭成义": ["BV1jQsXzREf5", "BV1Ehn7zmEHN", "BV1mcsBzYE97"],
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
                log.write(f"FAIL R7c {bv} {tag}: {str(e)[:200]}\n")
                log.flush()
                continue
            n_flag = len(rep.get("flagged") or [])
            total_valid += rep["valid"]
            total_flagged += n_flag
            line = f"✅ R7c {blogger}/{bv}[{tag or 'all'}] 提炼{rep['extracted']} 有效{rep['valid']} 标红{n_flag}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

print(f"\n== R7c 汇总 == 有效 {total_valid}，标红 {total_flagged}", flush=True)
log.write(f"R7c TOTAL valid={total_valid} flagged={total_flagged}\n")
log.close()
