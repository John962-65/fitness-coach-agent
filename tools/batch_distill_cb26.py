"""collection_batch_20261006：18 个新视频 → claims（账本限额 40 次调用，超限即停）。

范围调整：发起人指示收集优先，vlog/备赛内容纳入（本轮含 TCY 47min 训练生活Vlog）。
账本：sources/maintenance/budgets/collection_batch_20261006.json（每窗口 +2，失败也计数）。
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
LEDGER = ROOT / "sources" / "maintenance" / "budgets" / "collection_batch_20261006.json"

TARGETS = {
    "谭成义": ["BV1PcNQ6AE3f", "BV1FL2MBME3G", "BV177yUB3E3B", "BV1BxxAzpEzH",
              "BV1fv4izEExY", "BV1BTWWzuEMs", "BV1utntzhE9a", "BV1hyWwzeETh",
              "BV1dJYS6EEWq"],
    "凯圣王": ["BV1fjgC62EWN", "BV1W2ga6xEBC", "BV1vHa36zERC", "BV1rya86iEVE",
              "BV1QR3E6qECQ", "BV1E9an6zExw"],
    "陈石": ["BV128Ye6xEHr", "BV18ib46eE3D", "BV145326zEsN"],
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
            # ---- 账本限额检查（每次窗口 = 2 次调用：提炼+反幻觉）----
            led = json.loads(LEDGER.read_text())
            if led["used_llm_calls"] + 2 > led["cap_llm_calls"]:
                msg = f"⛔ budget_exhausted：账本 {led['used_llm_calls']}/{led['cap_llm_calls']}，停止后续窗口"
                print(msg, flush=True)
                log.write(msg + "\n")
                sys.exit(2)
            tag = f"w{a}" if a is not None else ""
            try:
                rep = dm.distill(tf, blogger, llm, dry_run=False, start=a, end=b, tag=tag)
            except Exception as e:
                print(f"❌ {bv}[{tag or 'all'}]: {str(e)[:120]}", flush=True)
                log.write(f"FAIL CB26 {bv} {tag}: {str(e)[:200]}\n")
                log.flush()
                led = json.loads(LEDGER.read_text())
                led["used_llm_calls"] += 2
                led["failed_llm_calls"] += 2
                led["usage"].append({"at": tag or "all", "video": bv, "calls": 2, "ok": False})
                json.dump(led, open(LEDGER, "w"), ensure_ascii=False, indent=1)
                continue
            n_flag = len(rep.get("flagged") or [])
            total_valid += rep["valid"]
            total_flagged += n_flag
            led = json.loads(LEDGER.read_text())
            led["used_llm_calls"] += 2
            led["usage"].append({"at": tag or "all", "video": bv, "calls": 2, "ok": True,
                                 "valid": rep["valid"], "flagged": n_flag})
            json.dump(led, open(LEDGER, "w"), ensure_ascii=False, indent=1)
            line = f"✅ CB26 {blogger}/{bv}[{tag or 'all'}] 提炼{rep['extracted']} 有效{rep['valid']} 标红{n_flag}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

led = json.loads(LEDGER.read_text())
print(f"\n== CB26 汇总 == 有效 {total_valid}，标红 {total_flagged}，账本 {led['used_llm_calls']}/{led['cap_llm_calls']}", flush=True)
log.write(f"CB26 TOTAL valid={total_valid} flagged={total_flagged}\n")
log.close()
