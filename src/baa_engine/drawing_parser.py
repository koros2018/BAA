"""
BAA 图纸解析引擎 - ezdxf 集成
负责：DXF/DWG 文件解析、基础几何提取

升级日志:
  v1.25.0 (2026-06-30): P13 DWG 解析覆盖率提升
    - 天正 T3 格式自动检测与提示
    - DWG→同目录 DXF 自动兜底
    - LibreCAD CLI 自动转换路径
    - 第二级手动转换增强（INSERT 展开、HATCH、SOLID）
    - 更精确的错误提示与降级策略
"""
import ezdxf
from ezdxf.math import Vec2
from pathlib import Path
from typing import List, Dict, Any, Optional
import subprocess
import tempfile
import shutil

# ── ezdwg fallback（系统级安装，venv 可能不可见） ──────
_ezdwg_raw = None
try:
    from ezdwg import raw as _ezdwg_raw
except ImportError:
    try:
        import sys as _sys
        _sys.path.insert(0, '/home/kezhigang/.local/lib/python3.12/site-packages')
        from ezdwg import raw as _ezdwg_raw
    except ImportError:
        pass

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
        """处理RawPrimitive相关逻辑"""
        return {  # 返回
            "dxf_type": self.dxf_type,  # 字段
            "layer": self.layer,  # 字段
            "handle": self.handle,  # 字段
            "bbox": self.bbox,  # 字段
            "properties": self.properties,  # 字段
        }  # 闭合


class DrawingResult:
    """图纸解析结果"""
    def __init__(self, file_path: str, file_id: str,
                 primitives: List[RawPrimitive] = None,  # 操作
                 dimensions: List[Dict] = None,  # 操作
                 error: Optional[str] = None):  # 操作
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
            )  # 闭合

        if not path.exists():  # 条件判断
            return DrawingResult(  # 返回
                file_path=file_path,  # 赋值
                file_id=file_id or f"baa-file-{path.stem}",  # 赋值
                error=f"文件不存在: {file_path}"  # 赋值
            )  # 闭合

        try:  # 尝试
            if ext == ".dwg":  # 条件判断
                dxf_doc = self._parse_dwg(path)  # 赋值
                if dxf_doc is None:  # 条件判断
                    # DWG 格式检测
                    format_hint = self._detect_dwg_format(path)
                    
                    # 版本检测
                    version_hint = ""  # 赋值
                    try:  # 尝试
                        ver = _ezdwg_raw.detect_version(str(path)) if _ezdwg_raw else None
                        if ver is None:
                            raise ValueError("ezdwg not available")
                        version_hint = f" (AutoCAD {ver})"
                    except Exception:
                        try:
                            with open(path, "rb") as f:
                                header = f.read(6)
                            if header.startswith(b"AC10"):
                                ver = header[:6].decode("ascii", errors="ignore")
                                version_hint = f" (AutoCAD {ver})"
                        except Exception:
                            pass

                    # 构建诊断信息
                    diag_parts = ["DWG 解析失败"]
                    if version_hint:
                        diag_parts.append(version_hint)
                    if format_hint == '天正 T3 加密格式':
                        diag_parts.append(f"，检测到{format_hint}")
                        diag_parts.append("请用 AutoCAD 打开后执行 T3转T0(T3→T0) 命令，或另存为 DXF 格式。")
                    elif format_hint:
                        diag_parts.append(f"，检测到{format_hint}")
                        diag_parts.append("请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。")
                    else:
                        diag_parts.append("，当前解析器无法读取此格式。")
                        diag_parts.append("请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。")
                    
                    return DrawingResult(  # 返回
                        file_path=file_path,  # 赋值
                        file_id=file_id or f"baa-file-{path.stem}",  # 赋值
                        error="".join(diag_parts)
                    )  # 闭合
                self._doc = dxf_doc  # 赋值
            else:  # 否则
                self._doc = ezdxf.readfile(str(path))  # 赋值
        except Exception as e:  # 捕获异常
            return DrawingResult(  # 返回
                file_path=file_path,  # 赋值
                file_id=file_id or f"baa-file-{path.stem}",  # 赋值
                error=f"DXF 解析失败: {str(e)}"  # 赋值
            )  # 闭合

        primitives = self._extract_primitives()  # 赋值
        dimensions = self._extract_dimensions()  # 赋值

        return DrawingResult(  # 返回
            file_path=file_path,  # 赋值
            file_id=file_id or f"baa-file-{path.stem}",  # 赋值
            primitives=primitives,  # 赋值
            dimensions=dimensions,  # 赋值
        )  # 闭合

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
            ))  # 闭合

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
                        "handle": entity.dxf.handle if hasattr(entity.dxf, 'handle') else '',  # 字段
                        "layer": entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',  # 字段
                        "measurement": meas,  # 字段
                        "text": entity.get_measurement_text() if hasattr(entity, 'get_measurement_text') else str(meas),  # 字段
                        "dimtype": str(entity.dxf.dimtype) if hasattr(entity.dxf, 'dimtype') else 'LINEAR',  # 字段
                        "position": {  # 字段
                            "x": entity.dxf.defpoint.x if hasattr(entity.dxf.defpoint, 'x') else 0,  # 字段
                            "y": entity.dxf.defpoint.y if hasattr(entity.dxf.defpoint, 'y') else 0,  # 字段
                        },  # 闭合
                        "defpoint2": {  # 字段
                            "x": defp2.x if defp2 and hasattr(defp2, 'x') else 0,  # 字段
                            "y": defp2.y if defp2 and hasattr(defp2, 'y') else 0,  # 字段
                        },  # 闭合
                        "defpoint3": {  # 字段
                            "x": defp3.x if defp3 and hasattr(defp3, 'x') else 0,  # 字段
                            "y": defp3.y if defp3 and hasattr(defp3, 'y') else 0,  # 字段
                        },  # 闭合
                        "text_midpoint": {  # 字段
                            "x": tmid.x if tmid and hasattr(tmid, 'x') else 0,  # 字段
                            "y": tmid.y if tmid and hasattr(tmid, 'y') else 0,  # 字段
                        },  # 闭合
                    }  # 闭合
                    if meas is not None and meas > 0.1:  # 条件判断
                        dimensions.append(dim)  # 调用
                except Exception:  # 捕获异常
                    continue  # 继续循环

        return dimensions  # 返回

    # ── DWG 解析（六级兜底） ───────────────────────────

    def _detect_dwg_format(self, path: Path) -> Optional[str]:
        """检测 DWG 文件格式问题，返回诊断信息

        检测类型：
        1. 天正 T3 加密：AcDbObjects section size 远超文件大小
        2. 格式损坏/不兼容：section offset 超出文件大小
        3. 其他 ezdwg 无法解析的格式

        返回:
            str: 格式说明，可正常解析返回 None
        """
        try:
            if not _ezdwg_raw:
                return None
            sections = _ezdwg_raw.list_section_locators(str(path))
            file_size = path.stat().st_size

            for name, offset, size in sections:
                expected_end = offset + size
                if name == 'AcDb:AcDbObjects' and expected_end > file_size * 1.5:
                    return '天正 T3 加密格式'
                # section 在文件范围外
                if offset > file_size and name not in ('', 'Unknown3'):
                    return '格式不兼容'
            return None
        except Exception:
            return None

    def _try_same_dir_dxf(self, path: Path) -> Optional[Any]:
        """尝试加载同目录的 DXF 文件作为兜底

        天正 T3 图纸通常同时提供 DWG 和 DXF 版本。
        如果同目录有同名 DXF，直接用它。
        """
        dxf_path = path.with_suffix('.dxf')
        if dxf_path.exists():
            try:
                dxf_doc = ezdxf.readfile(str(dxf_path))
                msp = dxf_doc.modelspace()
                count = len(list(msp))
                if count > 10:
                    return dxf_doc
            except Exception:
                pass
        return None

    def _try_librecad_convert(self, path: Path) -> Optional[Any]:
        """尝试用 LibreCAD CLI 将 DWG 转换为 DXF

        LibreCAD 对天正 T3 格式有较好的兼容性。
        需要系统中安装 LibreCAD。
        """
        librecad = shutil.which('librecad')
        if not librecad:
            return None

        tmp_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False)
        tmp_path = tmp_dxf.name
        tmp_dxf.close()

        try:
            result = subprocess.run(
                [librecad, '-c', str(path), tmp_path],
                capture_output=True,
                timeout=60,
                cwd='/tmp'
            )
            if result.returncode == 0 and Path(tmp_path).stat().st_size > 1000:
                dxf_doc = ezdxf.readfile(tmp_path)
                msp = dxf_doc.modelspace()
                count = len(list(msp))
                if count > 10:
                    return dxf_doc
        except Exception:
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return None

    def _try_ezdwg_export_dxf(self, path: Path) -> Optional[Any]:
        """第 1 级：ezdwg.read() + export_dxf() 直转"""
        try:
            from ezdwg import Document as _DwgDoc
            dwg_doc = _DwgDoc.read(str(path))
            tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
            tmp_path = tmp.name
            tmp.close()
            dwg_doc.export_dxf(tmp_path)
            dxf_doc = ezdxf.readfile(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
            return dxf_doc
        except Exception:
            return None

    def _try_manual_convert(self, path: Path) -> Optional[Any]:
        """第 2 级：ezdwg Entity.dxf 字典手动逐元素重建

        增强版：增加 INSERT 展开、HATCH、SOLID 实体支持
        """
        try:
            from ezdwg import Document as _DwgDoc
            dwg_doc = _DwgDoc.read(str(path))
            msp_src = dwg_doc.modelspace()
            dxf_doc = ezdxf.new("R2010")
            msp_dst = dxf_doc.modelspace()

            total = 0
            for dxf_type in ["LINE", "LWPOLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT",
                             "INSERT", "HATCH", "SOLID", "POINT", "ELLIPSE", "SPLINE"]:
                try:
                    entities = list(msp_src.query(types=dxf_type))
                except Exception:
                    continue

                for ent in entities:
                    try:
                        d = ent.dxf
                        color = d.get("resolved_color_index", 7) or 7
                        layer = d.get("layer", "0")

                        if dxf_type == "LINE":
                            msp_dst.add_line(
                                d["start"][:2], d["end"][:2],
                                dxfattribs={"color": color, "layer": layer},
                            )
                            total += 1
                        elif dxf_type == "LWPOLYLINE":
                            pts = [(p[0], p[1]) for p in d["points"]]
                            if len(pts) >= 2:
                                msp_dst.add_lwpolyline(pts, dxfattribs={"color": color, "layer": layer})
                                total += 1
                        elif dxf_type == "CIRCLE":
                            msp_dst.add_circle(
                                (d["center"][0], d["center"][1]), d["radius"],
                                dxfattribs={"color": color, "layer": layer},
                            )
                            total += 1
                        elif dxf_type == "ARC":
                            msp_dst.add_arc(
                                (d["center"][0], d["center"][1]), d["radius"],
                                d["start_angle"], d["end_angle"],
                                dxfattribs={"color": color, "layer": layer},
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
                                    "layer": layer,
                                },
                            )
                            total += 1
                        elif dxf_type == "INSERT":
                            ins_pt = d.get("insert", (0, 0, 0))
                            name = d.get("name", "UNKNOWN")
                            x, y = ins_pt[0], ins_pt[1]
                            half = 50.0
                            msp_dst.add_lwpolyline([
                                (x - half, y - half),
                                (x + half, y - half),
                                (x + half, y + half),
                                (x - half, y + half),
                                (x - half, y - half),
                            ], dxfattribs={"color": 1, "layer": layer})
                            msp_dst.add_text(
                                name,
                                dxfattribs={
                                    "color": 1, "height": 100.0,
                                    "insert": (x + half + 10, y), "layer": layer,
                                },
                            )
                            total += 1
                        elif dxf_type == "HATCH":
                            try:
                                paths = ent.paths
                                for path_data in paths:
                                    vertices = list(path_data.vertices)
                                    if len(vertices) >= 3:
                                        pts = [(v[0], v[1]) for v in vertices]
                                        msp_dst.add_lwpolyline(
                                            pts + [pts[0]],
                                            dxfattribs={"color": color, "layer": layer},
                                        )
                                        total += 1
                            except Exception:
                                pass
                        elif dxf_type == "SOLID":
                            pts_2d = [(d.get(f"{ax}{i}", 0), d.get(f"{ay}{i}", 0))
                                      for ax, ay, i in [("x", "y", 0), ("x", "y", 1),
                                                        ("x", "y", 2), ("x", "y", 3)]]
                            if len(pts_2d) >= 3:
                                msp_dst.add_solid(pts_2d[:4], dxfattribs={"color": color, "layer": layer})
                                total += 1
                        elif dxf_type == "POINT":
                            pt = d.get("location", (0, 0, 0))
                            msp_dst.add_point((pt[0], pt[1]), dxfattribs={"color": color, "layer": layer})
                            total += 1
                    except Exception:
                        pass

            if total > 10:
                return dxf_doc
        except Exception:
            pass
        return None

    def _try_raw_decode(self, path: Path) -> Optional[Any]:
        """第 3 级：ezdwg raw 逐个类型解码（跳过格式错误的类型）

        增强版：增加 HATCH、INSERT、DIMENSION 等实体的 raw 层解码
        """
        try:
            if not _ezdwg_raw:
                raise ImportError("ezdwg not available")

            dxf_doc = ezdxf.new("R2010")
            msp_dst = dxf_doc.modelspace()
            total = 0

            _raw = _ezdwg_raw
            decode_map = {
                "LINE": lambda: _raw.decode_line_entities(str(path)),
                "LWPOLYLINE": lambda: _raw.decode_lwpolyline_entities(str(path)),
                "CIRCLE": lambda: _raw.decode_circle_entities(str(path)),
                "ARC": lambda: _raw.decode_arc_entities(str(path)),
                "TEXT": lambda: _raw.decode_text_entities(str(path)),
                "DIMENSION": lambda: _raw.decode_dimension_entities(str(path)),
                "INSERT": lambda: _raw.decode_insert_entities(str(path)),
                "HATCH": lambda: _raw.decode_hatch_entities(str(path)),
                "SOLID": lambda: _raw.decode_solid_entities(str(path)),
                "ELLIPSE": lambda: _raw.decode_ellipse_entities(str(path)),
                "SPLINE": lambda: _raw.decode_spline_entities(str(path)),
                "POINT": lambda: _raw.decode_point_entities(str(path)),
                "MTEXT": lambda: _raw.decode_mtext_entities(str(path)),
                "LEADER": lambda: _raw.decode_leader_entities(str(path)),
            }
            for dxf_type, decode_func in decode_map.items():
                try:
                    for row in decode_func():
                        try:
                            color = row.get("color_index", 7)
                            layer = row.get("layer", "0")
                            if dxf_type == "LINE":
                                msp_dst.add_line(
                                    (row.get("start_x", 0), row.get("start_y", 0)),
                                    (row.get("end_x", 0), row.get("end_y", 0)),
                                    dxfattribs={"color": color, "layer": layer},
                                )
                                total += 1
                            elif dxf_type == "LWPOLYLINE":
                                pts = row.get("points", [])
                                if len(pts) >= 2:
                                    msp_dst.add_lwpolyline(pts, dxfattribs={"color": color, "layer": layer})
                                    total += 1
                            elif dxf_type == "CIRCLE":
                                msp_dst.add_circle(
                                    (row.get("center_x", 0), row.get("center_y", 0)),
                                    row.get("radius", 1),
                                    dxfattribs={"color": color, "layer": layer},
                                )
                                total += 1
                            elif dxf_type == "ARC":
                                msp_dst.add_arc(
                                    (row.get("center_x", 0), row.get("center_y", 0)),
                                    row.get("radius", 1),
                                    row.get("start_angle", 0),
                                    row.get("end_angle", 360),
                                    dxfattribs={"color": color, "layer": layer},
                                )
                                total += 1
                            elif dxf_type == "TEXT":
                                msp_dst.add_text(
                                    row.get("text", ""),
                                    dxfattribs={
                                        "color": color,
                                        "height": row.get("height", 2.5),
                                        "insert": (row.get("insert_x", 0), row.get("insert_y", 0)),
                                        "layer": layer,
                                    },
                                )
                                total += 1
                            elif dxf_type == "MTEXT":
                                msp_dst.add_mtext(
                                    row.get("text", ""),
                                    dxfattribs={
                                        "color": color,
                                        "char_height": row.get("height", 2.5),
                                        "insert": (row.get("insert_x", 0), row.get("insert_y", 0)),
                                        "layer": layer,
                                    },
                                )
                                total += 1
                            elif dxf_type == "INSERT":
                                ins_x = row.get("insert_x", 0)
                                ins_y = row.get("insert_y", 0)
                                name = row.get("block_name", "UNKNOWN")
                                half = 50.0
                                msp_dst.add_lwpolyline([
                                    (ins_x - half, ins_y - half),
                                    (ins_x + half, ins_y - half),
                                    (ins_x + half, ins_y + half),
                                    (ins_x - half, ins_y + half),
                                    (ins_x - half, ins_y - half),
                                ], dxfattribs={"color": 1, "layer": layer})
                                msp_dst.add_text(
                                    name,
                                    dxfattribs={"color": 1, "height": 100.0,
                                                 "insert": (ins_x + half + 10, ins_y), "layer": layer},
                                )
                                total += 1
                            elif dxf_type == "POINT":
                                msp_dst.add_point(
                                    (row.get("x", 0), row.get("y", 0)),
                                    dxfattribs={"color": color, "layer": layer},
                                )
                                total += 1
                        except Exception:
                            pass
                except Exception:
                    continue

            if total > 10:
                return dxf_doc
        except Exception:
            pass
        return None

    def _parse_dwg(self, path: Path):
        """解析 DWG 文件，六级兜底策略

        级别（优先级从高到低）：
        0. 同目录 DXF 自动兜底（天正 T3 图纸通常有配套 DXF）
        1. ezdwg.read() + export_dxf() 直转
        2. LibreCAD CLI 自动转换（如已安装）
        3. ezdwg Entity.dxf 字典手动逐元素重建（增强版：含INSERT/HATCH/SOLID）
        4. ezdwg raw 逐个类型解码（增强版：含DIMENSION/INSERT/HATCH/ELLIPSE）
        5. 返回 None 让上层给友好提示
        """
        # ── 第 0 级：同目录 DXF 自动兜底 ──
        dxf_result = self._try_same_dir_dxf(path)
        if dxf_result is not None:
            return dxf_result

        # ── 第 1 级：export_dxf 直转 ──
        result = self._try_ezdwg_export_dxf(path)
        if result is not None:
            return result

        # ── 第 1.5 级：LibreCAD CLI 转换 ──
        result = self._try_librecad_convert(path)
        if result is not None:
            return result

        # ── 第 2 级：手动逐元素转换 ──
        result = self._try_manual_convert(path)
        if result is not None:
            return result

        # ── 第 3 级：raw 逐个类型解码 ──
        result = self._try_raw_decode(path)
        if result is not None:
            return result

        # ── 第 5 级：所有方案都失败 ──
        return None

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
                props["length"] = Vec2(start).distance(Vec2(end))  # 操作
                props["angle"] = Vec2(end - start).angle_deg  # 操作

            elif entity.dxftype() == 'CIRCLE':  # 分支
                props["radius"] = entity.dxf.radius  # 操作
                props["diameter"] = entity.dxf.radius * 2  # 操作

            elif entity.dxftype() == 'LWPOLYLINE':  # 分支
                if hasattr(entity, 'length'):  # 条件判断
                    props["length"] = entity.length  # 操作
                if entity.closed:  # 条件判断
                    props["area"] = self._compute_polygon_area(entity)  # 操作
                # 记录顶点数（ezdwg 重建的图元用 points）
                try:  # 尝试
                    pts = entity.dxf.get('points', [])  # 赋值
                    props["point_count"] = len(pts)  # 操作
                except Exception:  # 捕获异常
                    try:  # 尝试
                        pts = list(entity.vertices())  # 赋值
                        props["point_count"] = len(pts)  # 操作
                    except Exception:  # 捕获异常
                        pass  # 占位

            elif entity.dxftype() == 'ARC':  # 分支
                props["radius"] = entity.dxf.radius  # 操作
                props["start_angle"] = entity.dxf.start_angle  # 操作
                props["end_angle"] = entity.dxf.end_angle  # 操作

            elif entity.dxftype() == 'TEXT':  # 分支
                props["text"] = entity.dxf.text  # 操作
                props["height"] = entity.dxf.height  # 操作

            elif entity.dxftype() == 'INSERT':  # 分支
                # 提取块名和插入点
                try:  # 尝试
                    block_name = entity.dxf.name if hasattr(entity.dxf, 'name') else ''  # 赋值
                    props["block_name"] = block_name or ''  # 操作
                    ins = entity.dxf.insert if hasattr(entity.dxf, 'insert') else None  # 赋值
                    if ins:  # 条件判断
                        props["insert_x"] = ins[0] if hasattr(ins, '__getitem__') else ins.x  # 操作
                        props["insert_y"] = ins[1] if hasattr(ins, '__getitem__') else ins.y  # 操作
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
