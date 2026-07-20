"""
DWG 转换子模块 — 多种 DWG→DXF 转换策略

从 drawing_parser.py 拆分出来，包含 10 个 DWG 处理方法：
- 天正格式检测
- 同目录 DXF 自动兜底
- LibreCAD/Aspose/ezdwg 转换
- 手动转换（INSERT/HATCH/SOLID）
- 原始解码

这些函数原本是 DrawingParser 的实例方法，拆出为独立函数。
"""

from pathlib import Path
from typing import Optional, Any, List, Dict, Tuple, Union
import os
import sys
import subprocess
import tempfile

# ── ezdwg fallback（系统级安装，venv 可能不可见） ──────
_ezdwg_raw = None
try:
    from ezdwg import raw as _ezdwg_raw
except ImportError:
    try:
        import sys as _sys
        _sys.path.insert(0, "/home/kezhigang/.local/lib/python3.12/site-packages")
        from ezdwg import raw as _ezdwg_raw
    except ImportError:
        pass


def _detect_dwg_format(path: Path
) -> Optional[str]:  # method: def _detect_dwg_format(self, path: Path) -> Optional[str]:
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
            if (
                name == "AcDb:AcDbObjects" and expected_end > file_size * 1.5
            ):  # check: numeric comparison
                return "天正 T3 加密格式"  # return
            # section 在文件范围外
            if offset > file_size and name not in ("", "Unknown3"):  # check: numeric comparison
                return "格式不兼容"  # return
        return None  # return: None
    except Exception:  # catch exception
        return None  # return: None

def _try_same_dir_dxf(path: Path
) -> Optional[Any]:  # method: def _try_same_dir_dxf(self, path: Path) -> Optional[Any]:
    """尝试加载同目录的 DXF 文件作为兜底

    天正 T3 图纸通常同时提供 DWG 和 DXF 版本。
    如果同目录有同名 DXF，直接用它。
    增强：如果同目录没有，也搜索父目录和同级目录。
    """
    # 1. 同目录同名 DXF
    dxf_path = path.with_suffix(".dxf")  # function call
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
        for dxf_file in parent_dir.rglob("*.dxf"):  # loop: iterate
            dxf_stem = dxf_file.stem  # assignment
            # 匹配规则：去掉编号、_t3 后缀后比较核心名称
            if _names_match(
                dwg_name, dxf_stem
            ):  # condition: _names_match(dwg_name, dxf_stem):
                try:  # try block
                    dxf_doc = ezdxf.readfile(str(dxf_file))  # str conversion
                    msp = dxf_doc.modelspace()  # function call
                    count = len(list(msp))  # get length
                    if count > 10:  # check: numeric comparison
                        return dxf_doc  # return
                except Exception:  # catch exception
                    pass  # code

    return None  # return: None

def _names_match(dwg_name: str, dxf_name: str
) -> bool:  # method: def _names_match(self, dwg_name: str, dxf_name: str) -> bool
    """检查 DWG 和 DXF 文件名是否匹配

    天正 T3 文件命名不统一，需要做模糊匹配：
    - 去掉编号前缀（数字开头的部分）
    - 去掉 _t3 后缀
    - 统一空格和括号
    """
    import re  # stdlib: regex

    def normalize(name: str) -> str:  # method: def normalize(name: str) -> str:
        # 去掉 _t3 后缀
        name = re.sub(r"_t3$", "", name, flags=re.IGNORECASE)  # regex operation
        # 去掉开头的数字编号（如 "6.", "20210409-3#"）
        name = re.sub(r"^[\d#\-\.\s]+", "", name)  # regex operation
        # 统一括号和空格
        name = name.replace("（", "(").replace("）", ")")  # function call
        name = name.replace("_", "").replace(" ", "")  # function call
        return name.lower()  # return

    dwg_norm = normalize(dwg_name)  # function call
    dxf_norm = normalize(dxf_name)  # function call
    return dwg_norm == dxf_norm or dwg_norm in dxf_norm or dxf_norm in dwg_norm  # return

def _try_librecad_convert(path: Path
) -> Optional[Any]:  # method: def _try_librecad_convert(self, path: Path) -> Optional[Any]
    """尝试用 LibreCAD CLI 将 DWG 转换为 DXF

    LibreCAD -c 不生成输出文件，CLI 只支持 dxf2pdf，无法做 DWG→DXF 转换。
    此方法目前返回 None，保留接口以备未来支持。
    """
    # LibreCAD CLI 不支持 DWG→DXF 转换，跳过
    return None  # return: None

def _try_aspose_cad_convert(path: Path
) -> Optional[Any]:  # method: def _try_aspose_cad_convert(self, path: Path) -> Optional[An
    """尝试用 aspose-cad 将 DWG 转换为 DXF

    aspose-cad 基于 .NET 互操作，能解析 T3 DWG 但触发 ICU/libssl SIGABRT。
    用子进程隔离避免主进程崩溃，并设置 DOTNET_SYSTEM_GLOBALIZATION_INVARIANT。
    """
    tmp_dxf = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)  # function call
    tmp_path = tmp_dxf.name  # assignment
    tmp_dxf.close()  # function call

    try:  # try block
        script = f"""
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
if img is None:  # # 图像加载失败
    sys.exit(1)
opts = DxfOptions()
img.save("{tmp_path}", opts)
except Exception:
sys.exit(2)
"""
        env = os.environ.copy()
        env["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            timeout=180,
            cwd="/tmp",
            env=env,
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

def _resolve_xref_external(
    xref_names: List[str],
    dwg_path: Path,
    dxf_doc: Any,
    block_defs: Dict[str, Any],
    depth: int = 0,
    max_depth: int = 5,
    visited: set = None,
) -> List[str]:
    """解析外部参照（xref）文件，将内容合并到主 dxf_doc

    递归搜索 xref 文件：优先同目录，其次搜索子目录树，
    支持 ANON 匿名块、递归块嵌套（最深 max_depth 层）、防循环引用。

    返回：未找到文件的 xref 名称列表
    """
    if depth > max_depth:  # # 达到最大递归深度
        return list(xref_names)  # # 返回已收集的 xref 名称
    if visited is None:  # # 首次调用初始化 visited 集合
        visited = set()

    unresolved = []
    parent_dir = dwg_path.parent
    # 搜索路径：同目录 → 递归子目录
    search_dirs = [parent_dir]
    try:
        search_dirs.extend(parent_dir.rglob("*"))
    except Exception:
        pass
    # 扁平化：目录在前
    dirs = [d for d in search_dirs if d.is_dir()]
    dirs.sort(key=lambda p: len(str(p)))  # 短路径优先

    for xref_name in xref_names:  # # 遍历当前层的 xref 名称
        if xref_name.upper() in visited:  # # 已访问的 xref 跳过防循环
            continue
        visited.add(xref_name.upper())

        # 在搜索路径中查找 xref 文件
        xref_path = None
        for d in dirs:
            for ext in (".dwg", ".dxf", ".DXF", ".DWG"):
                candidate = d / f"{xref_name}{ext}"
                if candidate.exists():
                    xref_path = candidate
                    break
            if xref_path:
                break

        if xref_path is None:  # # 未找到 xref 外部文件
            logger.warning(f"未找到 xref 文件: {xref_name} (搜索目录: {dirs[:3]}...)")
            unresolved.append(xref_name)
            continue

        # 读取外部参照文件
        try:
            ext = xref_path.suffix.lower()
            if ext == ".dxf":  # # DXF 文件用 ezdxf 读取
                xref_doc = ezdxf.readfile(str(xref_path))
            else:  # # DWG 文件用 ezdwg 尝试读取
                # DWG：尝试 ezdwg 转换
                try:
                    import ezdwg as _ezdwg_xref

                    xref_dwg = _ezdwg_xref.read(str(xref_path))
                    tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
                    tmp_path = tmp.name
                    tmp.close()
                    xref_dwg.export_dxf(tmp_path)
                    xref_doc = ezdxf.readfile(tmp_path)
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    logger.warning(f"读取 xref DWG 文件失败: {xref_path}")
                    unresolved.append(xref_name)
                    continue

            # 提取该文件的 block_defs（含 ANON 匿名块）
            xref_block_defs: Dict[str, Any] = {}
            xref_xref_names = []
            for name, blk in xref_doc.blocks:
                if blk.is_xref:  # # 跳过 xref 自身的引用
                    xref_xref_names.append(name)
                    continue
                entities = list(blk)
                if entities:  # # 有展开的实体
                    # ANON 块：使用原名称（保留匿名标识）
                    key = name.upper()
                    xref_block_defs[key] = entities

            # 合并 block_defs
            for k, v in xref_block_defs.items():  # # 合并块定义
                if k not in block_defs:  # # 不覆盖已有的块定义
                    block_defs[k] = v

            # 递归解析嵌套 xref
            _resolve_xref_external(
                xref_xref_names,
                xref_path,
                dxf_doc,
                block_defs,
                depth=depth + 1,
                max_depth=max_depth,
                visited=visited,
            )

            # 将 xref 文件中的实体复制到主 dxf_doc 的 modelspace
            msp_dst = dxf_doc.modelspace()
            for ent in xref_doc.modelspace():  # # 遍历 xref 文件的所有图元
                dxf_type = ent.dxftype()
                try:
                    color = getattr(ent.dxf, "color", 7) or 7
                    layer = getattr(ent.dxf, "layer", "0") or "0"

                    if dxf_type == "LINE":  # # LINE 类型
                        msp_dst.add_line(
                            (ent.dxf.start[0], ent.dxf.start[1]),
                            (ent.dxf.end[0], ent.dxf.end[1]),
                            dxfattribs={"color": color, "layer": layer},
                        )
                    elif dxf_type == "LWPOLYLINE":  # # LWPOLYLINE 类型
                        pts = [(p[0], p[1]) for p in getattr(ent.dxf, "points", [])]
                        if len(pts) >= 2:  # # 至少 2 个点才构成线段
                            msp_dst.add_lwpolyline(
                                pts, dxfattribs={"color": color, "layer": layer}
                            )
                    elif dxf_type == "CIRCLE":  # # CIRCLE 类型
                        msp_dst.add_circle(
                            (ent.dxf.center[0], ent.dxf.center[1]),
                            ent.dxf.radius,
                            dxfattribs={"color": color, "layer": layer},
                        )
                    elif dxf_type == "ARC":  # # ARC 类型
                        msp_dst.add_arc(
                            (ent.dxf.center[0], ent.dxf.center[1]),
                            ent.dxf.radius,
                            ent.dxf.start_angle,
                            ent.dxf.end_angle,
                            dxfattribs={"color": color, "layer": layer},
                        )
                    elif dxf_type == "INSERT":  # # INSERT 块引用，递归展开
                        ins_pt = getattr(ent.dxf, "insert", (0, 0, 0))
                        name = getattr(ent.dxf, "name", "UNKNOWN")
                        x, y = ins_pt[0], ins_pt[1]
                        scale = (
                            getattr(ent.dxf, "x_scale", getattr(ent.dxf, "y_scale", 1.0)) or 1.0
                        )
                        rotation = getattr(ent.dxf, "rotation", 0.0) or 0.0
                        expanded = False
                        for (
                            blk_name,
                            blk_entities,
                        ) in block_defs.items():  # # 在已有块定义中查找匹配
                            if blk_name.lower() == name.lower():  # # 不区分大小写匹配块名
                                _insert_block_expand(
                                    blk_entities,
                                    msp_dst,
                                    x,
                                    y,
                                    scale,
                                    rotation,
                                    color,
                                    layer,
                                    block_defs=block_defs,
                                    depth=0,
                                    max_depth=5,
                                )
                                expanded = True
                                break
                        if not expanded:  # # 有未展开的 xref
                            half = max(50.0, scale * 20.0)
                            msp_dst.add_lwpolyline(
                                [
                                    (x - half, y - half),
                                    (x + half, y - half),
                                    (x + half, y + half),
                                    (x - half, y + half),
                                    (x - half, y - half),
                                ],
                                dxfattribs={"color": 1, "layer": layer},
                            )
                            msp_dst.add_text(
                                f"XREF:{name}",
                                dxfattribs={
                                    "color": 1,
                                    "height": 100.0,
                                    "insert": (x + half + 10, y),
                                    "layer": layer,
                                },
                            )
                except Exception:
                    pass

            xref_doc.close()
        except Exception:
            unresolved.append(xref_name)

    return unresolved  # # 返回未解析的 xref 列表

def _try_manual_convert(path: Path
) -> Optional[Any]:  # method: def _try_manual_convert(self, path: Path) -> Optional[Any]:
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

            # ── 自动解析外部参照文件 ──
            _resolve_xref_external(xref_names, path, dxf_doc, block_defs)

            xref_doc.close()  # function call
            os.unlink(tmp_xref.name)  # function call
        except Exception:  # catch exception
            pass  # code

        # ── 遍历 modelspace 实体 ──
        msp_src = dwg_doc.modelspace()  # function call
        msp_dst = dxf_doc.modelspace()  # function call

        total = 0  # assignment
        for dxf_type in [
            "LINE",
            "LWPOLYLINE",
            "CIRCLE",
            "ARC",
            "TEXT",
            "MTEXT",  # loop: iterate
            "INSERT",
            "HATCH",
            "SOLID",
            "POINT",
            "ELLIPSE",
            "SPLINE",
        ]:  # code
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
                            d["start"][:2],
                            d["end"][:2],  # code
                            dxfattribs={"color": color, "layer": layer},  # assignment
                        )  # code
                        total += 1  # accumulate
                    elif dxf_type == "LWPOLYLINE":  # elif condition
                        pts = [(p[0], p[1]) for p in d["points"]]  # function call
                        if len(pts) >= 2:  # check: numeric comparison
                            msp_dst.add_lwpolyline(
                                pts, dxfattribs={"color": color, "layer": layer}
                            )  # function call
                            total += 1  # accumulate
                    elif dxf_type == "CIRCLE":  # elif condition
                        msp_dst.add_circle(  # code
                            (d["center"][0], d["center"][1]),
                            d["radius"],  # function call
                            dxfattribs={"color": color, "layer": layer},  # assignment
                        )  # code
                        total += 1  # accumulate
                    elif dxf_type == "ARC":  # elif condition
                        msp_dst.add_arc(  # code
                            (d["center"][0], d["center"][1]),
                            d["radius"],  # function call
                            d["start_angle"],
                            d["end_angle"],  # code
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
                            if (
                                blk_name.lower() == name.lower()
                            ):  # condition: blk_name.lower() == name.lower():
                                _insert_block_expand(  # code
                                    blk_entities,
                                    msp_dst,
                                    x,
                                    y,
                                    scale,
                                    rotation,  # code
                                    color,
                                    layer,  # code
                                    block_defs=block_defs,
                                    depth=0,
                                    max_depth=5,  # assignment
                                )  # code
                                expanded = True  # assignment
                                break  # code
                        if not expanded:  # check: negated condition
                            # 无块定义或解析失败 → 回退到占位框
                            half = max(50.0, scale * 20.0)  # get maximum
                            msp_dst.add_lwpolyline(
                                [  # code
                                    (x - half, y - half),  # function call
                                    (x + half, y - half),  # function call
                                    (x + half, y + half),  # function call
                                    (x - half, y + half),  # function call
                                    (x - half, y - half),  # function call
                                ],
                                dxfattribs={"color": 1, "layer": layer},
                            )  # assignment
                            msp_dst.add_text(  # code
                                f"INSERT:{name}",  # code
                                dxfattribs={  # assignment
                                    "color": 1,
                                    "height": 100.0,  # code
                                    "insert": (x + half + 10, y),
                                    "layer": layer,  # function call
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
                                        dxfattribs={
                                            "color": color,
                                            "layer": layer,
                                        },  # assignment
                                    )  # code
                                    total += 1  # accumulate
                        except Exception:  # catch exception
                            pass  # code
                    elif dxf_type == "SOLID":  # elif condition
                        pts_2d = [
                            (d.get(f"{ax}{i}", 0), d.get(f"{ay}{i}", 0))  # function call
                            for ax, ay, i in [
                                ("x", "y", 0),
                                ("x", "y", 1),  # loop: iterate
                                ("x", "y", 2),
                                ("x", "y", 3),
                            ]
                        ]  # function call
                        if len(pts_2d) >= 3:  # check: numeric comparison
                            msp_dst.add_solid(
                                pts_2d[:4], dxfattribs={"color": color, "layer": layer}
                            )  # function call
                            total += 1  # accumulate
                    elif dxf_type == "POINT":  # elif condition
                        pt = d.get("location", (0, 0, 0))  # function call
                        msp_dst.add_point(
                            (pt[0], pt[1]), dxfattribs={"color": color, "layer": layer}
                        )  # int conversion
                        total += 1  # accumulate
                except Exception:  # catch exception
                    pass  # code

        if total > 10:  # check: numeric comparison
            return dxf_doc  # return
    except Exception:  # catch exception
        pass  # code
    return None  # return: None

def _try_raw_decode(path: Path
) -> Optional[Any]:  # method: def _try_raw_decode(self, path: Path) -> Optional[Any]:
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
                                msp_dst.add_lwpolyline(
                                    pts, dxfattribs={"color": color, "layer": layer}
                                )  # function call
                                total += 1  # accumulate
                        elif dxf_type == "CIRCLE":  # elif condition
                            msp_dst.add_circle(  # code
                                (
                                    row.get("center_x", 0),
                                    row.get("center_y", 0),
                                ),  # function call
                                row.get("radius", 1),  # function call
                                dxfattribs={"color": color, "layer": layer},  # assignment
                            )  # code
                            total += 1  # accumulate
                        elif dxf_type == "ARC":  # elif condition
                            msp_dst.add_arc(  # code
                                (
                                    row.get("center_x", 0),
                                    row.get("center_y", 0),
                                ),  # function call
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
                                    "insert": (
                                        row.get("insert_x", 0),
                                        row.get("insert_y", 0),
                                    ),  # function call
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
                                    "insert": (
                                        row.get("insert_x", 0),
                                        row.get("insert_y", 0),
                                    ),  # function call
                                    "layer": layer,  # code
                                },  # code
                            )  # code
                            total += 1  # accumulate
                        elif dxf_type == "INSERT":  # elif condition
                            ins_x = row.get("insert_x", 0)  # function call
                            ins_y = row.get("insert_y", 0)  # function call
                            name = row.get("block_name", "UNKNOWN")  # function call
                            half = 50.0  # assignment
                            msp_dst.add_lwpolyline(
                                [  # code
                                    (ins_x - half, ins_y - half),  # function call
                                    (ins_x + half, ins_y - half),  # function call
                                    (ins_x + half, ins_y + half),  # function call
                                    (ins_x - half, ins_y + half),  # function call
                                    (ins_x - half, ins_y - half),  # function call
                                ],
                                dxfattribs={"color": 1, "layer": layer},
                            )  # assignment
                            msp_dst.add_text(  # code
                                name,  # code
                                dxfattribs={
                                    "color": 1,
                                    "height": 100.0,  # assignment
                                    "insert": (ins_x + half + 10, ins_y),
                                    "layer": layer,
                                },  # function call
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
    dxf_result = _try_same_dir_dxf(path)  # function call
    if dxf_result is not None:  # check: value is not None
        return dxf_result  # return

    # ── 第 1 级：aspose-cad 转换（最可靠，支持 T3） ──
    result = _try_aspose_cad_convert(path)  # function call
    if result is not None:  # check: value is not None
        return result  # return

    # ── 第 2 级：export_dxf 直转 ──
    result = _try_ezdwg_export_dxf(path)  # function call
    if result is not None:  # check: value is not None
        return result  # return

    # ── 第 3 级：LibreCAD CLI 转换 ──
    result = _try_librecad_convert(path)  # function call
    if result is not None:  # check: value is not None
        return result  # return

    # ── 第 4 级：手动逐元素转换 ──
    result = _try_manual_convert(path)  # function call
    if result is not None:  # check: value is not None
        return result  # return

    # ── 第 5 级：raw 逐个类型解码 ──
    result = _try_raw_decode(path)  # function call
    if result is not None:  # check: value is not None
        return result  # return

    # ── 第 5 级：所有方案都失败 ──
    return None  # return: None

def _insert_block_expand(
    block_entities,
    msp_dst,
    base_x,
    base_y,  # method: def _insert_block_expand(self, block_entities, msp_dst, base
    scale,
    rotation,
    color,
    layer,  # code
    block_defs=None,
    depth=0,
    max_depth=5,
):  # assignment
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
                ent_color = (
                    getattr(ent.dxf, "color", color) if hasattr(ent.dxf, "color") else color
                )  # attribute check
                ent_layer = (
                    getattr(ent.dxf, "layer", layer) if hasattr(ent.dxf, "layer") else layer
                )  # attribute check
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
                            if (
                                blk_name.lower() == name.lower()
                            ):  # condition: blk_name.lower() == name.lower():
                                _insert_block_expand(  # code
                                    blk_entities,
                                    msp_dst,
                                    ins_x,
                                    ins_y,  # code
                                    ins_scale * scale,
                                    ins_rot + rotation,  # code
                                    ent_color,
                                    ent_layer,  # code
                                    block_defs=block_defs,
                                    depth=depth + 1,
                                    max_depth=max_depth,  # assignment
                                )  # code
                                break  # code
                    continue  # code
                elif dxf_type == "LINE":  # elif condition
                    start = transform_point(
                        (ent.dxf.start[0], ent.dxf.start[1])
                    )  # int conversion
                    end = transform_point((ent.dxf.end[0], ent.dxf.end[1]))  # int conversion
                    msp_dst.add_line(
                        start, end, dxfattribs={"color": ent_color, "layer": ent_layer}
                    )  # function call
                elif dxf_type == "LWPOLYLINE":  # elif condition
                    pts = [
                        transform_point((p[0], p[1])) for p in getattr(ent.dxf, "points", [])
                    ]  # get attribute
                    if len(pts) >= 2:  # check: numeric comparison
                        msp_dst.add_lwpolyline(
                            pts, dxfattribs={"color": ent_color, "layer": ent_layer}
                        )  # function call
                elif dxf_type == "CIRCLE":  # elif condition
                    center = transform_point(
                        (ent.dxf.center[0], ent.dxf.center[1])
                    )  # int conversion
                    radius = ent.dxf.radius * scale  # assignment
                    msp_dst.add_circle(
                        center, radius, dxfattribs={"color": ent_color, "layer": ent_layer}
                    )  # function call
                elif dxf_type == "ARC":  # elif condition
                    center = transform_point(
                        (ent.dxf.center[0], ent.dxf.center[1])
                    )  # int conversion
                    radius = ent.dxf.radius * scale  # assignment
                    start_a = ent.dxf.start_angle + rotation  # assignment
                    end_a = ent.dxf.end_angle + rotation  # assignment
                    msp_dst.add_arc(
                        center,
                        radius,
                        start_a,
                        end_a,
                        dxfattribs={"color": ent_color, "layer": ent_layer},
                    )  # function call
                elif dxf_type in ("TEXT", "MTEXT"):  # elif condition
                    ins = getattr(ent.dxf, "insert", (0, 0, 0))  # get attribute
                    new_ins = transform_point((ins[0], ins[1]))  # int conversion
                    height = (getattr(ent.dxf, "height", 2.5) or 2.5) * scale  # get attribute
                    msp_dst.add_text(
                        getattr(ent.dxf, "text", ""),  # get attribute
                        dxfattribs={
                            "color": ent_color,
                            "height": height,  # assignment
                            "insert": new_ins,
                            "layer": ent_layer,
                        },
                    )  # code
                elif dxf_type == "SOLID":  # elif condition
                    pts_2d = [
                        (
                            getattr(ent.dxf, f"{ax}{i}", 0),
                            getattr(ent.dxf, f"{ay}{i}", 0),
                        )  # get attribute
                        for ax, ay, i in [
                            ("x", "y", 0),
                            ("x", "y", 1),
                            ("x", "y", 2),
                            ("x", "y", 3),
                        ]
                    ]  # loop: iterate
                    new_pts = [transform_point(p) for p in pts_2d]  # int conversion
                    if len(new_pts) >= 3:  # check: numeric comparison
                        msp_dst.add_solid(
                            new_pts[:4], dxfattribs={"color": ent_color, "layer": ent_layer}
                        )  # function call
                elif dxf_type == "POINT":  # elif condition
                    loc = getattr(ent.dxf, "location", (0, 0, 0))  # get attribute
                    new_loc = transform_point((loc[0], loc[1]))  # int conversion
                    msp_dst.add_point(
                        new_loc, dxfattribs={"color": ent_color, "layer": ent_layer}
                    )  # int conversion
                elif dxf_type == "ELLIPSE":  # elif condition
                    center = transform_point(
                        (
                            getattr(ent.dxf, "center", (0, 0, 0))[0],
                            getattr(ent.dxf, "center", (0, 0, 0))[1],
                        )
                    )  # int conversion
                    major_axis = (
                        getattr(ent.dxf, "major_axis", (0, 0, 0))[0],
                        getattr(ent.dxf, "major_axis", (0, 0, 0))[1],
                    )  # get attribute
                    new_major = transform_point(major_axis)
                    axis_ratio = getattr(ent.dxf, "axis_ratio", 1.0)
                    import math as _math  # stdlib: math

                    # 从 major_axis 计算长轴半径
                    mx = new_major[0] - center[0]
                    my = new_major[1] - center[1]
                    major_r = max(1.0, math.hypot(mx, my))
                    major_r *= scale
                    minor_r = major_r * axis_ratio * scale
                    msp_dst.add_ellipse(
                        center,
                        major_r,
                        minor_r,
                        dxfattribs={"color": ent_color, "layer": ent_layer},
                    )
                elif dxf_type == "SPLINE":  # elif condition
                    # SPLINE：用 CONTROL_POINTS 展开
                    cps = getattr(ent.dxf, "control_points", [])
                    if cps:
                        new_cps = [transform_point((p[0], p[1])) for p in cps]
                        msp_dst.add_spline(
                            control_points=new_cps,
                            dxfattribs={"color": ent_color, "layer": ent_layer},
                        )
            except Exception:  # catch exception
                pass  # 单个实体展开失败不影响其他实体
    except Exception:  # catch exception
        pass  # code
