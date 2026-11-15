"""Extended baseline: run isolated-process semantic analysis on ALL unique drawings.

Deduplicates by MD5 content hash, then runs analyze_isolated_file on every
unique drawing with >0 primitives. Supports resume (saves progress JSON).

Usage:
  python scripts/run_extended_baseline.py              # run all unique drawings
  python scripts/run_extended_baseline.py --max 100    # limit to 100 drawings
"""
import time
import json
import hashlib
import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.parsers.isolated_analysis import analyze_isolated_file

SEMANTIC_ANALYSIS_TIMEOUT_SEC = 120.0
FILES_DIR = PROJECT_ROOT / "data" / "files"
OUTPUT_FILE = PROJECT_ROOT / "scripts" / "extended_baseline_output.json"
PROGRESS_FILE = PROJECT_ROOT / "scripts" / "extended_baseline_progress.json"


def dedup_unique():
    """Return list of unique drawings (by MD5), sorted by primitives desc."""
    seen = {}
    for f in sorted(FILES_DIR.glob("*.dxf")):
        h = hashlib.md5(f.read_bytes()).hexdigest()
        if h not in seen:
            seen[h] = f
    return list(seen.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None, help="Max drawings to run")
    ap.add_argument("--resume", action="store_true", help="Resume from progress file")
    args = ap.parse_args()

    unique = dedup_unique()
    print(f"Unique drawings: {len(unique)}")

    parser = DrawingParser()
    results = {}
    if args.resume and PROGRESS_FILE.exists():
        results = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        print(f"Resuming: {len(results)} already done")

    total_start = time.time()
    done = 0
    for f in unique:
        if f.name in results:
            continue
        # Probe primitives (fast parse)
        try:
            r = parser.parse(str(f))
            n_prim = len(r.primitives)
        except Exception as e:
            results[f.name] = {"status": "parse_error", "primitives": 0, "elapsed": 0}
            continue
        if n_prim == 0:
            results[f.name] = {"status": "empty", "primitives": 0, "elapsed": 0}
            continue

        t0 = time.time()
        iso = analyze_isolated_file(
            dxf_path=str(f),
            max_entities=100000,
            soft_timeout_sec=SEMANTIC_ANALYSIS_TIMEOUT_SEC,
        )
        elapsed = time.time() - t0
        if iso.status == "ok":
            res = iso.result
            results[f.name] = {
                "primitives": n_prim,
                "entities": len(res.get("entities", [])),
                "relations": len(res.get("relations", [])),
                "elapsed": elapsed,
                "status": "ok",
            }
        else:
            results[f.name] = {
                "primitives": n_prim,
                "entities": 0,
                "elapsed": elapsed,
                "status": iso.status,
                "error": iso.error,
            }
        done += 1
        # Save progress every 10
        if done % 10 == 0:
            PROGRESS_FILE.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
            print(f"  ...{done} done, {time.time()-total_start:.0f}s elapsed")

        if args.max and done >= args.max:
            break

    # Final summary
    ok = sum(1 for v in results.values() if v.get("status") == "ok")
    fail = sum(1 for v in results.values() if v.get("status") not in ("ok", "empty"))
    print(f"\n=== Extended Baseline Summary ===")
    print(f"Total unique: {len(unique)}")
    print(f"OK: {ok}  |  Empty: {sum(1 for v in results.values() if v.get('status')=='empty')}  |  Failed: {fail}")
    print(f"Total time: {time.time()-total_start:.0f}s")

    OUTPUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Results saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
