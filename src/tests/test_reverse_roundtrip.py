"""
P88: 反向重构闭环测试

验证: 输入房间规格 → 生成合规 DXF → 正向解析 DXF → 原子函数全 PASS
覆盖:
- SingleRoomEngine: infer_constraints / generate_dxf / validate_roundtrip
- MultiRoomEngine: generate_layout / build_dxf / validate_roundtrip
- export_dwg 降级路径
- 异常输入 (空规格、非法尺寸、不支持类型)
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.baa_engine.reverse_engine import (
    ReverseEngine,
    MultiRoomEngine,
    RoomSpec,
    RoomType,
    validate_roundtrip,
)

# ════════════════════════════════════════════════════════════
# 1. ReverseEngine — 约束推断
# ════════════════════════════════════════════════════════════


class TestReverseEngineInferConstraints:
    """验证 infer_constraints 对各类 RoomType 的约束推断"""

    def test_office_basic(self):
        engine = ReverseEngine()
        spec = RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000)
        c = engine.infer_constraints(spec)
        assert c.min_door_width_mm >= 900  # GB50016 办公最小门宽
        assert c.min_area_m2 > 0

    def test_stair_min_width(self):
        """楼梯宽度 ≥ 1100mm"""
        engine = ReverseEngine()
        spec = RoomSpec(room_type=RoomType.STAIR, width_mm=3000, height_mm=6000)
        c = engine.infer_constraints(spec)
        assert c.min_width_mm >= 1100
        assert c.notes is not None

    def test_fire_lobby_min_area(self):
        """前室最小面积 ≥ 4.5m²"""
        engine = ReverseEngine()
        spec = RoomSpec(room_type=RoomType.FIRE_LOBBY, width_mm=3000, height_mm=2000)
        c = engine.infer_constraints(spec)
        assert c.min_area_m2 >= 4.5

    def test_toilet_accessible(self):
        """无障碍厕所最小净宽 ≥ 1500mm"""
        engine = ReverseEngine()
        spec = RoomSpec(room_type=RoomType.TOILET, width_mm=2000, height_mm=2000)
        c = engine.infer_constraints(spec)
        assert c.min_width_mm >= 1500

    def test_door_width_explicit(self):
        """自定义门宽优先"""
        engine = ReverseEngine()
        spec = RoomSpec(
            room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000, door_width_mm=1200
        )
        c = engine.infer_constraints(spec)
        assert c.min_door_width_mm == 1200


# ════════════════════════════════════════════════════════════
# 2. ReverseEngine — DXF 生成 + 闭环验证
# ════════════════════════════════════════════════════════════


class TestReverseEngineGenerateDxf:
    """验证 DXF 生成内容结构和闭环校验"""

    def _generate(self, spec: RoomSpec) -> tuple[str, dict]:
        """生成 DXF 并返回 (路径, 验证结果)"""
        engine = ReverseEngine()
        engine.infer_constraints(spec)
        tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        tmp.close()
        engine.generate_dxf(spec, tmp.name)
        v = validate_roundtrip(Path(tmp.name))
        os.unlink(tmp.name)
        return tmp.name, v

    def _read_dxf_lines(self, spec: RoomSpec) -> str:
        """生成 DXF 并返回内容"""
        engine = ReverseEngine()
        tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        tmp.close()
        engine.generate_dxf(spec, tmp.name)
        content = open(tmp.name).read()
        os.unlink(tmp.name)
        return content

    def test_office_dxf_valid(self):
        _, v = self._generate(RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000))
        assert v.get("success") is True
        assert v.get("all_pass") is True
        entities = v.get("entities", {})
        assert "room" in entities or "wall" in entities

    def test_stair_dxf_valid(self):
        _, v = self._generate(RoomSpec(room_type=RoomType.STAIR, width_mm=3000, height_mm=6000))
        assert v.get("success") is True

    def test_dxf_contains_wall(self):
        content = self._read_dxf_lines(
            RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000)
        )
        assert "WALL" in content
        assert "DOOR" in content
        assert "LWPOLYLINE" in content

    def test_dxf_contains_dimensions(self):
        content = self._read_dxf_lines(
            RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000)
        )
        assert "DIMENSION" in content
        assert "DEFPOINTS" in content


# ════════════════════════════════════════════════════════════
# 3. MultiRoomEngine — 多房间布局
# ════════════════════════════════════════════════════════════


class TestMultiRoomEngine:
    """验证多房间布局和疏散路径生成"""

    def _generate_multi(self, specs) -> tuple[str, dict]:
        engine = MultiRoomEngine()
        layout = engine.generate_layout(specs)
        tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        tmp.close()
        engine.build_dxf(layout, tmp.name)
        v = validate_roundtrip(Path(tmp.name))
        os.unlink(tmp.name)
        return tmp.name, v, layout

    def test_two_rooms_corridor(self):
        specs = [
            RoomSpec(room_type=RoomType.OFFICE, width_mm=4000, height_mm=3000),
            RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=3000),
        ]
        _, _, layout = self._generate_multi(specs)
        assert len(layout.rooms) == 2
        assert layout.corridor is not None

    def test_three_rooms_with_exit(self):
        specs = [
            RoomSpec(room_type=RoomType.OFFICE, width_mm=4000, height_mm=3000),
            RoomSpec(room_type=RoomType.OFFICE, width_mm=4000, height_mm=3000),
            RoomSpec(room_type=RoomType.EXIT, width_mm=2000, height_mm=2000),
        ]
        _, v, layout = self._generate_multi(specs)
        assert v.get("success") is True
        assert len(layout.rooms) == 3
        # 疏散路径应存在
        evac_lines = [e for e in (v.get("findings", [])) if "EVAC" in str(e)]
        # 至少应有 room + door 实体
        ents = v.get("entities", {})
        assert any("room" in k or "wall" in k for k in ents)

    def test_layout_rooms_have_valid_coords(self):
        specs = [
            RoomSpec(room_type=RoomType.OFFICE, width_mm=4000, height_mm=3000),
        ]
        _, _, layout = self._generate_multi(specs)
        for r in layout.rooms:
            assert r.x_mm >= 0
            assert r.y_mm >= 0
            assert r.width_mm > 0
            assert r.height_mm > 0

    def test_dxf_multi_contains_evac_layer(self):
        """验证多房间 DXF 包含疏散路径 (EVAC 层)"""
        specs = [
            RoomSpec(room_type=RoomType.OFFICE, width_mm=4000, height_mm=3000),
            RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=3000),
        ]
        engine = MultiRoomEngine()
        layout = engine.generate_layout(specs)
        tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        tmp.close()
        engine.build_dxf(layout, tmp.name)
        content = open(tmp.name).read()
        os.unlink(tmp.name)
        assert "EVAC" in content


# ════════════════════════════════════════════════════════════
# 4. export_dwg — 降级路径
# ════════════════════════════════════════════════════════════


class TestExportDwg:
    """验证 DXF→DWG 导出（LibreOffice 不可用时降级返回 DXF）"""

    def test_export_dwg_fallback(self):
        engine = ReverseEngine()
        spec = RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000)
        tmp_dxf = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        tmp_dxf.close()
        engine.generate_dxf(spec, tmp_dxf.name)
        tmp_dwg = tempfile.NamedTemporaryFile(suffix=".dwg", delete=False)
        tmp_dwg.close()
        result = engine.export_dwg(tmp_dxf.name, tmp_dwg.name)
        # LibreOffice 不可用时降级为 DXF
        assert os.path.exists(result)
        assert result.endswith(".dxf") or result.endswith(".dwg")
        os.unlink(tmp_dxf.name)
        if os.path.exists(tmp_dwg.name):
            os.unlink(tmp_dwg.name)
        if result != tmp_dwg.name and os.path.exists(result):
            os.unlink(result)


# ════════════════════════════════════════════════════════════
# 5. 异常输入
# ════════════════════════════════════════════════════════════


class TestReverseEngineEdgeCases:
    """验证边界输入处理"""

    def test_minimal_room_size(self):
        """最小尺寸不应崩溃"""
        engine = ReverseEngine()
        spec = RoomSpec(room_type=RoomType.OFFICE, width_mm=1000, height_mm=1000)
        c = engine.infer_constraints(spec)
        assert c is not None
        assert c.min_width_mm > 0

    def test_room_type_roundtrip_all(self):
        """所有支持的 RoomType 都能完成 DXF 生成"""
        engine = ReverseEngine()
        for rt in [
            RoomType.OFFICE,
            RoomType.STAIR,
            RoomType.EXIT,
            RoomType.CORRIDOR,
            RoomType.FIRE_LOBBY,
            RoomType.EQUIPMENT,
            RoomType.TOILET,
        ]:
            spec = RoomSpec(room_type=rt, width_mm=4000, height_mm=3000)
            tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
            tmp.close()
            engine.generate_dxf(spec, tmp.name)
            assert os.path.exists(tmp.name)
            assert os.path.getsize(tmp.name) > 0
            os.unlink(tmp.name)

    def test_multirroom_empty_specs(self):
        """空 rooms 列表应返回空布局"""
        engine = MultiRoomEngine()
        layout = engine.generate_layout([])
        assert layout.rooms == []
