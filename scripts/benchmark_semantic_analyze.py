#!/usr/bin/env python3
"""SemanticAnalyzer 真实大图性能基准（CI 门禁）。

P0-8 后续增强（2026-11-05）：在 CI 中加入 50MB 大图性能基准，
防止性能回退。阈值默认 total < 1.0s（优化后实测 0.425s，留 2.3× 余量）。

用法：
  python scripts/benchmark_semantic_analyze.py [--dxf <path>] [--threshold <秒>] [--runs <n>]

退出码：
  0 = 通过（total < threshold）
  1 = 失败（total >= threshold 或图纸缺失）
"""
import sys
import os
import time
import argparse
import statistics
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 默认基准图：50MB 电气图（48,844 primitives / 1,680 dimensions）
_DEFAULT_DXF = "data/files/baa-file-2319613b52cb.dxf"
_DEFAULT_THRESHOLD = 1.0  # 秒


def find_dxf(candidate: str) -> Path:
    """在 data/ 下递归查找基准图。"""
    p = Path(candidate)
    if p.exists():
        return p
    # 递归搜索 data/ 下的同名文件
    data_dir = Path("data")
    if data_dir.exists():
        for f in data_dir.rglob(p.name):
            return f
    return p  # 返回原路径（不存在，调用方处理）


def main():
    parser = argparse.ArgumentParser(description="SemanticAnalyzer 真实大图性能基准")
    parser.add_argument("--dxf", default=_DEFAULT_DXF, help="基准 DXF 路径")
    parser.add_argument("--threshold", type=float, default=_DEFAULT_THRESHOLD, help="耗时阈值（秒）")
    parser.add_argument("--runs", type=int, default=3, help="运行次数取中位数")
    args = parser.parse_args()

    dxf = find_dxf(args.dxf)
    if not dxf.exists():
        print(f"❌ 基准图缺失: {dxf}（.gitignore 排除数据目录，需配置图纸数据源）")
        return 2

    print(f"📐 基准图: {dxf} ({dxf.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"⏱  阈值: total < {args.threshold}s，运行 {args.runs} 次取中位数")

    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer

    parser = DrawingParser()

    # 解析（不计入阈值，只测 analyze）
    rp = parser.parse(str(dxf), "t")
    prims = rp.primitives or []
    dims = rp.dimensions or []
    print(f"   primitives={len(prims)}, dimensions={len(dims)}")

    # analyze 计时（多次取中位数）
    # 注意：SemanticAnalyzer 有 _analyze_cache（hash→result），
    # 同一实例第二次起命中缓存返回 0.000s。必须每次新建实例测真实性能。
    times = []
    for i in range(args.runs):
        sa = SemanticAnalyzer()  # 新建实例，避免缓存命中
        t0 = time.perf_counter()
        sa.analyze(prims, dims)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        print(f"   run {i + 1}: {elapsed:.3f}s")

    median = statistics.median(times)
    print(f"📊 中位数: {median:.3f}s")

    if median < args.threshold:
        print(f"✅ 通过: {median:.3f}s < {args.threshold}s")
        return 0
    else:
        print(f"❌ 失败: {median:.3f}s >= {args.threshold}s（性能回退，需排查）")
        return 1


if __name__ == "__main__":
    sys.exit(main())
