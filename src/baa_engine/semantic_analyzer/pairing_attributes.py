"""拓扑配对补齐（Roadmap v4 阶段 B / T-A4 标准①收口，Step 3.8）。

M1（当前范围）：双线墙厚度配对。
普通 CAD 图纸的墙体以两条平行线元表达（双线墙惯例），线元 bbox 退化、
厚度缺失（T-A4 252 张实测：wall 缺失 28850，占 dimable 缺口 70.8%）。
厚度是「两条平行线的间距」——图元间对偶量，单图元视角（T-A4 尺寸/TEXT/
native/几何四条链路）无法获得，必须配对推断。

算法（延续宁缺勿错）：
1. 候选：墙族 + bbox 退化线元（短边 ≤1mm 即轴对齐水平/垂直线）+
   图层非标注类（DIM/AXIS/TEXT 等黑名单）。
2. 同向平行对：垂直间距 ∈ [100, 600]mm（覆盖常见墙厚量级），
   纵向投影重叠率 ≥50%（按较短线段归一）。
3. 逐线仲裁：候选按间距聚类（5mm 容差），组得分 =（命中常见墙厚表，
   最高重叠率）；唯一最优组 → 注入 width=组内平均间距；组间并列 →
   放弃（宁缺勿错）。间距聚类使「整墙线 + 开洞分段线」的多候选
   （同间距）仍可命中，只有间距真歧义（如三线 200/300 竞争）才放弃。
4. 不覆盖既有非零值；写 ``_attribute_source = "paired_wall_thickness"``。

窗/门洞口与梯段配对（方案 §3.2/3.3）在 M2 扩展本模块；
对偶边（线对 + 间距）为 T-B1 拓扑建图预留。
"""

from typing import Dict, List, Optional

from .geometry_attributes import _to_meters_small
from .models import SemanticEntity
from .text_attributes import (
    _THICKNESS_MAX_M,
    _THICKNESS_MIN_M,
    _inject_attr,
)

# ── 目标实体类型（墙族）─────────────────────────────────
_WALL_TYPES = {"wall", "shear_wall", "fire_wall", "exterior_wall"}

# ── 配对阈值 ────────────────────────────────────────────
_THICKNESS_MIN_MM = 100.0  # 平行线间距下限（mm）
_THICKNESS_MAX_MM = 600.0  # 平行线间距上限（mm）
_OVERLAP_MIN = 0.5  # 纵向投影重叠率下限（按较短线段归一）
_DEGENERATE_MM = 1.0  # bbox 短边 ≤1mm 视为退化线元
_DIST_GROUP_TOL_MM = 5.0  # 候选间距聚类容差（同组视为同一对墙面）
_COMMON_TOL_MM = 5.0  # 常见墙厚表命中容差
# 常见墙厚表（mm）：仲裁加分项，非硬门槛——唯一候选组不在表内同样注入
_COMMON_THICKNESS_MM = (
    100, 120, 140, 150, 180, 200, 220, 240, 250, 280,
    300, 350, 370, 400, 450, 500, 600,
)

# 标注类图层黑名单（轴网/尺寸/文字线不应参与墙体配对）
_EXCLUDE_LAYER_TOKENS = ("DIM", "AXIS", "TEXT", "标注", "轴线", "辅助")


class _Line:
    """退化线元的轴对齐抽象：axis=v/h，cross=横向坐标，lo/hi=纵向区间。"""

    __slots__ = ("ent", "axis", "cross", "lo", "hi")

    def __init__(self, ent, axis, cross, lo, hi):
        self.ent = ent
        self.axis = axis
        self.cross = cross
        self.lo = lo
        self.hi = hi


def _is_excluded_layer(layer) -> bool:
    """标注类图层（轴网/尺寸/文字）不参与配对。"""
    if not layer:
        return False
    lu = str(layer).upper()
    return any(tok in lu for tok in _EXCLUDE_LAYER_TOKENS)


def _degenerate_line(ent: SemanticEntity) -> Optional[_Line]:
    """bbox 退化（短边 ≤1mm）的轴对齐线元 → _Line；其余返回 None。"""
    bbox = ent.bbox or {}
    try:
        x = float(bbox.get("x") or 0)
        y = float(bbox.get("y") or 0)
        w = float(bbox.get("width") or 0)
        h = float(bbox.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if x != x or y != y or w != w or h != h:  # NaN 防御
        return None
    if w <= _DEGENERATE_MM and h > _DEGENERATE_MM:
        return _Line(ent, "v", x + w / 2.0, y, y + h)
    if h <= _DEGENERATE_MM and w > _DEGENERATE_MM:
        return _Line(ent, "h", y + h / 2.0, x, x + w)
    return None


def _overlap_rate(a: _Line, b: _Line) -> float:
    """纵向投影重叠率（按较短线段归一）；无重叠/零长返回 0。"""
    ov = min(a.hi, b.hi) - max(a.lo, b.lo)
    if ov <= 0:
        return 0.0
    shorter = min(a.hi - a.lo, b.hi - b.lo)
    if shorter <= 0:
        return 0.0
    return ov / shorter


def _arbitrate(cands: List) -> Optional[float]:
    """候选 [(间距mm, 重叠率)] 按间距聚类仲裁，返回组内平均间距或 None。

    组得分 =（命中常见墙厚表, 最高重叠率）；最高分组并列 → 放弃。
    """
    if not cands:
        return None
    groups = []  # {anchor, dists, max_ov}
    for d, ov in sorted(cands):
        for g in groups:
            if abs(d - g["anchor"]) <= _DIST_GROUP_TOL_MM:
                g["dists"].append(d)
                g["max_ov"] = max(g["max_ov"], ov)
                break
        else:
            groups.append({"anchor": d, "dists": [d], "max_ov": ov})
    scored = [
        (
            (
                1 if any(abs(d - t) <= _COMMON_TOL_MM for t in _COMMON_THICKNESS_MM) else 0,
                g["max_ov"],
            ),
            sum(g["dists"]) / len(g["dists"]),
        )
        for g in groups
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None  # 间距歧义并列 → 宁缺勿错
    return scored[0][1]


def _pair_wall_thickness(entities: List[SemanticEntity]) -> List[SemanticEntity]:
    """双线墙厚度配对：同向平行退化线元，间距 ∈[100,600]mm 且重叠 ≥50%。

    只对 width 仍缺失的墙实体注入；已有宽度者仍可作对偶证据参与。
    """
    lines = []
    for ent in entities:
        if ent.type not in _WALL_TYPES:
            continue
        if _is_excluded_layer(ent.layer):
            continue
        ln = _degenerate_line(ent)
        if ln is not None:
            lines.append(ln)
    if len(lines) < 2:
        return entities

    by_axis = {"v": [], "h": []}
    for ln in lines:
        by_axis[ln.axis].append(ln)

    for group in by_axis.values():
        n = len(group)
        if n < 2:
            continue
        group.sort(key=lambda L: L.cross)
        cand: List[List] = [[] for _ in range(n)]
        for i in range(n):
            a = group[i]
            if a.hi - a.lo <= 0:
                continue
            for j in range(i + 1, n):
                b = group[j]
                if b.hi - b.lo <= 0:
                    continue
                d = b.cross - a.cross  # 已按 cross 升序，d ≥ 0
                if d > _THICKNESS_MAX_MM:
                    break
                if d < _THICKNESS_MIN_MM:
                    continue
                ov = _overlap_rate(a, b)
                if ov >= _OVERLAP_MIN:
                    cand[i].append((d, ov))
                    cand[j].append((d, ov))
        for i in range(n):
            ent = group[i].ent
            existing = ent.properties.get("width")
            if isinstance(existing, (int, float)) and existing > 0:
                continue  # 只补缺失，不覆盖既有值
            dist = _arbitrate(cand[i])
            if dist is None:
                continue
            m_val = _to_meters_small(dist, _THICKNESS_MIN_M, _THICKNESS_MAX_M)
            if m_val is not None:
                _inject_attr(ent, "width", m_val, "paired_wall_thickness")
    return entities


def _inject_paired_attributes(
    self,
    entities: List[SemanticEntity],
    primitives: List,
) -> List[SemanticEntity]:
    """Step 3.8 入口（签名与其它 Step 一致；primitives 预留 M2 洞口配对）。"""
    del primitives  # 当前实现只消费实体自身 bbox
    if not entities:
        return entities
    _pair_wall_thickness(entities)
    return entities
