"""R7b 批量提炼：陈石首批 18 个视频（官方空间 uid=364281292）→ claims/cs.yaml。

视频均 <9 分钟，单窗口即可。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("distill_mod", ROOT / "tools" / "distill.py")
dm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dm)

from coach.llm import LLMClient  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

TARGETS = [
    "BV1jpeq6QEPw", "BV1qZKq6SE5T", "BV1Y1tb6GEgw", "BV1S7bN6ME2g",
    "BV1Tiec6TEv1", "BV1xpYT6jEAJ", "BV1AzgU6TEDJ", "BV17hTM6zEXt",
    "BV1CfMZ64ErB", "BV1NEtS6HEux", "BV1fZT161Ewh", "BV1bNb966EQG",
    "BV1TyMg6aE4R", "BV1gzNZ68EUd", "BV13qgV6QEZP", "BV1Ag376SEUM",
    "BV174u86zEUf", "BV1u4NS6iEs4",
]

load_dotenv(ROOT / ".env")
llm = LLMClient()
if llm.fake:
    sys.exit("FAKE_LLM 开着，提炼结果为占位不能入库——用真实 key 跑。")

log_path = ROOT / "sources" / "distill_log.txt"
log = open(log_path, "a", encoding="utf-8")

total_valid = total_flagged = 0
for bv in TARGETS:
    tf = ROOT / "sources" / "transcripts" / "陈石" / f"{bv}.json"
    if not tf.exists():
        print(f"⏭ {bv} 无文字稿", flush=True)
        continue
    try:
        rep = dm.distill(tf, "陈石", llm, dry_run=False)
    except Exception as e:
        print(f"❌ {bv}: {str(e)[:120]}", flush=True)
        log.write(f"FAIL R7b {bv}: {str(e)[:200]}\n")
        log.flush()
        continue
    n_flag = len(rep.get("flagged") or [])
    total_valid += rep["valid"]
    total_flagged += n_flag
    line = f"✅ R7b 陈石/{bv} 提炼{rep['extracted']} 有效{rep['valid']} 标红{n_flag}"
    print(line, flush=True)
    log.write(line + "\n")
    log.flush()

print(f"\n== R7b 汇总 == 有效 {total_valid}，标红 {total_flagged}", flush=True)
log.write(f"R7b TOTAL valid={total_valid} flagged={total_flagged}\n")
log.close()
