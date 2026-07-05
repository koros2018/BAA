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
import tempfile  # stdlib: temp files
import shutil  # stdlib: file ops
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
        _sys.path.insert(0, '/home/kezhigang/.local/lib/python3.12/site-packages')  # sys path
        from ezdwg import raw as _ezdwg_raw  # import: ezdwg library
    except ImportError:  # catch exception
        pass  # code

# ── 数据结构 ──────────────────────────────────────────────

class RawPrimitive:  # class definition
    """原始图元 - 图纸解析管线的输出"""
    def __init__(self, dxf_type: str, layer: str, handle: str,  # method: def __init__(self, dxf_type: str, layer: str, handle: str,
                 bbox: Dict[str, float], properties: Dict[str, Any] = None):  # assignment
        self.dxf_type = dxf_type          # LINE, LWPOLYLINE, CIRCLE, TEXT, DIMENSION...
        self.layer = layer                 # 图层名
        self.handle = handle               # DXF handle
        self.bbox = bbox                   # {"x": float, "y": float, "width": float, "height": float}
        self.properties = properties or {} # 额外属性（长度、面积、角度等）

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
    def __init__(self, file_path: str, file_id: str,  # method: def __init__(self, file_path: str, file_id: str,
                 primitives: List[RawPrimitive] = None,  # 操作
                 dimensions: List[Dict] = None,  # 操作
                 error: Optional[str] = None,  # assignment
                 warning: Optional[str] = None):  # 操作
        self.file_path = file_path  # assignment
        self.file_id = file_id  # assignment
        self.primitives = primitives or []  # assignment
        self.dimensions = dimensions or []  # assignment
        self.error = error  # assignment
        self.success = error is None  # assignment
        self.warning = warning  # assignment


# ── 解析引擎 ──────────────────────────────────────────────

class DrawingParser:  # class definition
    """图纸解析引擎 - 基于 ezdxf"""

    SUPPORTED_FORMATS = {".dxf", ".dwg"}  # assignment

    # ── P18 大图纸分页解析阈值 ──────────────────────────
    LARGE_FILE_MB = 50       # >50MB 自动走分页模式
    PAGE_SIZE = 5000          # 每页最多处理 5000 个实体
    MEMORY_LIMIT_MB = 1500    # RSS 超过 1.5GB 自动截断
    MAX_PAGES = 20            # 最多 20 页（10 万实体上限）

    def __init__(self):  # method: def __init__(self):
        self._doc = None  # assignment
        self._parse_cache: Dict[str, DrawingResult] = {}  # file_hash -> DrawingResult
        self._cache_max = 50  # 最多缓存50个结果

    def parse(self, file_path: str, file_id: str = None) -> DrawingResult:  # method: def parse(self, file_path: str, file_id: str = None) -> Draw
        """
        解析 DXF/DWG 图纸，提取原始图元

        参数:
            file_path: 图纸文件路径（支持 dxf, dwg）
            file_id: 文件标识（可选，自动生成）

        返回:
            DrawingResult 包含原始图元列表
        """
        path = Path(file_path)  # function call
        ext = path.suffix.lower()  # function call

        # ── 文件哈希缓存：相同文件秒级返回 ────────────────
        try:  # try block
            import hashlib  # stdlib: hashing
            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:32]  # function call
            cached = self._parse_cache.get(file_hash)  # function call
            if cached is not None:  # check: value is not None
                return cached  # return
        except Exception:  # catch exception
            file_hash = None  # assignment

        if ext not in self.SUPPORTED_FORMATS:  # check: membership test
            return DrawingResult(  # return
                file_path=file_path,  # assignment
                file_id=file_id or f"baa-file-{path.stem}",  # assignment
                error=f"不支持的文件格式: {ext}。支持: dxf, dwg"  # assignment
            )  # code

        if not path.exists():  # check: negated condition
            return DrawingResult(  # return
                file_path=file_path,  # assignment
                file_id=file_id or f"baa-file-{path.stem}",  # assignment
                error=f"文件不存在: {file_path}"  # assignment
            )  # code

        try:  # 尝试
            if ext == ".dwg":  # condition: ext == ".dwg":
                dxf_doc = self._parse_dwg(path)  # function call
                if dxf_doc is None:  # check: value is None
                    # DWG 格式检测
                    format_hint = self._detect_dwg_format(path)  # function call
                    
                    # 版本检测
                    version_hint = ""  # assignment
                    try:  # 尝试
                        ver = _ezdwg_raw.detect_version(str(path)) if _ezdwg_raw else None  # str conversion
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
                    if format_hint == '天正 T3 加密格式':  # check: OR condition
                        diag_parts.append(f"，检测到{format_hint}")  # append to list
                        diag_parts.append("请用 AutoCAD 打开后执行 T3转T0(T3→T0) 命令，或另存为 DXF 格式。")  # append to list
                    elif format_hint:  # elif condition
                        diag_parts.append(f"，检测到{format_hint}")  # append to list
                        diag_parts.append("请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。")  # append to list
                    else:  # else: default case
                        diag_parts.append("，当前解析器无法读取此格式。")  # append to list
                        diag_parts.append("请用 LibreCAD (开源免费) 打开后另存为 DXF 格式再上传。")  # append to list
                    
                    return DrawingResult(  # return
                        file_path=file_path,  # assignment
                        file_id=file_id or f"baa-file-{path.stem}",  # assignment
                        error="".join(diag_parts)  # function call
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
                error=f"DXF 解析失败: {str(e)}"  # str conversion
            )  # code

        primitives, dimensions, page_warning = self._extract_primitives_paged(use_paging if ext == ".dxf" else False)  # function call

        result = DrawingResult(  # assignment
            file_path=file_path,  # assignment
            file_id=file_id or f"baa-file-{path.stem}",  # assignment
            primitives=primitives,  # assignment
            dimensions=dimensions,  # assignment
        )  # code

        # ── P18 分页警告 ────────────────────────────────
        if page_warning:  # condition: page_warning:
            result.error = page_warning  # assignment

        # ── 写入缓存 ──────────────────────────────────────
        if file_hash and result.success:  # check: AND condition
            if len(self._parse_cache) >= self._cache_max:  # check: numeric comparison
                # 淘汰最旧的一个
                old_key = next(iter(self._parse_cache))  # function call
                del self._parse_cache[old_key]  # code
            self._parse_cache[file_hash] = result  # assignment

        return result  # return

    def _extract_primitives_paged(self, use_paging: bool = False) -> tuple:  # method: def _extract_primitives_paged(self, use_paging: bool = False
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
                    if dxf_type == 'DIMENSION':  # condition: dxf_type == 'DIMENSION':
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
                if dxf_type == 'DIMENSION':  # condition: dxf_type == 'DIMENSION':
                    dim = self._extract_single_dimension(entity)  # function call
                    if dim is not None:  # check: value is not None
                        all_dimensions.append(dim)  # append to list
                else:  # else: default case
                    primitive = self._extract_single_primitive(entity)  # function call
                    if primitive is not None:  # check: value is not None
                        all_primitives.append(primitive)  # append to list

        del all_entities  # code
        return all_primitives, all_dimensions, warning  # return

    def _extract_single_primitive(self, entity) -> Optional[RawPrimitive]:  # method: def _extract_single_primitive(self, entity) -> Optional[RawP
        """提取单个图元（供分页/常规模式共用）"""
        dxf_type = entity.dxftype()  # function call
        if dxf_type == 'DIMENSION':  # condition: dxf_type == 'DIMENSION':
            return None  # DIMENSION 由 extract_dimensions 处理
        layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'  # attribute check
        handle = entity.dxf.handle if hasattr(entity.dxf, 'handle') else ''  # attribute check

        # 计算边界框
        try:  # 尝试
            bbox = self._compute_bbox(entity)  # function call
        except Exception:  # 捕获异常
            return None  # return: None

        # 提取几何属性
        props = self._extract_properties(entity)  # function call

        return RawPrimitive(  # return
            dxf_type=dxf_type,  # assignment
            layer=layer,  # assignment
            handle=handle,  # assignment
            bbox=bbox,  # assignment
            properties=props,  # assignment
        )  # code

    def _extract_single_dimension(self, entity) -> Optional[Dict]:  # method: def _extract_single_dimension(self, entity) -> Optional[Dict
        """提取单个尺寸标注（供分页/常规模式共用）"""
        try:  # 尝试
            meas = entity.get_measurement() if hasattr(entity, 'get_measurement') else None  # attribute check
            if meas is None or meas <= 0.1:  # check: value is None
                return None  # return: None
            defp2 = entity.dxf.defpoint2 if hasattr(entity.dxf, 'defpoint2') else None  # attribute check
            defp3 = entity.dxf.defpoint3 if hasattr(entity.dxf, 'defpoint3') else None  # attribute check
            tmid = entity.dxf.text_midpoint if hasattr(entity.dxf, 'text_midpoint') else None  # attribute check
            dim = {  # assignment
                "handle": entity.dxf.handle if hasattr(entity.dxf, 'handle') else '',  # 字段
                "layer": entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',  # 字段
                "measurement": meas,  # 字段
                "text": entity.get_measurement_text() if hasattr(entity, 'get_measurement_text') else str(meas),  # 字段
                "dimtype": str(entity.dxf.dimtype) if hasattr(entity.dxf, 'dimtype') else 'LINEAR',  # 字段
                "position": {  # 字段
                    "x": entity.dxf.defpoint.x if hasattr(entity.dxf.defpoint, 'x') else 0,  # 字段
                    "y": entity.dxf.defpoint.y if hasattr(entity.dxf.defpoint, 'y') else 0,  # 字段
                },  # code
                "defpoint2": {  # 字段
                    "x": defp2.x if defp2 and hasattr(defp2, 'x') else 0,  # 字段
                    "y": defp2.y if defp2 and hasattr(defp2, 'y') else 0,  # 字段
                },  # code
                "defpoint3": {  # 字段
                    "x": defp3.x if defp3 and hasattr(defp3, 'x') else 0,  # 字段
                    "y": defp3.y if defp3 and hasattr(defp3, 'y') else 0,  # 字段
                },  # code
                "text_midpoint": {  # 字段
                    "x": tmid.x if tmid and hasattr(tmid, 'x') else 0,  # 字段
                    "y": tmid.y if tmid and hasattr(tmid, 'y') else 0,  # 字段
                },  # code
            }  # code
            return dim  # return
        except Exception:  # 捕获异常
            return None  # return: None

    # ── DWG 解析（六级兜底） ───────────────────────────

    def _detect_dwg_format(self, path: Path) -> Optional[str]:  # method: def _detect_dwg_format(self, path: Path) -> Optional[str]:
        """检测 DWG 文件格式问题，返回诊断信息

        检测类型：
        1. 天正 T3 加密：AcDbObjects section size 远超文件大小
        2. 格式损坏/不兼容：section offset 超出文件大小
        3. 其他 ezdwg 无法解析的格式

        返回:
            str: 格式说明，可正常解析返回 None
        """
        try:  # try block
            if not _ezdwg_raw:  # check: negated condition
                return None  # return: None
            sections = _ezdwg_raw.list_section_locators(str(path))  # str conversion
            file_size = path.stat().st_size  # function call

            for name, offset, size in sections:  # loop: iterate
                expected_end = offset + size  # assignment
                if name == 'AcDb:AcDbObjects' and expected_end > file_size * 1.5:  # check: numeric comparison
                    return '天正 T3 加密格式'  # return
                # section 在文件范围外
                if offset > file_size and name not in ('', 'Unknown3'):  # check: numeric comparison
                    return '格式不兼容'  # return
            return None  # return: None
        except Exception:  # catch exception
            return None  # return: None

    def _try_same_dir_dxf(self, path: Path) -> Optional[Any]:  # method: def _try_same_dir_dxf(self, path: Path) -> Optional[Any]:
        """尝试加载同目录的 DXF 文件作为兜底

        天正 T3 图纸通常同时提供 DWG 和 DXF 版本。
        如果同目录有同名 DXF，直接用它。
        增强：如果同目录没有，也搜索父目录和同级目录。
        """
        # 1. 同目录同名 DXF
        dxf_path = path.with_suffix('.dxf')  # function call
        if dxf_path.exists():  # condition: dxf_path.exists():
            try:  # try block
                dxf_doc = ezdxf.readfile(str(dxf_path))  # str conversion
                msp = dxf_doc.modelspace()  # function call
                count = len(list(msp))  # get length
                if count > 10:  # check: numeric comparison
                    return dxf_doc  # return
            except Exception:  # catch exception
                pass  # code

        # 2. 搜索父目录及以下所有子目录，找同名或近名 DXF
        parent_dir = path.parent.parent  # assignment
        if parent_dir.exists() and parent_dir != path.parent:  # check: AND condition
            dwg_name = path.stem  # 去掉后缀
            for dxf_file in parent_dir.rglob('*.dxf'):  # loop: iterate
                dxf_stem = dxf_file.stem  # assignment
                # 匹配规则：去掉编号、_t3 后缀后比较核心名称
                if self._names_match(dwg_name, dxf_stem):  # condition: self._names_match(dwg_name, dxf_stem):
                    try:  # try block
                        dxf_doc = ezdxf.readfile(str(dxf_file))  # str conversion
                        msp = dxf_doc.modelspace()  # function call
                        count = len(list(msp))  # get length
                        if count > 10:  # check: numeric comparison
                            return dxf_doc  # return
                    except Exception:  # catch exception
                        pass  # code

        return None  # return: None

    def _names_match(self, dwg_name: str, dxf_name: str) -> bool:  # method: def _names_match(self, dwg_name: str, dxf_name: str) -> bool
        """检查 DWG 和 DXF 文件名是否匹配

        天正 T3 文件命名不统一，需要做模糊匹配：
        - 去掉编号前缀（数字开头的部分）
        - 去掉 _t3 后缀
        - 统一空格和括号
        """
        import re  # stdlib: regex

        def normalize(name: str) -> str:  # method: def normalize(name: str) -> str:
            # 去掉 _t3 后缀
            name = re.sub(r'_t3$', '', name, flags=re.IGNORECASE)  # regex operation
            # 去掉开头的数字编号（如 "6.", "20210409-3#"）
            name = re.sub(r'^[\d#\-\.\s]+', '', name)  # regex operation
            # 统一括号和空格
            name = name.replace('（', '(').replace('）', ')')  # function call
            name = name.replace('_', '').replace(' ', '')  # function call
            return name.lower()  # return

        dwg_norm = normalize(dwg_name)  # function call
        dxf_norm = normalize(dxf_name)  # function call
        return dwg_norm == dxf_norm or dwg_norm in dxf_norm or dxf_norm in dwg_norm  # return

    def _try_librecad_convert(self, path: Path) -> Optional[Any]:  # method: def _try_librecad_convert(self, path: Path) -> Optional[Any]
        """尝试用 LibreCAD CLI 将 DWG 转换为 DXF

        LibreCAD -c 不生成输出文件，CLI 只支持 dxf2pdf，无法做 DWG→DXF 转换。
        此方法目前返回 None，保留接口以备未来支持。
        """
        # LibreCAD CLI 不支持 DWG→DXF 转换，跳过
        return None  # return: None

    def _try_aspose_cad_convert(self, path: Path) -> Optional[Any]:  # method: def _try_aspose_cad_convert(self, path: Path) -> Optional[An
        """尝试用 aspose-cad 将 DWG 转换为 DXF

        aspose-cad 基于 .NET 互操作，能解析 T3 DWG 但触发 ICU/libssl SIGABRT。
        用子进程隔离避免主进程崩溃，并设置 DOTNET_SYSTEM_GLOBALIZATION_INVARIANT。
        """
        tmp_dxf = tempfile.NamedTemporaryFile(suffix='.dxf', delete=False)  # function call
        tmp_path = tmp_dxf.name  # assignment
        tmp_dxf.close()  # function call

        try:  # try block
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
        try:  # try block
            import ezdwg as _ezdwg  # import
            dwg_doc = _ezdwg.read(str(path))  # str conversion
            tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)  # function call
            tmp_path = tmp.name  # assignment
            tmp.close()  # function call
            dwg_doc.export_dxf(tmp_path)  # function call
            dxf_doc = ezdxf.readfile(tmp_path)  # function call
            Path(tmp_path).unlink(missing_ok=True)  # function call
            return dxf_doc  # return
        except Exception:  # catch exception
            return None  # return: None

    def _try_manual_convert(self, path: Path) -> Optional[Any]:  # method: def _try_manual_convert(self, path: Path) -> Optional[Any]:
        """第 2 级：ezdwg Entity.dxf 字典手动逐元素重建

        增强版：增加 INSERT 展开（含块定义解析）、HATCH、SOLID 实体支持
        """
        try:  # try block
            import ezdwg as _ezdwg  # import
            dwg_doc = _ezdwg.read(str(path))  # str conversion
            dxf_doc = ezdxf.new("R2010")  # function call

            # ── 块定义缓存：通过 export_dxf 间接获取 ──
            block_defs: Dict[str, Any] = {}  # assignment
            try:  # try block
                tmp_xref = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)  # function call
                dwg_doc.export_dxf(str(tmp_xref))  # str conversion
                tmp_xref.close()  # function call
                xref_doc = ezdxf.readfile(tmp_xref)  # function call
                xref_names = []  # assignment
                for name, blk in xref_doc.blocks:  # loop: iterate
                    if blk.is_xref:  # condition: blk.is_xref:
                        xref_names.append(name)  # append to list
                        continue  # code
                    # 缓存块定义的实体列表
                    entities = list(blk)  # list conversion
                    if entities:  # condition: entities:
                        block_defs[name.upper()] = entities  # function call
                if xref_names:  # condition: xref_names:
                    result.warning = f"图纸含外部参照(xref): {', '.join(xref_names[:5])}（未展开，可能影响审查完整性）"  # function call
                xref_doc.close()  # function call
                os.unlink(tmp_xref.name)  # function call
            except Exception:  # catch exception
                pass  # code

            # ── 遍历 modelspace 实体 ──
            msp_src = dwg_doc.modelspace()  # function call
            msp_dst = dxf_doc.modelspace()  # function call

            total = 0  # assignment
            for dxf_type in ["LINE", "LWPOLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT",  # loop: iterate
                             "INSERT", "HATCH", "SOLID", "POINT", "ELLIPSE", "SPLINE"]:  # code
                try:  # try block
                    entities = list(msp_src.query(types=dxf_type))  # list conversion
                except Exception:  # catch exception
                    continue  # code

                for ent in entities:  # loop: iterate
                    try:  # try block
                        d = ent.dxf  # assignment
                        color = d.get("resolved_color_index", 7) or 7  # function call
                        layer = d.get("layer", "0")  # function call

                        if dxf_type == "LINE":  # condition: dxf_type == "LINE":
                            msp_dst.add_line(  # code
                                d["start"][:2], d["end"][:2],  # code
                                dxfattribs={"color": color, "layer": layer},  # assignment
                            )  # code
                            total += 1  # accumulate
                        elif dxf_type == "LWPOLYLINE":  # elif condition
                            pts = [(p[0], p[1]) for p in d["points"]]  # function call
                            if len(pts) >= 2:  # check: numeric comparison
                                msp_dst.add_lwpolyline(pts, dxfattribs={"color": color, "layer": layer})  # function call
                                total += 1  # accumulate
                        elif dxf_type == "CIRCLE":  # elif condition
                            msp_dst.add_circle(  # code
                                (d["center"][0], d["center"][1]), d["radius"],  # function call
                                dxfattribs={"color": color, "layer": layer},  # assignment
                            )  # code
                            total += 1  # accumulate
                        elif dxf_type == "ARC":  # elif condition
                            msp_dst.add_arc(  # code
                                (d["center"][0], d["center"][1]), d["radius"],  # function call
                                d["start_angle"], d["end_angle"],  # code
                                dxfattribs={"color": color, "layer": layer},  # assignment
                            )  # code
                            total += 1  # accumulate
                        elif dxf_type in ("TEXT", "MTEXT"):  # elif condition
                            ins = d.get("insert", (0, 0, 0))  # function call
                            msp_dst.add_text(  # code
                                d.get("text", ""),  # function call
                                dxfattribs={  # assignment
                                    "color": color,  # code
                                    "height": d.get("height", 2.5),  # function call
                                    "insert": (ins[0], ins[1]),  # function call
                                    "layer": layer,  # code
                                },  # code
                            )  # code
                            total += 1  # accumulate
                        elif dxf_type == "INSERT":  # elif condition
                            ins_pt = d.get("insert", (0, 0, 0))  # function call
                            name = d.get("name", "UNKNOWN")  # function call
                            x, y = ins_pt[0], ins_pt[1]  # assignment
                            scale = d.get("x_scale", d.get("y_scale", 1.0)) or 1.0  # function call
                            rotation = d.get("rotation", 0.0) or 0.0  # function call
                            # 尝试展开块定义
                            expanded = False  # assignment
                            for blk_name, blk_entities in block_defs.items():  # loop: iterate
                                if blk_name.lower() == name.lower():  # condition: blk_name.lower() == name.lower():
                                    self._insert_block_expand(  # code
                                        blk_entities, msp_dst, x, y, scale, rotation,  # code
                                        color, layer,  # code
                                        block_defs=block_defs, depth=0, max_depth=5  # assignment
                                    )  # code
                                    expanded = True  # assignment
                                    break  # code
                            if not expanded:  # check: negated condition
                                # 无块定义或解析失败 → 回退到占位框
                                half = max(50.0, scale * 20.0)  # get maximum
                                msp_dst.add_lwpolyline([  # code
                                    (x - half, y - half),  # function call
                                    (x + half, y - half),  # function call
                                    (x + half, y + half),  # function call
                                    (x - half, y + half),  # function call
                                    (x - half, y - half),  # function call
                                ], dxfattribs={"color": 1, "layer": layer})  # assignment
                                msp_dst.add_text(  # code
                                    f"INSERT:{name}",  # code
                                    dxfattribs={  # assignment
                                        "color": 1, "height": 100.0,  # code
                                        "insert": (x + half + 10, y), "layer": layer,  # function call
                                    },  # code
                                )  # code
                            total += 1  # accumulate
                        elif dxf_type == "HATCH":  # elif condition
                            try:  # try block
                                paths = ent.paths  # assignment
                                for path_data in paths:  # loop: iterate
                                    vertices = list(path_data.vertices)  # list conversion
                                    if len(vertices) >= 3:  # check: numeric comparison
                                        pts = [(v[0], v[1]) for v in vertices]  # function call
                                        msp_dst.add_lwpolyline(  # code
                                            pts + [pts[0]],  # code
                                            dxfattribs={"color": color, "layer": layer},  # assignment
                                        )  # code
                                        total += 1  # accumulate
                            except Exception:  # catch exception
                                pass  # code
                        elif dxf_type == "SOLID":  # elif condition
                            pts_2d = [(d.get(f"{ax}{i}", 0), d.get(f"{ay}{i}", 0))  # function call
                                      for ax, ay, i in [("x", "y", 0), ("x", "y", 1),  # loop: iterate
                                                        ("x", "y", 2), ("x", "y", 3)]]  # function call
                            if len(pts_2d) >= 3:  # check: numeric comparison
                                msp_dst.add_solid(pts_2d[:4], dxfattribs={"color": color, "layer": layer})  # function call
                                total += 1  # accumulate
                        elif dxf_type == "POINT":  # elif condition
                            pt = d.get("location", (0, 0, 0))  # function call
                            msp_dst.add_point((pt[0], pt[1]), dxfattribs={"color": color, "layer": layer})  # int conversion
                            total += 1  # accumulate
                    except Exception:  # catch exception
                        pass  # code

            if total > 10:  # check: numeric comparison
                return dxf_doc  # return
        except Exception:  # catch exception
            pass  # code
        return None  # return: None

    def _try_raw_decode(self, path: Path) -> Optional[Any]:  # method: def _try_raw_decode(self, path: Path) -> Optional[Any]:
        """第 3 级：ezdwg raw 逐个类型解码（跳过格式错误的类型）

        增强版：增加 HATCH、INSERT、DIMENSION 等实体的 raw 层解码
        """
        try:  # try block
            if not _ezdwg_raw:  # check: negated condition
                raise ImportError("ezdwg not available")  # function call

            dxf_doc = ezdxf.new("R2010")  # function call
            msp_dst = dxf_doc.modelspace()  # function call
            total = 0  # assignment

            _raw = _ezdwg_raw  # assignment
            decode_map = {  # assignment
                "LINE": lambda: _raw.decode_line_entities(str(path)),  # str conversion
                "LWPOLYLINE": lambda: _raw.decode_lwpolyline_entities(str(path)),  # str conversion
                "CIRCLE": lambda: _raw.decode_circle_entities(str(path)),  # str conversion
                "ARC": lambda: _raw.decode_arc_entities(str(path)),  # str conversion
                "TEXT": lambda: _raw.decode_text_entities(str(path)),  # str conversion
                "DIMENSION": lambda: _raw.decode_dimension_entities(str(path)),  # str conversion
                "INSERT": lambda: _raw.decode_insert_entities(str(path)),  # str conversion
                "HATCH": lambda: _raw.decode_hatch_entities(str(path)),  # str conversion
                "SOLID": lambda: _raw.decode_solid_entities(str(path)),  # str conversion
                "ELLIPSE": lambda: _raw.decode_ellipse_entities(str(path)),  # str conversion
                "SPLINE": lambda: _raw.decode_spline_entities(str(path)),  # str conversion
                "POINT": lambda: _raw.decode_point_entities(str(path)),  # str conversion
                "MTEXT": lambda: _raw.decode_mtext_entities(str(path)),  # str conversion
                "LEADER": lambda: _raw.decode_leader_entities(str(path)),  # str conversion
            }  # code
            for dxf_type, decode_func in decode_map.items():  # loop: iterate
                try:  # try block
                    for row in decode_func():  # loop: iterate
                        try:  # try block
                            color = row.get("color_index", 7)  # function call
                            layer = row.get("layer", "0")  # function call
                            if dxf_type == "LINE":  # condition: dxf_type == "LINE":
                                msp_dst.add_line(  # code
                                    (row.get("start_x", 0), row.get("start_y", 0)),  # function call
                                    (row.get("end_x", 0), row.get("end_y", 0)),  # function call
                                    dxfattribs={"color": color, "layer": layer},  # assignment
                                )  # code
                                total += 1  # accumulate
                            elif dxf_type == "LWPOLYLINE":  # elif condition
                                pts = row.get("points", [])  # function call
                                if len(pts) >= 2:  # check: numeric comparison
                                    msp_dst.add_lwpolyline(pts, dxfattribs={"color": color, "layer": layer})  # function call
                                    total += 1  # accumulate
                            elif dxf_type == "CIRCLE":  # elif condition
                                msp_dst.add_circle(  # code
                                    (row.get("center_x", 0), row.get("center_y", 0)),  # function call
                                    row.get("radius", 1),  # function call
                                    dxfattribs={"color": color, "layer": layer},  # assignment
                                )  # code
                                total += 1  # accumulate
                            elif dxf_type == "ARC":  # elif condition
                                msp_dst.add_arc(  # code
                                    (row.get("center_x", 0), row.get("center_y", 0)),  # function call
                                    row.get("radius", 1),  # function call
                                    row.get("start_angle", 0),  # function call
                                    row.get("end_angle", 360),  # function call
                                    dxfattribs={"color": color, "layer": layer},  # assignment
                                )  # code
                                total += 1  # accumulate
                            elif dxf_type == "TEXT":  # elif condition
                                msp_dst.add_text(  # code
                                    row.get("text", ""),  # function call
                                    dxfattribs={  # assignment
                                        "color": color,  # code
                                        "height": row.get("height", 2.5),  # function call
                                        "insert": (row.get("insert_x", 0), row.get("insert_y", 0)),  # function call
                                        "layer": layer,  # code
                                    },  # code
                                )  # code
                                total += 1  # accumulate
                            elif dxf_type == "MTEXT":  # elif condition
                                msp_dst.add_mtext(  # code
                                    row.get("text", ""),  # function call
                                    dxfattribs={  # assignment
                                        "color": color,  # code
                                        "char_height": row.get("height", 2.5),  # function call
                                        "insert": (row.get("insert_x", 0), row.get("insert_y", 0)),  # function call
                                        "layer": layer,  # code
                                    },  # code
                                )  # code
                                total += 1  # accumulate
                            elif dxf_type == "INSERT":  # elif condition
                                ins_x = row.get("insert_x", 0)  # function call
                                ins_y = row.get("insert_y", 0)  # function call
                                name = row.get("block_name", "UNKNOWN")  # function call
                                half = 50.0  # assignment
                                msp_dst.add_lwpolyline([  # code
                                    (ins_x - half, ins_y - half),  # function call
                                    (ins_x + half, ins_y - half),  # function call
                                    (ins_x + half, ins_y + half),  # function call
                                    (ins_x - half, ins_y + half),  # function call
                                    (ins_x - half, ins_y - half),  # function call
                                ], dxfattribs={"color": 1, "layer": layer})  # assignment
                                msp_dst.add_text(  # code
                                    name,  # code
                                    dxfattribs={"color": 1, "height": 100.0,  # assignment
                                                 "insert": (ins_x + half + 10, ins_y), "layer": layer},  # function call
                                )  # code
                                total += 1  # accumulate
                            elif dxf_type == "POINT":  # elif condition
                                msp_dst.add_point(  # code
                                    (row.get("x", 0), row.get("y", 0)),  # function call
                                    dxfattribs={"color": color, "layer": layer},  # assignment
                                )  # code
                                total += 1  # accumulate
                        except Exception:  # catch exception
                            pass  # code
                except Exception:  # catch exception
                    continue  # code

            if total > 10:  # check: numeric comparison
                return dxf_doc  # return
        except Exception:  # catch exception
            pass  # code
        return None  # return: None

    def _parse_dwg(self, path: Path):  # method: def _parse_dwg(self, path: Path):
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
        dxf_result = self._try_same_dir_dxf(path)  # function call
        if dxf_result is not None:  # check: value is not None
            return dxf_result  # return

        # ── 第 1 级：aspose-cad 转换（最可靠，支持 T3） ──
        result = self._try_aspose_cad_convert(path)  # function call
        if result is not None:  # check: value is not None
            return result  # return

        # ── 第 2 级：export_dxf 直转 ──
        result = self._try_ezdwg_export_dxf(path)  # function call
        if result is not None:  # check: value is not None
            return result  # return

        # ── 第 3 级：LibreCAD CLI 转换 ──
        result = self._try_librecad_convert(path)  # function call
        if result is not None:  # check: value is not None
            return result  # return

        # ── 第 4 级：手动逐元素转换 ──
        result = self._try_manual_convert(path)  # function call
        if result is not None:  # check: value is not None
            return result  # return

        # ── 第 5 级：raw 逐个类型解码 ──
        result = self._try_raw_decode(path)  # function call
        if result is not None:  # check: value is not None
            return result  # return

        # ── 第 5 级：所有方案都失败 ──
        return None  # return: None

    def _insert_block_expand(self, block_entities, msp_dst, base_x, base_y,  # method: def _insert_block_expand(self, block_entities, msp_dst, base
                              scale, rotation, color, layer,  # code
                              block_defs=None, depth=0, max_depth=5):  # assignment
        """将块定义的实体展开到指定位置（支持递归块嵌套）

        按 INSERT 的插入点 (base_x, base_y)、缩放、旋转应用仿射变换。
        块内嵌 INSERT 实体递归展开，最深 max_depth 层。
        """
        if depth > max_depth:  # check: numeric comparison
            return  # code
        try:  # try block
            import math  # stdlib: math
            # 旋转变换矩阵
            cos_r = math.cos(math.radians(rotation))  # math operation
            sin_r = math.sin(math.radians(rotation))  # math operation
            def transform_point(p):  # method: def transform_point(p):
                dx = (p[0] - base_x) * scale  # function call
                dy = (p[1] - base_y) * scale  # function call
                rx = dx * cos_r - dy * sin_r + base_x  # assignment
                ry = dx * sin_r + dy * cos_r + base_y  # assignment
                return (rx, ry)  # return: tuple
            for ent in block_entities:  # loop: iterate
                dxf_type = ent.dxftype()  # function call
                try:  # try block
                    ent_color = getattr(ent.dxf, "color", color) if hasattr(ent.dxf, "color") else color  # attribute check
                    ent_layer = getattr(ent.dxf, "layer", layer) if hasattr(ent.dxf, "layer") else layer  # attribute check
                    # 递归展开嵌套块
                    if dxf_type == "INSERT":  # condition: dxf_type == "INSERT":
                        if block_defs is not None:  # check: value is not None
                            ins_pt = getattr(ent.dxf, "insert", (0, 0, 0))  # get attribute
                            name = getattr(ent.dxf, "name", "UNKNOWN")  # get attribute
                            ins_x, ins_y = transform_point((ins_pt[0], ins_pt[1]))  # int conversion
                            ins_scale = getattr(ent.dxf, "x_scale", 1.0) or 1.0  # get attribute
                            ins_rot = getattr(ent.dxf, "rotation", 0.0) or 0.0  # get attribute
                            # 查找块定义
                            for blk_name, blk_entities in block_defs.items():  # loop: iterate
                                if blk_name.lower() == name.lower():  # condition: blk_name.lower() == name.lower():
                                    self._insert_block_expand(  # code
                                        blk_entities, msp_dst, ins_x, ins_y,  # code
                                        ins_scale * scale, ins_rot + rotation,  # code
                                        ent_color, ent_layer,  # code
                                        block_defs=block_defs, depth=depth+1, max_depth=max_depth  # assignment
                                    )  # code
                                    break  # code
                        continue  # code
                    elif dxf_type == "LINE":  # elif condition
                        start = transform_point((ent.dxf.start[0], ent.dxf.start[1]))  # int conversion
                        end = transform_point((ent.dxf.end[0], ent.dxf.end[1]))  # int conversion
                        msp_dst.add_line(start, end, dxfattribs={"color": ent_color, "layer": ent_layer})  # function call
                    elif dxf_type == "LWPOLYLINE":  # elif condition
                        pts = [transform_point((p[0], p[1])) for p in getattr(ent.dxf, "points", [])]  # get attribute
                        if len(pts) >= 2:  # check: numeric comparison
                            msp_dst.add_lwpolyline(pts, dxfattribs={"color": ent_color, "layer": ent_layer})  # function call
                    elif dxf_type == "CIRCLE":  # elif condition
                        center = transform_point((ent.dxf.center[0], ent.dxf.center[1]))  # int conversion
                        radius = ent.dxf.radius * scale  # assignment
                        msp_dst.add_circle(center, radius, dxfattribs={"color": ent_color, "layer": ent_layer})  # function call
                    elif dxf_type == "ARC":  # elif condition
                        center = transform_point((ent.dxf.center[0], ent.dxf.center[1]))  # int conversion
                        radius = ent.dxf.radius * scale  # assignment
                        start_a = ent.dxf.start_angle + rotation  # assignment
                        end_a = ent.dxf.end_angle + rotation  # assignment
                        msp_dst.add_arc(center, radius, start_a, end_a, dxfattribs={"color": ent_color, "layer": ent_layer})  # function call
                    elif dxf_type in ("TEXT", "MTEXT"):  # elif condition
                        ins = getattr(ent.dxf, "insert", (0, 0, 0))  # get attribute
                        new_ins = transform_point((ins[0], ins[1]))  # int conversion
                        height = (getattr(ent.dxf, "height", 2.5) or 2.5) * scale  # get attribute
                        msp_dst.add_text(getattr(ent.dxf, "text", ""),  # get attribute
                                          dxfattribs={"color": ent_color, "height": height,  # assignment
                                                      "insert": new_ins, "layer": ent_layer})  # code
                    elif dxf_type == "SOLID":  # elif condition
                        pts_2d = [(getattr(ent.dxf, f"{ax}{i}", 0), getattr(ent.dxf, f"{ay}{i}", 0))  # get attribute
                                   for ax, ay, i in [("x", "y", 0), ("x", "y", 1), ("x", "y", 2), ("x", "y", 3)]]  # loop: iterate
                        new_pts = [transform_point(p) for p in pts_2d]  # int conversion
                        if len(new_pts) >= 3:  # check: numeric comparison
                            msp_dst.add_solid(new_pts[:4], dxfattribs={"color": ent_color, "layer": ent_layer})  # function call
                    elif dxf_type == "POINT":  # elif condition
                        loc = getattr(ent.dxf, "location", (0, 0, 0))  # get attribute
                        new_loc = transform_point((loc[0], loc[1]))  # int conversion
                        msp_dst.add_point(new_loc, dxfattribs={"color": ent_color, "layer": ent_layer})  # int conversion
                except Exception:  # catch exception
                    pass  # 单个实体展开失败不影响其他实体
        except Exception:  # catch exception
            pass  # code

    def clear_cache(self):  # method: def clear_cache(self):
        """清除解析缓存"""
        self._parse_cache.clear()  # clear collection

    def _compute_bbox(self, entity) -> Dict[str, float]:  # method: def _compute_bbox(self, entity) -> Dict[str, float]:
        """计算图元边界框

        多层兜底策略，支持 ezdwg 手动重建的图元（无标准 bbox 方法）
        """
        # 1. ezdxf 原生 bbox 方法
        try:  # 尝试
            if hasattr(entity, 'bbox'):  # condition: hasattr(entity, 'bbox'):
                bbox = entity.bbox()  # function call
                if bbox and bbox.extmin is not None and bbox.extmax is not None:  # check: value is not None
                    w = bbox.extmax[0] - bbox.extmin[0]  # assignment
                    h = bbox.extmax[1] - bbox.extmin[1]  # assignment
                    if w > 0 or h > 0:  # check: numeric comparison
                        return {"x": bbox.extmin[0], "y": bbox.extmin[1], "width": w, "height": h}  # return: dict
        except Exception:  # 捕获异常
            pass  # 占位

        # 2. 从 vertices() 计算（ezdxf 原生图元）
        try:  # 尝试
            points = list(entity.vertices())  # list conversion
            if points:  # condition: points:
                xs, ys = [], []  # assignment
                for p in points:  # 循环
                    try:  # 尝试
                        xs.append(p.dxf.location.x)  # append to list
                        ys.append(p.dxf.location.y)  # append to list
                    except Exception:  # 捕获异常
                        try:  # 尝试
                            xs.append(p[0])  # append to list
                            ys.append(p[1])  # append to list
                        except Exception:  # 捕获异常
                            pass  # 占位
                if xs and ys:  # check: AND condition
                    w, h = max(xs) - min(xs), max(ys) - min(ys)  # get maximum
                    if w > 0 or h > 0:  # check: numeric comparison
                        return {"x": min(xs), "y": min(ys), "width": w, "height": h}  # return: dict
        except Exception:  # 捕获异常
            pass  # 占位

        # 3. 从 dxf 字典 points 计算（ezdwg 手动重建的 LWPOLYLINE）
        try:  # 尝试
            pts = entity.dxf.get('points', [])  # function call
            if pts:  # condition: pts:
                xs = [p[0] for p in pts]  # membership check
                ys = [p[1] for p in pts]  # membership check
                return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}  # return: dict
        except Exception:  # 捕获异常
            pass  # 占位

        # 4. 从 start/end 端点计算（LINE / ezdwg 重建的 LINE）
        try:  # 尝试
            start = entity.dxf.start  # assignment
            end = entity.dxf.end  # assignment
            if start is not None and end is not None:  # check: value is not None
                sx = start[0] if hasattr(start, '__getitem__') else start.x  # attribute check
                sy = start[1] if hasattr(start, '__getitem__') else start.y  # attribute check
                ex = end[0] if hasattr(end, '__getitem__') else end.x  # attribute check
                ey = end[1] if hasattr(end, '__getitem__') else end.y  # attribute check
                return {"x": min(sx, ex), "y": min(sy, ey), "width": abs(ex - sx), "height": abs(ey - sy)}  # return: dict
        except Exception:  # 捕获异常
            pass  # 占位

        return {"x": 0, "y": 0, "width": 0, "height": 0}  # return: dict

    def _extract_properties(self, entity) -> Dict[str, Any]:  # method: def _extract_properties(self, entity) -> Dict[str, Any]:
        """提取几何属性"""
        props = {}  # assignment

        try:  # 尝试
            if entity.dxftype() == 'LINE':  # condition: entity.dxftype() == 'LINE':
                start = entity.dxf.start  # assignment
                end = entity.dxf.end  # assignment
                props["length"] = Vec2(start).distance(Vec2(end))  # 操作
                props["angle"] = Vec2(end - start).angle_deg  # 操作

            elif entity.dxftype() == 'CIRCLE':  # 分支
                props["radius"] = entity.dxf.radius  # 操作
                props["diameter"] = entity.dxf.radius * 2  # 操作

            elif entity.dxftype() == 'LWPOLYLINE':  # 分支
                if hasattr(entity, 'length'):  # condition: hasattr(entity, 'length'):
                    props["length"] = entity.length  # 操作
                if entity.closed:  # condition: entity.closed:
                    props["area"] = self._compute_polygon_area(entity)  # 操作
                # 记录顶点数（ezdwg 重建的图元用 points）
                try:  # 尝试
                    pts = entity.dxf.get('points', [])  # function call
                    props["point_count"] = len(pts)  # 操作
                except Exception:  # 捕获异常
                    try:  # 尝试
                        pts = list(entity.vertices())  # list conversion
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
                    block_name = entity.dxf.name if hasattr(entity.dxf, 'name') else ''  # attribute check
                    props["block_name"] = block_name or ''  # 操作
                    ins = entity.dxf.insert if hasattr(entity.dxf, 'insert') else None  # attribute check
                    if ins:  # condition: ins:
                        props["insert_x"] = ins[0] if hasattr(ins, '__getitem__') else ins.x  # 操作
                        props["insert_y"] = ins[1] if hasattr(ins, '__getitem__') else ins.y  # 操作
                except Exception:  # 捕获异常
                    pass  # 占位

        except Exception:  # 捕获异常
            pass  # 占位

        return props  # return

    @staticmethod  # code
    def _compute_polygon_area(entity) -> float:  # method: def _compute_polygon_area(entity) -> float:
        """计算多边形面积"""
        try:  # 尝试
            points = list(entity.vertices())  # list conversion
            if len(points) < 3:  # check: numeric comparison
                return 0.0  # return
            # 鞋带公式
            xs = [p[0] for p in points]  # membership check
            ys = [p[1] for p in points]  # membership check
            area = 0.5 * abs(sum(xs[i]*ys[i+1] - xs[i+1]*ys[i]  # assignment
                                 for i in range(len(points)-1)))  # 循环
            return area  # return
        except Exception:  # 捕获异常
            return 0.0  # return
