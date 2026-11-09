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
import logging
import statistics  # stdlib: 单位推断取中位数（与 _area_unit_scale 同口径）

logger = logging.getLogger(__name__)

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
        logger.warning("[P120] ezdwg raw 导入失败，DWG 原生解析将不可用")

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
        """初始化实例。"""
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
        drawing_type: Optional[Dict] = None,  # P121: 图纸类型分类
        sheet_type: Optional[Dict] = None,  # P121: 图幅类型（平面/立面剖面/不可审查/未知）
        corrupt: Optional[Dict] = None,  # P121: 损坏检测
        block_refs: List[Dict] = None,  # P127-S1: 块引用（块名/ATTRIB/位置）
        parse_status: Optional[Dict] = None,  # P127-T3: 解析状态诊断（T3 加密/代理/零图元不静默）
        t3_components: Optional[Dict] = None,  # P127-T3: 天正原生识别构件（墙/门/窗/柱实例）
        unit_normalization: Optional[Dict] = None,  # 解析层单位归一化审计（源单位/缩放系数/依据）
        view_frames: Optional[List[Dict]] = None,  # P121-V: 视图级 scope_mode（混合图集子视框聚类）
    ):  # 操作
        """初始化实例。"""
        self.file_path = file_path  # assignment
        self.file_id = file_id  # assignment
        self.primitives = primitives or []  # assignment
        self.dimensions = dimensions or []  # assignment
        self.error = error  # assignment
        self.success = error is None  # assignment
        self.warning = warning  # assignment
        self.sheets = sheets or []  # P73: 每个 sheet 为 {name, primitives, dimensions}
        self.drawing_type = drawing_type or {}  # P121: {type, confidence, reason, suggested_action}
        self.sheet_type = sheet_type or {}  # P121: {sheet_type, scope_mode, evidence, metrics}
        self.corrupt = corrupt or {}  # P121: {corrupt, reason, recoverable}
        self.block_refs = block_refs or []  # P127-S1: 块引用列表
        self.view_frames = view_frames or []  # P121-V: 视图级 scope_mode（混合图集子视框聚类）
        # P127-T3: 天正 T3 解析状态与原生构件（非 T3 图纸为 None）
        self.parse_status = parse_status
        self.t3_components = t3_components
        # 解析层单位归一化审计：{applied, source_unit, coordinate_scale, method, line_median, reason}
        self.unit_normalization = unit_normalization or {}


# ── 解析层单位归一化 ─────────────────────────────────────
# 全引擎阈值（500/2000mm、门宽、面积下限等）都按毫米设计。米制图纸若直接进入
# 语义分析与规则判定，会整体错位 1000 倍。这里在解析出口统一到毫米，而不是
# 逐处修改阈值常量（散落且易漏）。单位判据复用 drawing_classifier 的
# _area_unit_scale()：LINE 长度中位数 ≥ 50 → mm，否则 m。
# 注意：$INSUNITS/$MEASUREMENT 实测不可靠（样本 6 张中 4 张与实际几何不符），
# 不参与判定，仅作审计参考。


def _detect_source_unit(primitives) -> Dict[str, Any]:
    """按 LINE 长度中位数推断源单位（与 _area_unit_scale 同一判据来源）。

    返回 coordinate_scale：源单位 → 毫米的倍数（mm=1.0，m=1000.0）。
    """
    from src.baa_engine.drawing_classifier import _area_unit_scale

    line_lengths = []
    for p in primitives or []:
        if getattr(p, "dxf_type", "") != "LINE":
            continue
        props = getattr(p, "properties", {}) or {}
        length = props.get("length")
        if length is None:
            bbox = getattr(p, "bbox", {}) or {}
            length = max(abs(bbox.get("width", 0) or 0), abs(bbox.get("height", 0) or 0))
        try:
            length = abs(float(length))
        except (TypeError, ValueError):
            length = 0.0
        if length > 0:
            line_lengths.append(length)

    method = "_area_unit_scale(LINE length median)"
    if not line_lengths:
        return {
            "source_unit": "unknown",
            "coordinate_scale": 1.0,
            "line_median": None,
            "method": method,
        }
    line_median = statistics.median(line_lengths)
    if _area_unit_scale(line_lengths) == 1e-6:
        return {
            "source_unit": "mm",
            "coordinate_scale": 1.0,
            "line_median": round(line_median, 5),
            "method": method,
        }
    return {
        "source_unit": "m",
        "coordinate_scale": 1000.0,
        "line_median": round(line_median, 5),
        "method": method,
    }


_GEOMETRY_LENGTH_KEYS = ("length", "radius", "diameter", "height", "measured_length")
_GEOMETRY_POINT_DICT_KEYS = ("start_point", "end_point")
_GEOMETRY_POINT_SCALAR_KEYS = ("insert_x", "insert_y")
_DIMENSION_POINT_KEYS = ("position", "defpoint2", "defpoint3", "text_midpoint")


def _scale_raw_primitive_to_mm(prim, scale: float) -> None:
    """就地缩放图元坐标与几何属性（只挂几何字段，文本/单位无关字段不动）。"""
    if scale == 1.0:
        return
    scale_sq = scale * scale
    bbox = getattr(prim, "bbox", None)
    if isinstance(bbox, dict):
        for key in ("x", "y", "width", "height"):
            val = bbox.get(key)
            if isinstance(val, (int, float)):
                bbox[key] = val * scale
    props = getattr(prim, "properties", None)
    if not isinstance(props, dict):
        return
    for key in _GEOMETRY_LENGTH_KEYS:
        val = props.get(key)
        if isinstance(val, (int, float)):
            props[key] = val * scale
    val = props.get("area")
    if isinstance(val, (int, float)):
        props["area"] = val * scale_sq
    for key in _GEOMETRY_POINT_DICT_KEYS:
        pt = props.get(key)
        if isinstance(pt, dict):
            for axis in ("x", "y"):
                if isinstance(pt.get(axis), (int, float)):
                    pt[axis] = pt[axis] * scale
    for key in _GEOMETRY_POINT_SCALAR_KEYS:
        val = props.get(key)
        if isinstance(val, (int, float)):
            props[key] = val * scale
    pts = props.get("points")
    if isinstance(pts, list):
        props["points"] = [
            (p[0] * scale, p[1] * scale)
            if isinstance(p, (list, tuple)) and len(p) >= 2
            else p
            for p in pts
        ]


def _scale_dimension_to_mm(dim, scale: float) -> None:
    """就地缩放 DIMENSION 测量值与定位点（text 展示串保持原样）。"""
    if scale == 1.0 or not isinstance(dim, dict):
        return
    val = dim.get("measurement")
    if isinstance(val, (int, float)):
        dim["measurement"] = val * scale
    for key in _DIMENSION_POINT_KEYS:
        pt = dim.get(key)
        if isinstance(pt, dict):
            for axis in ("x", "y"):
                if isinstance(pt.get(axis), (int, float)):
                    pt[axis] = pt[axis] * scale


def _scale_block_ref_to_mm(ref, scale: float) -> None:
    """就地缩放块引用插入点；x_scale/y_scale 是块内比例，保持不变。"""
    if scale == 1.0 or not isinstance(ref, dict):
        return
    ip = ref.get("insert_point")
    if isinstance(ip, (list, tuple)) and len(ip) >= 2:
        ref["insert_point"] = [ip[0] * scale, ip[1] * scale] + list(ip[2:])


def _normalize_parsed_geometry(primitives, dimensions, block_refs, sheets, scale: float) -> None:
    """把解析结果统一到毫米（就地修改，坐标/几何属性/标注测量值）。"""
    if scale == 1.0:
        return
    for prim in primitives or []:
        _scale_raw_primitive_to_mm(prim, scale)
    for dim in dimensions or []:
        _scale_dimension_to_mm(dim, scale)
    for ref in block_refs or []:
        _scale_block_ref_to_mm(ref, scale)
    for sheet in sheets or []:
        for prim in sheet.get("primitives") or []:
            _scale_raw_primitive_to_mm(prim, scale)
        for dim in sheet.get("dimensions") or []:
            _scale_dimension_to_mm(dim, scale)


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
from src.baa_engine.parsers.block_refs import read_block_ref


class DrawingParser:
    """图纸解析引擎 - 基于 ezdxf"""

    SUPPORTED_FORMATS = {".dxf", ".dwg", ".pdf"}
    LARGE_FILE_MB = 50
    PAGE_SIZE = 5000
    MEMORY_LIMIT_MB = 1500
    MAX_PAGES = 20

    def __init__(self):
        """初始化实例。"""
        self._doc = None
        self._parse_cache: Dict[str, DrawingResult] = {}
        self._cache_max = 50

    def parse(
        self, file_path: str, file_id: str = None, detect_sheets: bool = False, page_index: int = 0
    ) -> (
        DrawingResult
    ):  # method: def parse(self, file_path: str, file_id: str = None, detect_sheets: bool = False, page_index: int = 0) -> Draw
        """
        解析 DXF/DWG/PDF 图纸，提取原始图元

        参数:
            file_path: 图纸文件路径（支持 dxf, dwg, pdf）
            file_id: 文件标识（可选，自动生成）
            detect_sheets: P73: 是否检测多Sheet（Layout）分区
            page_index: P100: PDF 目标页索引（默认第 1 页），仅 PDF 有效

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
                        except Exception as _e:  # catch exception
                            logger.debug(
                                "[P120] DWG 版本头读取失败，跳过版本探测: %s: %s",
                                type(_e).__name__,
                                _e,
                            )

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

                    encrypted_status = None
                    if format_hint == "天正 T3 加密格式":
                        encrypted_status = {
                            "is_t3": True,
                            "storage_form": "encrypted_t3_dwg",
                            "proxy_count": 0,
                            "component_counts": {
                                "walls": 0,
                                "doors": 0,
                                "windows": 0,
                                "columns": 0,
                            },
                            "diagnostic": "".join(diag_parts),
                        }
                    return DrawingResult(  # return
                        file_path=file_path,  # assignment
                        file_id=file_id or f"baa-file-{path.stem}",  # assignment
                        error="".join(diag_parts),  # function call
                        parse_status=encrypted_status,  # P127-T3: 加密 T3 诊断不静默
                    )  # code
                self._doc = dxf_doc  # assignment
            elif ext == ".pdf":  # condition: ext == ".pdf" — P100 PDF 直接接入
                # T-C4：默认走独立子进程（AGPL 许可隔离，主进程不加载 PyMuPDF）；
                # BAA_PDF_ISOLATION=0 时回退进程内直接调用（仅本地开发/测试）。
                from src.baa_engine.parsers.pdf_isolation import (  # 延迟导入避免循环
                    pdf_isolation_enabled,
                    pdf_to_dxf_isolated,
                )

                if pdf_isolation_enabled():
                    pdf_result = pdf_to_dxf_isolated(str(path), page_index=page_index)
                else:
                    from src.baa_engine.parsers.pdf_parser import pdf_to_dxf

                    pdf_result = pdf_to_dxf(str(path), page_index=page_index)
                if pdf_result is None:
                    return DrawingResult(
                        file_path=file_path,
                        file_id=file_id or f"baa-file-{path.stem}",
                        error="PDF 解析失败：无法提取矢量数据",
                    )
                # 读取生成的 DXF
                self._doc = ezdxf.readfile(pdf_result["dxf_path"])
                use_paging = False
            else:  # 否则: .dxf 默认路径
                file_size_mb = path.stat().st_size / (1024 * 1024)
                use_paging = file_size_mb >= self.LARGE_FILE_MB
                if use_paging:
                    self._doc = ezdxf.readfile(str(path))
                else:
                    self._doc = ezdxf.readfile(str(path))
        except Exception as e:  # 捕获异常
            return DrawingResult(  # return
                file_path=file_path,  # assignment
                file_id=file_id or f"baa-file-{path.stem}",  # assignment
                error=f"DXF 解析失败: {str(e)}",  # str conversion
            )  # code

        primitives, dimensions, block_refs, page_warning = self._extract_primitives_paged(
            use_paging if ext == ".dxf" else False
        )  # function call

        # ── P121: 图纸类型分类 + 损坏检测 ─────────────────
        drawing_type = {}
        sheet_type = {}
        corrupt = {}
        try:
            from src.baa_engine.drawing_classifier import (
                classify_drawing,
                classify_sheet_type,
                is_likely_corrupt,
            )  # import: P121 图纸类型分类

            # 损坏检测（即使解析成功也要检查，小文件可能只有 HEADER 无实体）
            corrupt = is_likely_corrupt(file_path)
            if corrupt.get("corrupt") and (primitives is None or len(primitives) == 0):
                result = DrawingResult(
                    file_path=file_path,
                    file_id=file_id or f"baa-file-{path.stem}",
                    error=f"图纸疑似损坏: {corrupt.get('reason')}",
                    corrupt=corrupt,
                )
                # 缓存并返回
                if file_hash:
                    self._parse_cache[file_hash] = result
                return result

            # 从 primitives 收集 layer 名（比 self._doc.layers 更可靠，DWG 下可能为空）
            layer_names = []
            try:
                layer_set = set()
                for p in (primitives or [])[:5000]:
                    ln = getattr(p, "layer", None)
                    if ln:
                        layer_set.add(ln)
                layer_names = sorted(layer_set)
            except Exception:
                pass

            drawing_type = classify_drawing(
                filename=path.name,
                layer_names=layer_names,
                entity_types=[
                    getattr(p, "dxf_type", "") or getattr(p, "type", "")
                    for p in (primitives or [])[:2000]
                ],
                file_size_mb=path.stat().st_size / (1024 * 1024),
            )

            # 图幅类型：平面图 / 立面剖面 / 不可审查 / 未知
            # 仅基于图元与图层分布，供入口层决定是否进入审查范围
            sheet_type = classify_sheet_type(primitives or [])
        except Exception:
            pass  # 分类失败不影响解析结果

        # ── P127-T3: 天正 T3 原生识别（特征探测廉价，命中才跑全量识别）──
        # 铁律：T3 特征命中但解出 0 构件必须输出 parse_status 诊断，不得静默。
        parse_status = None
        t3_components = None
        if self._doc is not None:
            try:
                from src.baa_engine.parsers.t3_native import (
                    attach_t3_markers,
                    detect_t3_signature,
                    extract_t3,
                )

                signature = detect_t3_signature(self._doc)
                if signature.get("is_t3"):
                    t3_components = extract_t3(self._doc)
                    parse_status = t3_components.get("status")
                    # 门窗/柱语义按 handle 落到图元 properties，供分类覆盖图层误判
                    attach_t3_markers(primitives, t3_components)
            except Exception as t3_err:  # T3 识别失败不得影响主解析链路
                logger.warning(
                    "[P127-T3] 天正识别异常（已降级为普通图层管线）: %s: %s",
                    type(t3_err).__name__,
                    t3_err,
                )
                parse_status = {
                    "is_t3": True,
                    "storage_form": "recognizer_error",
                    "diagnostic": f"天正识别器异常: {type(t3_err).__name__}: {t3_err}",
                }

        # ── 解析层单位归一化（统一到毫米）──────────────
        # 图幅判为非平面/不可审查（如描线矢量化产物）时不归一化：那种图任何
        # 尺度都不成立，强行 ×1000 只会制造假几何，交由上层标「非可审查」。
        unit_normalization: Dict[str, Any] = {
            "applied": False,
            "source_unit": "unknown",
            "coordinate_scale": 1.0,
            "line_median": None,
            "method": "_area_unit_scale(LINE length median)",
            "reason": "未归一化",
        }
        try:
            scope_mode = (sheet_type or {}).get("scope_mode")
            if primitives and scope_mode != "non_plan":
                info = _detect_source_unit(primitives)
                unit_normalization.update(info)
                scale = info["coordinate_scale"]
                if scale != 1.0:
                    _normalize_parsed_geometry(
                        primitives, dimensions, block_refs, None, scale
                    )
                    unit_normalization["applied"] = True
                    unit_normalization["reason"] = "源单位为米，坐标与标注已 ×1000 统一为毫米"
                elif info["source_unit"] == "mm":
                    unit_normalization["reason"] = "源单位为毫米，无需缩放"
                else:
                    unit_normalization["reason"] = "无有效 LINE 长度，保持原坐标"
            elif scope_mode == "non_plan":
                unit_normalization["reason"] = "图幅判为非平面/不可审查，不归一化"
        except Exception as unit_err:  # 归一化失败不得影响解析主链路
            unit_normalization["reason"] = (
                f"单位归一化失败（保持原坐标）: {type(unit_err).__name__}: {unit_err}"
            )
            logger.warning(
                "[unit] 解析层单位归一化失败（保持原坐标）: %s: %s",
                type(unit_err).__name__,
                unit_err,
            )

        # ── P121-V: 视图级 scope_mode（混合图集子视框聚类）──
        # 必须在单位归一化之后调用：聚类阈值（_VIEW_GAP_MM=5000mm）按毫米设计，
        # 若在归一化前调用（源单位为米时坐标在 0-100 量级），会因尺度错位
        # 把所有图元聚成一簇，返回空。仅当整图被判为 plan 且内部存在明显
        # Y 向断层（多视图共存）时才有值；单视幅图集返回空列表，不影响既有行为。
        view_frames: List[Dict] = []
        try:
            from src.baa_engine.drawing_classifier import classify_view_frames

            view_frames = classify_view_frames(primitives or [])
        except Exception as vf_err:
            logger.warning(
                "[P121-V] 视图级分类异常（已降级为空）: %s: %s",
                type(vf_err).__name__,
                vf_err,
            )
            view_frames = []

        result = DrawingResult(
            file_path=file_path,
            file_id=file_id or f"baa-file-{path.stem}",
            primitives=primitives,
            dimensions=dimensions,
            drawing_type=drawing_type,
            sheet_type=sheet_type,
            corrupt=corrupt,
            block_refs=block_refs,
            parse_status=parse_status,
            t3_components=t3_components,
            unit_normalization=unit_normalization,
            view_frames=view_frames,
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
                        sheets.append(
                            {
                                "name": name,
                                "primitives": sheet_prims,  # 保留原始对象供 analyze() 使用
                                "dimensions": sheet_dims,
                                "entity_count": len(sheet_prims),
                            }
                        )
                if sheets:
                    # 分区图元与主图共用同一源单位，归一化必须同步
                    _normalize_parsed_geometry(
                        None, None, None, sheets, unit_normalization["coordinate_scale"]
                    )
                    result.sheets = sheets
                    result.warning = (result.warning or "") + f"检测到 {len(sheets)} 个分区(Layout)"
            except Exception as e:
                logger.warning(
                    "[P120] 多Sheet 检测失败，回退为单Sheet 解析: %s: %s", type(e).__name__, e
                )

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
            (primitives, dimensions, block_refs, warning)
        """
        all_primitives = []  # assignment
        all_dimensions = []  # assignment
        all_block_refs = []  # P127-S1: 块引用
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
                    if dxf_type == "INSERT":  # P127-S1: 块引用不展平，单独收集
                        bref = self._extract_block_ref(entity)
                        if bref is not None:
                            all_block_refs.append(bref)
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
                except Exception as _e:  # catch exception
                    logger.debug(
                        "[P120] 分页内存监控失败，继续下一页: %s: %s", type(_e).__name__, _e
                    )

                # ── 进度提示 ──────────────────────────────
                if page_idx > 0 and page_idx % 5 == 0:  # check: numeric comparison
                    pass  # 日志留给上层

            if truncated:  # condition: truncated:
                pass  # warning 已设置
        else:  # else: default case
            # ── 常规模式（不分页） ──────────────────────
            for entity in all_entities:  # loop: iterate
                dxf_type = entity.dxftype()  # function call
                if dxf_type == "INSERT":  # P127-S1: 块引用不展平，单独收集
                    bref = self._extract_block_ref(entity)
                    if bref is not None:
                        all_block_refs.append(bref)
                if dxf_type == "DIMENSION":  # condition: dxf_type == 'DIMENSION':
                    dim = self._extract_single_dimension(entity)  # function call
                    if dim is not None:  # check: value is not None
                        all_dimensions.append(dim)  # append to list
                else:  # else: default case
                    primitive = self._extract_single_primitive(entity)  # function call
                    if primitive is not None:  # check: value is not None
                        all_primitives.append(primitive)  # append to list

        del all_entities  # code
        return all_primitives, all_dimensions, all_block_refs, warning  # return

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

    def _extract_block_ref(self, entity) -> Optional[Dict]:  # P127-S1: 块引用提取
        """提取单个块引用（INSERT）为结构化 Dict；非 INSERT 或失败返回 None。"""
        ref = read_block_ref(entity)
        return ref.to_dict() if ref is not None else None

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
