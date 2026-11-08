"""Overlapping entity merge — spatial hash accelerated."""

from typing import Dict, List
from collections import defaultdict
from .models import SemanticEntity

# 合并阶段允许单实体覆盖的网格上限。比 spatial_grid 的 500 更宽
# （256×256 格 ≈ 256m×256m），避免把几十米级大厅/底板误判为退化实体
# 而漏合并；只拦截千米~数十千米级 xref/视口残留。
_MERGE_MAX_CELLS = 65536


def _merge_overlapping(self, entities: List[SemanticEntity]) -> List[SemanticEntity]:
    """合并重叠/相邻的同类图元（空间哈希加速版）

    小数据量（<2000）直接 O(n²) 全量对比；
    大数据量使用网格分桶，只对比同网格或相邻网格内的实体。
    """
    n = len(entities)
    if n < 2:  # check: numeric comparison
        return entities

    # ── 小数据量：直接 O(n²) 全量对比（开销小，无额外内存） ──
    if n < 2000:  # check: numeric comparison
        merged = []
        used = set()
        for i, a in enumerate(entities):
            if i in used:  # check: membership test
                continue  # code
            cluster = [a]
            used.add(i)  # call
            for j, b in enumerate(entities):
                if j in used:  # check: membership test
                    continue  # code
                if (
                    a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5
                ):  # check: numeric comparison
                    cluster.append(b)  # append: add to list
                    used.add(j)  # call
            if len(cluster) > 1:  # check: numeric comparison
                merged_bbox = self._union_bbox([e.bbox for e in cluster])
                merged.append(
                    SemanticEntity(  # code
                        entity_id=a.id,
                        entity_type=a.type,
                        bbox=merged_bbox,
                        layer=a.layer,
                        confidence=max(e.confidence for e in cluster),
                        properties=a.properties,
                    )
                )  # code
            else:  # else: default case
                merged.append(a)  # append: add to list
        return merged

    # ── 大数据量：per-type 空间哈希分桶 ──
    # P0-2 优化（2026-11-04）：原单一 grid（CELL_SIZE=500mm）在 50MB 电气图上
    # 产生 37 万 cells，47891 实体查询耗时 1.2s。优化：
    #   1. 按类型分 grid：查询时只查同类型 candidates，减少无效遍历
    #   2. CELL_SIZE 500→1000mm：cells 降至 ~10 万，grid 开销减半
    #   3. 面积预过滤：IoU>0.5 ⟹ 大面积<2×小面积，廉价跳过面积差异大的对
    #   4. 单实体类型跳过：不可能合并，不建 grid
    # P0-6 优化（2026-11-04）：预计算实体几何 (bx,by,bw,bh,area) 到数组，
    # 避免 grid 构建/查询中重复 e.bbox.get + max（103173 次 max + 85232 次 append）。
    # 历史实测（P0-2/P0-6，2026-11-04）：merge 1.22s → 0.51s → 0.26s，输出等价。
    # P0-9 优化（2026-11-05）：治理跨格爆炸（10119 实体 merge 当时仍占 0.201s / 21.3%）：
    #   1. 查询范围去掉 ±1 外扩：IoU>0.5 ⟹ 两框有正面积交集 ⟹ 必共享至少一格，
    #      故只查自身覆盖格即可，候选集为原外扩版的子集，且外扩多出的候选
    #      因无交集必被 IoU 过滤 → 输出严格等价（p50 实体查询格 12→2）。
    #   2. 网格改嵌套 dict[gx][gy]：省去 10 万次 tuple 构造/hash 与重复 grid.get。
    #   3. 候选去重改「gen 戳数组」，删除逐实体 set 构造 + sorted()；
    #      候选内 j 只与 a 比较，cluster 成员集合与集合顺序无关（union bbox
    #      与 max confidence 均顺序无关），故 sorted 无行为作用。
    #   4. 只扫 j>i：外层按下标升序，i 之前的实体必已 used，原逻辑对其全部跳过。
    #   5. 内联 IoU（复用预计算原值），省去每对 _compute_iou 的 dict 取键。
    # T2 实测（2026-11-06，48.9MB 电气图 / 10119 实体）：0.201s → 0.056s
    # （宿主机空闲窗口）；负载 ≈50% 时 ≈0.11s，约占 analyze 总量（≈0.70s）
    # 的 15%。复杂度 O(n + Σ候选对数)，候选对数由同类型实体的网格重叠程度决定。
    CELL_SIZE = 1000.0  # mm

    # 预计算几何信息（避免重复 bbox.get + max）
    # area_f 为网格口径（宽高下限 1.0，面积预过滤沿用原口径）
    # area_r 为原始面积（IoU 并集口径，与 compute_iou 完全一致）
    bx_a: List[float] = [0.0] * n
    by_a: List[float] = [0.0] * n
    x2_a: List[float] = [0.0] * n
    y2_a: List[float] = [0.0] * n
    area_f: List[float] = [0.0] * n
    area_r: List[float] = [0.0] * n
    gx1_a: List[int] = [0] * n
    gx2_a: List[int] = [0] * n
    gy1_a: List[int] = [0] * n
    gy2_a: List[int] = [0] * n
    for idx in range(n):
        b = entities[idx].bbox
        bx = b.get("x", 0)
        by = b.get("y", 0)
        bw = b.get("width", 0)
        bh = b.get("height", 0)
        bx_a[idx] = bx
        by_a[idx] = by
        x2_a[idx] = bx + bw
        y2_a[idx] = by + bh
        area_r[idx] = bw * bh
        bwf = bw if bw >= 1.0 else 1.0
        bhf = bh if bh >= 1.0 else 1.0
        area_f[idx] = bwf * bhf
        gx1_a[idx] = int(bx / CELL_SIZE)
        gx2_a[idx] = int((bx + bwf) / CELL_SIZE)
        gy1_a[idx] = int(by / CELL_SIZE)
        gy2_a[idx] = int((by + bhf) / CELL_SIZE)
        # 退化实体护栏（与 spatial_grid.bbox_cells 同口径）：DWG 残留的
        # 70km 级杂散线在 mm 坐标系下会覆盖数万×数万格，逐格枚举退化为
        # 数十亿次循环（实测 baa-file-584/b042 语义分析卡死）。超过格数
        # 上限时退化为「只用中心点入一格」，极端大实体不可能与正常构件
        # 有 IoU>0.5，不影响有效合并结果。
        span_cells = (gx2_a[idx] - gx1_a[idx] + 1) * (gy2_a[idx] - gy1_a[idx] + 1)
        if span_cells > _MERGE_MAX_CELLS:
            cx = int((bx + bwf / 2) / CELL_SIZE)
            cy = int((by + bhf / 2) / CELL_SIZE)
            gx1_a[idx] = gx2_a[idx] = cx
            gy1_a[idx] = gy2_a[idx] = cy

    # 按类型分组
    type_indices: Dict[str, List[int]] = defaultdict(list)
    for idx in range(n):
        type_indices[entities[idx].type].append(idx)

    # 每种类型独立建 grid（仅对 >=2 个实体的类型）；嵌套 dict 免 tuple 键
    type_grids: Dict[str, Dict[int, Dict[int, List[int]]]] = {}
    for etype, idxs in type_indices.items():
        if len(idxs) < 2:
            continue
        rows: Dict[int, Dict[int, List[int]]] = {}
        for idx in idxs:
            for gx in range(gx1_a[idx], gx2_a[idx] + 1):
                row = rows.get(gx)
                if row is None:
                    row = {}
                    rows[gx] = row
                for gy in range(gy1_a[idx], gy2_a[idx] + 1):
                    cell = row.get(gy)
                    if cell is None:
                        row[gy] = [idx]
                    else:
                        cell.append(idx)
        type_grids[etype] = rows

    merged = []
    used = bytearray(n)
    stamp = [-1] * n  # 候选去重（gen 戳），避免逐实体 set 构造

    for i in range(n):
        if used[i]:
            continue
        a = entities[i]
        used[i] = 1

        grid = type_grids.get(a.type)
        if grid is None:
            merged.append(a)
            continue

        ax = bx_a[i]
        ay = by_a[i]
        ax2 = x2_a[i]
        ay2 = y2_a[i]
        af = area_f[i]
        ar = area_r[i]
        cluster = None  # 懒创建：未发生合并时保持 None

        for gx in range(gx1_a[i], gx2_a[i] + 1):
            row = grid.get(gx)
            if row is None:
                continue
            for gy in range(gy1_a[i], gy2_a[i] + 1):
                cell = row.get(gy)
                if cell is None:
                    continue
                for j in cell:
                    if used[j] or stamp[j] == i:
                        continue
                    stamp[j] = i
                    # 面积预过滤：IoU>0.5 ⟹ max(area) < 2*min(area)
                    area_b = area_f[j]
                    if af > 2.0 * area_b or area_b > 2.0 * af:
                        continue
                    # 内联 IoU（与 compute_iou 同算式，复用预计算原值）
                    bxj = bx_a[j]
                    byj = by_a[j]
                    bx2j = x2_a[j]
                    by2j = y2_a[j]
                    ix1 = ax if ax > bxj else bxj
                    iy1 = ay if ay > byj else byj
                    ix2 = ax2 if ax2 < bx2j else bx2j
                    iy2 = ay2 if ay2 < by2j else by2j
                    iw = ix2 - ix1
                    ih = iy2 - iy1
                    if iw <= 0.0 or ih <= 0.0:
                        continue
                    inter = iw * ih
                    union = ar + area_r[j] - inter
                    if union <= 0.0:
                        continue
                    if inter / union > 0.5:
                        if cluster is None:
                            cluster = [a]
                        cluster.append(entities[j])
                        used[j] = 1

        if cluster is not None:
            merged_bbox = self._union_bbox([e.bbox for e in cluster])
            merged.append(
                SemanticEntity(
                    entity_id=a.id,
                    entity_type=a.type,
                    bbox=merged_bbox,
                    layer=a.layer,
                    confidence=max(e.confidence for e in cluster),
                    properties=a.properties,
                )
            )
        else:
            merged.append(a)

    return merged
