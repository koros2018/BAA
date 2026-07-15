"""
BAA 反向重构引擎 v1（原型）

验证"正向→反向"闭环可行性：
1. 输入：房间尺寸 + 功能类型 → 约束推理
2. 输出：合规 DXF 文件
3. 验证：正向解析 DXF → 原子函数全 PASS

当前阶段：简易场景——单个房间 + 一个门 + 尺寸标注
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
from .atomic_functions import FuncRegistry


class RoomType(str, Enum):
    """房间功能类型（与 atomic_functions 的 target_entities 对齐）"""
    OFFICE = "office"
    STAIR = "stair"
    EXIT = "exit"
    CORRIDOR = "corridor"
    FIRE_LOBBY = "fire_lobby"
    EQUIPMENT = "equipment"
    TOILET = "accessible_toilet"


@dataclass
class RoomSpec:
    """房间规格输入"""
    room_type: RoomType
    width_mm: float
    height_mm: float
    door_width_mm: Optional[float] = None  # None = 自动推断


@dataclass
class LayoutConstraint:
    """布局约束输出"""
    min_width_mm: float
    min_height_mm: float
    min_door_width_mm: float
    min_area_m2: float
    max_area_m2: Optional[float] = None
    has_window: bool = False
    has_sprinkler: bool = False
    notes: List[str] = field(default_factory=list)


class ReverseEngine:
    """反向重构引擎"""

    # 房间类型 → 默认最小尺寸（mm）
    DEFAULT_MIN_SIZES: Dict[RoomType, Tuple[float, float, float]] = {
        RoomType.OFFICE: (3000, 3000, 900),      # 3m x 3m, 门 900mm
        RoomType.STAIR: (2500, 4000, 1100),       # 楼梯间
        RoomType.EXIT: (2000, 2000, 1000),        # 安全出口
        RoomType.CORRIDOR: (2000, 6000, 1200),    # 走廊
        RoomType.FIRE_LOBBY: (2000, 2000, 1000),  # 前室
        RoomType.EQUIPMENT: (2000, 2000, 900),    # 设备间
        RoomType.TOILET: (2000, 2000, 900),       # 无障碍卫生间
    }

    def __init__(self):
        self.registry = FuncRegistry()

    def infer_constraints(self, spec: RoomSpec) -> LayoutConstraint:
        """根据房间类型 + 尺寸，推断应满足的规范约束"""
        defaults = self.DEFAULT_MIN_SIZES.get(spec.room_type, (3000, 3000, 900))
        min_w = max(spec.width_mm, defaults[0])
        min_h = max(spec.height_mm, defaults[1])
        min_door = spec.door_width_mm or defaults[2]

        notes = []
        area_m2 = (spec.width_mm * spec.height_mm) / 1e6

        # 查找匹配的原子函数，提取约束
        for func in self.registry.list_all():
            if func.func_id == "DIM-001":  # 疏散楼梯净宽 ≥ 1.2m
                if spec.room_type == RoomType.STAIR:
                    min_door = max(min_door, 1200)
                    notes.append("DIM-001: 疏散楼梯净宽 ≥ 1.2m")

            elif func.func_id == "DIM-003":  # 消防车道宽度
                if spec.room_type == RoomType.CORRIDOR:
                    min_w = max(min_w, 4000)
                    notes.append("DIM-003: 消防车道宽度 ≥ 4m")

            elif func.func_id == "DIM-009":  # 疏散门净宽 ≥ 0.8m
                min_door = max(min_door, 800)
                notes.append("DIM-009: 疏散门净宽 ≥ 0.8m")

            elif func.func_id == "DIM-010":  # 无障碍门宽 ≥ 0.9m
                if spec.room_type == RoomType.TOILET:
                    min_door = max(min_door, 900)
                    notes.append("DIM-010: 无障碍门宽 ≥ 0.9m")

            elif func.func_id == "DIST-001":  # 疏散距离 ≤ 30m
                notes.append("DIST-001: 疏散距离 ≤ 30m")

            elif func.func_id == "ARE-001":  # 防火分区面积
                notes.append("ARE-001: 防火分区面积 ≤ 规范上限")

        return LayoutConstraint(
            min_width_mm=min_w,
            min_height_mm=min_h,
            min_door_width_mm=min_door,
            min_area_m2=area_m2,
            notes=notes,
        )

    def generate_dxf(self, spec: RoomSpec, output_path: str) -> str:
        """生成 DXF 文件"""
        constraints = self.infer_constraints(spec)
        return self._build_dxf(spec, constraints, output_path)

    def _build_dxf(self, spec: RoomSpec, constraints: LayoutConstraint,
                    output_path: str) -> str:
        """构建 DXF 内容（与正向解析识别规则对齐）"""
        lines = []
        lines.append("0")
        lines.append("SECTION")
        lines.append("2")
        lines.append("HEADER")
        lines.append("0")
        lines.append("ENDSEC")
        lines.append("0")
        lines.append("SECTION")
        lines.append("2")
        lines.append("ENTITIES")

        w = constraints.min_width_mm
        h = constraints.min_height_mm
        door_w = constraints.min_door_width_mm
        door_x = int(w * 0.15)  # 门在底边墙 15% 位置

        # 1. 房间轮廓：LWPOLYLINE 闭合多边形（被正向识别为 room）
        # 面积 > 500000000 mm² (= 500 m²) 且宽高比 < 8 判为 room
        lines.extend(self._lwpolyline_rect(0, 0, w, h, "WALL"))

        # 2. 门：短 LINE (700-2000mm, short_edge < 50 → door)
        lines.extend(self._line(door_x, 0, door_x + door_w, 0, "DOOR"))

        # 3. 门弧：ARC (100-2000mm 半径 → door)
        lines.extend(self._arc(door_x, 0, door_w, 0, 90, "DOOR"))

        # 4. 尺寸标注：DIMENSION 加 DEFPOINTS 线（被 _classify_by_layer 识别）
        # DXF 尺寸标注需要关联点 + 标注线才能被解析
        lines.extend(self._dim_with_defpoint(
            0, -1000, w, -1000, f"{w}mm", "DIM"))
        lines.extend(self._dim_with_defpoint(
            -1000, 0, -1000, h, f"{h}mm", "DIM"))

        # 5. 文字标注：在 DEFPOINTS 层加 TEXT（被识别为 other）
        lines.extend(self._text(
            spec.room_type.value.upper(), w / 2, h / 2, 300, "TEXT"))

        lines.append("0")
        lines.append("ENDSEC")
        lines.append("0")
        lines.append("EOF")

        dxf_content = "\n".join(lines)
        with open(output_path, "w") as f:
            f.write(dxf_content)
        return output_path

    def _line(self, x1, y1, x2, y2, layer):
        return [
            "0", "LINE",
            "8", layer,
            "10", str(x1),
            "20", str(y1),
            "30", "0",
            "11", str(x2),
            "21", str(y2),
            "31", "0",
        ]

    def _arc(self, cx, cy, r, start_angle, end_angle, layer):
        return [
            "0", "ARC",
            "8", layer,
            "10", str(cx),
            "20", str(cy),
            "30", "0",
            "40", str(r),
            "50", str(start_angle),
            "51", str(end_angle),
        ]

    def _text(self, text, x, y, height, layer):
        return [
            "0", "TEXT",
            "8", layer,
            "10", str(x),
            "20", str(y),
            "30", "0",
            "40", str(height),
            "1", text,
        ]

    def _lwpolyline_rect(self, x, y, w, h, layer):
        """LWPOLYLINE 矩形（4 顶点闭合多边形，被识别为 room/wall）"""
        return [
            "0", "LWPOLYLINE",
            "8", layer,
            "100", "AcDbEntity",
            "100", "AcDbPolyline",
            "90", "4",  # 顶点数
            "70", "1",  # 闭合
            "10", str(x), "20", str(y),
            "10", str(x + w), "20", str(y),
            "10", str(x + w), "20", str(y + h),
            "10", str(x), "20", str(y + h),
        ]

    def _dim_with_defpoint(self, x1, y1, x2, y2, text, layer):
        """DIMENSION + DEFPOINTS 线（被 _classify_by_layer 识别为 dimension）"""
        # DEFPOINTS 层上的短 LINE 被识别为标注参考线
        lines = []
        lines.extend(self._line(x1, y1, x2, y2, "DEFPOINTS"))
        lines.extend([
            "0", "DIMENSION",
            "8", layer,
            "10", str(x1), "20", str(y1), "30", "0",
            "11", str(x2), "21", str(y2), "31", "0",
            "70", "0",
            "1", text,
        ])
        return lines


# ═══════════════════════════════════════════════════════════════════
# P58 多房间布局生成
# ═══════════════════════════════════════════════════════════════════


@dataclass
class RoomPlacement:
    """房间在最终布局中的位置和门朝向"""
    room_type: RoomType
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    door_x_mm: float  # 门在房间边上的位置（沿门边方向）
    door_side: str  # "bottom" | "top" | "left" | "right"


@dataclass
class MultiRoomLayout:
    """多房间布局结果"""
    rooms: List[RoomPlacement]
    corridor: Optional[RoomPlacement]  # 连接所有房间的走廊
    constraints: List[LayoutConstraint]
    notes: List[str]


class MultiRoomEngine:
    """多房间布局生成引擎"""

    # 走廊两侧的余量（mm）
    CORRIDOR_MARGIN = 200
    # 房间之间的间距（mm）
    ROOM_GAP = 200
    # 走廊最小宽度（mm）
    CORRIDOR_MIN_WIDTH = 2000

    def __init__(self):
        self.engine = ReverseEngine()

    def generate_layout(self, room_specs: List[RoomSpec]) -> MultiRoomLayout:
        """
        将多个房间排列成"走廊+两侧房间"的典型布局。

        布局算法：
        1. 房间沿水平方向排列，上下两排，中间走廊
        2. 上排房间门朝下（朝向走廊），下排房间门朝上
        3. 走廊宽度取所有房间的最大门宽 + 余量
        4. 整体布局尺寸标注
        """
        if not room_specs:
            return MultiRoomLayout(rooms=[], corridor=None, constraints=[], notes=["无房间输入"])

        constraints = [self.engine.infer_constraints(spec) for spec in room_specs]
        notes = []

        # 计算走廊宽度：取所有房间最大门宽 + 余量
        corridor_width = self.CORRIDOR_MIN_WIDTH
        for c in constraints:
            corridor_width = max(corridor_width, c.min_door_width_mm + self.CORRIDOR_MARGIN)

        # 分两排：上排（偶数索引）和下排（奇数索引）
        top_rooms: List[RoomSpec] = []
        bottom_rooms: List[RoomSpec] = []
        for i, spec in enumerate(room_specs):
            if i % 2 == 0:
                top_rooms.append(spec)
            else:
                bottom_rooms.append(spec)

        # 计算每排的最大高度
        bottom_max_h = max((s.height_mm for s in bottom_rooms), default=3000)

        # 走廊 Y 起始位置 = 下排房间高度 + 间距
        corridor_y = bottom_max_h + self.ROOM_GAP

        # 布局：水平方向从左到右排列
        placements: List[RoomPlacement] = []
        current_x = 0

        # 先放置下排房间（索引为奇数，门朝上 -> 朝向走廊）
        for i, spec in enumerate(bottom_rooms):
            w = constraints[room_specs.index(spec)].min_width_mm
            h = constraints[room_specs.index(spec)].min_height_mm
            door_w = constraints[room_specs.index(spec)].min_door_width_mm
            # 门在房间底边（朝向走廊的方向），居中放置
            door_x = current_x + (w - door_w) / 2
            placements.append(RoomPlacement(
                room_type=spec.room_type,
                x_mm=current_x,
                y_mm=0,
                width_mm=w,
                height_mm=h,
                door_x_mm=door_x,
                door_side="top",  # 门朝上（朝向走廊）
            ))
            current_x += w + self.ROOM_GAP

        # 走廊宽度取所有房间最大门宽
        max_door_w = max(c.min_door_width_mm for c in constraints)
        corridor_w = max(self.CORRIDOR_MIN_WIDTH, max_door_w + self.CORRIDOR_MARGIN)

        # 走廊
        corridor = RoomPlacement(
            room_type=RoomType.CORRIDOR,
            x_mm=0,
            y_mm=corridor_y,
            width_mm=current_x - self.ROOM_GAP,  # 走廊宽度 = 所有房间宽度总和
            height_mm=corridor_w,
            door_x_mm=0,
            door_side="bottom",
        )

        # 重置 X 坐标放置上排房间
        current_x = 0
        for i, spec in enumerate(top_rooms):
            w = constraints[room_specs.index(spec)].min_width_mm
            h = constraints[room_specs.index(spec)].min_height_mm
            door_w = constraints[room_specs.index(spec)].min_door_width_mm
            door_x = current_x + (w - door_w) / 2
            placements.append(RoomPlacement(
                room_type=spec.room_type,
                x_mm=current_x,
                y_mm=corridor_y + corridor_w + self.ROOM_GAP,
                width_mm=w,
                height_mm=h,
                door_x_mm=door_x,
                door_side="bottom",  # 门朝下（朝向走廊）
            ))
            current_x += w + self.ROOM_GAP

        notes.append(f"走廊宽度: {corridor_w}mm")
        notes.append(f"上排房间: {len(top_rooms)}个, 下排房间: {len(bottom_rooms)}个")
        notes.append("疏散路径: 通过走廊疏散")

        return MultiRoomLayout(
            rooms=placements,
            corridor=corridor,
            constraints=constraints,
            notes=notes,
        )

    def build_dxf(self, layout: MultiRoomLayout, output_path: str) -> str:
        """
        为多房间布局生成 DXF 文件。

        包含：
        - 每个房间的 LWPOLYLINE + 门 LINE + 门 ARC
        - 走廊 LWPOLYLINE
        - 尺寸标注 DIMENSION
        - 房间功能 TEXT 标注
        """
        lines = []
        lines.append("0")
        lines.append("SECTION")
        lines.append("2")
        lines.append("HEADER")
        lines.append("0")
        lines.append("ENDSEC")
        lines.append("0")
        lines.append("SECTION")
        lines.append("2")
        lines.append("ENTITIES")

        # 1. 绘制每个房间
        for room in layout.rooms:
            self._draw_room(room, lines)

        # 2. 绘制走廊
        if layout.corridor:
            self._draw_room(layout.corridor, lines)

        # 3. 整体尺寸标注
        if layout.rooms:
            all_x = [r.x_mm for r in layout.rooms]
            all_y = [r.y_mm for r in layout.rooms]
            all_xw = [r.x_mm + r.width_mm for r in layout.rooms]
            all_yh = [r.y_mm + r.height_mm for r in layout.rooms]

            total_w = max(all_xw) - min(all_x)
            total_h = max(all_yh) - min(all_y)

            # 底部总宽度标注
            lines.extend(self._dim_with_defpoint(
                min(all_x), -1000, max(all_xw), -1000,
                f"{total_w}mm", "DIM"))

            # 右侧总高度标注
            lines.extend(self._dim_with_defpoint(
                max(all_xw) + 1000, min(all_y), max(all_xw) + 1000, max(all_yh),
                f"{total_h}mm", "DIM"))

        # 4. 房间功能文字标注
        for room in layout.rooms:
            cx = room.x_mm + room.width_mm / 2
            cy = room.y_mm + room.height_mm / 2
            lines.extend(self._text(
                room.room_type.value.upper(), cx, cy, 250, "TEXT"))

        if layout.corridor:
            cx = layout.corridor.x_mm + layout.corridor.width_mm / 2
            cy = layout.corridor.y_mm + layout.corridor.height_mm / 2
            lines.extend(self._text(
                "CORRIDOR", cx, cy, 250, "TEXT"))

        # 5. 疏散路径标注（箭头线从房间门→走廊→出口方向）
        # 在 EVAC 层绘制疏散箭头线，用于正向解析识别疏散路径
        evac_lines = self._build_evacuation_paths(layout)
        for el in evac_lines:
            lines.extend(el)

        lines.append("0")
        lines.append("ENDSEC")
        lines.append("0")
        lines.append("EOF")

        dxf_content = "\n".join(lines)
        with open(output_path, "w") as f:
            f.write(dxf_content)
        return output_path

    def _build_evacuation_paths(self, layout: MultiRoomLayout) -> list:
        """
        生成疏散路径箭头线（EVAC 层）。
        
        每个房间生成两条路径段：
        1. 从房间门中心点到走廊中心
        2. 从走廊中心沿走廊方向到出口（走廊右端或左端）
        
        路径段用带箭头的 LINE 表示，被正向解析识别为疏散路径。
        """
        evac_paths = []
        
        if not layout.corridor:
            return evac_paths
        
        corridor_cx = layout.corridor.x_mm + layout.corridor.width_mm / 2
        corridor_cy = layout.corridor.y_mm + layout.corridor.height_mm / 2
        
        # 出口方向：走廊右端（假设安全出口在右侧）
        exit_x = layout.corridor.x_mm + layout.corridor.width_mm
        exit_y = corridor_cy
        
        for room in layout.rooms:
            # 房间门中心点
            if room.door_side in ("top", "bottom"):
                door_cx = room.door_x_mm + room.width_mm * 0.075  # 门宽一半
                door_cy = room.y_mm + (room.height_mm if room.door_side == "top" else 0)
            else:
                door_cx = room.x_mm + (room.width_mm if room.door_side == "right" else 0)
                door_cy = room.door_x_mm + room.height_mm * 0.075
            
            # 段1: 门中心 → 走廊中心
            # 中间点：从门垂直延伸到走廊边缘
            if room.door_side == "bottom":
                mid_y = layout.corridor.y_mm
                mid_x = door_cx
                evac_paths.append(self._evac_line(door_cx, door_cy, mid_x, mid_y))
                evac_paths.append(self._evac_line(mid_x, mid_y, corridor_cx, corridor_cy))
            elif room.door_side == "top":
                mid_y = layout.corridor.y_mm + layout.corridor.height_mm
                mid_x = door_cx
                evac_paths.append(self._evac_line(door_cx, door_cy, mid_x, mid_y))
                evac_paths.append(self._evac_line(mid_x, mid_y, corridor_cx, corridor_cy))
            else:
                # 侧边门，直接连接到走廊中心
                evac_paths.append(self._evac_line(door_cx, door_cy, corridor_cx, corridor_cy))
            
            # 段2: 走廊中心 → 出口方向
            evac_paths.append(self._evac_line(corridor_cx, corridor_cy, exit_x, exit_y))
        
        return evac_paths

    def _evac_line(self, x1, y1, x2, y2):
        """疏散路径 LINE（EVAC 层），带箭头指示"""
        return [
            "0", "LINE",
            "8", "EVAC",
            "10", str(x1),
            "20", str(y1),
            "30", "0",
            "11", str(x2),
            "21", str(y2),
            "31", "0",
        ]

    def _draw_room(self, room: RoomPlacement, lines: list):
        """绘制单个房间：轮廓 + 门线 + 门弧"""
        # 房间轮廓
        lines.extend(self._lwpolyline_rect(
            room.x_mm, room.y_mm, room.width_mm, room.height_mm, "WALL"))

        # 门线 + 门弧
        door_w = room.width_mm * 0.15  # 门宽约为房间宽的 15%
        door_w = max(700, min(door_w, 2000))  # 700-2000mm 范围

        if room.door_side == "bottom":
            # 门在底边
            dx = room.door_x_mm
            dy = room.y_mm
            lines.extend(self._line(dx, dy, dx + door_w, dy, "DOOR"))
            lines.extend(self._arc(dx, dy, door_w, 0, 90, "DOOR"))
        elif room.door_side == "top":
            # 门在顶边
            dx = room.door_x_mm
            dy = room.y_mm + room.height_mm
            lines.extend(self._line(dx, dy, dx + door_w, dy, "DOOR"))
            lines.extend(self._arc(dx, dy, door_w, 180, 270, "DOOR"))
        elif room.door_side == "left":
            # 门在左边
            dx = room.x_mm
            dy = room.door_x_mm
            lines.extend(self._line(dx, dy, dx, dy + door_w, "DOOR"))
            lines.extend(self._arc(dx, dy, door_w, 90, 180, "DOOR"))
        elif room.door_side == "right":
            # 门在右边
            dx = room.x_mm + room.width_mm
            dy = room.door_x_mm
            lines.extend(self._line(dx, dy, dx, dy + door_w, "DOOR"))
            lines.extend(self._arc(dx, dy, door_w, 270, 360, "DOOR"))

    def _lwpolyline_rect(self, x, y, w, h, layer):
        """LWPOLYLINE 矩形（4 顶点闭合多边形）"""
        return [
            "0", "LWPOLYLINE",
            "8", layer,
            "100", "AcDbEntity",
            "100", "AcDbPolyline",
            "90", "4",
            "70", "1",
            "10", str(x), "20", str(y),
            "10", str(x + w), "20", str(y),
            "10", str(x + w), "20", str(y + h),
            "10", str(x), "20", str(y + h),
        ]

    def _line(self, x1, y1, x2, y2, layer):
        return [
            "0", "LINE",
            "8", layer,
            "10", str(x1),
            "20", str(y1),
            "30", "0",
            "11", str(x2),
            "21", str(y2),
            "31", "0",
        ]

    def _arc(self, cx, cy, r, start_angle, end_angle, layer):
        return [
            "0", "ARC",
            "8", layer,
            "10", str(cx),
            "20", str(cy),
            "30", "0",
            "40", str(r),
            "50", str(start_angle),
            "51", str(end_angle),
        ]

    def _text(self, text, x, y, height, layer):
        return [
            "0", "TEXT",
            "8", layer,
            "10", str(x),
            "20", str(y),
            "30", "0",
            "40", str(height),
            "1", text,
        ]

    def _dim_with_defpoint(self, x1, y1, x2, y2, text, layer):
        """DIMENSION + DEFPOINTS 线"""
        lines = []
        lines.extend(self._line(x1, y1, x2, y2, "DEFPOINTS"))
        lines.extend([
            "0", "DIMENSION",
            "8", layer,
            "10", str(x1), "20", str(y1), "30", "0",
            "11", str(x2), "21", str(y2), "31", "0",
            "70", "0",
            "1", text,
        ])
        return lines


def validate_roundtrip(dxf_path: str) -> Dict:
    """验证正向→反向闭环：解析 DXF → 原子函数检查"""
    import sys
    sys.path.insert(0, str(dxf_path.parent.parent))
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer

    parser = DrawingParser()
    analyzer = SemanticAnalyzer()
    registry = FuncRegistry()

    result = parser.parse(str(dxf_path), "reverse_test")
    if not result.success:
        return {"success": False, "error": result.error}

    semantic = analyzer.analyze(result.primitives, result.dimensions)
    entities = semantic["entities"]

    findings = []
    for e in entities:
        # entities 是 dict，而非对象
        entity_id = e.get("id", "unknown")
        entity_type = e.get("type", "unknown")
        for func in registry.list_all():
            if func.matches(e):
                f = func.execute(e)
                if f:
                    findings.append({
                        "func_id": f.func_id,
                        "result": f.result,
                        "entity_id": entity_id,
                        "entity_type": entity_type,
                    })

    pass_count = sum(1 for f in findings if f["result"] == "PASS")
    fail_count = sum(1 for f in findings if f["result"] == "FAIL")

    return {
        "success": True,
        "entities": {t: len([x for x in entities if x["type"] == t])
                     for t in set(x["type"] for x in entities)},
        "findings": findings,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "all_pass": fail_count == 0,
    }