"""T-C8 IFC4 导出：T3 平面构件 → IFC4 文件（独立文件输出）。

设计要点：
- 引擎为 IfcOpenShell（LGPL-3.0，动态导入，主进程直调无 AGPL 问题）
- 输入为 extract_t3() 产出的 components dict（mm 单位轴对齐几何），
  IFC 侧按 SI 米制写出（mm→m 换算集中在本模块）
- 墙导出为 IfcWall + IfcExtrudedAreaSolid（IfcRectangleProfileDef 居中定位，
  位置即墙矩形中心，读回校验可直接取 profile 参数重建足迹）
- 柱/门/窗导出为 IfcColumn/IfcDoor/IfcWindow 简单盒体
- 依赖缺失时 export_ifc4 返回 None（优雅降级，不抛异常）

 Hausdorff 验收配套：`read_wall_rects_ifc()` 从 IFC 文件读回墙足迹矩形（mm）。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_STORY_HEIGHT_MM = 3000.0
_DOOR_SIZE_MM = (900.0, 2100.0)  # 门块无尺寸字段，用标称洞口宽 × 门高
_SILL_HEIGHT_MM = 900.0

Rect = Tuple[float, float, float, float]  # x0, y0, x1, y1（mm）


def ifc_available() -> bool:
    try:
        import ifcopenshell  # noqa: F401

        return True
    except ImportError:
        return False


# ── 构件 → 足迹矩形（mm，两模块共用口径）───────────────────


def wall_rect_mm(wall: Dict) -> Optional[Rect]:
    """T3 墙 seg → 足迹矩形。缺关键字段返回 None。"""
    pos = wall.get("pos")
    start = wall.get("start")
    end = wall.get("end")
    if pos is None or start is None or end is None:
        return None
    t = wall.get("thickness") or 200.0  # 未配对面（single）给标称 200
    s, e = min(start, end), max(start, end)
    if e - s <= 0:
        return None
    if wall.get("orientation") == "h":
        return (s, pos - t / 2.0, e, pos + t / 2.0)
    return (pos - t / 2.0, s, pos + t / 2.0, e)


def column_rect_mm(col: Dict) -> Optional[Rect]:
    x, y = col.get("x"), col.get("y")
    if x is None or y is None:
        return None
    if col.get("source") == "circle" and col.get("radius"):
        r = float(col["radius"])
        return (x - r, y - r, x + r, y + r)
    w = float(col.get("width") or 400.0)
    h = float(col.get("height") or 400.0)
    return (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)


def window_rect_mm(win: Dict) -> Optional[Rect]:
    x, y = win.get("x"), win.get("y")
    if x is None or y is None:
        return None
    w = float(win.get("width") or 1200.0)
    h = float(win.get("height") or 200.0)
    return (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)


def door_rect_mm(door: Dict) -> Optional[Rect]:
    x, y = door.get("x"), door.get("y")
    if x is None or y is None:
        return None
    w = _DOOR_SIZE_MM[0]
    rot = float(door.get("rotation") or 0.0) % 180.0
    # 旋转 90° 门洞沿 Y 向展开
    if 45.0 < rot < 135.0:
        return (x - 100.0, y - w / 2.0, x + 100.0, y + w / 2.0)
    return (x - w / 2.0, y - 100.0, x + w / 2.0, y + 100.0)


# ── IFC 构建 ──────────────────────────────────────────────


def _pt(f, *coords):
    return f.create_entity("IfcCartesianPoint", Coordinates=tuple(float(c) for c in coords))


def _axis2d(f, x, y):
    return f.create_entity("IfcAxis2Placement2D", Location=_pt(f, x, y))


def _axis3d(f, x=0.0, y=0.0, z=0.0):
    return f.create_entity("IfcAxis2Placement3D", Location=_pt(f, x, y, z))


def _add_box(f, body_ctx, element, rect_m: Rect, height_m: float, name: str):
    """给元素挂矩形拉伸体（profile 居中于 rect 中心，底面 z=0）。"""
    x0, y0, x1, y1 = rect_m
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    profile = f.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        ProfileName=name,
        Position=_axis2d(f, cx, cy),
        XDim=x1 - x0,
        YDim=y1 - y0,
    )
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=_axis3d(f),
        ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=height_m,
    )
    shape = f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    element.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[shape])
    element.ObjectPlacement = f.create_entity("IfcLocalPlacement", RelativePlacement=_axis3d(f))


def export_ifc4(
    components: Dict,
    out_path: str,
    *,
    story_height_mm: float = _STORY_HEIGHT_MM,
    project_name: str = "BAA Export",
) -> Optional[Dict]:
    """将 T3 构件导出为 IFC4 文件。

    components：extract_t3() 返回的 dict（walls/doors/windows/columns，mm）。
    返回统计 dict；依赖缺失或无墙时返回 None。
    """
    try:
        import ifcopenshell
        import ifcopenshell.api
    except ImportError:
        logger.warning("[T-C8] ifcopenshell 未安装，跳过 IFC 导出")
        return None

    walls = [wall_rect_mm(w) for w in components.get("walls", [])]
    walls = [r for r in walls if r]
    if not walls:
        logger.warning("[T-C8] 无墙构件，跳过 IFC 导出")
        return None

    f = ifcopenshell.file(schema="IFC4")
    run = ifcopenshell.api.run
    project = run("root.create_entity", f, ifc_class="IfcProject", name=project_name)
    run("unit.assign_unit", f)  # SI 米制
    model_ctx = run("context.add_context", f, context_type="Model")
    body_ctx = run(
        "context.add_context",
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )
    site = run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    building = run("root.create_entity", f, ifc_class="IfcBuilding", name="Building")
    storey = run(
        "root.create_entity", f, ifc_class="IfcBuildingStorey", name="F1"
    )
    run("aggregate.assign_object", f, relating_object=project, products=[site])
    run("aggregate.assign_object", f, relating_object=site, products=[building])
    run("aggregate.assign_object", f, relating_object=building, products=[storey])

    h_m = story_height_mm / 1000.0
    counts = {"walls": 0, "columns": 0, "doors": 0, "windows": 0}

    def _rect_m(rect: Rect) -> Rect:
        return tuple(v / 1000.0 for v in rect)  # type: ignore

    for i, rect in enumerate(walls):
        el = run("root.create_entity", f, ifc_class="IfcWall", name=f"WALL_{i:03d}")
        run("spatial.assign_container", f, relating_structure=storey, products=[el])
        _add_box(f, body_ctx, el, _rect_m(rect), h_m, f"WALL_{i:03d}")
        counts["walls"] += 1

    for i, col in enumerate(components.get("columns", [])):
        rect = column_rect_mm(col)
        if not rect:
            continue
        el = run("root.create_entity", f, ifc_class="IfcColumn", name=f"COL_{i:03d}")
        run("spatial.assign_container", f, relating_structure=storey, products=[el])
        _add_box(f, body_ctx, el, _rect_m(rect), h_m, f"COL_{i:03d}")
        counts["columns"] += 1

    for i, door in enumerate(components.get("doors", [])):
        rect = door_rect_mm(door)
        if not rect:
            continue
        el = run("root.create_entity", f, ifc_class="IfcDoor", name=f"DOOR_{i:03d}")
        run("spatial.assign_container", f, relating_structure=storey, products=[el])
        _add_box(f, body_ctx, el, _rect_m(rect), _DOOR_SIZE_MM[1] / 1000.0, f"DOOR_{i:03d}")
        counts["doors"] += 1

    for i, win in enumerate(components.get("windows", [])):
        rect = window_rect_mm(win)
        if not rect:
            continue
        el = run("root.create_entity", f, ifc_class="IfcWindow", name=f"WIN_{i:03d}")
        run("spatial.assign_container", f, relating_structure=storey, products=[el])
        _add_box(f, body_ctx, el, _rect_m(rect), 1.5, f"WIN_{i:03d}")
        counts["windows"] += 1

    f.write(out_path)
    logger.info("[T-C8] IFC4 导出 %s：%s", out_path, counts)
    return {"path": out_path, "counts": counts, "story_height_mm": story_height_mm}


def read_wall_rects_ifc(path: str) -> List[Rect]:
    """从 IFC 文件读回墙足迹矩形（mm）——供 Hausdorff 距离校验。"""
    import ifcopenshell

    f = ifcopenshell.open(path)
    rects: List[Rect] = []
    for wall in f.by_type("IfcWall"):
        rep = wall.Representation
        if not rep:
            continue
        for shape in rep.Representations:
            for item in shape.Items:
                if item.is_a("IfcExtrudedAreaSolid") and item.SweptArea.is_a(
                    "IfcRectangleProfileDef"
                ):
                    prof = item.SweptArea
                    cx, cy = (v * 1000.0 for v in prof.Position.Location.Coordinates[:2])
                    xd = prof.XDim * 1000.0
                    yd = prof.YDim * 1000.0
                    rects.append((cx - xd / 2.0, cy - yd / 2.0, cx + xd / 2.0, cy + yd / 2.0))
    return rects
