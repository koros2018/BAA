"""
几何计算子模块 — 边界框、属性提取、多边形面积

从 drawing_parser.py 拆分出来，消除 1556 行单文件的技术债。
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def compute_bbox(entity) -> Optional[Dict[str, float]]:
    """计算图元边界框

    多层兜底策略，支持 ezdwg 手动重建的图元（无标准 bbox 方法）。
    """
    # 1. ezdxf 原生 bbox 方法
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

    # 2. 从 vertices() 计算（ezdxf 原生图元）
    try:
        points = list(entity.vertices())
        if points:
            xs, ys = [], []
            for p in points:
                try:
                    xs.append(p.x)
                    ys.append(p.y)
                except Exception:
                    pass
            if xs and ys:
                w = max(xs) - min(xs)
                h = max(ys) - min(ys)
                return {"x": min(xs), "y": min(ys), "width": w, "height": h}
    except Exception:
        pass

    # 3. 从 handle 属性计算（ezdxf 特殊图元）
    try:
        handle = entity.dxf.handle
        if hasattr(handle, "get"):
            x = handle.get("x", 0)
            y = handle.get("y", 0)
            w = handle.get("width", 0)
            h = handle.get("height", 0)
            return {"x": x, "y": y, "width": w, "height": h}
    except Exception:
        pass

    # 4. 从 insert 属性计算（INSERT 实体）
    try:
        if hasattr(entity, "dxf") and hasattr(entity.dxf, "insert"):
            ins = entity.dxf.insert
            if hasattr(ins, "__getitem__"):
                return {"x": ins[0], "y": ins[1], "width": 0, "height": 0}
    except Exception:
        pass

    # 5. 尝试 get_bbox（ezdxf 部分图元支持）
    try:
        if hasattr(entity, "get_bbox"):
            bbox = entity.get_bbox()
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
    """
    from ezdxf.math import Vec2
    import math

    try:
        # 优先尝试 LWPOLYLINE 的面积
        if hasattr(entity, "length"):
            length = entity.length
            # LWPOLYLINE 如果是闭合的，使用顶点坐标计算
            try:
                points = list(entity.vertices())
                if points and len(points) >= 3:
                    xs = [p.x for p in points]
                    ys = [p.y for p in points]
                    area = 0.0
                    n = len(xs)
                    for i in range(n):
                        j = (i + 1) % n
                        area += xs[i] * ys[j] - xs[j] * ys[i]
                    return abs(area) / 2.0
            except Exception:
                pass

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
