"""
P121 Phase 1: 真实图纸解析诊断
扫描所有真实图纸，记录解析状态、大小、耗时、错误类型
产出: data/p121_scan_results.json
"""
import json
import signal
import time
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.baa_engine.drawing_parser import DrawingParser

REAL_DIR = Path("data/drawings/real")
PARSED_DIR = Path("data/files")  # 之前批量处理过的真实图纸副本
TIMEOUT_S = 30

parser = DrawingParser()


def scan_one(filepath: Path) -> dict:
    start = time.time()
    result = {
        "filename": filepath.name,
        "size_mb": round(filepath.stat().st_size / (1024 * 1024), 2),
        "ext": filepath.suffix.lower(),
        "status": "unknown",
        "error": None,
        "entity_count": 0,
        "elapsed_s": 0,
    }
    try:
        signal.signal(signal.SIGALRM, lambda s, f: (_ for _ in ()).throw(TimeoutError(f"超时>{TIMEOUT_S}s")))
        signal.alarm(TIMEOUT_S)

        dr = parser.parse(str(filepath))
        elapsed = time.time() - start
        result["elapsed_s"] = round(elapsed, 2)
        result["entity_count"] = len(dr.primitives or [])

        if dr.error:
            result["status"] = "error"
            result["error"] = dr.error
        elif dr.primitives is None or len(dr.primitives) == 0:
            result["status"] = "empty"
        else:
            result["status"] = "ok"

        signal.alarm(0)
    except TimeoutError:
        result["status"] = "timeout"
        result["elapsed_s"] = time.time() - start
        result["error"] = f"timeout>{TIMEOUT_S}s"
    except Exception as e:
        result["status"] = "exception"
        result["elapsed_s"] = time.time() - start
        result["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        signal.alarm(0)
    return result


def main():
    # 收集所有真实图纸
    files_real = sorted(REAL_DIR.glob("*.dxf")) + sorted(REAL_DIR.glob("*.dwg"))
    files_parsed = sorted(
        f for f in PARSED_DIR.glob("*.dxf")
        if f.stat().st_size > 20 * 1024 * 1024  # 只取大文件副本
    )
    all_files = files_real + files_parsed
    print(f"真实图纸目录: {len(files_real)} 张")
    print(f"data/files 大文件副本: {len(files_parsed)} 张")
    print(f"总计: {len(all_files)} 张")

    t0 = time.time()
    results = []
    for i, f in enumerate(all_files):
        r = scan_one(f)
        results.append(r)
        sym = "✅" if r["status"] == "ok" else "❌"
        err = f" [{r['error'][:70]}]" if r.get("error") else ""
        print(
            f"{i+1:3d}/{len(all_files):3d} {sym} {r['filename'][:50]:50s} "
            f"{r['status']:8s} {r['size_mb']:8.2f}MB "
            f"{r['entity_count']:6d}ents {r['elapsed_s']:6.1f}s{err}"
        )
        if (i + 1) % 20 == 0:
            elapsed = time.time() - t0
            print(f"  >> {i+1}/{len(all_files)}, 已用 {elapsed:.1f}s")

    # 统计
    total = len(results)
    ok = sum(1 for r in results if r["status"] == "ok")
    timeout = sum(1 for r in results if r["status"] == "timeout")
    error = sum(1 for r in results if r["status"] == "error")
    empty = sum(1 for r in results if r["status"] == "empty")
    exc = sum(1 for r in results if r["status"] == "exception")

    # 错误分类
    error_types = {}
    for r in results:
        if r["error"]:
            # 提取错误关键词
            if "天正" in r["error"] or "T3" in r["error"]:
                key = "天正T3格式"
            elif "timeout" in r["error"].lower():
                key = "超时"
            elif "不支持" in r["error"] or "format" in r["error"].lower():
                key = "格式不支持"
            elif "不存在" in r["error"]:
                key = "文件不存在"
            else:
                key = r["error"].split(":")[0].split(" ")[0][:40]
            error_types[key] = error_types.get(key, 0) + 1

    # 可用率按类型
    struct_files = [r for r in results if "结构" in r["filename"]]
    struct_ok = sum(1 for r in struct_files if r["status"] == "ok")
    elec_files = [r for r in results if "电气" in r["filename"] or "火灾自动" in r["filename"]]
    elec_ok = sum(1 for r in elec_files if r["status"] == "ok")

    stats = {
        "total": total,
        "ok": ok,
        "timeout": timeout,
        "error": error,
        "empty": empty,
        "exception": exc,
        "ok_rate": f"{ok/total*100:.1f}%" if total else "N/A",
        "unavailable_rate": f"{(total-ok)/total*100:.1f}%" if total else "N/A",
        "error_types": error_types,
        "structure_files": len(struct_files),
        "structure_ok": struct_ok,
        "elec_files": len(elec_files),
        "elec_ok": elec_ok,
        "scan_time_s": round(time.time() - t0, 1),
    }

    out_path = PARSED_DIR.parent / "p121_scan_results.json"
    with open(out_path, "w") as f:
        json.dump({"stats": stats, "files": results}, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*60}")
    print(f"P121 扫描报告")
    print(f"{'='*60}")
    print(f"总文件: {total}")
    print(f"  ✅ OK:      {ok} ({ok/total*100:.1f}%)")
    print(f"  ⏱ 超时:    {timeout}")
    print(f"  ❌ 错误:    {error}")
    print(f"  ⚠️  空:      {empty}")
    print(f"  💥 异常:    {exc}")
    print(f"  不可用率: {(total-ok)/total*100:.1f}%")
    print(f"\n按图纸类型:")
    print(f"  结构图: {struct_ok}/{len(struct_files)} OK" if struct_files else "  结构图: 0 张")
    print(f"  电气/报警: {elec_ok}/{len(elec_files)} OK" if elec_files else "  电气/报警: 0 张")
    print(f"\n错误类型:")
    for k, v in sorted(error_types.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"\n扫描耗时: {stats['scan_time_s']}s")
    print(f"结果: {out_path}")


if __name__ == "__main__":
    main()