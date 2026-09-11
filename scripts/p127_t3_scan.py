#!/usr/bin/env python3
"""
P127 天正 T3 降级管线 — 扫描脚本

对 data/drawings/real/*_t3.dxf 扫描，输出：
- 每张图各类构件数（wall/door/window/column/axis/dimension）
- 总构件数、平均 confidence
- JSON 报告到 runs/t3_scan/report.json
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.baa_engine.tianzheng_t3 import TianzhengT3, build_summary

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "drawings" / "real"
OUT_DIR = Path(__file__).resolve().parents[1] / "runs" / "t3_scan"


def scan_one(dxf_path: Path) -> dict:
    """
    扫描单张图纸，返回结果摘要。

    注意：T3 加密格式 ezdxf 无法解析（返回 0 图元），
    这类文件会标记 parse_status='encrypted_or_empty' 并说明原因。
    """
    tz = TianzhengT3(verbose=False)
    t0 = time.time()
    components = tz.scan(dxf_path)
    elapsed = time.time() - t0

    summary = build_summary(components)
    summary["file"] = dxf_path.name
    summary["entity_count"] = len(components)

    # 解析状态诊断：0 构件时说明原因
    if len(components) == 0:
        parse_status = "encrypted_or_empty"
        parse_note = (
            "ezdxf 未能提取任何图元。T3 加密格式需先用 AutoCAD "
            "执行 T3→T0 命令另存为 DXF，或用 LibreCAD 另存后再扫描。"
        )
    else:
        parse_status = "ok"
        parse_note = ""

    summary["parse_status"] = parse_status
    summary["parse_note"] = parse_note

    return {
        "summary": summary,
        "elapsed_sec": round(elapsed, 2),
        "parse_status": parse_status,
        "components_sample": [
            c.to_dict() for c in components[:20]
        ],  # 前 20 条作样本
        "components_all": [c.to_dict() for c in components],
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    t3_files = sorted(DATA_DIR.glob("*_t3.dxf"))
    if not t3_files:
        print(f"[P127] 未找到 T3 测试图：{DATA_DIR}")
        sys.exit(1)

    print(f"[P127] 找到 {len(t3_files)} 张 T3 图纸")
    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": []}

    for dxf_path in t3_files:
        print(f"\n=== 扫描: {dxf_path.name} ===")
        result = scan_one(dxf_path)
        s = result["summary"]
        print(f"  解析状态: {s['parse_status']}")
        if s.get("parse_note"):
            print(f"  说明: {s['parse_note']}")
        print(f"  总构件: {s['total']}")
        for k in ["wall", "door", "window", "column", "axis", "dimension"]:
            print(f"    {k:10s}: {s['by_type'].get(k, 0)}")
        print(f"  平均 confidence: {s['avg_confidence']:.3f}")
        print(f"  耗时: {result['elapsed_sec']}s")
        report["files"].append({
            "file": result["summary"]["file"],
            "summary": result["summary"],
            "elapsed_sec": result["elapsed_sec"],
            "components": result["components_all"],
        })

    # 汇总
    all_types = {}
    total_components = 0
    total_conf = 0.0
    for f in report["files"]:
        total_components += f["summary"]["total"]
        for k, v in f["summary"]["by_type"].items():
            all_types[k] = all_types.get(k, 0) + v
        total_conf += f["summary"]["avg_confidence"] * f["summary"]["total"]

    report["aggregate"] = {
        "total_files": len(report["files"]),
        "total_components": total_components,
        "by_type": all_types,
        "avg_confidence_weighted": round(total_conf / total_components, 3) if total_components else 0,
    }

    out_path = OUT_DIR / "report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 汇总 ===")
    print(f"  文件数: {report['aggregate']['total_files']}")
    print(f"  总构件数: {report['aggregate']['total_components']}")
    for k, v in all_types.items():
        print(f"    {k:10s}: {v}")
    print(f"  平均 confidence（加权）: {report['aggregate']['avg_confidence_weighted']}")
    print(f"\n报告已写入: {out_path}")


if __name__ == "__main__":
    main()
