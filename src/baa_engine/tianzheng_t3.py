"""
P127 天正 T3 降级管线 — 主模块

天正（TArch）T3 加密格式无法被 ezdxf 直接解析。
本模块在 DrawingParser 解析能力之上做「图层规则 → 构件分类 → 汇总」降级管线，
输出结构化构件清单（wall / door / window / column / axis / dimension）。

三层降级策略：
  L1 图层名精确/模糊匹配（最强信号）
  L2 DXF 实体类型 + 几何特征推断（弱信号）
  L3 默认归入未分类（兜底）
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── 构件分类常量 ──────────────────────────────────────────────────────

C_WALL = "wall"
C_DOOR = "door"
C_WINDOW = "window"
C_COLUMN = "column"
C_AXIS = "axis"
C_DIMENSION = "dimension"
C_TEXT = "text"
C_UNSPECIFIED = "unspecified"

KNOWN_COMPONENT_TYPES = (
    C_WALL,
    C_DOOR,
    C_WINDOW,
    C_COLUMN,
    C_AXIS,
    C_DIMENSION,
    C_TEXT,
)


# ── 图层规则表（L1 精确匹配 + 关键字模糊匹配） ───────────────────────

# 精确匹配：图层名 → (component_type, 基础置信度)
_LAYER_EXACT_RULES: Dict[str, Tuple[str, float]] = {
    # 墙体
    "WALL": (C_WALL, 0.95),
    "WALL-1": (C_WALL, 0.92),
    "WALL-2": (C_WALL, 0.92),
    "A-WALL": (C_WALL, 0.95),
    "WALLS": (C_WALL, 0.90),
    # 门窗
    "DOOR": (C_DOOR, 0.95),
    "DOOR-OPEN": (C_DOOR, 0.90),
    "DOOR-CLOSED": (C_DOOR, 0.90),
    "WINDOW": (C_WINDOW, 0.95),
    "WINDOW-OPEN": (C_WINDOW, 0.90),
    # 柱
    "COLUMN": (C_COLUMN, 0.95),
    "COLUMNS": (C_COLUMN, 0.90),
    "A-COLUMN": (C_COLUMN, 0.95),
    "STRUCT-COL": (C_COLUMN, 0.92),
    # 轴
    "AXIS": (C_AXIS, 0.95),
    "A-AXIS": (C_AXIS, 0.95),
    "GRID": (C_AXIS, 0.90),
    # 标注
    "DIM": (C_DIMENSION, 0.95),
    "DIMENSION": (C_DIMENSION, 0.95),
    "A-DIM": (C_DIMENSION, 0.92),
    # 文字
    "TEXT": (C_TEXT, 0.90),
    "A-TEXT": (C_TEXT, 0.90),
}

# 关键字模糊匹配：图层名包含关键字 → (component_type, 置信度)
_LAYER_KEYWORD_RULES: List[Tuple[str, str, float]] = [
    ("wall", C_WALL, 0.80),
    ("墙体", C_WALL, 0.80),
    ("door", C_DOOR, 0.80),
    ("门", C_DOOR, 0.80),
    ("window", C_WINDOW, 0.80),
    ("窗", C_WINDOW, 0.80),
    ("column", C_COLUMN, 0.80),
    ("柱", C_COLUMN, 0.80),
    ("axis", C_AXIS, 0.80),
    ("轴", C_AXIS, 0.80),
    ("dim", C_DIMENSION, 0.75),
    ("标注", C_DIMENSION, 0.75),
]


def classify_layer(layer: str) -> Tuple[Optional[str], float]:
    """
    L1 图层名分类：精确匹配优先，其次关键字模糊匹配。

    Returns:
        (component_type, confidence)；未命中返回 (None, 0.0)
    """
    if not layer:
        return None, 0.0

    key = layer.strip().upper()
    if key in _LAYER_EXACT_RULES:
        ctype, conf = _LAYER_EXACT_RULES[key]
        return ctype, conf

    lower = layer.strip().lower()
    for keyword, ctype, conf in _LAYER_KEYWORD_RULES:
        if keyword in lower:
            return ctype, conf
    return None, 0.0


# ── 几何推断（L2） ─────────────────────────────────────────────────────


def infer_by_geometry(dxf_type: str, bbox: Dict[str, float]) -> Tuple[Optional[str], float]:
    """
    L2 实体类型 + 几何特征推断。仅在 L1 未命中时调用。
    """
    t = (dxf_type or "").upper()
    w = bbox.get("width", 0.0) if bbox else 0.0
    h = bbox.get("height", 0.0) if bbox else 0.0

    # DIMENSION 类型直接归类
    if t == "DIMENSION":
        return C_DIMENSION, 0.85

    # 极长矩形 → 墙体候选
    if t in ("LWPOLYLINE", "POLYLINE", "LINE", "SOLID", "HATCH"):
        long_axis = max(w, h)
        short_axis = min(w, h) if min(w, h) > 0 else 1e-9
        aspect = long_axis / short_axis if short_axis > 0 else 0
        # 墙体：长宽比 > 10，且宽度在 60~800mm 之间
        if aspect > 10 and 60.0 <= min(w, h) <= 800.0:
            return C_WALL, 0.55

    # 门：LWPOLYLINE + 适中尺寸
    if t == "LWPOLYLINE" and 400.0 <= w <= 1500.0 and 400.0 <= h <= 1000.0:
        return C_DOOR, 0.50

    # 窗：LWPOLYLINE + 较大尺寸
    if t == "LWPOLYLINE" and 600.0 <= w <= 3000.0 and 400.0 <= h <= 2500.0:
        return C_WINDOW, 0.50

    # CIRCLE + 小半径 → 柱
    if t == "CIRCLE":
        r = bbox.get("width", 0.0) / 2.0
        if 100.0 <= r <= 600.0:
            return C_COLUMN, 0.50

    # TEXT
    if t in ("TEXT", "MTEXT"):
        return C_TEXT, 0.70

    return None, 0.0


# ── 构件数据结构 ───────────────────────────────────────────────────────


@dataclass
class Component:
    """单条构件记录"""

    dxf_type: str
    layer: str
    handle: str
    bbox: Dict[str, float]
    properties: Dict[str, Any]
    component_type: str
    confidence: float
    evidence: str  # layer_exact / layer_keyword / geometry / unspecified

    def to_dict(self) -> dict:
        return {
            "dxf_type": self.dxf_type,
            "layer": self.layer,
            "handle": self.handle,
            "bbox": self.bbox,
            "properties": self.properties,
            "component_type": self.component_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


# ── 汇总 ───────────────────────────────────────────────────────────────


def build_summary(components: List[Component]) -> dict:
    """
    构建构件汇总：total / by_type / avg_confidence / by_evidence
    """
    by_type: Dict[str, int] = {}
    by_evidence: Dict[str, int] = {}
    total_conf = 0.0
    total = len(components)

    for c in components:
        by_type[c.component_type] = by_type.get(c.component_type, 0) + 1
        by_evidence[c.evidence] = by_evidence.get(c.evidence, 0) + 1
        total_conf += c.confidence

    avg_conf = total_conf / total if total else 0.0

    # 确保主要类型都在输出中（即使为 0）
    for ctype in KNOWN_COMPONENT_TYPES + (C_UNSPECIFIED,):
        by_type.setdefault(ctype, 0)

    return {
        "total": total,
        "by_type": by_type,
        "by_evidence": by_evidence,
        "avg_confidence": round(avg_conf, 4),
    }


# ── 主管线 ─────────────────────────────────────────────────────────────


class TianzhengT3:
    """
    天正 T3 降级管线

    使用方式:
        tz = TianzhengT3(verbose=False)
        components = tz.scan("path/to/drawing.dxf")
        summary = build_summary(components)
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._parser = None
        self._cache: Dict[str, List[Component]] = {}

    @property
    def parser(self):
        """延迟加载 DrawingParser（避免测试时依赖完整依赖链）"""
        if self._parser is None:
            try:
                from src.baa_engine.drawing_parser import DrawingParser

                self._parser = DrawingParser()
            except Exception as e:  # pragma: no cover
                logger.error("[P127] DrawingParser 加载失败: %s", e)
                raise
        return self._parser

    def classify_entity(
        self,
        dxf_type: str,
        layer: str,
        bbox: Dict[str, float],
    ) -> Tuple[str, float, str]:
        """
        三层降级分类单实体。

        Returns:
            (component_type, confidence, evidence)
        """
        # L1: 图层精确匹配
        layer_type, layer_conf = classify_layer(layer)
        if layer_type and layer_conf >= 0.90:
            return layer_type, layer_conf, "layer_exact"

        # L1: 图层关键字匹配
        if layer_type and layer_conf > 0:
            return layer_type, layer_conf, "layer_keyword"

        # L2: 几何推断
        geo_type, geo_conf = infer_by_geometry(dxf_type, bbox)
        if geo_type and geo_conf > 0.45:
            return geo_type, geo_conf, "geometry"

        # L3: 未分类
        return C_UNSPECIFIED, 0.10, "unspecified"

    def scan(
        self,
        dxf_path: str,
        file_id: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[Component]:
        """
        扫描单张图纸，返回构件列表。
        """
        dxf_path = str(dxf_path)

        if use_cache and dxf_path in self._cache:
            return self._cache[dxf_path]

        if self.verbose:
            print(f"[P127] 解析: {dxf_path}")

        result = self.parser.parse(dxf_path, file_id=file_id)

        if getattr(result, "error", None):
            logger.warning("[P127] 解析错误 %s: %s", dxf_path, result.error)

        components: List[Component] = []
        primitives = getattr(result, "primitives", None) or []

        for prim in primitives:
            dxf_type = getattr(prim, "dxf_type", "") or ""
            layer = getattr(prim, "layer", "") or ""
            handle = getattr(prim, "handle", "") or ""
            bbox = getattr(prim, "bbox", {}) or {}
            props = getattr(prim, "properties", {}) or {}

            ctype, conf, evidence = self.classify_entity(dxf_type, layer, bbox)

            components.append(
                Component(
                    dxf_type=dxf_type,
                    layer=layer,
                    handle=handle,
                    bbox=bbox,
                    properties=props,
                    component_type=ctype,
                    confidence=conf,
                    evidence=evidence,
                )
            )

        # 标注维度单独收集
        dimensions = getattr(result, "dimensions", None) or []
        for dim in dimensions:
            if not isinstance(dim, dict):
                continue
            bbox = dim.get("bbox", {})
            layer = dim.get("layer", "")
            ctype, conf, evidence = self.classify_entity("DIMENSION", layer, bbox)
            components.append(
                Component(
                    dxf_type="DIMENSION",
                    layer=layer,
                    handle=dim.get("handle", ""),
                    bbox=bbox,
                    properties=dim,
                    component_type=ctype,
                    confidence=conf,
                    evidence=evidence,
                )
            )

        if use_cache:
            self._cache[dxf_path] = components

        if self.verbose:
            s = build_summary(components)
            print(f"[P127] {Path(dxf_path).name}: 总构件={s['total']}, 平均置信度={s['avg_confidence']}")

        return components

    def scan_batch(
        self,
        data_dir: str,
        pattern: str = "*_t3.dxf",
        use_cache: bool = True,
    ) -> List[dict]:
        """
        批量扫描目录下的 T3 图纸。
        """
        data_path = Path(data_dir)
        files = sorted(data_path.glob(pattern))
        if not files:
            logger.warning("[P127] 未找到匹配文件: %s / %s", data_dir, pattern)
            return []

        results = []
        for f in files:
            components = self.scan(str(f), use_cache=use_cache)
            summary = build_summary(components)
            summary["file"] = f.name
            summary["components"] = [c.to_dict() for c in components]
            results.append(summary)
        return results

    def clear_cache(self) -> None:
        self._cache.clear()
