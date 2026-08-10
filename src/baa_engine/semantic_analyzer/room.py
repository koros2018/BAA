"""Room recognition — near-closed detection + LINE chain merge.
"""
from typing import List
from .models import SemanticEntity
import math
from ..drawing_parser import RawPrimitive

def _is_near_closed(
    self, prim: RawPrimitive, gap_threshold_mm: float = 500.0
) -> bool:
    """接近闭合检测：开放多边形首尾点距离 < 阈值 → 视为闭合

    用于处理缺口房间（L 形/U 形房间在墙体断开处形成缺口）
    """
    pts = prim.properties.get("points")
    if not pts or len(pts) < 3:  # check: numeric comparison
        return False
    # 校验 pts 结构（可能是 [(x,y), ...] 或 [[x,y], ...]）
    try:  # try: operation block
        first = pts[0]
        last = pts[-1]
        if isinstance(first, (list, tuple)) and len(first) >= 2:  # check: numeric comparison
            start = (float(first[0]), float(first[1]))
            end = (float(last[0]), float(last[1]))
        else:  # else: default case
            return False
    except (TypeError, IndexError, ValueError):  # catch: exception handler
        return False
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    gap = math.sqrt(dx * dx + dy * dy)
    return gap < gap_threshold_mm




def _merge_line_chains_to_rooms(
    self, entities: List[SemanticEntity], primitives: List[RawPrimitive]
) -> List[
    SemanticEntity
]:
    """多段线复合房间识别：LINE 链闭合检测

    将首尾相连的 LINE 图元组合成闭合链，满足条件后合并为 room 实体。
    处理建筑师用多个 LINE 绘制房间轮廓的情况。
    """
    # 收集 LINE 图元（仅 wall 候选：>=2000mm，减少 60x 噪声）
    # P101: PDF 数据中 94726 条 line 中 643 条是 wall，DFS 全量跑 94000+ 线
    # 会爆栈/超时。改为只收集 wall 候选线段（>=2000mm）。
    lines = []
    for prim in primitives:
        if prim.dxf_type == "LINE":
            length = max(
                (prim.bbox or {}).get("width", 0),
                (prim.bbox or {}).get("height", 0),
            )
            # P101: 只有 >=2000mm 的 LINE 才可能是建筑墙体
            if length >= 2000:
                lines.append(prim)
    if len(lines) < 3:
        return entities

    # 端点匹配阈值（mm）——PDF 数据精度损失，放宽到 10mm
    # P101: 端点坐标匹配精度放宽到 10mm（PDF→DXF 精度损失）
    coord_tolerance = 10.0  # mm
    # 闭合检测的端点距离阈值：原 100mm，PDF 数据保留原值
    match_threshold = 100.0  # mm

    # 建立邻接表（使用坐标四舍五入到 tolerance 精度，补偿 PDF 精度损失）
    def _round_point(p):
        return (round(p[0] / coord_tolerance), round(p[1] / coord_tolerance))

    point_to_lines = {}
    for i, line in enumerate(lines):
        sp = line.properties.get("start_point", {})
        ep = line.properties.get("end_point", {})
        p1 = (sp.get("x", 0), sp.get("y", 0))
        p2 = (ep.get("x", 0), ep.get("y", 0))
        rp1 = _round_point(p1)
        rp2 = _round_point(p2)
        point_to_lines.setdefault(rp1, []).append((i, 0, p1, p2))  # append: add to list
        point_to_lines.setdefault(rp2, []).append((i, 1, p1, p2))  # append: add to list

    # DFS 找闭合链
    visited = [False] * len(lines)
    closed_chains = []

    for start_i in range(len(lines)):
        if visited[start_i]:  # condition: visited[start_i]:
            continue  # code
        chain = [start_i]
        visited[start_i] = True
        current = start_i
        current_end = 1  # 0=start, 1=end
        # 记录遍历路径中的端点（用于面积计算）
        path_pts = []

        # 获取起始线的端点
        sl = lines[start_i]
        sp = sl.properties.get("start_point", {})
        ep = sl.properties.get("end_point", {})
        path_pts.append((sp.get("x", 0), sp.get("y", 0)))  # append: add to list
        path_pts.append((ep.get("x", 0), ep.get("y", 0)))  # append: add to list

        # 遍历链
        max_depth = 50  # 防止无限循环
        depth = 0
        while depth < max_depth:
            depth += 1  # accumulate
            # 获取当前线的端点
            line = lines[current]
            sp = line.properties.get("start_point", {})
            ep = line.properties.get("end_point", {})
            p1 = (sp.get("x", 0), sp.get("y", 0))
            p2 = (ep.get("x", 0), ep.get("y", 0))
            rp1 = _round_point(p1)
            rp2 = _round_point(p2)

            # 当前端点（四舍五入后）
            current_rp = rp1 if current_end == 0 else rp2  # compare: equality

            # 找下一个线
            found_next = False
            for ni, nend, nsp, nep in point_to_lines.get(
                current_rp, []
            ):
                if ni == current:  # condition: ni == current:
                    continue  # code
                if visited[ni]:  # condition: visited[ni]:
                    # 如果回到起点且链长度 >= 3 → 闭合
                    if ni == start_i and len(chain) >= 3:  # check: numeric comparison
                        closed_chains.append((chain, path_pts))  # append: add to list
                        break  # code
                    continue  # code
                visited[ni] = True
                chain.append(ni)  # append: add to list
                # 添加新线的另一个端点（非连接点）到路径
                if nend == 0:  # 连接点是 start，新端点是 end
                    path_pts.append((nep[0], nep[1]))  # append: add to list
                else:  # 连接点是 end，新端点是 start
                    path_pts.append((nsp[0], nsp[1]))  # append: add to list
                current = ni
                # 确定下一个线的起始端点
                current_end = 1 - nend
                found_next = True
                break  # code
            if not found_next:  # check: negated condition
                break  # code

        # 检查是否闭合回到起点（通过距离阈值）
        if len(chain) >= 3:  # check: numeric comparison
            # 路径最后一个点
            last_pt = path_pts[-1] if path_pts else None
            # 起始线的两个端点
            sl = lines[start_i]
            sp = sl.properties.get("start_point", {})
            ep = sl.properties.get("end_point", {})
            sp_start = (sp.get("x", 0), sp.get("y", 0))
            sp_end = (ep.get("x", 0), ep.get("y", 0))
            if last_pt and (
                (
                    abs(last_pt[0] - sp_start[0]) < match_threshold
                    and abs(last_pt[1] - sp_start[1]) < match_threshold
                )
                or (
                    abs(last_pt[0] - sp_end[0]) < match_threshold
                    and abs(last_pt[1] - sp_end[1]) < match_threshold
                )
            ):
                # 检查是否已存在
                is_dup = False
                for (
                    existing_chain,
                    _,
                ) in closed_chains:
                    if set(chain) == set(
                        existing_chain
                    ):  # condition: set(chain) == set(existing_chain):
                        is_dup = True
                        break  # code
                if not is_dup:  # check: negated condition
                    closed_chains.append((chain, path_pts))  # append: add to list

    # 对闭合链计算面积，符合条件的合并为 room
    non_room_layers = [
        "COLU",
        "视口",
        "洞口",
        "板边",
        "梁边",
        "轴",
        "BASE",
        "梁",
        "吊筋",
        "板层",
        "文字",
        "钢筋",
        "标注",
        "DIM",
        "立面看线",
        "立面",
        "看线",
        "园林",
        "井",
        "电-",
        "电气",
        "照明",
        "插座",
        "弱电",
        "消防",
        "火灾",
        "报警",
        "设备",
        "电缆",
        "系统",
        "Defpoints",
    ]
    new_rooms = []
    for chain, pts in closed_chains:
        if len(pts) < 3:  # check: numeric comparison
            continue  # code

        # 检查链中是否有非建筑图元（任一 LINE 在非建筑图层上）
        has_non_building = False
        for idx in chain:
            prim = lines[idx]
            if any(
                kw in prim.layer.upper() for kw in non_room_layers
            ):  # check: membership test
                has_non_building = True
                break  # code
        if has_non_building:  # condition: has_non_building:
            continue  # code

        # 计算面积（鞋带公式）
        area = abs(
            sum(
                pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts))
            )
            / 2
        )

        # 面积条件：1m² < area < 500m²
        if area < 1000000 or area > 500000000:  # check: numeric comparison
            continue  # code

        # bbox
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        # 宽高比过滤：极端长条形不是房间
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bw > 0 and bh > 0:  # check: both positive
            aspect = max(bw, bh) / min(bw, bh)
            if aspect > 8.0:  # 宽高比 > 8:1 不是房间（走廊/管道/线槽）
                continue  # code

        # bbox dict
        bbox = {
            "x": min(xs),
            "y": min(ys),
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys),
        }

        # 创建 room 实体
        room_id = f"line_chain_room_{self._entity_counter}"
        self._entity_counter += 1
        room = SemanticEntity(
            entity_id=room_id,
            entity_type="room",
            layer="",
            properties={"area": area / 1000000},  # 转为 m²
            bbox=bbox,
        )  # code
        new_rooms.append(room)  # append: add to list

    return entities + new_rooms

