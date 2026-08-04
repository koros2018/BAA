"""Overlapping entity merge — spatial hash accelerated.
"""
from typing import List
from collections import defaultdict
from .models import SemanticEntity

def _merge_overlapping(
    self, entities: List[SemanticEntity]
) -> List[
    SemanticEntity
]:
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
                merged_bbox = self._union_bbox(
                    [e.bbox for e in cluster]
                )
                merged.append(
                    SemanticEntity(  # code
                        entity_id=a.id,
                        entity_type=a.type,
                        bbox=merged_bbox,
                        layer=a.layer,
                        confidence=max(
                            e.confidence for e in cluster
                        ),
                        properties=a.properties,
                    )
                )  # code
            else:  # else: default case
                merged.append(a)  # append: add to list
        return merged

    # ── 大数据量：空间哈希分桶 ──
    CELL_SIZE = 500.0  # mm，网格大小
    from collections import defaultdict  # stdlib import

    # 构建网格索引：{(gx, gy): [idx, ...]}
    grid = defaultdict(list)
    for idx, e in enumerate(entities):
        bx = e.bbox.get("x", 0)
        by = e.bbox.get("y", 0)
        bw = max(e.bbox.get("width", 0), 1.0)
        bh = max(e.bbox.get("height", 0), 1.0)
        gx1 = int(bx / CELL_SIZE)
        gx2 = int((bx + bw) / CELL_SIZE)
        gy1 = int(by / CELL_SIZE)
        gy2 = int((by + bh) / CELL_SIZE)
        for gx in range(gx1, gx2 + 1):
            for gy in range(gy1, gy2 + 1):
                grid[(gx, gy)].append(idx)  # append: add to list

    # 去重标记
    merged = []
    used = set()

    for i, a in enumerate(entities):
        if i in used:  # check: membership test
            continue  # code

        cluster = [a]
        used.add(i)  # call

        # 找到 a 所在的网格
        bx = a.bbox.get("x", 0)
        by = a.bbox.get("y", 0)
        bw = max(a.bbox.get("width", 0), 1.0)
        bh = max(a.bbox.get("height", 0), 1.0)
        gx1 = int(bx / CELL_SIZE)
        gx2 = int((bx + bw) / CELL_SIZE)
        gy1 = int(by / CELL_SIZE)
        gy2 = int((by + bh) / CELL_SIZE)

        # 收集相邻网格中的候选实体
        candidates = set()
        for gx in range(gx1 - 1, gx2 + 2):
            for gy in range(gy1 - 1, gy2 + 2):
                for idx in grid.get((gx, gy), []):
                    if idx not in used:  # check: membership test
                        candidates.add(idx)  # call

        for j in sorted(candidates):
            if j in used:  # check: membership test
                continue  # code
            b = entities[j]
            if (
                a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5
            ):  # check: numeric comparison
                cluster.append(b)  # append: add to list
                used.add(j)  # call

        if len(cluster) > 1:  # check: numeric comparison
            merged_bbox = self._union_bbox(
                [e.bbox for e in cluster]
            )
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

