"""
BAA 图纸解析引擎 - ezdxf 集成
负责：DXF 文件解析、基础几何提取
"""
import ezdxf
from ezdxf.math import Vec2
from pathlib import Path
from typing import List, Dict, Any, Optional

# ── 数据结构 ──────────────────────────────────────────────

class RawPrimitive:
    """原始图元 - 图纸解析管线的输出"""
    def __init__(self, dxf_type: str, layer: str, handle: str,
                 bbox: Dict[str, float], properties: Dict[str, Any] = None):
        self.dxf_type = dxf_type          # LINE, LWPOLYLINE, CIRCLE, TEXT, DIMENSION...
        self.layer = layer                 # 图层名
        self.handle = handle               # DXF handle
        self.bbox = bbox                   # {"x": float, "y": float, "width": float, "height": float}
        self.properties = properties or {} # 额外属性（长度、面积、角度等）

    def to_dict(self) -> dict:
        return {
            "dxf_type": self.dxf_type,
            "layer": self.layer,
            "handle": self.handle,
            "bbox": self.bbox,
            "properties": self.properties,
        }


class DrawingResult:
    """图纸解析结果"""
    def __init__(self, file_path: str, file_id: str,
                 primitives: List[RawPrimitive] = None,
                 dimensions: List[Dict] = None,
                 error: Optional[str] = None):
        self.file_path = file_path
        self.file_id = file_id
        self.primitives = primitives or []
        self.dimensions = dimensions or []
        self.error = error
        self.success = error is None


# ── 解析引擎 ──────────────────────────────────────────────

class DrawingParser:
    """图纸解析引擎 - 基于 ezdxf"""

    SUPPORTED_FORMATS = {".dxf", ".dwg"}

    def __init__(self):
        self._doc = None

    def parse(self, file_path: str, file_id: str = None) -> DrawingResult:
        """
        解析 DXF/DWG 图纸，提取原始图元

        参数:
            file_path: 图纸文件路径（支持 dxf, dwg）
            file_id: 文件标识（可选，自动生成）

        返回:
            DrawingResult 包含原始图元列表
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext not in self.SUPPORTED_FORMATS:
            return DrawingResult(
                file_path=file_path,
                file_id=file_id or f"baa-file-{path.stem}",
                error=f"不支持的文件格式: {ext}。支持: dxf, dwg"
            )

        if not path.exists():
            return DrawingResult(
                file_path=file_path,
                file_id=file_id or f"baa-file-{path.stem}",
                error=f"文件不存在: {file_path}"
            )

        try:
            if ext == ".dwg":
                dxf_doc = self._parse_dwg(path)
                if dxf_doc is None:
                    # 检查文件头，提供针对性建议
                    version_hint = ""
                    try:
                        with open(path, "rb") as f:
                            header = f.read(6)
                        if header.startswith(b"AC10"):
                            ver = header[:6].decode("ascii", errors="ignore")
                            version_hint = f" (AutoCAD {ver} 格式，"
                    except Exception:
                        pass
                    return DrawingResult(
                        file_path=file_path,
                        file_id=file_id or f"baa-file-{path.stem}",
                        error=f"DWG 解析失败{version_hint}ezdwg 无法读取此文件)。"
                               f"请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。"
                    )
                self._doc = dxf_doc
            else:
                self._doc = ezdxf.readfile(str(path))
        except Exception as e:
            return DrawingResult(
                file_path=file_path,
                file_id=file_id or f"baa-file-{path.stem}",
                error=f"DXF 解析失败: {str(e)}"
            )

        primitives = self._extract_primitives()
        dimensions = self._extract_dimensions()

        return DrawingResult(
            file_path=file_path,
            file_id=file_id or f"baa-file-{path.stem}",
            primitives=primitives,
            dimensions=dimensions,
        )

    def _extract_primitives(self) -> List[RawPrimitive]:
        """提取所有图元"""
        primitives = []

        # 模型空间
        msp = self._doc.modelspace()

        for entity in msp:
            dxf_type = entity.dxftype()
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'
            handle = entity.dxf.handle if hasattr(entity.dxf, 'handle') else ''

            # 计算边界框
            try:
                bbox = self._compute_bbox(entity)
            except Exception:
                continue

            # 提取几何属性
            props = self._extract_properties(entity)

            primitives.append(RawPrimitive(
                dxf_type=dxf_type,
                layer=layer,
                handle=handle,
                bbox=bbox,
                properties=props,
            ))

        return primitives

    def _extract_dimensions(self) -> List[Dict]:
        """提取尺寸标注"""
        dimensions = []
        msp = self._doc.modelspace()

        for entity in msp:
            dxftype = entity.dxftype()
            if dxftype == 'DIMENSION':
                try:
                    # ezdxf DIMENSION 实体
                    meas = entity.get_measurement() if hasattr(entity, 'get_measurement') else None
                    defp2 = entity.dxf.defpoint2 if hasattr(entity.dxf, 'defpoint2') else None
                    defp3 = entity.dxf.defpoint3 if hasattr(entity.dxf, 'defpoint3') else None
                    tmid = entity.dxf.text_midpoint if hasattr(entity.dxf, 'text_midpoint') else None
                    dim = {
                        "handle": entity.dxf.handle if hasattr(entity.dxf, 'handle') else '',
                        "layer": entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',
                        "measurement": meas,
                        "text": entity.get_measurement_text() if hasattr(entity, 'get_measurement_text') else str(meas),
                        "dimtype": str(entity.dxf.dimtype) if hasattr(entity.dxf, 'dimtype') else 'LINEAR',
                        "position": {
                            "x": entity.dxf.defpoint.x if hasattr(entity.dxf.defpoint, 'x') else 0,
                            "y": entity.dxf.defpoint.y if hasattr(entity.dxf.defpoint, 'y') else 0,
                        },
                        "defpoint2": {
                            "x": defp2.x if defp2 and hasattr(defp2, 'x') else 0,
                            "y": defp2.y if defp2 and hasattr(defp2, 'y') else 0,
                        },
                        "defpoint3": {
                            "x": defp3.x if defp3 and hasattr(defp3, 'x') else 0,
                            "y": defp3.y if defp3 and hasattr(defp3, 'y') else 0,
                        },
                        "text_midpoint": {
                            "x": tmid.x if tmid and hasattr(tmid, 'x') else 0,
                            "y": tmid.y if tmid and hasattr(tmid, 'y') else 0,
                        },
                    }
                    if meas is not None and meas > 0.1:
                        dimensions.append(dim)
                except Exception:
                    continue

        return dimensions

    # ── DWG 解析（三级兜底） ───────────────────────────

    def _parse_dwg(self, path: Path):
        """解析 DWG 文件，三级兜底策略

        1. ezdwg.read() + export_dxf() 直转
        2. ezdwg Entity.dxf 字典手动逐元素重建
        3. 返回 None 让上层给友好提示
        """
        import tempfile

        # ── 第一级：export_dxf 直转 ──
        try:
            import ezdwg
            dwg_doc = ezdwg.read(str(path))
            tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
            tmp_path = tmp.name
            tmp.close()
            dwg_doc.export_dxf(tmp_path)
            dxf_doc = ezdxf.readfile(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
            return dxf_doc
        except Exception:
            pass

        # ── 第二级：手动逐元素转换 ──
        try:
            import ezdwg
            dwg_doc = ezdwg.read(str(path))
            msp_src = dwg_doc.modelspace()
            dxf_doc = ezdxf.new("R2010")
            msp_dst = dxf_doc.modelspace()

            total = 0
            for dxf_type in ["LINE", "LWPOLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT"]:
                try:
                    entities = list(msp_src.query(types=dxf_type))
                except Exception:
                    continue

                for ent in entities:
                    try:
                        d = ent.dxf
                        color = d.get("resolved_color_index", 7) or 7

                        if dxf_type == "LINE":
                            msp_dst.add_line(
                                d["start"][:2], d["end"][:2],
                                dxfattribs={"color": color},
                            )
                            total += 1
                        elif dxf_type == "LWPOLYLINE":
                            pts = [(p[0], p[1]) for p in d["points"]]
                            if len(pts) >= 2:
                                msp_dst.add_lwpolyline(pts, dxfattribs={"color": color})
                                total += 1
                        elif dxf_type == "CIRCLE":
                            msp_dst.add_circle(
                                (d["center"][0], d["center"][1]), d["radius"],
                                dxfattribs={"color": color},
                            )
                            total += 1
                        elif dxf_type == "ARC":
                            msp_dst.add_arc(
                                (d["center"][0], d["center"][1]), d["radius"],
                                d["start_angle"], d["end_angle"],
                                dxfattribs={"color": color},
                            )
                            total += 1
                        elif dxf_type in ("TEXT", "MTEXT"):
                            ins = d.get("insert", (0, 0, 0))
                            msp_dst.add_text(
                                d.get("text", ""),
                                dxfattribs={
                                    "color": color,
                                    "height": d.get("height", 2.5),
                                    "insert": (ins[0], ins[1]),
                                },
                            )
                            total += 1
                    except Exception:
                        pass

            if total > 10:
                return dxf_doc
        except Exception:
            pass

        # ── 第四级：ezdwg raw 逐个类型解码（跳过格式错误的类型）
        try:
            import ezdwg
            from ezdwg import raw
            dwg_doc = ezdwg.read(str(path))
            dxf_doc = ezdxf.new("R2010")
            msp_dst = dxf_doc.modelspace()
            total = 0
            
            # 逐个类型解码，跳过格式错误的
            decode_map = {
                "LINE": lambda: raw.decode_line_entities(str(path)),
                "LWPOLYLINE": lambda: raw.decode_lwpolyline_entities(str(path)),
                "CIRCLE": lambda: raw.decode_circle_entities(str(path)),
                "ARC": lambda: raw.decode_arc_entities(str(path)),
                "TEXT": lambda: raw.decode_text_entities(str(path)),
            }
            for dxf_type, decode_func in decode_map.items():
                try:
                    for row in decode_func():
                        try:
                            if dxf_type == "LINE":
                                msp_dst.add_line(
                                    (row.get("start_x", 0), row.get("start_y", 0)),
                                    (row.get("end_x", 0), row.get("end_y", 0)),
                                    dxfattribs={"color": row.get("color_index", 7)},
                                )
                                total += 1
                            elif dxf_type == "LWPOLYLINE":
                                pts = row.get("points", [])
                                if len(pts) >= 2:
                                    msp_dst.add_lwpolyline(pts, dxfattribs={"color": row.get("color_index", 7)})
                                    total += 1
                            elif dxf_type == "CIRCLE":
                                msp_dst.add_circle(
                                    (row.get("center_x", 0), row.get("center_y", 0)),
                                    row.get("radius", 1),
                                    dxfattribs={"color": row.get("color_index", 7)},
                                )
                                total += 1
                            elif dxf_type == "ARC":
                                msp_dst.add_arc(
                                    (row.get("center_x", 0), row.get("center_y", 0)),
                                    row.get("radius", 1),
                                    row.get("start_angle", 0),
                                    row.get("end_angle", 360),
                                    dxfattribs={"color": row.get("color_index", 7)},
                                )
                                total += 1
                            elif dxf_type == "TEXT":
                                msp_dst.add_text(
                                    row.get("text", ""),
                                    dxfattribs={
                                        "color": row.get("color_index", 7),
                                        "height": row.get("height", 2.5),
                                        "insert": (row.get("insert_x", 0), row.get("insert_y", 0)),
                                    },
                                )
                                total += 1
                        except Exception:
                            pass
                except Exception:
                    continue  # 这种类型格式错误，跳过
            
            if total > 10:
                return dxf_doc
        except Exception:
            pass

        # ── 第五级：所有方案都失败 ──
        return None

    def _compute_bbox(self, entity) -> Dict[str, float]:
        """计算图元边界框

        多层兜底策略，支持 ezdwg 手动重建的图元（无标准 bbox 方法）
        """
        # 1. ezdxf 原生 bbox 方法
        try:
            if hasattr(entity, 'bbox'):
                bbox = entity.bbox()
                if bbox and bbox.extmin is not None and bbox.extmax is not None:
                    w = bbox.extmax[0] - bbox.extmin[0]
                    h = bbox.extmax[1] - bbox.extmin[1]
                    if w > 0 or h > 0:
                        return {"x": bbox.extmin[0], "y": bbox.extmin[1], "width": w, "height": h}
        except Exception:
            pass

        # 2. 从 vertices() 计算（ezdxf 原生图元）
        try:
            points = list(entity.vertices())
            if points:
                xs, ys = [], []
                for p in points:
                    try:
                        xs.append(p.dxf.location.x)
                        ys.append(p.dxf.location.y)
                    except Exception:
                        try:
                            xs.append(p[0])
                            ys.append(p[1])
                        except Exception:
                            pass
                if xs and ys:
                    w, h = max(xs) - min(xs), max(ys) - min(ys)
                    if w > 0 or h > 0:
                        return {"x": min(xs), "y": min(ys), "width": w, "height": h}
        except Exception:
            pass

        # 3. 从 dxf 字典 points 计算（ezdwg 手动重建的 LWPOLYLINE）
        try:
            pts = entity.dxf.get('points', [])
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
        except Exception:
            pass

        # 4. 从 start/end 端点计算（LINE / ezdwg 重建的 LINE）
        try:
            start = entity.dxf.start
            end = entity.dxf.end
            if start is not None and end is not None:
                sx = start[0] if hasattr(start, '__getitem__') else start.x
                sy = start[1] if hasattr(start, '__getitem__') else start.y
                ex = end[0] if hasattr(end, '__getitem__') else end.x
                ey = end[1] if hasattr(end, '__getitem__') else end.y
                return {"x": min(sx, ex), "y": min(sy, ey), "width": abs(ex - sx), "height": abs(ey - sy)}
        except Exception:
            pass

        return {"x": 0, "y": 0, "width": 0, "height": 0}

    def _extract_properties(self, entity) -> Dict[str, Any]:
        """提取几何属性"""
        props = {}

        try:
            if entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                props["length"] = Vec2(start).distance(Vec2(end))
                props["angle"] = Vec2(end - start).angle_deg

            elif entity.dxftype() == 'CIRCLE':
                props["radius"] = entity.dxf.radius
                props["diameter"] = entity.dxf.radius * 2

            elif entity.dxftype() == 'LWPOLYLINE':
                if hasattr(entity, 'length'):
                    props["length"] = entity.length
                if entity.closed:
                    props["area"] = self._compute_polygon_area(entity)
                # 记录顶点数（ezdwg 重建的图元用 points）
                try:
                    pts = entity.dxf.get('points', [])
                    props["point_count"] = len(pts)
                except Exception:
                    try:
                        pts = list(entity.vertices())
                        props["point_count"] = len(pts)
                    except Exception:
                        pass

            elif entity.dxftype() == 'ARC':
                props["radius"] = entity.dxf.radius
                props["start_angle"] = entity.dxf.start_angle
                props["end_angle"] = entity.dxf.end_angle

            elif entity.dxftype() == 'TEXT':
                props["text"] = entity.dxf.text
                props["height"] = entity.dxf.height

            elif entity.dxftype() == 'INSERT':
                # 提取块名和插入点
                try:
                    block_name = entity.dxf.name if hasattr(entity.dxf, 'name') else ''
                    props["block_name"] = block_name or ''
                    ins = entity.dxf.insert if hasattr(entity.dxf, 'insert') else None
                    if ins:
                        props["insert_x"] = ins[0] if hasattr(ins, '__getitem__') else ins.x
                        props["insert_y"] = ins[1] if hasattr(ins, '__getitem__') else ins.y
                except Exception:
                    pass

        except Exception:
            pass

        return props

    @staticmethod
    def _compute_polygon_area(entity) -> float:
        """计算多边形面积"""
        try:
            points = list(entity.vertices())
            if len(points) < 3:
                return 0.0
            # 鞋带公式
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            area = 0.5 * abs(sum(xs[i]*ys[i+1] - xs[i+1]*ys[i]
                                 for i in range(len(points)-1)))
            return area
        except Exception:
            return 0.0
