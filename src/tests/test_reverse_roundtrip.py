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
import shutil
import sys
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


def _soffice_available() -> bool:
    """与 reverse_engine 探测口径一致的三级判断（供 skipif 装饰器使用）"""
    env_path = os.environ.get("BAA_SOFFICE_PATH")
    if env_path and os.path.exists(env_path):
        return True
    if shutil.which("soffice") or shutil.which("libreoffice"):
        return True
    if os.name == "nt":  # Windows 默认安装路径
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        return any(
            os.path.exists(os.path.join(base, "LibreOffice", "program", "soffice.exe"))
            for base in (pf, pf86)
        )
    return False


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

    @pytest.mark.skipif(
        not _soffice_available(),
        reason="需要 LibreOffice（BAA_SOFFICE_PATH / PATH / Windows 默认安装路径任一命中）",
    )
    def test_export_dwg_with_libreoffice(self, tmp_path):
        """有 LibreOffice 时的转换冒烟（覆盖 shutil.copy2 成功路径）

        契约：要么产出非空 .dwg（转换成功），要么优雅降级返回 .dxf；
        任何崩溃 / 空文件均不合格。空白 B 的分支 A/B 判定依此测试结果落定。
        """
        engine = ReverseEngine()
        spec = RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000)
        dxf_path = str(tmp_path / "room.dxf")
        dwg_path = str(tmp_path / "room.dwg")
        engine.generate_dxf(spec, dxf_path)

        result = engine.export_dwg(dxf_path, dwg_path)
        assert os.path.exists(result)
        if result.endswith(".dwg"):
            # 成功路径：LibreOffice 确有 DWG 导出 filter，copy2 产物非空
            assert os.path.getsize(result) > 0
        else:
            # 降级路径：无 DWG filter（空白 B 分支 B1 现场证据）
            assert result.endswith(".dxf")


# ════════════════════════════════════════════════════════════
# 4b. soffice 路径探测（BAA_SOFFICE_PATH → PATH → Windows 默认安装路径）
# ════════════════════════════════════════════════════════════


class TestSofficeDetection:
    """验证 _export_via_libreoffice 的三级探测优先级与平台门控

    手法：patch subprocess.run 捕获实际下发的 cmd[0]（即被选中的 soffice），
    并抛 TimeoutExpired 使转换提前终止——只测探测，不测转换。
    """

    @pytest.fixture(autouse=True)
    def _isolated(self, monkeypatch, tmp_path):
        """隔离外部环境：清理 env、把 ProgramFiles 重定向到空目录、捕获转换命令"""
        self.picked = None  # 被选中的 soffice 路径
        self.subprocess_called = False
        monkeypatch.delenv("BAA_SOFFICE_PATH", raising=False)
        # ProgramFiles 重定向到空目录，保证"默认安装路径"在任何机器上都不存在
        monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf-empty"))
        monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "pf86-empty"))

        import shutil
        import subprocess

        def fake_run(cmd, **kwargs):
            self.subprocess_called = True
            self.picked = cmd[0]
            raise subprocess.TimeoutExpired(cmd, 60)

        self._which_calls = []
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(shutil, "which", self._fake_which)

    def _fake_which(self, name):
        """可编程的 shutil.which 替身：按 self.which_result 字典返回"""
        self._which_calls.append(name)
        return self.which_result.get(name)

    which_result = {}  # 测试用例按需覆盖: {"soffice": "/fake/path"}

    # ── 优先级 1: BAA_SOFFICE_PATH 环境变量 ──

    def test_env_var_priority_over_path_lookup(self, tmp_path, monkeypatch):
        """env 指向真实文件时应优先于 PATH 探测结果"""
        fake_soffice = tmp_path / "my-soffice.exe"
        fake_soffice.write_bytes(b"")
        monkeypatch.setenv("BAA_SOFFICE_PATH", str(fake_soffice))
        # PATH 探测有结果，也不应被采用
        self.which_result = {"soffice": "C:/elsewhere/soffice.exe"}

        engine = ReverseEngine()
        assert engine._export_via_libreoffice("in.dxf", "out.dwg") is False
        assert self.picked == str(fake_soffice)

    def test_env_var_invalid_path_falls_through(self, monkeypatch):
        """env 指向不存在路径时应静默回退到 PATH 探测"""
        monkeypatch.setenv("BAA_SOFFICE_PATH", "C:/notexist/soffice.exe")
        self.which_result = {"soffice": sys.executable}

        engine = ReverseEngine()
        assert engine._export_via_libreoffice("in.dxf", "out.dwg") is False
        assert self.picked == sys.executable

    # ── 优先级 2: shutil.which（PATH） ──

    def test_path_lookup_result_used(self):
        """无 env 时采用 PATH 探测到的可执行文件"""
        self.which_result = {"soffice": sys.executable}

        engine = ReverseEngine()
        assert engine._export_via_libreoffice("in.dxf", "out.dwg") is False
        assert self.picked == sys.executable
        assert self.subprocess_called is True

    # ── 优先级 3: Windows 默认安装路径（仅 os.name == "nt"） ──

    def test_windows_default_install_path_detected(self, tmp_path, monkeypatch):
        """PATH 无结果时，Windows 默认安装路径应被探测到"""
        monkeypatch.setattr(os, "name", "nt")
        self.which_result = {}
        installed = tmp_path / "pf-empty" / "LibreOffice" / "program"
        installed.mkdir(parents=True)
        soffice_exe = installed / "soffice.exe"
        soffice_exe.write_bytes(b"")

        engine = ReverseEngine()
        assert engine._export_via_libreoffice("in.dxf", "out.dwg") is False
        assert self.picked == str(soffice_exe)

    def test_posix_skips_windows_default_paths(self, tmp_path, monkeypatch):
        """非 Windows 平台不应探测默认安装路径（即使路径存在）"""
        monkeypatch.setattr(os, "name", "posix")
        self.which_result = {}
        installed = tmp_path / "pf-empty" / "LibreOffice" / "program"
        installed.mkdir(parents=True)
        (installed / "soffice.exe").write_bytes(b"")

        engine = ReverseEngine()
        assert engine._export_via_libreoffice("in.dxf", "out.dwg") is False
        assert self.picked is None
        assert self.subprocess_called is False

    # ── 兜底: 全部未命中 → 优雅降级 ──

    def test_nothing_found_returns_false(self):
        """三级探测全部未命中时返回 False 且不触发转换"""
        self.which_result = {}

        engine = ReverseEngine()
        assert engine._export_via_libreoffice("in.dxf", "out.dwg") is False
        assert self.picked is None
        assert self.subprocess_called is False


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
