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
                 bbox: Dict[str, float], properties: Dict[str, Any] = None):  # 赋值
        self.dxf_type = dxf_type          # LINE, LWPOLYLINE, CIRCLE, TEXT, DIMENSION...
        self.layer = layer                 # 图层名
        self.handle = handle               # DXF handle
        self.bbox = bbox                   # {"x": float, "y": float, "width": float, "height": float}
        self.properties = properties or {} # 额外属性（长度、面积、角度等）

    def to_dict(self) -> dict:
        return {  # 返回
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
        self.file_path = file_path  # 赋值
        self.file_id = file_id  # 赋值
        self.primitives = primitives or []  # 赋值
        self.dimensions = dimensions or []  # 赋值
        self.error = error  # 赋值
        self.success = error is None  # 赋值


# ── 解析引擎 ──────────────────────────────────────────────

class DrawingParser:
    """图纸解析引擎 - 基于 ezdxf"""

    SUPPORTED_FORMATS = {".dxf", ".dwg"}  # 赋值

    def __init__(self):
        self._doc = None  # 赋值

    def parse(self, file_path: str, file_id: str = None) -> DrawingResult:
        """
        解析 DXF/DWG 图纸，提取原始图元

        参数:
            file_path: 图纸文件路径（支持 dxf, dwg）
            file_id: 文件标识（可选，自动生成）

        返回:
            DrawingResult 包含原始图元列表
        """
        path = Path(file_path)  # 赋值
        ext = path.suffix.lower()  # 赋值

        if ext not in self.SUPPORTED_FORMATS:  # 条件判断
            return DrawingResult(  # 返回
                file_path=file_path,  # 赋值
                file_id=file_id or f"baa-file-{path.stem}",  # 赋值
                error=f"不支持的文件格式: {ext}。支持: dxf, dwg"  # 赋值
            )

        if not path.exists():  # 条件判断
            return DrawingResult(  # 返回
                file_path=file_path,  # 赋值
                file_id=file_id or f"baa-file-{path.stem}",  # 赋值
                error=f"文件不存在: {file_path}"  # 赋值
            )

        try:  # 尝试
            if ext == ".dwg":  # 条件判断
                dxf_doc = self._parse_dwg(path)  # 赋值
                if dxf_doc is None:  # 条件判断
                    # 检查文件头，提供针对性建议
                    version_hint = ""  # 赋值
                    try:  # 尝试
                        with open(path, "rb") as f:
                            header = f.read(6)  # 赋值
                        if header.startswith(b"AC10"):  # 条件判断
                            ver = header[:6].decode("ascii", errors="ignore")  # 赋值
                            version_hint = f" (AutoCAD {ver} 格式，"  # 赋值
                    except Exception:  # 捕获异常
                        pass  # 占位
                    return DrawingResult(  # 返回
                        file_path=file_path,  # 赋值
                        file_id=file_id or f"baa-file-{path.stem}",  # 赋值
                        error=f"DWG 解析失败{version_hint}ezdwg 无法读取此文件)。"
                               f"请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。"
                    )
                self._doc = dxf_doc  # 赋值
            else:  # 否则
                self._doc = ezdxf.readfile(str(path))  # 赋值
        except Exception as e:  # 捕获异常
            return DrawingResult(  # 返回
                file_path=file_path,  # 赋值
                file_id=file_id or f"baa-file-{path.stem}",  # 赋值
                error=f"DXF 解析失败: {str(e)}"  # 赋值
            )

        primitives = self._extract_primitives()  # 赋值
        dimensions = self._extract_dimensions()  # 赋值

        return DrawingResult(  # 返回
            file_path=file_path,  # 赋值
            file_id=file_id or f"baa-file-{path.stem}",  # 赋值
            primitives=primitives,  # 赋值
            dimensions=dimensions,  # 赋值
        )

    def _extract_primitives(self) -> List[RawPrimitive]:
        """提取所有图元"""
        primitives = []  # 赋值

        # 模型空间
        msp = self._doc.modelspace()  # 赋值

        for entity in msp:  # 循环
            dxf_type = entity.dxftype()  # 赋值
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'  # 赋值
            handle = entity.dxf.handle if hasattr(entity.dxf, 'handle') else ''  # 赋值

            # 计算边界框
            try:  # 尝试
                bbox = self._compute_bbox(entity)  # 赋值
            except Exception:  # 捕获异常
                continue  # 继续循环

            # 提取几何属性
            props = self._extract_properties(entity)  # 赋值

            primitives.append(RawPrimitive(  # 调用
                dxf_type=dxf_type,  # 赋值
                layer=layer,  # 赋值
                handle=handle,  # 赋值
                bbox=bbox,  # 赋值
                properties=props,  # 赋值
            ))

        return primitives  # 返回

    def _extract_dimensions(self) -> List[Dict]:
        """提取尺寸标注"""
        dimensions = []  # 赋值
        msp = self._doc.modelspace()  # 赋值

        for entity in msp:  # 循环
            dxftype = entity.dxftype()  # 赋值
            if dxftype == 'DIMENSION':  # 条件判断
                try:  # 尝试
                    # ezdxf DIMENSION 实体
                    meas = entity.get_measurement() if hasattr(entity, 'get_measurement') else None  # 赋值
                    defp2 = entity.dxf.defpoint2 if hasattr(entity.dxf, 'defpoint2') else None  # 赋值
                    defp3 = entity.dxf.defpoint3 if hasattr(entity.dxf, 'defpoint3') else None  # 赋值
                    tmid = entity.dxf.text_midpoint if hasattr(entity.dxf, 'text_midpoint') else None  # 赋值
                    dim = {  # 赋值
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
                    if meas is not None and meas > 0.1:  # 条件判断
                        dimensions.append(dim)  # 调用
                except Exception:  # 捕获异常
                    continue  # 继续循环

        return dimensions  # 返回

    # ── DWG 解析（三级兜底） ───────────────────────────

    def _parse_dwg(self, path: Path):
        """解析 DWG 文件，三级兜底策略

        1. ezdwg.read() + export_dxf() 直转
        2. ezdwg Entity.dxf 字典手动逐元素重建
        3. 返回 None 让上层给友好提示
        """
        import tempfile

        # ── 第一级：export_dxf 直转 ──
        try:  # 尝试
            import ezdwg
            dwg_doc = ezdwg.read(str(path))  # 赋值
            tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)  # 赋值
            tmp_path = tmp.name  # 赋值
            tmp.close()  # 调用
            dwg_doc.export_dxf(tmp_path)  # 调用
            dxf_doc = ezdxf.readfile(tmp_path)  # 赋值
            Path(tmp_path).unlink(missing_ok=True)  # 调用
            return dxf_doc  # 返回
        except Exception:  # 捕获异常
            pass  # 占位

        # ── 第二级：手动逐元素转换 ──
        try:  # 尝试
            import ezdwg
            dwg_doc = ezdwg.read(str(path))  # 赋值
            msp_src = dwg_doc.modelspace()  # 赋值
            dxf_doc = ezdxf.new("R2010")  # 赋值
            msp_dst = dxf_doc.modelspace()  # 赋值

            total = 0  # 赋值
            for dxf_type in ["LINE", "LWPOLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT"]:  # 遍历
                try:  # 尝试
                    entities = list(msp_src.query(types=dxf_type))  # 赋值
                except Exception:  # 捕获异常
                    continue  # 继续循环

                for ent in entities:  # 循环
                    try:  # 尝试
                        d = ent.dxf  # 赋值
                        color = d.get("resolved_color_index", 7) or 7  # 赋值

                        if dxf_type == "LINE":  # 条件判断
                            msp_dst.add_line(  # 调用
                                d["start"][:2], d["end"][:2],
                                dxfattribs={"color": color},  # 赋值
                            )
                            total += 1  # 赋值
                        elif dxf_type == "LWPOLYLINE":  # 分支
                            pts = [(p[0], p[1]) for p in d["points"]]  # 赋值
                            if len(pts) >= 2:  # 条件判断
                                msp_dst.add_lwpolyline(pts, dxfattribs={"color": color})  # 调用
                                total += 1  # 赋值
                        elif dxf_type == "CIRCLE":  # 分支
                            msp_dst.add_circle(  # 调用
                                (d["center"][0], d["center"][1]), d["radius"],
                                dxfattribs={"color": color},  # 赋值
                            )
                            total += 1  # 赋值
                        elif dxf_type == "ARC":  # 分支
                            msp_dst.add_arc(  # 调用
                                (d["center"][0], d["center"][1]), d["radius"],
                                d["start_angle"], d["end_angle"],
                                dxfattribs={"color": color},  # 赋值
                            )
                            total += 1  # 赋值
                        elif dxf_type in ("TEXT", "MTEXT"):  # 分支
                            ins = d.get("insert", (0, 0, 0))  # 赋值
                            msp_dst.add_text(  # 调用
                                d.get("text", ""),
                                dxfattribs={  # 赋值
                                    "color": color,
                                    "height": d.get("height", 2.5),
                                    "insert": (ins[0], ins[1]),
                                },
                            )
                            total += 1  # 赋值
                    except Exception:  # 捕获异常
                        pass  # 占位

            if total > 10:  # 条件判断
                return dxf_doc  # 返回
        except Exception:  # 捕获异常
            pass  # 占位

        # ── 第四级：ezdwg raw 逐个类型解码（跳过格式错误的类型）
        try:  # 尝试
            import ezdwg
            from ezdwg import raw
            dwg_doc = ezdwg.read(str(path))  # 赋值
            dxf_doc = ezdxf.new("R2010")  # 赋值
            msp_dst = dxf_doc.modelspace()  # 赋值
            total = 0  # 赋值
            
            # 逐个类型解码，跳过格式错误的
            decode_map = {  # 赋值
                "LINE": lambda: raw.decode_line_entities(str(path)),
                "LWPOLYLINE": lambda: raw.decode_lwpolyline_entities(str(path)),
                "CIRCLE": lambda: raw.decode_circle_entities(str(path)),
                "ARC": lambda: raw.decode_arc_entities(str(path)),
                "TEXT": lambda: raw.decode_text_entities(str(path)),
            }
            for dxf_type, decode_func in decode_map.items():  # 循环
                try:  # 尝试
                    for row in decode_func():  # 循环
                        try:  # 尝试
                            if dxf_type == "LINE":  # 条件判断
                                msp_dst.add_line(  # 调用
                                    (row.get("start_x", 0), row.get("start_y", 0)),
                                    (row.get("end_x", 0), row.get("end_y", 0)),
                                    dxfattribs={"color": row.get("color_index", 7)},  # 赋值
                                )
                                total += 1  # 赋值
                            elif dxf_type == "LWPOLYLINE":  # 分支
                                pts = row.get("points", [])  # 赋值
                                if len(pts) >= 2:  # 条件判断
                                    msp_dst.add_lwpolyline(pts, dxfattribs={"color": row.get("color_index", 7)})  # 调用
                                    total += 1  # 赋值
                            elif dxf_type == "CIRCLE":  # 分支
                                msp_dst.add_circle(  # 调用
                                    (row.get("center_x", 0), row.get("center_y", 0)),
                                    row.get("radius", 1),
                                    dxfattribs={"color": row.get("color_index", 7)},  # 赋值
                                )
                                total += 1  # 赋值
                            elif dxf_type == "ARC":  # 分支
                                msp_dst.add_arc(  # 调用
                                    (row.get("center_x", 0), row.get("center_y", 0)),
                                    row.get("radius", 1),
                                    row.get("start_angle", 0),
                                    row.get("end_angle", 360),
                                    dxfattribs={"color": row.get("color_index", 7)},  # 赋值
                                )
                                total += 1  # 赋值
                            elif dxf_type == "TEXT":  # 分支
                                msp_dst.add_text(  # 调用
                                    row.get("text", ""),
                                    dxfattribs={  # 赋值
                                        "color": row.get("color_index", 7),
                                        "height": row.get("height", 2.5),
                                        "insert": (row.get("insert_x", 0), row.get("insert_y", 0)),
                                    },
                                )
                                total += 1  # 赋值
                        except Exception:  # 捕获异常
                            pass  # 占位
                except Exception:  # 捕获异常
                    continue  # 这种类型格式错误，跳过
            
            if total > 10:  # 条件判断
                return dxf_doc  # 返回
        except Exception:  # 捕获异常
            pass  # 占位

        # ── 第五级：所有方案都失败 ──
        return None  # 返回

    def _compute_bbox(self, entity) -> Dict[str, float]:
        """计算图元边界框

        多层兜底策略，支持 ezdwg 手动重建的图元（无标准 bbox 方法）
        """
        # 1. ezdxf 原生 bbox 方法
        try:  # 尝试
            if hasattr(entity, 'bbox'):  # 条件判断
                bbox = entity.bbox()  # 赋值
                if bbox and bbox.extmin is not None and bbox.extmax is not None:  # 条件判断
                    w = bbox.extmax[0] - bbox.extmin[0]  # 赋值
                    h = bbox.extmax[1] - bbox.extmin[1]  # 赋值
                    if w > 0 or h > 0:  # 条件判断
                        return {"x": bbox.extmin[0], "y": bbox.extmin[1], "width": w, "height": h}  # 返回
        except Exception:  # 捕获异常
            pass  # 占位

        # 2. 从 vertices() 计算（ezdxf 原生图元）
        try:  # 尝试
            points = list(entity.vertices())  # 赋值
            if points:  # 条件判断
                xs, ys = [], []  # 赋值
                for p in points:  # 循环
                    try:  # 尝试
                        xs.append(p.dxf.location.x)  # 调用
                        ys.append(p.dxf.location.y)  # 调用
                    except Exception:  # 捕获异常
                        try:  # 尝试
                            xs.append(p[0])  # 调用
                            ys.append(p[1])  # 调用
                        except Exception:  # 捕获异常
                            pass  # 占位
                if xs and ys:  # 条件判断
                    w, h = max(xs) - min(xs), max(ys) - min(ys)  # 赋值
                    if w > 0 or h > 0:  # 条件判断
                        return {"x": min(xs), "y": min(ys), "width": w, "height": h}  # 返回
        except Exception:  # 捕获异常
            pass  # 占位

        # 3. 从 dxf 字典 points 计算（ezdwg 手动重建的 LWPOLYLINE）
        try:  # 尝试
            pts = entity.dxf.get('points', [])  # 赋值
            if pts:  # 条件判断
                xs = [p[0] for p in pts]  # 赋值
                ys = [p[1] for p in pts]  # 赋值
                return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}  # 返回
        except Exception:  # 捕获异常
            pass  # 占位

        # 4. 从 start/end 端点计算（LINE / ezdwg 重建的 LINE）
        try:  # 尝试
            start = entity.dxf.start  # 赋值
            end = entity.dxf.end  # 赋值
            if start is not None and end is not None:  # 条件判断
                sx = start[0] if hasattr(start, '__getitem__') else start.x  # 赋值
                sy = start[1] if hasattr(start, '__getitem__') else start.y  # 赋值
                ex = end[0] if hasattr(end, '__getitem__') else end.x  # 赋值
                ey = end[1] if hasattr(end, '__getitem__') else end.y  # 赋值
                return {"x": min(sx, ex), "y": min(sy, ey), "width": abs(ex - sx), "height": abs(ey - sy)}  # 返回
        except Exception:  # 捕获异常
            pass  # 占位

        return {"x": 0, "y": 0, "width": 0, "height": 0}  # 返回

    def _extract_properties(self, entity) -> Dict[str, Any]:
        """提取几何属性"""
        props = {}  # 赋值

        try:  # 尝试
            if entity.dxftype() == 'LINE':  # 条件判断
                start = entity.dxf.start  # 赋值
                end = entity.dxf.end  # 赋值
                props["length"] = Vec2(start).distance(Vec2(end))
                props["angle"] = Vec2(end - start).angle_deg

            elif entity.dxftype() == 'CIRCLE':  # 分支
                props["radius"] = entity.dxf.radius
                props["diameter"] = entity.dxf.radius * 2

            elif entity.dxftype() == 'LWPOLYLINE':  # 分支
                if hasattr(entity, 'length'):  # 条件判断
                    props["length"] = entity.length
                if entity.closed:  # 条件判断
                    props["area"] = self._compute_polygon_area(entity)
                # 记录顶点数（ezdwg 重建的图元用 points）
                try:  # 尝试
                    pts = entity.dxf.get('points', [])  # 赋值
                    props["point_count"] = len(pts)
                except Exception:  # 捕获异常
                    try:  # 尝试
                        pts = list(entity.vertices())  # 赋值
                        props["point_count"] = len(pts)
                    except Exception:  # 捕获异常
                        pass  # 占位

            elif entity.dxftype() == 'ARC':  # 分支
                props["radius"] = entity.dxf.radius
                props["start_angle"] = entity.dxf.start_angle
                props["end_angle"] = entity.dxf.end_angle

            elif entity.dxftype() == 'TEXT':  # 分支
                props["text"] = entity.dxf.text
                props["height"] = entity.dxf.height

            elif entity.dxftype() == 'INSERT':  # 分支
                # 提取块名和插入点
                try:  # 尝试
                    block_name = entity.dxf.name if hasattr(entity.dxf, 'name') else ''  # 赋值
                    props["block_name"] = block_name or ''
                    ins = entity.dxf.insert if hasattr(entity.dxf, 'insert') else None  # 赋值
                    if ins:  # 条件判断
                        props["insert_x"] = ins[0] if hasattr(ins, '__getitem__') else ins.x
                        props["insert_y"] = ins[1] if hasattr(ins, '__getitem__') else ins.y
                except Exception:  # 捕获异常
                    pass  # 占位

        except Exception:  # 捕获异常
            pass  # 占位

        return props  # 返回

    @staticmethod
    def _compute_polygon_area(entity) -> float:
        """计算多边形面积"""
        try:  # 尝试
            points = list(entity.vertices())  # 赋值
            if len(points) < 3:  # 条件判断
                return 0.0  # 返回
            # 鞋带公式
            xs = [p[0] for p in points]  # 赋值
            ys = [p[1] for p in points]  # 赋值
            area = 0.5 * abs(sum(xs[i]*ys[i+1] - xs[i+1]*ys[i]  # 赋值
                                 for i in range(len(points)-1)))  # 循环
            return area  # 返回
        except Exception:  # 捕获异常
            return 0.0  # 返回
