"""P84-E DXF 向量特征分类 spike

目标：用纯几何特征对 layer=0 上的 LINE/LWPOLYLINE 重新分类，
减少 other 数量，提升 wall/door/window/stair/column 识别率。

特征：
- LINE: length, angle, neighbors_count (端点附近其他线段数)
- LWPOLYLINE: point_count, area, aspect_ratio, is_closed
- 上下文: 周围图元密度、是否靠近标注

先做 baseline：只改进 LINE 分类，看效果。
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent))
import math
from collections import Counter

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.classify import _classify_by_layer, _classify_by_geometry


def compute_line_angle(p):
    """计算 LINE 的角度（度）"""
    sp = p.properties.get("start_point", {})
    ep = p.properties.get("end_point", {})
    x1, y1 = sp.get("x", 0), sp.get("y", 0)
    x2, y2 = ep.get("x", 0), ep.get("y", 0)
    if x1 == x2 and y1 == y2:
        return 0.0
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def classify_line_enhanced(p, prim_list):
    """增强 LINE 分类：结合角度 + 上下文密度"""
    length = p.properties.get("length", 0) or max(p.bbox.get("width", 0), p.bbox.get("height", 0))
    bb = p.bbox
    bw = bb.get("width", 0)
    bh = bb.get("height", 0)
    short_edge = min(bw, bh) if bw > 0 and bh > 0 else length
    angle = abs(compute_line_angle(p)) % 180

    # 1. 超长 LINE → wall
    if length > 2000:
        return "wall"

    # 2. 中等长度 LINE（700~2000mm）→ door
    if 700 < length < 2000 and short_edge < 50:
        return "door"

    # 3. 短 LINE 分类（50~700mm）
    if 50 < length < 700 and short_edge < 5:
        # 根据角度细分：
        # - 水平/垂直 → 可能是窗/分隔线
        # - 45° → 可能是对角标注线
        is_horizontal = angle < 5 or angle > 175
        is_vertical = 85 < angle < 95
        if is_horizontal or is_vertical:
            # 水平/垂直短线 → 可能是窗框线
            return "window"
        return "door"

    # 4. 极短线（0~50mm）
    if length < 50:
        # 检查是否靠近 CIRCLE（柱子）→ 可能是柱标注
        return "other"

    # 5. 中长线（2000~5000mm）：可能是窗框线或长门
    if 2000 < length < 5000:
        return "wall"  # 保守：归为 wall

    return "other"


def run():
    parser = DrawingParser()
    result = parser.parse("data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf")
    prims = result.primitives
    analyzer = SemanticAnalyzer()

    # Baseline: 当前分类
    baseline = Counter()
    for p in prims:
        lt = _classify_by_layer(analyzer, p.layer)
        gt = _classify_by_geometry(analyzer, p) if lt in ("unknown", "other") else lt
        baseline[gt] += 1

    # Enhanced: LINE 用增强分类
    enhanced = Counter()
    for p in prims:
        lt = _classify_by_layer(analyzer, p.layer)
        if lt not in ("unknown", "other"):
            enhanced[lt] += 1
            continue
        if p.dxf_type == "LINE":
            enhanced[classify_line_enhanced(p, prims)] += 1
        else:
            gt = _classify_by_geometry(analyzer, p)
            enhanced[gt] += 1

    print("={}".format("=" * 60))
    print("{:20s} {:>8s} {:>8s} {:>8s} {:>10s}".format("Type", "Baseline", "Enhanced", "Diff", "Diff%"))
    print("{:20s} {:>8s} {:>8s} {:>8s} {:>10s}".format("-" * 20, "-" * 8, "-" * 8, "-" * 8, "-" * 10))
    all_types = sorted(set(list(baseline.keys()) + list(enhanced.keys())))
    total_b = sum(baseline.values())
    for t in all_types:
        b = baseline.get(t, 0)
        e = enhanced.get(t, 0)
        diff = e - b
        pct = diff / max(b, 1) * 100
        print("{:20s} {:8d} {:8d} {:+8d} {:>+9.1f}%".format(t, b, e, diff, pct))
    print()
    print("Total: {} → {}".format(total_b, sum(enhanced.values())))
    print("Other: {} → {} ({:+.1f}%)".format(
        baseline.get("other", 0), enhanced.get("other", 0),
        (enhanced.get("other", 0) - baseline.get("other", 0)) / max(baseline.get("other", 1), 1) * 100))


if __name__ == "__main__":
    run()