"""T-C8 STEP 导出：T3 平面构件 → STEP AP214 文件（独立文件输出）。

设计要点：
- 引擎为 CadQuery/OCP（Apache-2.0），主进程直调
- 输入与 IFC 导出共用同一 components dict（mm 单位）；STEP 按 mm 写出
  （OCP 原生单位即 mm，免换算）
- 墙/柱/门窗均为盒体，逐构件独立 solid 打包为 compound，
  读回校验按 solid BoundingBox 重建足迹矩形
- 依赖缺失时 export_step 返回 None（优雅降级）

Hausdorff 验收配套：`read_wall_rects_step()` 按导出顺序取前 N 个 solid
（墙先于柱/门窗写入，读回顺序一致）重建足迹（mm）。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.baa_engine.ifc_export import (
    Rect,
    column_rect_mm,
    door_rect_mm,
    wall_rect_mm,
    window_rect_mm,
    _DOOR_SIZE_MM,
    _STORY_HEIGHT_MM,
)

logger = logging.getLogger(__name__)


def step_available() -> bool:
    try:
        import cadquery  # noqa: F401

        return True
    except ImportError:
        return False


def export_step(
    components: Dict,
    out_path: str,
    *,
    story_height_mm: float = _STORY_HEIGHT_MM,
) -> Optional[Dict]:
    """将 T3 构件导出为 STEP 文件。

    返回统计 dict；依赖缺失或无墙时返回 None。
    solid 写入顺序：墙 → 柱 → 门 → 窗（读回按同序对齐）。
    """
    try:
        import cadquery as cq
    except ImportError:
        logger.warning("[T-C8] cadquery 未安装，跳过 STEP 导出")
        return None

    walls = [wall_rect_mm(w) for w in components.get("walls", [])]
    walls = [r for r in walls if r]
    if not walls:
        logger.warning("[T-C8] 无墙构件，跳过 STEP 导出")
        return None

    def _box(rect: Rect, height: float):
        x0, y0, x1, y1 = rect
        return (
            cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, height, centered=(True, True, False))
            .translate(((x0 + x1) / 2.0, (y0 + y1) / 2.0, 0.0))
        )

    shapes = []
    counts = {"walls": 0, "columns": 0, "doors": 0, "windows": 0}

    for rect in walls:
        shapes.append(_box(rect, story_height_mm))
        counts["walls"] += 1
    for col in components.get("columns", []):
        rect = column_rect_mm(col)
        if rect:
            shapes.append(_box(rect, story_height_mm))
            counts["columns"] += 1
    for door in components.get("doors", []):
        rect = door_rect_mm(door)
        if rect:
            shapes.append(_box(rect, _DOOR_SIZE_MM[1]))
            counts["doors"] += 1
    for win in components.get("windows", []):
        rect = window_rect_mm(win)
        if rect:
            shapes.append(_box(rect, 1500.0))
            counts["windows"] += 1

    compound = cq.Compound.makeCompound([s.val() for s in shapes])
    compound.exportStep(out_path)
    logger.info("[T-C8] STEP 导出 %s：%s", out_path, counts)
    return {"path": out_path, "counts": counts, "story_height_mm": story_height_mm}


def read_wall_rects_step(path: str, wall_count: int) -> List[Rect]:
    """从 STEP 文件读回前 wall_count 个 solid（= 墙）的足迹矩形（mm）。"""
    import cadquery as cq

    imported = cq.importers.importStep(path)
    rects: List[Rect] = []
    for solid in imported.solids().vals()[:wall_count]:
        bb = solid.BoundingBox()
        rects.append((bb.xmin, bb.ymin, bb.xmax, bb.ymax))
    return rects
