"""Run full 16-drawing baseline with isolated analysis (subprocess parses file)."""
import time
import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.parsers.isolated_analysis import analyze_isolated_file

# Config
SEMANTIC_ANALYSIS_TIMEOUT_SEC = 120.0
LARGE_DRAWING_THRESHOLD = 50000

DATA_DIR = PROJECT_ROOT / "data"
DRAWINGS_DIR = DATA_DIR / "drawings" / "real"

FILES = [
    "baa-file-00582518a28e.dxf",
    "baa-file-00b3795cf6c2.dxf",
    "baa-file-016c23eb4018.dxf",
    "baa-file-007a2fa192ad.dxf",
    "baa-file-019ec606295e.dxf",
    "东莞通-建筑-外部参照（不打印）.dxf",
    "baa-file-006dafd086dd.dxf",
    "baa-file-030e6425d4fe.dxf",
    "baa-file-040d4ef55345.dxf",
    "baa-file-02f8d4ff2c6b.dxf",
    "baa-file-0071f9c2d170.dxf",
    "baa-file-02322fef68fd.dxf",
    "baa-file-014d56a34615.dxf",
    "baa-file-03d862eba9e3.dxf",
    "baa-file-05f5853faa62.dxf",
    "baa-file-014d56a34615.dxf",  # 16th: duplicate
]

# Build path map
FILE_PATHS = {}
for f in FILES:
    p1 = DATA_DIR / "files" / f
    p2 = DRAWINGS_DIR / f
    if p1.exists():
        FILE_PATHS[f] = p1
    elif p2.exists():
        FILE_PATHS[f] = p2

def main():
    print("=" * 70)
    print("BAA Full Baseline (16 drawings · isolated process)")
    print("=" * 70)

    parser = DrawingParser()
    total_start = time.time()

    results = []
    for i, fname in enumerate(FILES, 1):
        path = FILE_PATHS.get(fname)
        if not path:
            print(f"\n[{i}/{len(FILES)}] SKIP (not found): {fname}")
            continue

        print(f"\n[{i}/{len(FILES)}] {fname}")
        t0 = time.time()

        # 父进程仅解析 primitives 计数
        try:
            r = parser.parse(str(path))
            primitives_count = len(r.primitives)
            print(f"  primitives: {primitives_count:,}")
        except Exception as e:
            print(f"  [ERROR] parse failed: {e}")
            results.append({"file": fname, "status": "parse_error", "primitives": 0})
            continue

        # 使用独立进程分析（子进程自行解析图纸）
        t1 = time.time()
        iso_result = analyze_isolated_file(
            dxf_path=str(path),
            max_entities=100000,
            soft_timeout_sec=SEMANTIC_ANALYSIS_TIMEOUT_SEC,
        )
        elapsed = time.time() - t1

        if iso_result.status == "ok":
            result = iso_result.result
            entities = result.get("entities", [])
            relations = result.get("relations", [])
            print(f"  entities: {len(entities):,}  relations: {len(relations):,}")
            print(f"  elapsed: {elapsed:.1f}s  [ISOLATED]")
            status = "ok"
            entities_count = len(entities)
        else:
            print(f"  [ISOLATED_{iso_result.status.upper()}] elapsed={elapsed:.1f}s  {iso_result.error}")
            status = iso_result.status
            entities_count = 0

        results.append({
            "file": fname,
            "primitives": primitives_count,
            "entities": entities_count,
            "elapsed": elapsed,
            "status": status,
        })

    # Summary
    total_elapsed = time.time() - total_start
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    err_count = len(results) - ok_count
    print(f"Total: {len(results)}  |  OK: {ok_count}  |  Failed/Timeout: {err_count}")
    print(f"Total time: {total_elapsed:.1f}s")
    print(f"Config: soft_timeout={SEMANTIC_ANALYSIS_TIMEOUT_SEC}s, large_drawing_threshold={LARGE_DRAWING_THRESHOLD:,} primitives")

    # Save JSON
    output_file = PROJECT_ROOT / "scripts" / "entity_baseline_output.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nResults saved: {output_file}")

if __name__ == "__main__":
    main()