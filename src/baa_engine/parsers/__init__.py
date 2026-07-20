"""
解析子模块包 — 从 drawing_parser.py 拆分

- dwg_convert.py: DWG 转换（10个方法，~968行 → 独立模块）
- geometry.py: 几何计算（compute_bbox, extract_properties, compute_polygon_area, transform_point）
"""

from .dwg_convert import (
    _detect_dwg_format,
    _try_same_dir_dxf,
    _names_match,
    _try_librecad_convert,
    _try_aspose_cad_convert,
    _try_ezdwg_export_dxf,
    _resolve_xref_external,
    _try_manual_convert,
    _try_raw_decode,
    _parse_dwg,
    _insert_block_expand,
)
from .geometry import (
    compute_bbox,
    extract_properties,
    compute_polygon_area,
    transform_point,
)

__all__ = [
    # DWG
    "_detect_dwg_format",
    "_try_same_dir_dxf",
    "_names_match",
    "_try_librecad_convert",
    "_try_aspose_cad_convert",
    "_try_ezdwg_export_dxf",
    "_resolve_xref_external",
    "_try_manual_convert",
    "_try_raw_decode",
    "_parse_dwg",
    "_insert_block_expand",
    # geometry
    "compute_bbox",
    "extract_properties",
    "compute_polygon_area",
    "transform_point",
]
