"""P106 YOLO 训练数据发现脚本。

扫描测试图纸目录中的建筑类 DXF 平面图，解析后统计实体分布，
输出候选图纸列表（按实体丰富度排序），供 P106 标注管线筛选。

用法:
    python3 p106_discover.py
    python3 p106_discover.py --out data/p106_candidates.json
"""

import argparse
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer


TARGET_DIR = "/mnt/d/BaiduNetdiskDownload/测试图纸"

# 建筑类图纸关键词（排除电气/弱电/给排水/幕墙等非平面图）
BUILDING_KEYWORDS = ["建筑", "平面"]
EXCLUDE_KEYWORDS = ["目录", "说明", "详图", "节点", "立面", "剖面", "材料表", "用料表", "门窗表", "图例"]


def find_building_dxf(root: str) -> list[str]:
    """找出目标目录下所有建筑平面图 DXF。"""
    candidates = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            if not fname.lower().endswith(".dxf"):
                continue
            full = os.path.join(dirpath, fname)
            upper = fname.upper()
            if not any(kw in upper for kw in BUILDING_KEYWORDS):
                continue
            if any(kw in upper for kw in EXCLUDE_KEYWORDS):
                continue
            candidates.append(full)
    return sorted(candidates)


def try_parse(path: str, timeout: float = 30.0) -> dict | None:
    """尝试解析 DXF，超时/失败返回 None。"""
    start = time.time()
    try:
        dp = DrawingParser()
        result = dp.parse(path, file_id=os.path.basename(path))
        elapsed = time.time() - start
        if not result.success:
            return {
                "path": path,
                "success": False,
                "reason": "parse_failed",
                "elapsed_s": round(elapsed, 1),
            }
        sa = SemanticAnalyzer()
        primitives = result.primitives
        # 限制最大实体数避免 OOM
        max_ent = min(len(primitives), 10000)
        entities = sa._classify_entities(primitives[:max_ent])
        sweep_rooms = sa._sweep_line_detect_rooms(primitives[:max_ent])
        all_entities = entities + sweep_rooms

        # 去重（按 id）
        seen = set()
        unique = []
        for e in all_entities:
            if e.id not in seen:
                seen.add(e.id)
                unique.append(e)

        type_counts = Counter(e.type for e in unique)
        return {
            "path": path,
            "success": True,
            "elapsed_s": round(elapsed, 1),
            "entity_count": len(unique),
            "type_counts": dict(type_counts.most_common(30)),
            "primitives_count": len(primitives),
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "path": path,
            "success": False,
            "reason": type(e).__name__ + ": " + str(e)[:100],
            "elapsed_s": round(elapsed, 1),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/p106_candidates.json")
    ap.add_argument("--limit", type=int, default=0, help="只解析前 N 张（0=全部）")
    ap.add_argument("--time-budget", type=float, default=600.0, help="总耗时上限秒（默认10分钟）")
    args = ap.parse_args()

    candidates = find_building_dxf(TARGET_DIR)
    print(f"[P106] 找到 {len(candidates)} 张候选建筑 DXF")

    results = []
    total_time = 0.0
    for i, path in enumerate(candidates):
        if args.limit and i >= args.limit:
            break
        if total_time > args.time_budget:
            print(f"[P106] 时间预算 {args.time_budget}s 用尽，已处理 {len(results)} 张")
            break
        print(f"[P106] {i+1}/{len(candidates)} {os.path.basename(path)}...", end=" ")
        r = try_parse(path)
        results.append(r)
        total_time += r["elapsed_s"]
        if r["success"]:
            print(f"OK ({r['entity_count']} ent, {r['elapsed_s']}s)")
        else:
            print(f"FAIL: {r.get('reason','?')} ({r['elapsed_s']}s)")

    # 排序：按实体数降序
    ok = [r for r in results if r["success"]]
    ok.sort(key=lambda r: r["entity_count"], reverse=True)
    fail = [r for r in results if not r["success"]]

    print(f"\n[P106] 结果: {len(ok)} OK / {len(fail)} FAIL / {len(results)} total")
    print(f"[P106] 总耗时: {round(total_time,1)}s\n")

    # 汇总：实体类型分布
    agg = Counter()
    for r in ok:
        for t, c in r.get("type_counts", {}).items():
            agg[t] += c
    print(f"[P106] 全部成功图纸实体类型分布（共 {sum(agg.values())} 个实体）：")
    for t, c in agg.most_common(25):
        print(f"  {t:20s} {c:5d}")

    output = {
        "total_candidates": len(candidates),
        "parsed_ok": len(ok),
        "parsed_fail": len(fail),
        "total_time_s": round(total_time, 1),
        "aggregate_type_counts": dict(agg.most_common(50)),
        "ok_files": ok,
        "fail_files": fail,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[P106] 结果已写入 {args.out}")
    print(f"[P106] TOP 10 候选图纸：")
    for r in ok[:10]:
        print(f"  {r['entity_count']:5d} ent | {r['elapsed_s']:5.1f}s | {os.path.relpath(r['path'], TARGET_DIR)}")


if __name__ == "__main__":
    main()