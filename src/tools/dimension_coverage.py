"""DIMENSION 尺寸标注 → 实体属性注入覆盖率统计（Roadmap v4 T-A4，缺口 G9）。

对 DXF 图纸运行语义分析，统计关键属性（width/clear_width/height/length）在
实体 properties 上的覆盖率，以及 result["attributes"] 的非空实体数，用于量化
「尺寸/长度全 0 / 缺失」缺口的改前/改后对比。

用法:
    python src/tools/dimension_coverage.py <file.dxf|dir> [--limit N]
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser  # noqa: E402
from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # noqa: E402

KEY_PROPS = ("width", "clear_width", "height", "length")

# 尺寸标注应覆盖的关键实体类型（与 DimensionParser.DIMENSIONABLE_TYPES 对齐）
DIMENSIONABLE_TYPES = {
    "door",
    "window",
    "fire_door",
    "fire_window",
    "corridor",
    "staircase",
    "stair",
    "fire_lane",
    "room",
    "wall",
    "exit",
    "exit_door",
}


def collect_dxf(paths):
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.dxf")))
        elif p.is_file() and p.suffix.lower() == ".dxf":
            files.append(p)
    return files


def _non_zero(v):
    return isinstance(v, (int, float)) and v > 0


def _measure(files):
    parser = DrawingParser()
    agg = {
        "files": 0,
        "parsed": 0,
        "dim_total": 0,
        "ent_total": 0,
        "ent_key_total": 0,
        "ent_key_hit": 0,
        "dimable_total": 0,
        "dimable_hit": 0,
        "attrs_entities": 0,
        "attrs_missing": 0,
        "dim_source_entities": 0,
        "missing_by_type": Counter(),
        "dimable_missing_by_type": Counter(),
    }
    for f in files:
        agg["files"] += 1
        try:
            result = parser.parse(str(f))
        except Exception as e:  # 单图失败不影响整体
            print(f"  {f.name}: 解析异常 - {type(e).__name__}: {e}")
            continue
        if not result.success:
            print(f"  {f.name}: 解析失败 - {result.error}")
            continue
        agg["parsed"] += 1
        agg["dim_total"] += len(result.dimensions or [])

        analyzer = SemanticAnalyzer()
        out = analyzer.analyze(
            result.primitives,
            result.dimensions,
            block_refs=result.block_refs,
        )
        ents = out.get("entities", [])
        attrs = out.get("attributes", {}) or {}
        agg["ent_total"] += len(ents)
        agg["attrs_entities"] += len(attrs)

        # 尺寸关联实体口径：被 _bind_dimensions 匹配到的实体，其属性是否真正落库
        ent_by_id = {e.get("id"): e for e in ents}
        for eid, binding in attrs.items():
            intended = [k for k in binding if not k.startswith("_")]
            e = ent_by_id.get(eid)
            if e is None:
                agg["attrs_missing"] += 1
                continue
            props = e.get("properties", {}) or {}
            materialized = props.get("_dimension_source") is not None or any(
                _non_zero(props.get(k)) for k in intended
            )
            if not materialized:
                agg["attrs_missing"] += 1

        for e in ents:
            props = e.get("properties", {}) or {}
            if props.get("_dimension_source"):
                agg["dim_source_entities"] += 1
            etype = e.get("type")
            hit = any(_non_zero(props.get(k)) for k in KEY_PROPS)
            if hit:
                agg["ent_key_hit"] += 1
            else:
                agg["missing_by_type"][etype] += 1
            if etype in DIMENSIONABLE_TYPES:
                agg["dimable_total"] += 1
                if hit:
                    agg["dimable_hit"] += 1
                else:
                    agg["dimable_missing_by_type"][etype] += 1

    return agg


def _report(agg, label):
    def _rate(num, den):
        return round(num / den, 4) if den else 0.0

    ent_key_rate = _rate(agg["ent_key_hit"], agg["ent_total"])
    dimable_rate = _rate(agg["dimable_hit"], agg["dimable_total"])
    print(
        f"[{label}] files={agg['files']} parsed={agg['parsed']} "
        f"dims={agg['dim_total']} entities={agg['ent_total']}"
    )
    print(
        f"  关键属性(任一非0 width/clear_width/height/length)命中实体: "
        f"{agg['ent_key_hit']}/{agg['ent_total']} = {ent_key_rate} "
        f"(缺失率 {round(1 - ent_key_rate, 4)})"
    )
    print(
        f"  尺寸可标注类型命中: {agg['dimable_hit']}/{agg['dimable_total']} = {dimable_rate} "
        f"(缺失率 {round(1 - dimable_rate, 4)})"
    )
    print(
        f"  attributes(result) 非空实体数: {agg['attrs_entities']}  "
        f"_dimension_source 实体数: {agg['dim_source_entities']}"
    )
    attrs_miss_rate = _rate(agg["attrs_missing"], agg["attrs_entities"])
    print(
        f"  尺寸关联实体属性缺失率: {agg['attrs_missing']}/{agg['attrs_entities']} = "
        f"{attrs_miss_rate}"
    )

    def _top(counter, n=8):
        return ", ".join(f"{k}:{v}" for k, v in counter.most_common(n))

    print(f"  关键属性缺失 Top类型: {_top(agg['missing_by_type'])}")
    print(f"  DIMENSIONABLE 缺失 Top类型: {_top(agg['dimable_missing_by_type'])}")
    return {
        "ent_key_rate": ent_key_rate,
        "dimable_rate": dimable_rate,
        "attrs_entities": agg["attrs_entities"],
        "attrs_missing": agg["attrs_missing"],
        "attrs_miss_rate": attrs_miss_rate,
        "dim_source_entities": agg["dim_source_entities"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="DIMENSION→属性覆盖率统计（T-A4）")
    ap.add_argument("paths", nargs="+", help="一个或多个 .dxf 文件/目录")
    ap.add_argument("--limit", type=int, default=0, help="每批仅取前 N 个文件（0=全部）")
    args = ap.parse_args(argv)

    files = collect_dxf(args.paths)
    if not files:
        print("未找到任何 .dxf 文件，请检查路径。")
        return 1
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    agg = _measure(files)
    _report(agg, "current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
