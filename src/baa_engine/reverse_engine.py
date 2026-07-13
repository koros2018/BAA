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
        for func in registry.list_all():
            if func.matches(e):
                f = func.execute(e)
                if f:
                    findings.append({
                        "func_id": f.func_id,
                        "result": f.result,
                        "entity_id": e.id,
                        "entity_type": e.type,
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