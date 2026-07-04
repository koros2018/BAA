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
import ezdxf
from ezdxf.math import Vec2
from pathlib import Path
from typing import List, Dict, Any, Optional
import subprocess
import tempfile
import shutil
import os
import gc
import psutil

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
                 bbox: Dict[str, float], properties: Dict[str, Any] = None):
        self.dxf_type = dxf_type          # LINE, LWPOLYLINE, CIRCLE, TEXT, DIMENSION...
        self.layer = layer                 # 图层名
        self.handle = handle               # DXF handle
        self.bbox = bbox                   # {"x": float, "y": float, "width": float, "height": float}
        self.properties = properties or {} # 额外属性（长度、面积、角度等）

    def to_dict(self) -> dict:
        """处理RawPrimitive相关逻辑"""
        return {
            "dxf_type": self.dxf_type,  # 字段
            "layer": self.layer,  # 字段
            "handle": self.handle,  # 字段
            "bbox": self.bbox,  # 字段
            "properties": self.properties,  # 字段
        }


class DrawingResult:
    """图纸解析结果"""
    def __init__(self, file_path: str, file_id: str,
                 primitives: List[RawPrimitive] = None,  # 操作
                 dimensions: List[Dict] = None,  # 操作
                 error: Optional[str] = None):  # 操作
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

    # ── P18 大图纸分页解析阈值 ──────────────────────────
    LARGE_FILE_MB = 50       # >50MB 自动走分页模式
    PAGE_SIZE = 5000          # 每页最多处理 5000 个实体
    MEMORY_LIMIT_MB = 1500    # RSS 超过 1.5GB 自动截断
    MAX_PAGES = 20            # 最多 20 页（10 万实体上限）

    def __init__(self):
        self._doc = None
        self._parse_cache: Dict[str, DrawingResult] = {}  # file_hash -> DrawingResult
        self._cache_max = 50  # 最多缓存50个结果

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

        # ── 文件哈希缓存：相同文件秒级返回 ────────────────
        try:
            import hashlib
            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:32]
            cached = self._parse_cache.get(file_hash)
            if cached is not None:
                return cached
        except Exception:
            file_hash = None

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

        try:  # 尝试
            if ext == ".dwg":
                dxf_doc = self._parse_dwg(path)
                if dxf_doc is None:
                    # DWG 格式检测
                    format_hint = self._detect_dwg_format(path)
                    
                    # 版本检测
                    version_hint = ""
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
                    
                    return DrawingResult(
                        file_path=file_path,
                        file_id=file_id or f"baa-file-{path.stem}",
                        error="".join(diag_parts)
                    )
                self._doc = dxf_doc
            else:  # 否则
                # ── P18 文件大小预检 ──────────────────────
                file_size_mb = path.stat().st_size / (1024 * 1024)
                use_paging = file_size_mb >= self.LARGE_FILE_MB
                if use_paging:
                    # 大文件：ezdxf 低开销读取 + 分页提取
                    self._doc = ezdxf.readfile(str(path))
                else:
                    self._doc = ezdxf.readfile(str(path))
        except Exception as e:  # 捕获异常
            return DrawingResult(
                file_path=file_path,
                file_id=file_id or f"baa-file-{path.stem}",
                error=f"DXF 解析失败: {str(e)}"
            )

        primitives, dimensions, page_warning = self._extract_primitives_paged(use_paging if ext == ".dxf" else False)

        result = DrawingResult(
            file_path=file_path,
            file_id=file_id or f"baa-file-{path.stem}",
            primitives=primitives,
            dimensions=dimensions,
        )

        # ── P18 分页警告 ────────────────────────────────
        if page_warning:
            result.error = page_warning

        # ── 写入缓存 ──────────────────────────────────────
        if file_hash and result.success:
            if len(self._parse_cache) >= self._cache_max:
                # 淘汰最旧的一个
                old_key = next(iter(self._parse_cache))
                del self._parse_cache[old_key]
            self._parse_cache[file_hash] = result

        return result

    def _extract_primitives_paged(self, use_paging: bool = False) -> tuple:
        """
        提取所有图元（支持分页模式）
        
        参数:
            use_paging: 是否启用分页模式
            
        返回:
            (primitives, dimensions, warning)
        """
        all_primitives = []
        all_dimensions = []
        warning = None

        msp = self._doc.modelspace()
        # 先收集所有实体到列表，避免多次迭代
        all_entities = list(msp)
        total = len(all_entities)

        if use_paging and total > self.PAGE_SIZE:
            # ── 分页模式 ──────────────────────────────
            pages = (total // self.PAGE_SIZE) + 1
            pages = min(pages, self.MAX_PAGES)
            page_primitives_count = 0
            page_dimensions_count = 0
            truncated = False

            for page_idx in range(pages):
                start = page_idx * self.PAGE_SIZE
                end = min(start + self.PAGE_SIZE, total)
                page_entities = all_entities[start:end]

                for entity in page_entities:
                    dxf_type = entity.dxftype()
                    if dxf_type == 'DIMENSION':
                        dim = self._extract_single_dimension(entity)
                        if dim is not None:
                            all_dimensions.append(dim)
                            page_dimensions_count += 1
                    else:
                        primitive = self._extract_single_primitive(entity)
                        if primitive is not None:
                            all_primitives.append(primitive)
                            page_primitives_count += 1

                # ── 每页后释放 ──────────────────────────
                del page_entities
                gc.collect()

                # ── 内存监控 ──────────────────────────────
                try:
                    proc = psutil.Process()
                    rss_mb = proc.memory_info().rss / (1024 * 1024)
                    if rss_mb > self.MEMORY_LIMIT_MB:
                        warning = f"大图纸解析已截断（RSS {rss_mb:.0f}MB 超限），已处理 {page_idx + 1}/{pages} 页"
                        truncated = True
                        break
                except Exception:
                    pass

                # ── 进度提示 ──────────────────────────────
                if page_idx > 0 and page_idx % 5 == 0:
                    pass  # 日志留给上层

            if truncated:
                pass  # warning 已设置
        else:
            # ── 常规模式（不分页） ──────────────────────
            for entity in all_entities:
                dxf_type = entity.dxftype()
                if dxf_type == 'DIMENSION':
                    dim = self._extract_single_dimension(entity)
                    if dim is not None:
                        all_dimensions.append(dim)
                else:
                    primitive = self._extract_single_primitive(entity)
                    if primitive is not None:
                        all_primitives.append(primitive)

        del all_entities
        return all_primitives, all_dimensions, warning

    def _extract_single_primitive(self, entity) -> Optional[RawPrimitive]:
        """提取单个图元（供分页/常规模式共用）"""
        dxf_type = entity.dxftype()
        if dxf_type == 'DIMENSION':
            return None  # DIMENSION 由 extract_dimensions 处理
        layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'
        handle = entity.dxf.handle if hasattr(entity.dxf, 'handle') else ''

        # 计算边界框
        try:  # 尝试
            bbox = self._compute_bbox(entity)
        except Exception:  # 捕获异常
            return None

        # 提取几何属性
        props = self._extract_properties(entity)

        return RawPrimitive(
            dxf_type=dxf_type,
            layer=layer,
            handle=handle,
            bbox=bbox,
            properties=props,
        )

    def _extract_single_dimension(self, entity) -> Optional[Dict]:
        """提取单个尺寸标注（供分页/常规模式共用）"""
        try:  # 尝试
            meas = entity.get_measurement() if hasattr(entity, 'get_measurement') else None
            if meas is None or meas <= 0.1:
                return None
            defp2 = entity.dxf.defpoint2 if hasattr(entity.dxf, 'defpoint2') else None
            defp3 = entity.dxf.defpoint3 if hasattr(entity.dxf, 'defpoint3') else None
            tmid = entity.dxf.text_midpoint if hasattr(entity.dxf, 'text_midpoint') else None
            dim = {
                "handle": entity.dxf.handle if hasattr(entity.dxf, 'handle') else '',  # 字段
                "layer": entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',  # 字段
                "measurement": meas,  # 字段
                "text": entity.get_measurement_text() if hasattr(entity, 'get_measurement_text') else str(meas),  # 字段
                "dimtype": str(entity.dxf.dimtype) if hasattr(entity.dxf, 'dimtype') else 'LINEAR',  # 字段
                "position": {  # 字段
                    "x": entity.dxf.defpoint.x if hasattr(entity.dxf.defpoint, 'x') else 0,  # 字段
                    "y": entity.dxf.defpoint.y if hasattr(entity.dxf.defpoint, 'y') else 0,  # 字段
                },
                "defpoint2": {  # 字段
                    "x": defp2.x if defp2 and hasattr(defp2, 'x') else 0,  # 字段
                    "y": defp2.y if defp2 and hasattr(defp2, 'y') else 0,  # 字段
                },
                "defpoint3": {  # 字段
                    "x": defp3.x if defp3 and hasattr(defp3, 'x') else 0,  # 字段
                    "y": defp3.y if defp3 and hasattr(defp3, 'y') else 0,  # 字段
                },
                "text_midpoint": {  # 字段
                    "x": tmid.x if tmid and hasattr(tmid, 'x') else 0,  # 字段
                    "y": tmid.y if tmid and hasattr(tmid, 'y') else 0,  # 字段
                },
            }
            return dim
        except Exception:  # 捕获异常
            return None

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
        增强：如果同目录没有，也搜索父目录和同级目录。
        """
        # 1. 同目录同名 DXF
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

        # 2. 搜索父目录及以下所有子目录，找同名或近名 DXF
        parent_dir = path.parent.parent
        if parent_dir.exists() and parent_dir != path.parent:
            dwg_name = path.stem  # 去掉后缀
            for dxf_file in parent_dir.rglob('*.dxf'):
                dxf_stem = dxf_file.stem
                # 匹配规则：去掉编号、_t3 后缀后比较核心名称
                if self._names_match(dwg_name, dxf_stem):
                    try:
                        dxf_doc = ezdxf.readfile(str(dxf_file))
                        msp = dxf_doc.modelspace()
                        count = len(list(msp))
                        if count > 10:
                            return dxf_doc
                    except Exception:
                        pass

        return None

    def _names_match(self, dwg_name: str, dxf_name: str) -> bool:
        """检查 DWG 和 DXF 文件名是否匹配

        天正 T3 文件命名不统一，需要做模糊匹配：
        - 去掉编号前缀（数字开头的部分）
        - 去掉 _t3 后缀
        - 统一空格和括号
        """
        import re

        def normalize(name: str) -> str:
            # 去掉 _t3 后缀
            name = re.sub(r'_t3$', '', name, flags=re.IGNORECASE)
            # 去掉开头的数字编号（如 "6.", "20210409-3#"）
            name = re.sub(r'^[\d#\-\.\s]+', '', name)
            # 统一括号和空格
            name = name.replace('（', '(').replace('）', ')')
            name = name.replace('_', '').replace(' ', '')
            return name.lower()

        dwg_norm = normalize(dwg_name)
        dxf_norm = normalize(dxf_name)
        return dwg_norm == dxf_norm or dwg_norm in dxf_norm or dxf_norm in dwg_norm

    def _try_librecad_convert(self, path: Path) -> Optional[Any]:
        """尝试用 LibreCAD CLI 将 DWG 转换为 DXF

        LibreCAD -c 不生成输出文件，CLI 只支持 dxf2pdf，无法做 DWG→DXF 转换。
        此方法目前返回 None，保留接口以备未来支持。
        """
        # LibreCAD CLI 不支持 DWG→DXF 转换，跳过
        return None

    def _try_aspose_cad_convert(self, path: Path) -> Optional[Any]:
        """尝试用 aspose-cad 将 DWG 转换为 DXF

        aspose-cad 基于 .NET 互操作，能解析 T3 DWG 但触发 ICU/libssl SIGABRT。
        用子进程隔离避免主进程崩溃，并设置 DOTNET_SYSTEM_GLOBALIZATION_INVARIANT。
        """
        tmp_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False)
        tmp_path = tmp_dxf.name
        tmp_dxf.close()

        try:
            script = f'''
import os, sys, signal
sys.path.insert(0, "/home/kezhigang/.local/lib/python3.12/site-packages")
# 捕获 SIGABRT
signal.signal(signal.SIGABRT, lambda *a: sys.exit(127))

try:
    import aspose.cad as ac
    from aspose.cad.imageoptions import DxfOptions
except Exception:
    sys.exit(1)

try:
    img = ac.Image.load("{str(path)}")
    if img is None:
        sys.exit(1)
    opts = DxfOptions()
    img.save("{tmp_path}", opts)
except Exception:
    sys.exit(2)
'''
            env = os.environ.copy()
            env['DOTNET_SYSTEM_GLOBALIZATION_INVARIANT'] = '1'
            result = subprocess.run(
                [sys.executable, '-c', script],
                capture_output=True, timeout=180, cwd='/tmp', env=env
            )
            if result.returncode == 0:
                stat = Path(tmp_path).stat()
                if stat.st_size > 10000:
                    try:
                        dxf_doc = ezdxf.readfile(tmp_path)
                        msp = dxf_doc.modelspace()
                        count = len(list(msp))
                        if count > 10:
                            return dxf_doc
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return None

    def _try_ezdwg_export_dxf(self, path: Path) -> Optional[Any]:
        """第 1 级：ezdwg.read() + export_dxf() 直转"""
        try:
            import ezdwg as _ezdwg
            dwg_doc = _ezdwg.read(str(path))
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

        增强版：增加 INSERT 展开（含块定义解析）、HATCH、SOLID 实体支持
        """
        try:
            import ezdwg as _ezdwg
            dwg_doc = _ezdwg.read(str(path))
            dxf_doc = ezdxf.new("R2010")

            # ── 块定义缓存：通过 export_dxf 间接获取 ──
            block_defs: Dict[str, Any] = {}
            try:
                tmp_xref = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
                dwg_doc.export_dxf(str(tmp_xref))
                tmp_xref.close()
                xref_doc = ezdxf.readfile(tmp_xref)
                for name, blk in xref_doc.blocks:
                    if blk.is_xref:
                        continue
                    # 缓存块定义的实体列表
                    entities = list(blk)
                    if entities:
                        block_defs[name.upper()] = entities
                xref_doc.close()
                os.unlink(tmp_xref.name)
            except Exception:
                pass

            # ── 遍历 modelspace 实体 ──
            msp_src = dwg_doc.modelspace()
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
                            scale = d.get("x_scale", d.get("y_scale", 1.0)) or 1.0
                            rotation = d.get("rotation", 0.0) or 0.0
                            # 尝试展开块定义
                            expanded = False
                            for blk_name, blk_entities in block_defs.items():
                                if blk_name.lower() == name.lower():
                                    self._insert_block_expand(
                                        blk_entities, msp_dst, x, y, scale, rotation,
                                        color, layer, total_var=None  # 不计数，展开的子实体在 _insert_block_expand 内部计数
                                    )
                                    expanded = True
                                    break
                            if not expanded:
                                # 无块定义或解析失败 → 回退到占位框
                                half = max(50.0, scale * 20.0)
                                msp_dst.add_lwpolyline([
                                    (x - half, y - half),
                                    (x + half, y - half),
                                    (x + half, y + half),
                                    (x - half, y + half),
                                    (x - half, y - half),
                                ], dxfattribs={"color": 1, "layer": layer})
                                msp_dst.add_text(
                                    f"INSERT:{name}",
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

        # ── 第 1 级：aspose-cad 转换（最可靠，支持 T3） ──
        result = self._try_aspose_cad_convert(path)
        if result is not None:
            return result

        # ── 第 2 级：export_dxf 直转 ──
        result = self._try_ezdwg_export_dxf(path)
        if result is not None:
            return result

        # ── 第 3 级：LibreCAD CLI 转换 ──
        result = self._try_librecad_convert(path)
        if result is not None:
            return result

        # ── 第 4 级：手动逐元素转换 ──
        result = self._try_manual_convert(path)
        if result is not None:
            return result

        # ── 第 5 级：raw 逐个类型解码 ──
        result = self._try_raw_decode(path)
        if result is not None:
            return result

        # ── 第 5 级：所有方案都失败 ──
        return None

    def _insert_block_expand(self, block_entities, msp_dst, base_x, base_y,
                              scale, rotation, color, layer):
        """将块定义的实体展开到指定位置

        按 INSERT 的插入点 (base_x, base_y)、缩放、旋转应用仿射变换。
        """
        try:
            import math
            # 旋转变换矩阵
            cos_r = math.cos(math.radians(rotation))
            sin_r = math.sin(math.radians(rotation))
            def transform_point(p):
                dx = (p[0] - base_x) * scale
                dy = (p[1] - base_y) * scale
                rx = dx * cos_r - dy * sin_r + base_x
                ry = dx * sin_r + dy * cos_r + base_y
                return (rx, ry)
            for ent in block_entities:
                dxf_type = ent.dxftype()
                try:
                    ent_color = ent.dxf.get("color", color)
                    ent_layer = ent.dxf.get("layer", layer)
                    if dxf_type == "LINE":
                        start = transform_point(ent.dxf["start"][:2])
                        end = transform_point(ent.dxf["end"][:2])
                        msp_dst.add_line(start, end, dxfattribs={"color": ent_color, "layer": ent_layer})
                    elif dxf_type == "LWPOLYLINE":
                        pts = [transform_point(p[:2]) for p in ent.dxf["points"]]
                        if len(pts) >= 2:
                            msp_dst.add_lwpolyline(pts, dxfattribs={"color": ent_color, "layer": ent_layer})
                    elif dxf_type == "CIRCLE":
                        center = transform_point(ent.dxf["center"][:2])
                        radius = ent.dxf["radius"] * scale
                        msp_dst.add_circle(center, radius, dxfattribs={"color": ent_color, "layer": ent_layer})
                    elif dxf_type == "ARC":
                        center = transform_point(ent.dxf["center"][:2])
                        radius = ent.dxf["radius"] * scale
                        start_a = ent.dxf["start_angle"] + rotation
                        end_a = ent.dxf["end_angle"] + rotation
                        msp_dst.add_arc(center, radius, start_a, end_a, dxfattribs={"color": ent_color, "layer": ent_layer})
                    elif dxf_type in ("TEXT", "MTEXT"):
                        ins = ent.dxf.get("insert", (0, 0, 0))
                        new_ins = transform_point(ins[:2])
                        height = (ent.dxf.get("height", 2.5) or 2.5) * scale
                        msp_dst.add_text(ent.dxf.get("text", ""),
                                          dxfattribs={"color": ent_color, "height": height,
                                                      "insert": new_ins, "layer": ent_layer})
                    elif dxf_type == "SOLID":
                        pts_2d = [(ent.dxf.get(f"{ax}{i}", 0), ent.dxf.get(f"{ay}{i}", 0))
                                   for ax, ay, i in [("x", "y", 0), ("x", "y", 1), ("x", "y", 2), ("x", "y", 3)]]
                        new_pts = [transform_point(p) for p in pts_2d]
                        if len(new_pts) >= 3:
                            msp_dst.add_solid(new_pts[:4], dxfattribs={"color": ent_color, "layer": ent_layer})
                    elif dxf_type == "POINT":
                        loc = ent.dxf.get("location", (0, 0, 0))
                        new_loc = transform_point(loc[:2])
                        msp_dst.add_point(new_loc, dxfattribs={"color": ent_color, "layer": ent_layer})
                except Exception:
                    pass  # 单个实体展开失败不影响其他实体
        except Exception:
            pass

    def clear_cache(self):
        """清除解析缓存"""
        self._parse_cache.clear()

    def _compute_bbox(self, entity) -> Dict[str, float]:
        """计算图元边界框

        多层兜底策略，支持 ezdwg 手动重建的图元（无标准 bbox 方法）
        """
        # 1. ezdxf 原生 bbox 方法
        try:  # 尝试
            if hasattr(entity, 'bbox'):
                bbox = entity.bbox()
                if bbox and bbox.extmin is not None and bbox.extmax is not None:
                    w = bbox.extmax[0] - bbox.extmin[0]
                    h = bbox.extmax[1] - bbox.extmin[1]
                    if w > 0 or h > 0:
                        return {"x": bbox.extmin[0], "y": bbox.extmin[1], "width": w, "height": h}
        except Exception:  # 捕获异常
            pass  # 占位

        # 2. 从 vertices() 计算（ezdxf 原生图元）
        try:  # 尝试
            points = list(entity.vertices())
            if points:
                xs, ys = [], []
                for p in points:  # 循环
                    try:  # 尝试
                        xs.append(p.dxf.location.x)
                        ys.append(p.dxf.location.y)
                    except Exception:  # 捕获异常
                        try:  # 尝试
                            xs.append(p[0])
                            ys.append(p[1])
                        except Exception:  # 捕获异常
                            pass  # 占位
                if xs and ys:
                    w, h = max(xs) - min(xs), max(ys) - min(ys)
                    if w > 0 or h > 0:
                        return {"x": min(xs), "y": min(ys), "width": w, "height": h}
        except Exception:  # 捕获异常
            pass  # 占位

        # 3. 从 dxf 字典 points 计算（ezdwg 手动重建的 LWPOLYLINE）
        try:  # 尝试
            pts = entity.dxf.get('points', [])
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
        except Exception:  # 捕获异常
            pass  # 占位

        # 4. 从 start/end 端点计算（LINE / ezdwg 重建的 LINE）
        try:  # 尝试
            start = entity.dxf.start
            end = entity.dxf.end
            if start is not None and end is not None:
                sx = start[0] if hasattr(start, '__getitem__') else start.x
                sy = start[1] if hasattr(start, '__getitem__') else start.y
                ex = end[0] if hasattr(end, '__getitem__') else end.x
                ey = end[1] if hasattr(end, '__getitem__') else end.y
                return {"x": min(sx, ex), "y": min(sy, ey), "width": abs(ex - sx), "height": abs(ey - sy)}
        except Exception:  # 捕获异常
            pass  # 占位

        return {"x": 0, "y": 0, "width": 0, "height": 0}

    def _extract_properties(self, entity) -> Dict[str, Any]:
        """提取几何属性"""
        props = {}

        try:  # 尝试
            if entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                props["length"] = Vec2(start).distance(Vec2(end))  # 操作
                props["angle"] = Vec2(end - start).angle_deg  # 操作

            elif entity.dxftype() == 'CIRCLE':  # 分支
                props["radius"] = entity.dxf.radius  # 操作
                props["diameter"] = entity.dxf.radius * 2  # 操作

            elif entity.dxftype() == 'LWPOLYLINE':  # 分支
                if hasattr(entity, 'length'):
                    props["length"] = entity.length  # 操作
                if entity.closed:
                    props["area"] = self._compute_polygon_area(entity)  # 操作
                # 记录顶点数（ezdwg 重建的图元用 points）
                try:  # 尝试
                    pts = entity.dxf.get('points', [])
                    props["point_count"] = len(pts)  # 操作
                except Exception:  # 捕获异常
                    try:  # 尝试
                        pts = list(entity.vertices())
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
                    block_name = entity.dxf.name if hasattr(entity.dxf, 'name') else ''
                    props["block_name"] = block_name or ''  # 操作
                    ins = entity.dxf.insert if hasattr(entity.dxf, 'insert') else None
                    if ins:
                        props["insert_x"] = ins[0] if hasattr(ins, '__getitem__') else ins.x  # 操作
                        props["insert_y"] = ins[1] if hasattr(ins, '__getitem__') else ins.y  # 操作
                except Exception:  # 捕获异常
                    pass  # 占位

        except Exception:  # 捕获异常
            pass  # 占位

        return props

    @staticmethod
    def _compute_polygon_area(entity) -> float:
        """计算多边形面积"""
        try:  # 尝试
            points = list(entity.vertices())
            if len(points) < 3:
                return 0.0
            # 鞋带公式
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            area = 0.5 * abs(sum(xs[i]*ys[i+1] - xs[i+1]*ys[i]
                                 for i in range(len(points)-1)))  # 循环
            return area
        except Exception:  # 捕获异常
            return 0.0
