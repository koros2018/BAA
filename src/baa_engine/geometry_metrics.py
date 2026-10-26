"""T-C8 几何一致性度量：源矩形 vs 导出矩形 的 2D Hausdorff 距离（mm）。

口径：对两组足迹矩形的边界均匀采样（含角点），计算对称 Hausdorff——
max(源每点到目标集最近距离, 目标每点到源集最近距离)。
矩形完全一致时为 0；容差 2mm 用于吸收单位换算/浮点噪声。
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Rect = Tuple[float, float, float, float]

_SAMPLE_STEP_MM = 50.0


def _sample_rect(rect: Rect, step: float = _SAMPLE_STEP_MM) -> List[Tuple[float, float]]:
    x0, y0, x1, y1 = rect
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(length / step))
        for i in range(1, n):
            t = i / n
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return pts


def _min_dist(p, point_set) -> float:
    return min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in point_set)


def hausdorff_2d(rects_a: Sequence[Rect], rects_b: Sequence[Rect]) -> float:
    """两组矩形边界的对称 Hausdorff 距离（mm）。任一侧为空返回 inf。"""
    if not rects_a or not rects_b:
        return math.inf
    pts_a = [p for r in rects_a for p in _sample_rect(r)]
    pts_b = [p for r in rects_b for p in _sample_rect(r)]
    return max(
        max(_min_dist(p, pts_b) for p in pts_a),
        max(_min_dist(p, pts_a) for p in pts_b),
    )
