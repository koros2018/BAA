"""
几何计算子模块 — 边界框、属性提取、多边形面积

从 drawing_parser.py 拆分出来，消除 1556 行单文件的技术债。
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def compute_bbox(entity) -> Optional[Dict[str, float]]:
    """计算图元边界框

    多层兜底策略，支持 ezdwg 手动重建的图元（无标准 bbox 方法）。
    同时处理 ezdxf 原生图元：LWPOLYLINE.vertices() 返回 (x,y) 元组而非
    Vec2 对象；LINE/CIRCLE/ARC 无 bbox() 方法。
    P77 修复：泵房/配电房 stair bbox 全零根因——vertices() 点坐标是
    numpy 标量元组，无 .x/.y 属性，原实现静默吞异常后掉到 {0,0,0,0} 兜底。
    """
    from ezdxf.math import Vec2

    dxf_type = entity.dxftype() if hasattr(entity, "dxftype") else None

    # ── 1. LINE: 用 start/end 直接算包围盒 ──
    if dxf_type == "LINE":
        try:
            s = Vec2(entity.dxf.start)
            en = Vec2(entity.dxf.end)
            x1, x2 = sorted([s.x, en.x])
            y1, y2 = sorted([s.y, en.y])
            return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}
        except Exception:
            pass

    # ── 2. CIRCLE: 圆心 ± 半径 ──
    if dxf_type == "CIRCLE":
        try:
            c = Vec2(entity.dxf.center)
            r = float(entity.dxf.radius)
            return {"x": c.x - r, "y": c.y - r, "width": 2 * r, "height": 2 * r}
        except Exception:
            pass

    # ── 3. ARC: 圆心 ± 半径（近似包围盒，比实际略大但安全） ──
    if dxf_type == "ARC":
        try:
            c = Vec2(entity.dxf.center)
            r = float(entity.dxf.radius)
            return {"x": c.x - r, "y": c.y - r, "width": 2 * r, "height": 2 * r}
        except Exception:
            pass

    # ── 4. TEXT: 插入点 ± 文字高度 ──
    if dxf_type == "TEXT":
        try:
            p = Vec2(entity.dxf.insert)
            h = float(entity.dxf.height)
            return {"x": p.x, "y": p.y, "width": h * 1.5, "height": h}
        except Exception:
            pass

    # ── 5. LWPOLYLINE / POLYLINE / SPLINE: 从 vertices() 聚合 ──
    if dxf_type in ("LWPOLYLINE", "POLYLINE", "SPLINE"):
        try:
            points = list(entity.vertices())
            if points:
                xs = []
                ys = []
                for p in points:
                    try:
                        # Vec2 对象
                        if hasattr(p, "x") and hasattr(p, "y"):
                            xs.append(float(p.x))
                            ys.append(float(p.y))
                        # tuple/ndarray: (x, y) 或 (x, y, z)
                        elif isinstance(p, (tuple, list)) and len(p) >= 2:
                            xs.append(float(p[0]))
                            ys.append(float(p[1]))
                    except Exception:
                        pass
                if xs and ys:
                    w = max(xs) - min(xs)
                    h = max(ys) - min(ys)
                    return {"x": min(xs), "y": min(ys), "width": w, "height": h}
        except Exception:
            pass

    # 6. ezdxf 原生 bbox 方法（INSERT / 3DSOLID 等支持 bbox() 的图元）
    try:
        if hasattr(entity, "bbox"):
            bbox = entity.bbox()
            if bbox and bbox.extmin is not None and bbox.extmax is not None:
                w = bbox.extmax[0] - bbox.extmin[0]
                h = bbox.extmax[1] - bbox.extmin[1]
                if w > 0 or h > 0:
                    return {
                        "x": bbox.extmin[0],
                        "y": bbox.extmin[1],
                        "width": w,
                        "height": h,
                    }
    except Exception:
        pass

    # 7. 从 insert 属性计算（INSERT 块引用）
    try:
        if hasattr(entity, "dxf") and hasattr(entity.dxf, "insert"):
            ins = entity.dxf.insert
            if hasattr(ins, "__getitem__"):
                return {
                    "x": float(ins[0]),
                    "y": float(ins[1]),
                    "width": 0,
                    "height": 0,
                }
    except Exception:
        pass

    # 兜底：返回 0 边界框
    return {"x": 0, "y": 0, "width": 0, "height": 0}


def extract_properties(entity) -> Dict[str, Any]:
    """提取几何属性"""
    from ezdxf.math import Vec2

    props = {}

    try:
        if entity.dxftype() == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            props["length"] = Vec2(start).distance(Vec2(end))
            props["angle"] = Vec2(end - start).angle_deg

        elif entity.dxftype() == "CIRCLE":
            props["radius"] = entity.dxf.radius
            props["diameter"] = entity.dxf.radius * 2

        elif entity.dxftype() == "LWPOLYLINE":
            if hasattr(entity, "length"):
                props["length"] = entity.length
            if entity.closed:
                props["area"] = compute_polygon_area(entity)
            try:
                pts = entity.dxf.get("points", [])
                props["point_count"] = len(pts)
            except Exception:
                try:
                    pts = list(entity.vertices())
                    props["point_count"] = len(pts)
                except Exception:
                    pass

        elif entity.dxftype() == "ARC":
            props["radius"] = entity.dxf.radius
            props["start_angle"] = entity.dxf.start_angle
            props["end_angle"] = entity.dxf.end_angle

        elif entity.dxftype() == "TEXT":
            props["text"] = entity.dxf.text
            props["height"] = entity.dxf.height

        elif entity.dxftype() == "INSERT":
            try:
                block_name = entity.dxf.name if hasattr(entity.dxf, "name") else ""
                props["block_name"] = block_name or ""
                ins = entity.dxf.insert if hasattr(entity.dxf, "insert") else None
                if ins:
                    props["insert_x"] = ins[0] if hasattr(ins, "__getitem__") else ins.x
                    props["insert_y"] = ins[1] if hasattr(ins, "__getitem__") else ins.y
            except Exception:
                pass

        # DIMENSION
        elif entity.dxftype() == "DIMENSION":
            try:
                props["measured_length"] = (
                    float(entity.measure) if hasattr(entity, "measure") else None
                )
            except Exception:
                pass

        # DIM 实体
        elif entity.dxftype() == "DIMENSION" or (hasattr(entity, "measure")):
            pass

    except Exception:
        pass

    return props


def compute_polygon_area(entity) -> float:
    """计算多边形面积

    使用鞋带公式（shoelace formula），支持 LWPOLYLINE、POLYLINE、CIRCLE 等闭合图形。
    P77 修复：vertices() 返回 tuple 而非 Vec2，必须用索引访问而非 .x/.y。
    """
    from ezdxf.math import Vec2
    import math

    def _extract_points(entity):
        """提取顶点坐标，兼容 Vec2 对象和 tuple"""
        try:
            points = list(entity.vertices())
            if not points:
                return [], []
            xs, ys = [], []
            for p in points:
                try:
                    if hasattr(p, "x") and hasattr(p, "y"):
                        xs.append(float(p.x))
                        ys.append(float(p.y))
                    elif isinstance(p, (tuple, list)) and len(p) >= 2:
                        xs.append(float(p[0]))
                        ys.append(float(p[1]))
                except Exception:
                    pass
            return xs, ys
        except Exception:
            return [], []

    try:
        # LWPOLYLINE / POLYLINE
        if entity.dxftype() in ("LWPOLYLINE", "POLYLINE"):
            xs, ys = _extract_points(entity)
            if len(xs) >= 3:
                area = 0.0
                n = len(xs)
                for i in range(n):
                    j = (i + 1) % n
                    area += xs[i] * ys[j] - xs[j] * ys[i]
                return abs(area) / 2.0

        # CIRCLE
        if hasattr(entity, "dxf") and hasattr(entity.dxf, "radius"):
            r = entity.dxf.radius
            return math.pi * r * r

    except Exception:
        pass

    return 0.0


def transform_point(
    p: Tuple[float, float],
    base_x: float,
    base_y: float,
    scale: float,
    rotation: float,
) -> Tuple[float, float]:
    """旋转+缩放坐标变换

    用于 INSERT 块展开时的坐标转换。
    """
    import math

    cos_r = math.cos(math.radians(rotation))
    sin_r = math.sin(math.radians(rotation))
    dx = (p[0] - base_x) * scale
    dy = (p[1] - base_y) * scale
    rx = dx * cos_r - dy * sin_r + base_x
    ry = dx * sin_r + dy * cos_r + base_y
    return (rx, ry)


__all__ = ["compute_bbox", "extract_properties", "compute_polygon_area", "transform_point"]
