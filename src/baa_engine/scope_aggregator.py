"""聚合作用域判定引擎（Roadmap v4 T-B2 / 缺口 B2：修正 EXIST 误报）。

EXIST 类判定的误报机制（B2 评估定位）：
1. 整图二值（atomic_functions.execute_missing_batch）：图中无目标类型实体
   → 判「应设置 X 但缺失」FAIL。目标类型被分类噪声吞掉（喷淋符号未识别、
   staircase 召回不足）时，误报被整图放大。
2. 反向掩盖：单个碎片实体命中类型 → 整图「满足」，分区间真实缺失被隐藏。

本引擎将判定从「单图元/整图」升级为「作用域内聚合」：

作用域来源（优先级递减，均客观可测）：
1. ``fire_compartment`` / ``fire_zone`` 实体（分类层已从防火分区图层
   （A-FIRE、防火分区）的闭合区域产出；无分区实体的图纸回退网格）
2. 空间网格回退（默认 50m 网格）：纯几何划分，不依赖分区识别，立即可用

聚合语义（宁缺勿错）：
- 每个作用域独立统计目标类型实体数（质心归属）
- 全部作用域命中 → ``pass``；全部未命中 → ``missing``（维持现有 FAIL 语义，
  不因聚合放松）；部分命中 → ``partial``（精确指出缺失作用域，分类噪声下
  由「整图误报」收敛为「区域级提示」）
- 不做任何跨作用域臆测；作用域划分失败一律回退整图单作用域（现有行为）
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# 空间网格回退：默认 50m（防火分区典型尺度 1000~4000㎡ 即 30~70m 边长）
DEFAULT_GRID_MM = 50000.0

# 分区实体类型（classify.py 区域守卫产出：防火分区图层闭合多边形/HATCH；
# fire_zone 为「防火分区」中文图层规则产出类型；图纸无分区实体时回退网格）
_COMPARTMENT_TYPES = {"fire_compartment", "fire_zone"}


def _center(entity: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    bbox = entity.get("bbox") or {}
    try:
        x = float(bbox.get("x", 0) or 0)
        y = float(bbox.get("y", 0) or 0)
        w = float(bbox.get("width", 0) or 0)
        h = float(bbox.get("height", 0) or 0)
    except (TypeError, ValueError):
        return None
    return (x + w / 2, y + h / 2)


def _scope_of_point(
    px: float,
    py: float,
    compartments: List[Dict[str, Any]],
) -> Optional[str]:
    """质心落分区 bbox 内 → 分区作用域；否则 None（归 unscoped 兜底）。"""
    for comp in compartments:
        bbox = comp["bbox"]
        if (
            bbox["x"] <= px <= bbox["x"] + bbox["width"]
            and bbox["y"] <= py <= bbox["y"] + bbox["height"]
        ):
            return comp["scope_id"]
    return None


def build_scopes(
    entities: List[Dict[str, Any]],
    grid_size_mm: float = DEFAULT_GRID_MM,
    include_types: Optional[set] = None,
) -> Dict[str, Any]:
    """构建判定作用域。

    include_types: 实体归属/计数白名单（None=全部实体）。判定侧只需目标
    类型实体的作用域归属，传入可避免无关实体扩大网格/污染计数。
    """
    compartments = [
        {
            "scope_id": e.get("id"),
            "kind": "compartment",
            "bbox": e.get("bbox"),
        }
        for e in entities
        if e.get("type") in _COMPARTMENT_TYPES
        and isinstance(e.get("bbox"), dict)
        and (e["bbox"].get("width") or 0) > 0
    ]

    mode = "compartment" if compartments else "grid"
    scopes: List[Dict[str, Any]] = []
    assignment: Dict[str, str] = {}
    unscoped: List[str] = []

    def _in_scope_set(e: Dict[str, Any]) -> bool:
        return include_types is None or e.get("type") in include_types

    if mode == "compartment":
        scopes = [
            {"scope_id": c["scope_id"], "kind": "compartment", "bbox": c["bbox"], "entity_count": 0}
            for c in compartments
        ]
        for e in entities:
            eid = e.get("id")
            c = _center(e)
            if eid is None or c is None or not _in_scope_set(e):
                continue
            sid = _scope_of_point(c[0], c[1], compartments)
            if sid is None:
                unscoped.append(eid)
            else:
                assignment[eid] = sid
    else:
        # 网格回退：以含 bbox 实体的点集范围铺网格
        pts: List[Tuple[str, float, float]] = []
        xs: List[float] = []
        ys: List[float] = []
        for e in entities:
            if not _in_scope_set(e):
                continue
            c = _center(e)
            if c is not None:
                eid = e.get("id")
                if eid is not None:
                    pts.append((eid, c[0], c[1]))
                    xs.append(c[0])
                    ys.append(c[1])
        if pts:
            gs = max(float(grid_size_mm), 1000.0)
            x0, y0 = min(xs), min(ys)
            scope_ids: Dict[Tuple[int, int], str] = {}
            for eid, px, py in pts:
                gx = int(math.floor((px - x0) / gs))
                gy = int(math.floor((py - y0) / gs))
                sid = f"grid_{gx}_{gy}"
                scope_ids.setdefault((gx, gy), sid)
                assignment[eid] = sid
            scopes = [
                {"scope_id": sid, "kind": "grid_cell", "bbox": None, "entity_count": 0}
                for sid in sorted(scope_ids.values())
            ]

    for eid, sid in assignment.items():
        for s in scopes:
            if s["scope_id"] == sid:
                s["entity_count"] += 1
                break

    return {
        "mode": mode,
        "scopes": scopes,
        "assignment": assignment,
        "unscoped_entities": unscoped,
    }


def aggregate_exist_in_scopes(
    func_id: str,
    target_types: List[str],
    entities: List[Dict[str, Any]],
    scopes: Dict[str, Any],
) -> Dict[str, Any]:
    """EXIST 类判定的作用域内聚合。

    返回:
        {
          "func_id", "mode",
          "overall": "pass"|"partial"|"missing"|"no_scopes",
          "scope_results": [
            {"scope_id", "kind", "hit_count", "satisfied"}, ...
          ],
          "missing_scopes": [scope_id, ...],   # overall=partial 时非空
          "total_hits": int,
        }
    """
    targets = set(target_types or [])
    by_scope: Dict[str, Dict[str, int]] = {}
    kind_by_scope = {s["scope_id"]: s.get("kind", "grid_cell") for s in scopes["scopes"]}

    for e in entities:
        eid = e.get("id")
        if eid is None or e.get("type") not in targets:
            continue
        sid = scopes["assignment"].get(eid, "__unscoped__")
        stat = by_scope.setdefault(sid, {"hit": 0})
        stat["hit"] += 1

    scope_results = []
    for s in scopes["scopes"]:
        sid = s["scope_id"]
        hit = by_scope.get(sid, {}).get("hit", 0)
        scope_results.append(
            {
                "scope_id": sid,
                "kind": kind_by_scope.get(sid, "grid_cell"),
                "hit_count": hit,
                "satisfied": hit > 0,
            }
        )
    unscoped_hit = by_scope.get("__unscoped__", {}).get("hit", 0)
    if scopes["unscoped_entities"] and unscoped_hit:
        scope_results.append(
            {
                "scope_id": "__unscoped__",
                "kind": "unscoped",
                "hit_count": unscoped_hit,
                "satisfied": True,
            }
        )

    if not scope_results:
        overall = "no_scopes"
        missing = []
    else:
        missing = [r["scope_id"] for r in scope_results if not r["satisfied"]]
        if not missing:
            overall = "pass"
        elif all(not r["satisfied"] for r in scope_results):
            overall = "missing"
        else:
            overall = "partial"

    return {
        "func_id": func_id,
        "mode": scopes["mode"],
        "overall": overall,
        "scope_results": scope_results,
        "missing_scopes": missing,
        "total_hits": sum(r["hit_count"] for r in scope_results),
    }
