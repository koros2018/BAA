"""T-A2 真实图纸验收脚本（块语义分类 / G7）

用途
----
在真实图纸目录上实测「块语义分类」引入前后的**有效未分类率**变化，产出可评审的
证据链（图纸 ID + 命中块名 + 前后对比），用于 T-A2 验收标准：

  - 图元未分类率相较基线下降 ≥50%
  - 不引入新增误报（回归门：仅实体丢失/劣化为块语义回退计失败）
  - 出具前后对比证据链（真实图纸 ID + 命中块名）

口径
----
  unclassified      = entity_type == "unknown"（被丢弃）
  block_default     = INSERT 块名/图例均未命中，回退 wall（块语义未覆盖）
  effective_rate    = (unclassified + block_default) / total   ← 块语义可直接影响的度量
  baseline(pre-T-A2)= 原始 V1 规则表（patch classify.classify_block_name → V1）+ 关闭
                      图例兜底（patch classify.lookup_legend → None）+ 关闭图例学习器
                      （patch legend_learner._learn_legend_blocks → {}，M4 Step 0.9 复测口径修正）
  current           = 现状（扩充块名映射 + 图例兜底 + ATTRIB 落库）
  guard_removed     = 基线(V1 无守卫)误报为构件、现状命中 _SHEET_NAME_MARKERS 后正确
                      去分类的图纸/系统图块（属修复而非劣化），不计入失败
  changes           = 非上述两类回归的类型变化（含真修复，如 挂灯、柱灯 column→light），
                      仅供复核，不计入失败

用法
----
  python src/tools/ta2_real_drawing_acceptance.py "D:\\BaiduNetdiskDownload\\测试图纸"
  python src/tools/ta2_real_drawing_acceptance.py <dir> --limit 40 --json-out evidence.json
  python src/tools/ta2_real_drawing_acceptance.py <dir> --include-hints "建筑,建施,消防,平面"
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser  # noqa: E402
from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # noqa: E402
from src.baa_engine.semantic_analyzer.block_semantics import (  # noqa: E402
    BLOCK_NAME_RULES_V1,
    _SHEET_NAME_MARKERS,
)

# 图例兜底的补丁目标：classify 通过 from ... import lookup_legend 引入，
# 必须 patch 其所在命名空间（classify.lookup_legend）才能生效。
LEGEND_PATCH_TARGET = "src.baa_engine.semantic_analyzer.classify.lookup_legend"
# 块名规则的补丁目标（pre-T-A2 基线回退到原始 V1 规则表）。
BLOCK_NAME_PATCH_TARGET = "src.baa_engine.semantic_analyzer.classify.classify_block_name"
# M4 图例学习器的补丁目标（Step 0.9 预扫描学得的映射属图例兜底家族，
# baseline 必须一并关闭，否则基线被人为抬高、降幅失真）。
LEARNER_PATCH_TARGET = "src.baa_engine.semantic_analyzer.legend_learner._learn_legend_blocks"

DEFAULT_DIR = r"D:\BaiduNetdiskDownload\测试图纸"

# 明显无解析价值的文件：图框/外部参照/目录/说明，避免噪声污染统计
SKIP_NAME_HINTS = ("图框", "目录", "说明", "外部参照", "总图")


def _scan_dxf(
    root: Path,
    limit: int,
    min_size: int,
    include_hints: Sequence[str] = (),
    exclude_hints: Sequence[str] = (),
) -> List[Path]:
    files = [
        p
        for p in sorted(root.rglob("*.dxf"))
        if p.stat().st_size >= min_size
        and not any(h in p.name for h in SKIP_NAME_HINTS)
    ]
    # 目录筛选：relative path 命中任一 include hint 才保留；命中任一 exclude hint 剔除
    if include_hints:
        files = [
            p
            for p in files
            if any(h in str(p.relative_to(root)) for h in include_hints)
        ]
    if exclude_hints:
        files = [
            p
            for p in files
            if not any(h in str(p.relative_to(root)) for h in exclude_hints)
        ]
    if limit > 0:
        # 优先取中等体积文件：过小常为空壳，过大解析慢
        files.sort(key=lambda p: p.stat().st_size)
        files = files[:limit]
    return files


def _classify_block_name_v1(block_name: str) -> Optional[str]:
    """pre-T-A2 基线分类：仅原始 V1 规则表（无扩充、无图例兜底）。"""
    if not block_name:
        return None
    name = str(block_name).upper()
    for keyword, entity_type in BLOCK_NAME_RULES_V1:
        if keyword in name:
            return entity_type
    return None


def _run_once(path: Path, parser: DrawingParser, baseline: bool) -> Optional[Tuple[dict, dict]]:
    """返回 (parse_result, analyze_result)；不可用则 None。

    baseline=True 时回退到 pre-T-A2 口径：原始 V1 块名规则 + 关闭图例兜底。
    """
    with ExitStack() as stack:
        if baseline:
            stack.enter_context(
                patch(BLOCK_NAME_PATCH_TARGET, new=_classify_block_name_v1)
            )
            stack.enter_context(patch(LEGEND_PATCH_TARGET, return_value=None))
            stack.enter_context(patch(LEARNER_PATCH_TARGET, new=lambda prims: {}))
        result = parser.parse(str(path), f"ta2_{path.stem}")
        if not result.success or not result.primitives:
            return None
        # DrawingParser 按文件哈希缓存 DrawingResult，两次运行的图元对象是同一批；
        # classify 会在 properties 上写入 _block_default 标记，须在每次分析前清除，
        # 否则上一次运行的标记会污染本次统计。
        for prim in result.primitives:
            props = getattr(prim, "properties", None)
            if isinstance(props, dict):
                props.pop("_block_default", None)
        semantic = SemanticAnalyzer().analyze(
            result.primitives, result.dimensions, block_refs=result.block_refs
        )
    return result, semantic


def _entity_key(entity: dict) -> str:
    """跨类型稳定的实体键：entity_id 形如 TYPE_003，取数值序号（同图元顺序稳定）。

    entity_id 的类型前缀会随分类结果变化，不能用于跨基线匹配；数值序号由
    classify 的全局计数器按图元顺序分配，同一图元列表在两次运行中一致。
    """
    eid = str(entity.get("id", ""))
    return eid.rsplit("_", 1)[-1]


def _by_id(entities: List[dict]) -> Dict[str, dict]:
    return {_entity_key(e): e for e in entities}


def _is_block_default(entity: dict) -> bool:
    return bool(entity.get("properties", {}).get("_block_default"))


def _evaluate_file(path: Path, parser: DrawingParser) -> Optional[dict]:
    base = _run_once(path, parser, baseline=True)
    cur = _run_once(path, parser, baseline=False)
    if base is None or cur is None:
        return None
    base_parse, base_sem = base
    cur_parse, cur_sem = cur

    # ── 块引用诊断：块名分布 + ATTRIB 覆盖率（用于证据链与规则完善） ──
    block_names: Dict[str, int] = {}
    attrib_samples: List[dict] = []
    for ref in cur_parse.block_refs or []:
        bn = str(ref.get("block_name", ""))
        block_names[bn] = block_names.get(bn, 0) + 1
        if ref.get("attribs") and len(attrib_samples) < 8:
            attrib_samples.append(
                {"block_name": bn, "attribs": dict(ref.get("attribs") or {})}
            )

    base_stats = base_sem.get("classification_stats", {})
    cur_stats = cur_sem.get("classification_stats", {})
    base_ents = _by_id(base_sem["entities"])
    cur_ents = _by_id(cur_sem["entities"])

    # ── 回归门：仅「实体丢失」与「基线已分类 → 现状劣化为块语义回退 wall」计失败；
    #    其余类型变化（含真修复，如 挂灯、柱灯 column→light）记入 changes 供复核，不判失败。 ──
    regressions: List[dict] = []
    guard_removed: List[dict] = []
    changes: List[dict] = []
    reclassified: List[dict] = []
    for eid, be in base_ents.items():
        ce = cur_ents.get(eid)
        if ce is None:
            regressions.append(
                {
                    "id": eid,
                    "reason": "entity_missing",
                    "base": be["type"],
                    "layer": be.get("layer", ""),
                }
            )
            continue
        if be["type"] == ce["type"]:
            continue
        base_is_default = be["type"] == "wall" and _is_block_default(be)
        cur_is_default = ce["type"] == "wall" and _is_block_default(ce)
        if base_is_default:
            # 基线块语义未覆盖（回退 wall）→ 现状重新归类：证据链核心
            props = be.get("properties", {})
            reclassified.append(
                {
                    "block_name": props.get("block_name", ""),
                    "attribs": list((props.get("block_attribs") or {}).values()),
                    "from": be["type"],
                    "to": ce["type"],
                    "layer": be.get("layer", ""),
                }
            )
        elif cur_is_default:
            # 基线已分类 → 现状回退 wall。区分两类根因：
            #   (a) 图纸/标题/系统图块（命中 _SHEET_NAME_MARKERS）：V1 无守卫而误报，
            #       现状由守卫刻意去分类，属修复而非劣化 → guard_removed，不计失败；
            #   (b) 其余真实构件块：块名/图例均未命中导致回退 → 真实劣化，计失败。
            cur_props = ce.get("properties", {})
            cbn = str(cur_props.get("block_name", "") or "")
            if cbn and any(m in cbn.upper() for m in _SHEET_NAME_MARKERS):
                guard_removed.append(
                    {
                        "id": eid,
                        "block_name": cbn,
                        "base": be["type"],
                        "layer": ce.get("layer", ""),
                    }
                )
            else:
                regressions.append(
                    {
                        "id": eid,
                        "reason": "degraded_to_block_default",
                        "base": be["type"],
                        "block_name": cbn,
                        "layer": ce.get("layer", ""),
                    }
                )
        else:
            # 其他类型变化（不计失败，仅供复核）
            changes.append(
                {
                    "id": eid,
                    "reason": "type_changed",
                    "base": be["type"],
                    "current": ce["type"],
                    "block_name": str(ce.get("properties", {}).get("block_name", "") or ""),
                    "layer": ce.get("layer", ""),
                }
            )

    rel = str(path)
    try:
        rel = str(path.relative_to(Path.cwd()))
    except ValueError:
        pass

    total = cur_stats.get("total", 0)
    base_eff = base_stats.get("effective_rate", 0.0)
    cur_eff = cur_stats.get("effective_rate", 0.0)
    drop = (base_eff - cur_eff) / base_eff if base_eff > 0 else 0.0

    return {
        "drawing_id": rel,
        "total": total,
        "base": {
            "unclassified": base_stats.get("unclassified", 0),
            "block_default": base_stats.get("block_default", 0),
            "effective_rate": base_eff,
        },
        "current": {
            "unclassified": cur_stats.get("unclassified", 0),
            "block_default": cur_stats.get("block_default", 0),
            "effective_rate": cur_eff,
        },
        "effective_drop": round(drop, 4),
        "reclassified_blocks": reclassified,
        "regressions": regressions,
        "guard_removed": guard_removed,
        "changes": changes,
        "block_names": block_names,
        "attrib_samples": attrib_samples,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="T-A2 真实图纸验收（块语义分类）")
    ap.add_argument("directory", nargs="?", default=DEFAULT_DIR, help="真实图纸目录")
    ap.add_argument("--limit", type=int, default=40, help="最多评估的 DXF 数（0=不限）")
    ap.add_argument("--min-size", type=int, default=30 * 1024, help="最小文件字节数过滤")
    ap.add_argument("--min-drop", type=float, default=0.5, help="验收门槛：有效未分类率下降比例")
    ap.add_argument("--json-out", default="", help="证据链 JSON 输出路径")
    ap.add_argument("--dump-blocks", type=int, default=0, help="打印出现次数 Top-N 的块名")
    ap.add_argument(
        "--include-hints",
        default="",
        help="逗号分隔；给出时仅保留相对路径包含任一 hint 的图纸（如 建筑,建施,消防,平面）",
    )
    ap.add_argument(
        "--exclude-hints",
        default="",
        help="逗号分隔；剔除相对路径包含任一 hint 的图纸（默认空=不筛选）",
    )
    args = ap.parse_args()

    root = Path(args.directory)
    if not root.exists():
        print(f"[FAIL] 目录不存在: {root}")
        return 1

    include_hints = [h.strip() for h in args.include_hints.split(",") if h.strip()]
    exclude_hints = [h.strip() for h in args.exclude_hints.split(",") if h.strip()]
    files = _scan_dxf(
        root, args.limit, args.min_size, include_hints, exclude_hints
    )
    if not files:
        print(
            f"[FAIL] {root} 下未找到可用 DXF（min-size={args.min_size}, "
            f"include={include_hints}, exclude={exclude_hints}）"
        )
        return 1

    parser = DrawingParser()
    reports: List[dict] = []
    skipped = 0
    for p in files:
        rep = _evaluate_file(p, parser)
        if rep is None:
            skipped += 1
            continue
        reports.append(rep)

    if not reports:
        print(f"[FAIL] {len(files)} 个文件均无法解析（T3 空壳/损坏），无可用样本")
        return 1

    tot = sum(r["total"] for r in reports)
    tot_base_bd = sum(r["base"]["block_default"] for r in reports)
    tot_cur_bd = sum(r["current"]["block_default"] for r in reports)
    tot_base_unc = sum(r["base"]["unclassified"] for r in reports)
    tot_cur_unc = sum(r["current"]["unclassified"] for r in reports)
    base_eff = (tot_base_unc + tot_base_bd) / tot if tot else 0.0
    cur_eff = (tot_cur_unc + tot_cur_bd) / tot if tot else 0.0
    drop = (base_eff - cur_eff) / base_eff if base_eff > 0 else 0.0

    all_regressions = [(r["drawing_id"], g) for r in reports for g in r["regressions"]]
    all_guard_removed = [(r["drawing_id"], g) for r in reports for g in r["guard_removed"]]
    all_changes = [(r["drawing_id"], g) for r in reports for g in r["changes"]]
    reclassified_total = sum(len(r["reclassified_blocks"]) for r in reports)

    print("=" * 78)
    print(f"T-A2 真实图纸验收 | 目录: {root}")
    print(f"评估图纸: {len(reports)} 张（跳过 {skipped}）：{tot} 图元")
    if include_hints:
        print(f"  目录筛选 include={include_hints} exclude={exclude_hints}")
    print(
        f"  基线(unclassified={tot_base_unc}, block_default={tot_base_bd}) "
        f"effective_rate={base_eff:.4f}"
    )
    print(
        f"  现状(unclassified={tot_cur_unc}, block_default={tot_cur_bd}) "
        f"effective_rate={cur_eff:.4f}"
    )
    print(f"  有效未分类率下降: {drop * 100:.2f}%（门槛 {args.min_drop * 100:.0f}%）")
    print(f"  重新归类的块: {reclassified_total} 个")
    print(f"  误报回归项: {len(all_regressions)} 个")
    print(f"  守卫去分类(标题/系统图块, 不计失败): {len(all_guard_removed)} 个")
    print(f"  其他类型变化(不计失败): {len(all_changes)} 个")
    print("-" * 78)
    for r in reports:
        if (
            r["reclassified_blocks"]
            or r["regressions"]
            or r["guard_removed"]
            or r["changes"]
        ):
            print(
                f"  {r['drawing_id']}: eff {r['base']['effective_rate']:.4f} → "
                f"{r['current']['effective_rate']:.4f} "
                f"(block_default {r['base']['block_default']}→{r['current']['block_default']}, "
                f"重归类 {len(r['reclassified_blocks'])}, "
                f"changes {len(r['changes'])})"
            )
            for rb in r["reclassified_blocks"][:5]:
                print(
                    f"      命中: block={rb['block_name']!r} attribs={rb['attribs']} "
                    f"{rb['from']}→{rb['to']}"
                )
            for ch in r["changes"][:5]:
                print(
                    f"      变化: id={ch['id']} {ch.get('base')}→{ch.get('current')}"
                )
            for g in r["guard_removed"][:5]:
                print(f"      守卫: block={g['block_name']!r} {g['base']}→wall")
            for g in r["regressions"][:5]:
                print(
                    f"      回归: id={g['id']} {g.get('reason')} "
                    f"block={g.get('block_name', '')!r} base={g.get('base')}"
                )
    print("-" * 78)

    if args.dump_blocks > 0:
        from collections import Counter

        global_blocks: Counter = Counter()
        attrib_cov = 0
        attrib_total = 0
        samples: List[dict] = []
        for r in reports:
            global_blocks.update(r["block_names"])
            attrib_total += sum(r["block_names"].values())
            attrib_cov += sum(
                1 for ref in r["attrib_samples"] if ref.get("attribs")
            )
            samples.extend(r["attrib_samples"][:2])
        print(f"块引用 Top-{args.dump_blocks}（共 {sum(global_blocks.values())} 条）：")
        for bn, cnt in global_blocks.most_common(args.dump_blocks):
            print(f"  {cnt:>6}  {bn!r}")
        print("ATTRIB 样例：")
        for s in samples[:10]:
            print(f"  {s['block_name']!r} -> {s['attribs']}")
        print("-" * 78)

    verdict = []
    verdict.append(("回归控制", "PASS" if not all_regressions else "FAIL", len(all_regressions)))
    if tot_base_bd == 0:
        verdict.append(("未分类率下降", "INSUFFICIENT_SAMPLE", 0))
    else:
        verdict.append(
            ("未分类率下降", "PASS" if drop >= args.min_drop else "FAIL", round(drop, 4))
        )

    for name, res, val in verdict:
        print(f"  [{res}] {name} (值={val})")
    print("=" * 78)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "directory": str(root),
                    "evaluated": len(reports),
                    "skipped": skipped,
                    "aggregate": {
                        "total": tot,
                        "base_effective_rate": round(base_eff, 4),
                        "current_effective_rate": round(cur_eff, 4),
                        "effective_drop": round(drop, 4),
                        "block_default_base": tot_base_bd,
                        "block_default_current": tot_cur_bd,
                        "reclassified_blocks": reclassified_total,
                        "regressions": len(all_regressions),
                        "guard_removed": len(all_guard_removed),
                        "changes": len(all_changes),
                    },
                    "verdict": {name: res for name, res, _ in verdict},
                    "per_drawing": reports,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"证据链已写入: {out}")

    ok = all(res in ("PASS", "INSUFFICIENT_SAMPLE") for _, res, _ in verdict)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
