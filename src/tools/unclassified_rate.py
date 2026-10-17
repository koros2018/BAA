"""未分类率统计脚本（Roadmap v4 T-A2，关联缺口 G7）

对 DXF 图纸运行语义分析，统计 `classification_stats`（total / unclassified /
rate）与块引用汇总，用于量化块语义分类对未分类率的贡献。

用法:
    python src/tools/unclassified_rate.py <file.dxf|dir> [<...>] [--baseline]

--baseline: 用 mock 关闭图例（ATTRIB）兜底，输出「基线 vs 现状」对比与下降百分比。
"""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser  # noqa: E402
from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # noqa: E402

# 关闭图例兜底的 patch 目标：classify 通过 `from .legend_rules import lookup_legend`
# 引入了同名符号，因此必须 patch classify 模块内的引用。
LEGEND_PATCH_TARGET = "src.baa_engine.semantic_analyzer.classify.lookup_legend"


def collect_dxf(paths):
    """递归收集 .dxf 文件（目录输入）。"""
    files = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.dxf")))
        elif p.is_file() and p.suffix.lower() == ".dxf":
            files.append(p)
    return files


def _run(files, disable_legend):
    """执行一批图纸分析，返回 (per_file, totals, block_refs_summary)。"""
    parser = DrawingParser()
    per_file = []
    tot_total = 0
    tot_unc = 0
    tot_block_default = 0
    br_total = 0
    br_with_attrib = 0
    br_unique = set()

    def _analyze_all():
        nonlocal tot_total, tot_unc, tot_block_default, br_total, br_with_attrib
        for f in files:
            result = parser.parse(str(f))
            if not result.success:
                per_file.append((str(f), None, result.error))
                continue
            analyzer = SemanticAnalyzer()
            out = analyzer.analyze(
                result.primitives,
                result.dimensions,
                block_refs=result.block_refs,
            )
            st = out.get("classification_stats", {})
            per_file.append((str(f), st, None))
            tot_total += st.get("total", 0)
            tot_unc += st.get("unclassified", 0)
            tot_block_default += st.get("block_default", 0)
            for ref in result.block_refs or []:
                br_total += 1
                br_unique.add(ref.get("block_name"))
                if ref.get("attribs"):
                    br_with_attrib += 1

    if disable_legend:
        with patch(LEGEND_PATCH_TARGET, return_value=None):
            _analyze_all()
    else:
        _analyze_all()

    effective = tot_unc + tot_block_default
    totals = {
        "total": tot_total,
        "unclassified": tot_unc,
        "block_default": tot_block_default,
        "rate": round(tot_unc / tot_total, 4) if tot_total else 0.0,
        "effective_rate": round(effective / tot_total, 4) if tot_total else 0.0,
    }
    block_summary = {
        "total": br_total,
        "unique_blocks": len(br_unique),
        "attrib_coverage": round(br_with_attrib / br_total, 4) if br_total else 0.0,
    }
    return per_file, totals, block_summary


def _print_batch(files, label, disable_legend):
    """打印一批图纸的逐图与合计统计，返回合计 stats。"""
    per_file, totals, block_summary = _run(files, disable_legend)
    for path, st, error in per_file:
        if st is None:
            print(f"  {path}: 解析失败 - {error}")
            continue
        print(
            "  {path}: total={total} unclassified={unc} "
            "block_default={bd} rate={rate} effective_rate={er}".format(
                path=path,
                total=st.get("total", 0),
                unc=st.get("unclassified", 0),
                bd=st.get("block_default", 0),
                rate=st.get("rate", 0.0),
                er=st.get("effective_rate", 0.0),
            )
        )
    print(
        "[{label}] total={t} unclassified={u} block_default={b} rate={r} effective_rate={er}".format(
            label=label,
            t=totals["total"],
            u=totals["unclassified"],
            b=totals["block_default"],
            r=totals["rate"],
            er=totals["effective_rate"],
        )
    )
    print(
        "  块引用: total={t} unique_blocks={u} attrib_coverage={c}".format(
            t=block_summary["total"],
            u=block_summary["unique_blocks"],
            c=block_summary["attrib_coverage"],
        )
    )
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description="DXF 未分类率统计（T-A2）")
    parser.add_argument("paths", nargs="+", help="一个或多个 .dxf 文件/目录")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="对比模式：关闭图例兜底，输出基线 vs 现状下降百分比",
    )
    args = parser.parse_args(argv)

    files = collect_dxf(args.paths)
    if not files:
        print("未找到任何 .dxf 文件，请检查路径。")
        return 1

    if args.baseline:
        base = _print_batch(files, "baseline", disable_legend=True)
        cur = _print_batch(files, "current", disable_legend=False)
        # 用有效未分类率（含块语义回退）对比，才是 T-A2 可直接影响的度量。
        base_rate = base["effective_rate"]
        cur_rate = cur["effective_rate"]
        drop = (base_rate - cur_rate) / base_rate * 100 if base_rate > 0 else 0.0
        print(f"有效未分类率下降: {drop:.2f}%")
    else:
        _print_batch(files, "current", disable_legend=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
