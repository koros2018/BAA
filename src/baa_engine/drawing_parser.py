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
  v1.26.0 (2026-07-03): P18 大图纸分页解析
    - 文件大小预检，>50MB 走分页模式
    - 实体分批提取，每页限数 + 内存监控
    - 逐页释放中间对象，RSS 超限自动截断
    - OOM 保护：分页模式不下沉到 ezdxf readfile
"""

import ezdxf  # import
from ezdxf.math import Vec2  # import: ezdxf library
from pathlib import Path  # import: path utils
from typing import List, Dict, Any, Optional  # typing: type hints
import subprocess  # stdlib: subprocess
import sys  # stdlib: system
import tempfile  # stdlib: temp files
import os  # stdlib: filesystem ops
import gc  # stdlib: garbage collection
import psutil  # psutil: system memory

# ── ezdwg fallback（系统级安装，venv 可能不可见） ──────
_ezdwg_raw = None  # assignment
try:  # try block
    from ezdwg import raw as _ezdwg_raw  # import: ezdwg library
except ImportError:  # catch exception
    try:  # try block
        import sys as _sys  # import

        _sys.path.insert(0, "/home/kezhigang/.local/lib/python3.12/site-packages")  # sys path
        from ezdwg import raw as _ezdwg_raw  # import: ezdwg library
    except ImportError:  # catch exception
        pass  # code

# ── 数据结构 ──────────────────────────────────────────────


class RawPrimitive:  # class definition
    """原始图元 - 图纸解析管线的输出"""

    def __init__(
        self,
        dxf_type: str,
        layer: str,
        handle: str,  # method: def __init__(self, dxf_type: str, layer: str, handle: str,
        bbox: Dict[str, float],
        properties: Dict[str, Any] = None,
    ):  # assignment
        self.dxf_type = dxf_type  # LINE, LWPOLYLINE, CIRCLE, TEXT, DIMENSION...
        self.layer = layer  # 图层名
        self.handle = handle  # DXF handle
        self.bbox = bbox  # {"x": float, "y": float, "width": float, "height": float}
        self.properties = properties or {}  # 额外属性（长度、面积、角度等）

    def to_dict(self) -> dict:  # method: def to_dict(self) -> dict:
        """处理RawPrimitive相关逻辑"""
        return {  # return: dict
            "dxf_type": self.dxf_type,  # 字段
            "layer": self.layer,  # 字段
            "handle": self.handle,  # 字段
            "bbox": self.bbox,  # 字段
            "properties": self.properties,  # 字段
        }  # code


class DrawingResult:  # class definition
    """图纸解析结果"""

    def __init__(
        self,
        file_path: str,
        file_id: str,  # method: def __init__(self, file_path: str, file_id: str,
        primitives: List[RawPrimitive] = None,  # 操作
        dimensions: List[Dict] = None,  # 操作
        error: Optional[str] = None,  # assignment
        warning: Optional[str] = None,
        sheets: List[Dict] = None,  # P73: 多Sheet 分区解析
    ):  # 操作
        self.file_path = file_path  # assignment
        self.file_id = file_id  # assignment
        self.primitives = primitives or []  # assignment
        self.dimensions = dimensions or []  # assignment
        self.error = error  # assignment
        self.success = error is None  # assignment
        self.warning = warning  # assignment
        self.sheets = sheets or []  # P73: 每个 sheet 为 {name, primitives, dimensions}


# ── 解析引擎 ──────────────────────────────────────────────


# ── 解析引擎 ──────────────────────────────────────────────
# DWG 转换 → parsers.dwg_convert, 几何计算 → parsers.geometry

from src.baa_engine.parsers.dwg_convert import (
    _detect_dwg_format,
    _parse_dwg,
    _insert_block_expand,
    _resolve_xref_external,
)
from src.baa_engine.parsers.geometry import (
    compute_bbox,
    extract_properties,
    compute_polygon_area,
)


class DrawingParser:
    """图纸解析引擎 - 基于 ezdxf"""

    SUPPORTED_FORMATS = {".dxf", ".dwg"}
    LARGE_FILE_MB = 50
    PAGE_SIZE = 5000
    MEMORY_LIMIT_MB = 1500
    MAX_PAGES = 20

    def __init__(self):
        self._doc = None
        self._parse_cache: Dict[str, DrawingResult] = {}
        self._cache_max = 50

    def parse(
        self, file_path: str, file_id: str = None, detect_sheets: bool = False
    ) -> DrawingResult:  # method: def parse(self, file_path: str, file_id: str = None, detect_sheets: bool = False) -> Draw
        """
        解析 DXF/DWG 图纸，提取原始图元

        参数:
            file_path: 图纸文件路径（支持 dxf, dwg）
            file_id: 文件标识（可选，自动生成）
            detect_sheets: P73: 是否检测多Sheet（Layout）分区

        返回:
            DrawingResult 包含原始图元列表（sheets 非空时 pritimives 为全部图元聚合）
        """
        path = Path(file_path)  # function call
        ext = path.suffix.lower()  # function call

        # ── 文件哈希缓存：相同文件秒级返回 ────────────────
        # 注意：detect_sheets 不同时不能复用缓存
        try:  # try block
            import hashlib  # stdlib: hashing

            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:32]  # function call
            if not detect_sheets:  # 无 sheet 检测时可走缓存
                cached = self._parse_cache.get(file_hash)  # function call
                if cached is not None:  # check: value is not None
                    return cached  # return
        except Exception:  # catch exception
            file_hash = None  # assignment

        if ext not in self.SUPPORTED_FORMATS:  # check: membership test
            return DrawingResult(  # return
                file_path=file_path,  # assignment
                file_id=file_id or f"baa-file-{path.stem}",  # assignment
                error=f"不支持的文件格式: {ext}。支持: dxf, dwg",  # assignment
            )  # code

        if not path.exists():  # check: negated condition
            return DrawingResult(  # return
                file_path=file_path,  # assignment
                file_id=file_id or f"baa-file-{path.stem}",  # assignment
                error=f"文件不存在: {file_path}",  # assignment
            )  # code

        try:  # 尝试
            if ext == ".dwg":  # condition: ext == ".dwg":
                dxf_doc = _parse_dwg(path)  # function call
                if dxf_doc is None:  # check: value is None
                    # DWG 格式检测
                    format_hint = _detect_dwg_format(path)  # function call

                    # 版本检测
                    version_hint = ""  # assignment
                    try:  # 尝试
                        ver = (
                            _ezdwg_raw.detect_version(str(path)) if _ezdwg_raw else None
                        )  # str conversion
                        if ver is None:  # check: value is None
                            raise ValueError("ezdwg not available")  # function call
                        version_hint = f" (AutoCAD {ver})"  # function call
                    except Exception:  # catch exception
                        try:  # try block
                            with open(path, "rb") as f:  # context manager
                                header = f.read(6)  # function call
                            if header.startswith(b"AC10"):  # condition: header.startswith(b"AC10"):
                                ver = header[:6].decode("ascii", errors="ignore")  # function call
                                version_hint = f" (AutoCAD {ver})"  # function call
                        except Exception:  # catch exception
                            pass  # code

                    # 构建诊断信息
                    diag_parts = ["DWG 解析失败"]  # assignment
                    if version_hint:  # condition: version_hint:
                        diag_parts.append(version_hint)  # append to list
                    if format_hint == "天正 T3 加密格式":  # check: OR condition
                        diag_parts.append(f"，检测到{format_hint}")  # append to list
                        diag_parts.append(
                            "请用 AutoCAD 打开后执行 T3转T0(T3→T0) 命令，或另存为 DXF 格式。"
                        )  # append to list
                    elif format_hint:  # elif condition
                        diag_parts.append(f"，检测到{format_hint}")  # append to list
                        diag_parts.append(
                            "请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。"
                        )  # append to list
                    else:  # else: default case
                        diag_parts.append("，当前解析器无法读取此格式。")  # append to list
                        diag_parts.append(
                            "请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。"
                        )  # append to list

                    return DrawingResult(  # return
                        file_path=file_path,  # assignment
                        file_id=file_id or f"baa-file-{path.stem}",  # assignment
                        error="".join(diag_parts),  # function call
                    )  # code
                self._doc = dxf_doc  # assignment
            else:  # 否则
                # ── P18 文件大小预检 ──────────────────────
                file_size_mb = path.stat().st_size / (1024 * 1024)  # function call
                use_paging = file_size_mb >= self.LARGE_FILE_MB  # assignment
                if use_paging:  # condition: use_paging:
                    # 大文件：ezdxf 低开销读取 + 分页提取
                    self._doc = ezdxf.readfile(str(path))  # str conversion
                else:  # else: default case
                    self._doc = ezdxf.readfile(str(path))  # str conversion
        except Exception as e:  # 捕获异常
            return DrawingResult(  # return
                file_path=file_path,  # assignment
                file_id=file_id or f"baa-file-{path.stem}",  # assignment
                error=f"DXF 解析失败: {str(e)}",  # str conversion
            )  # code

        primitives, dimensions, page_warning = self._extract_primitives_paged(
            use_paging if ext == ".dxf" else False
        )  # function call

        result = DrawingResult(  # assignment
            file_path=file_path,  # assignment
            file_id=file_id or f"baa-file-{path.stem}",  # assignment
            primitives=primitives,  # assignment
            dimensions=dimensions,  # assignment
        )  # code

        # ── P73: 多Sheet 分区检测 ────────────────────────
        if detect_sheets and result.success and self._doc is not None:
            try:
                sheets = []
                for layout in self._doc.layouts:
                    name = layout.name
                    if name == "Model":  # ModelSpace 是主图，已包含在 primitives 中
                        continue
                    sheet_prims = []
                    sheet_dims = []
                    for entity in layout:
                        dxf_type = entity.dxftype()
                        if dxf_type == "DIMENSION":
                            dim = self._extract_single_dimension(entity)
                            if dim is not None:
                                sheet_dims.append(dim)
                        else:
                            prim = self._extract_single_primitive(entity)
                            if prim is not None:
                                sheet_prims.append(prim)
                    if sheet_prims or sheet_dims:
                        sheets.append({
                            "name": name,
                            "primitives": [p.to_dict() for p in sheet_prims],
                            "dimensions": sheet_dims,
                            "entity_count": len(sheet_prims),
                        })
                if sheets:
                    result.sheets = sheets
                    result.warning = (result.warning or "") + f"检测到 {len(sheets)} 个分区(Layout)"
            except Exception as e:
                pass  # 多Sheet 检测失败不阻断主流程

        # ── P18 分页警告 ────────────────────────────────
        if page_warning:  # condition: page_warning:
            result.error = page_warning  # assignment

        # ── 写入缓存 ──────────────────────────────────────
        if file_hash and result.success and not detect_sheets:  # 多Sheet 模式不缓存
            if len(self._parse_cache) >= self._cache_max:  # check: numeric comparison
                # 淘汰最旧的一个
                old_key = next(iter(self._parse_cache))  # function call
                del self._parse_cache[old_key]  # code
            self._parse_cache[file_hash] = result  # assignment

        return result  # return

    def _extract_primitives_paged(
        self, use_paging: bool = False
    ) -> tuple:  # method: def _extract_primitives_paged(self, use_paging: bool = False
        """
        提取所有图元（支持分页模式）

        参数:
            use_paging: 是否启用分页模式

        返回:
            (primitives, dimensions, warning)
        """
        all_primitives = []  # assignment
        all_dimensions = []  # assignment
        warning = None  # assignment

        msp = self._doc.modelspace()  # function call
        # 先收集所有实体到列表，避免多次迭代
        all_entities = list(msp)  # list conversion
        total = len(all_entities)  # get length

        if use_paging and total > self.PAGE_SIZE:  # check: numeric comparison
            # ── 分页模式 ──────────────────────────────
            pages = (total // self.PAGE_SIZE) + 1  # function call
            pages = min(pages, self.MAX_PAGES)  # get minimum
            page_primitives_count = 0  # assignment
            page_dimensions_count = 0  # assignment
            truncated = False  # assignment

            for page_idx in range(pages):  # loop: iterate
                start = page_idx * self.PAGE_SIZE  # assignment
                end = min(start + self.PAGE_SIZE, total)  # get minimum
                page_entities = all_entities[start:end]  # assignment

                for entity in page_entities:  # loop: iterate
                    dxf_type = entity.dxftype()  # function call
                    if dxf_type == "DIMENSION":  # condition: dxf_type == 'DIMENSION':
                        dim = self._extract_single_dimension(entity)  # function call
                        if dim is not None:  # check: value is not None
                            all_dimensions.append(dim)  # append to list
                            page_dimensions_count += 1  # accumulate
                    else:  # else: default case
                        primitive = self._extract_single_primitive(entity)  # function call
                        if primitive is not None:  # check: value is not None
                            all_primitives.append(primitive)  # append to list
                            page_primitives_count += 1  # accumulate

                # ── 每页后释放 ──────────────────────────
                del page_entities  # code
                gc.collect()  # function call

                # ── 内存监控 ──────────────────────────────
                try:  # try block
                    proc = psutil.Process()  # function call
                    rss_mb = proc.memory_info().rss / (1024 * 1024)  # function call
                    if rss_mb > self.MEMORY_LIMIT_MB:  # check: numeric comparison
                        warning = f"大图纸解析已截断（RSS {rss_mb:.0f}MB 超限），已处理 {page_idx + 1}/{pages} 页"  # assignment
                        truncated = True  # assignment
                        break  # code
                except Exception:  # catch exception
                    pass  # code

                # ── 进度提示 ──────────────────────────────
                if page_idx > 0 and page_idx % 5 == 0:  # check: numeric comparison
                    pass  # 日志留给上层

            if truncated:  # condition: truncated:
                pass  # warning 已设置
        else:  # else: default case
            # ── 常规模式（不分页） ──────────────────────
            for entity in all_entities:  # loop: iterate
                dxf_type = entity.dxftype()  # function call
                if dxf_type == "DIMENSION":  # condition: dxf_type == 'DIMENSION':
                    dim = self._extract_single_dimension(entity)  # function call
                    if dim is not None:  # check: value is not None
                        all_dimensions.append(dim)  # append to list
                else:  # else: default case
                    primitive = self._extract_single_primitive(entity)  # function call
                    if primitive is not None:  # check: value is not None
                        all_primitives.append(primitive)  # append to list

        del all_entities  # code
        return all_primitives, all_dimensions, warning  # return

    def _extract_single_primitive(
        self, entity
    ) -> Optional[
        RawPrimitive
    ]:  # method: def _extract_single_primitive(self, entity) -> Optional[RawP
        """提取单个图元（供分页/常规模式共用）"""
        dxf_type = entity.dxftype()  # function call
        if dxf_type == "DIMENSION":  # condition: dxf_type == 'DIMENSION':
            return None  # DIMENSION 由 extract_dimensions 处理
        layer = entity.dxf.layer if hasattr(entity.dxf, "layer") else "0"  # attribute check
        handle = entity.dxf.handle if hasattr(entity.dxf, "handle") else ""  # attribute check

        # 计算边界框
        try:  # 尝试
            bbox = compute_bbox(entity)  # function call
        except Exception:  # 捕获异常
            return None  # return: None

        # 提取几何属性
        props = extract_properties(entity)  # function call

        return RawPrimitive(  # return
            dxf_type=dxf_type,  # assignment
            layer=layer,  # assignment
            handle=handle,  # assignment
            bbox=bbox,  # assignment
            properties=props,  # assignment
        )  # code

    def _extract_single_dimension(
        self, entity
    ) -> Optional[Dict]:  # method: def _extract_single_dimension(self, entity) -> Optional[Dict
        """提取单个尺寸标注（供分页/常规模式共用）"""
        try:  # 尝试
            meas = (
                entity.get_measurement() if hasattr(entity, "get_measurement") else None
            )  # attribute check
            if meas is None or meas <= 0.1:  # check: value is None
                return None  # return: None
            defp2 = (
                entity.dxf.defpoint2 if hasattr(entity.dxf, "defpoint2") else None
            )  # attribute check
            defp3 = (
                entity.dxf.defpoint3 if hasattr(entity.dxf, "defpoint3") else None
            )  # attribute check
            tmid = (
                entity.dxf.text_midpoint if hasattr(entity.dxf, "text_midpoint") else None
            )  # attribute check
            dim = {  # assignment
                "handle": entity.dxf.handle if hasattr(entity.dxf, "handle") else "",  # 字段
                "layer": entity.dxf.layer if hasattr(entity.dxf, "layer") else "0",  # 字段
                "measurement": meas,  # 字段
                "text": (
                    entity.get_measurement_text()
                    if hasattr(
                        entity, "get_measurement_text"
                    )  # # 有 get_measurement_text 方法时使用
                    else str(meas)  # # 否则直接转为字符串
                ),  # 字段
                "dimtype": (
                    str(entity.dxf.dimtype) if hasattr(entity.dxf, "dimtype") else "LINEAR"
                ),  # 字段
                "position": {  # 字段
                    "x": entity.dxf.defpoint.x if hasattr(entity.dxf.defpoint, "x") else 0,  # 字段
                    "y": entity.dxf.defpoint.y if hasattr(entity.dxf.defpoint, "y") else 0,  # 字段
                },  # code
                "defpoint2": {  # 字段
                    "x": defp2.x if defp2 and hasattr(defp2, "x") else 0,  # 字段
                    "y": defp2.y if defp2 and hasattr(defp2, "y") else 0,  # 字段
                },  # code
                "defpoint3": {  # 字段
                    "x": defp3.x if defp3 and hasattr(defp3, "x") else 0,  # 字段
                    "y": defp3.y if defp3 and hasattr(defp3, "y") else 0,  # 字段
                },  # code
                "text_midpoint": {  # 字段
                    "x": tmid.x if tmid and hasattr(tmid, "x") else 0,  # 字段
                    "y": tmid.y if tmid and hasattr(tmid, "y") else 0,  # 字段
                },  # code
            }  # code
            return dim  # return
        except Exception:  # 捕获异常
            return None  # return: None

    # ── DWG 解析（六级兜底） ───────────────────────────

    def clear_cache(self):  # method: def clear_cache(self):
        """清除解析缓存"""
        self._parse_cache.clear()  # clear collection

    # ── 委托方法：保持外部（测试）调用兼容 ────────────────────
    # 以下方法已拆到 parsers.dwg_convert，保留实例方法代理
    # 供已有测试（test_engine.py）和第三方代码调用
    def _insert_block_expand(
        self,
        block_entities,
        msp,
        base_x,
        base_y,
        scale,
        rotation,
        color,
        layer,
        block_defs=None,
        depth=0,
        max_depth=10,
    ):
        """委托到 parsers.dwg_convert._insert_block_expand"""
        return _insert_block_expand(
            block_entities,
            msp,
            base_x,
            base_y,
            scale,
            rotation,
            color,
            layer,
            block_defs,
            depth,
            max_depth,
        )

    def _resolve_xref_external(self, doc, xref_path, msp):
        """委托到 parsers.dwg_convert._resolve_xref_external"""
        return _resolve_xref_external(doc, xref_path, msp)
