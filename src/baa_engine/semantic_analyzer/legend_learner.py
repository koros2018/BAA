"""图例学习器（阶段 B M4 · 残留缺口根治第一步）。

M1–M3 分类治理后，剩余 wall 缺失主体是 `0` 等默认图层上的未识别块
（k300 / AVE_RENDER / GHJKBVV 等无判别信号块名）。真实图纸的图例表
呈现「符号块 + 邻近名称 TEXT」的水平行结构，本模块在分类前预扫描
 primitives，从该结构学习 block_name → entity_type 映射，供
classify.py 的 INSERT 分支在兜底前查表。

规则（宁缺勿错，与既有链路一致）：
- 行对齐：TEXT 与 INSERT 垂直距离 ≤ _ROW_DY_MM 且水平距离 ≤ _ROW_DX_MM
  视为同一图例行（比半径圈定绑定度更高，抽样实测 60-72% → 行对齐提纯）。
- TEXT 类型判定复用 legend_rules.LEGEND_RULES（高价值词条，含消防/
  电气/门窗），首个命中即用。
- 仲裁：同块名共现多个词条时取最高频；样本 ≥ _MIN_SAMPLES 且
  最高频占比 ≥ _MIN_CONFIDENCE 才学习。
- 学习结果仅本图生效（main.py 每次分析重置），不做跨图库共享，
  防止个别图纸的非常规图例污染全局。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from typing import Dict, List

from .legend_rules import LEGEND_RULES
from .models import SemanticEntity  # noqa: F401  (类型一致性，暂未直接使用)

# 图例行对齐阈值（mm）
_ROW_DY_MM = 500.0
_ROW_DX_MM = 8000.0
# 学习仲裁阈值
# - 单一类型（无竞争）：图例行结构本身即强信号，共现 ≥1 即学习
# - 多类型竞争：样本 ≥ _MIN_SAMPLES 且最高频占比 ≥ _MIN_CONFIDENCE
_MIN_SAMPLES = 2
_MIN_CONFIDENCE = 0.6


def _legend_type_of_text(text: str) -> str | None:
    """TEXT 文本命中图例词条即返回类型（首个命中）。"""
    if not text:
        return None
    upper = text.upper()
    for keyword, entity_type in LEGEND_RULES:
        if keyword in upper or keyword in text:
            return entity_type
    return None


def _insert_center(props: dict, bbox: dict) -> tuple:
    """INSERT 中心坐标：优先插入点属性，回退 bbox 中心。"""
    x = props.get("insert_x")
    y = props.get("insert_y")
    if x is not None and y is not None:
        try:
            return float(x), float(y)
        except (TypeError, ValueError):
            pass
    return (
        float(bbox.get("x", 0) or 0) + float(bbox.get("width", 0) or 0) / 2,
        float(bbox.get("y", 0) or 0) + float(bbox.get("height", 0) or 0) / 2,
    )


def _text_center(bbox: dict) -> tuple:
    return (
        float(bbox.get("x", 0) or 0) + float(bbox.get("width", 0) or 0) / 2,
        float(bbox.get("y", 0) or 0) + float(bbox.get("height", 0) or 0) / 2,
    )


def _learn_legend_blocks(primitives: List) -> Dict[str, str]:
    """从「符号块 + 邻近图例 TEXT」行结构学习块名映射。

    返回 {block_name: entity_type}；无可学习样本返回空表。
    """
    inserts: List[tuple] = []  # (cx, cy, block_name)
    texts: List[tuple] = []  # (cx, cy, entity_type)
    for p in primitives:
        dxf = getattr(p, "dxf_type", "")
        if dxf == "INSERT":
            props = getattr(p, "properties", {}) or {}
            name = str(props.get("block_name", "") or "")
            if name:
                inserts.append((*_insert_center(props, getattr(p, "bbox", {}) or {}), name))
        elif dxf == "TEXT":
            props = getattr(p, "properties", {}) or {}
            t = str(props.get("text", "") or "")
            etype = _legend_type_of_text(t)
            if etype:
                texts.append((*_text_center(getattr(p, "bbox", {}) or {}), etype))

    # 共现计数（O(I·logI + T·k) 二分行带检索，大图防 O(T×I) 超时）：
    # block_name -> {entity_type: n}
    co: Dict[str, Counter] = defaultdict(Counter)
    inserts.sort(key=lambda t: t[1])
    ys = [by for _bx, by, _bn in inserts]
    for tx, ty, etype in texts:
        lo = bisect_left(ys, ty - _ROW_DY_MM)
        hi = bisect_right(ys, ty + _ROW_DY_MM)
        for bx, by, name in inserts[lo:hi]:
            if abs(bx - tx) <= _ROW_DX_MM:
                co[name][etype] += 1

    learned: Dict[str, str] = {}
    for name, counter in co.items():
        total = sum(counter.values())
        ((top_type, top_n),) = counter.most_common(1)
        if len(counter) == 1:
            # 单一类型无竞争：图例行「符号+名称」结构本身即强证据
            learned[name] = top_type
        elif total >= _MIN_SAMPLES and top_n / total >= _MIN_CONFIDENCE:
            learned[name] = top_type
    return learned
