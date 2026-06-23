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
            if entity.dxftype() in ('DIMENSION', 'ALIGNED_DIMENSION',
                                     'ROTATED_DIMENSION', 'LINEAR_DIMENSION'):
                try:
                    dim = {
                        "handle": entity.dxf.handle,
                        "layer": entity.dxf.layer,
                        "measurement": entity.get_measurement(),
                        "text": entity.get_measurement_text(),
                        "position": {"x": entity.dxf.defpoint.x,
                                      "y": entity.dxf.defpoint.y},
                    }
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

        # ── 第三级：所有方案都失败 ──
        return None

    def _compute_bbox(self, entity) -> Dict[str, float]:
        """计算图元边界框"""
        try:
            if hasattr(entity, 'bbox'):
                bbox = entity.bbox()
                return {
                    "x": bbox.extmin[0],
                    "y": bbox.extmin[1],
                    "width": bbox.extmax[0] - bbox.extmin[0],
                    "height": bbox.extmax[1] - bbox.extmin[1],
                }
        except Exception:
            pass

        # 兜底：从顶点计算
        try:
            points = list(entity.vertices())
            if points:
                xs = [p.dxf.location.x for p in points]
                ys = [p.dxf.location.y for p in points]
                return {
                    "x": min(xs), "y": min(ys),
                    "width": max(xs) - min(xs),
                    "height": max(ys) - min(ys),
                }
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

            elif entity.dxftype() == 'TEXT':
                props["text"] = entity.dxf.text
                props["height"] = entity.dxf.height

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
